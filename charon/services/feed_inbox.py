"""Every feed's items in one list, checked against the rules as they are right now."""

import base64
import binascii
from collections.abc import Collection, Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from itertools import islice

from charon.domain.events import EventType
from charon.domain.feeds import Feed, FeedItem
from charon.domain.models import SYSTEM, Actor, Job, Rule
from charon.domain.times import to_utc
from charon.errors import CharonError, InvalidInputError, NotFoundError
from charon.ports.clock import Clock, utc_now
from charon.ports.events import EventLog
from charon.ports.stores import FeedItemStore, FeedStore, ItemCursor, ItemFilter, UnreadCounts
from charon.services.download_service import DownloadService, Submission
from charon.services.rule_service import Matcher, Preview, RuleService

# Items fetched per query while filtering by match, which only Python can decide.
SCAN_BATCH = 200


class MatchFilter(StrEnum):
    ALL = "all"
    MATCHED = "matched"
    UNMATCHED = "unmatched"


@dataclass(frozen=True)
class Match:
    preview: Preview | None = None
    # Set instead of `preview` when the chosen rule can't be applied to the name.
    error: CharonError | None = None

    @property
    def rule(self) -> Rule | None:
        """The rule that would file the item, if one applies cleanly."""
        return self.preview.rule if self.preview else None

    @property
    def matched(self) -> bool:
        # A rule that breaks on this name still counts: it needs fixing, not a new rule.
        return self.error is not None or self.rule is not None

    def passes(self, wanted: MatchFilter) -> bool:
        return wanted is MatchFilter.ALL or self.matched is (wanted is MatchFilter.MATCHED)


def match_with(matcher: Matcher, name: str) -> Match:
    try:
        return Match(preview=matcher(name))
    except InvalidInputError as exc:
        return Match(error=exc)


@dataclass(frozen=True)
class InboxItem:
    item: FeedItem
    match: Match
    # The newest job for the same torrent, however it was added.
    job: Job | None
    feeds: list[Feed]


# Spelled out here because inside FeedInbox `list` is the method of that name.
InboxItems = list[InboxItem]
Matched = list[tuple[FeedItem, Match]]


@dataclass(frozen=True)
class InboxQuery:
    feed_id: str | None = None
    match: MatchFilter = MatchFilter.ALL
    unseen_only: bool = False
    search: str | None = None


@dataclass(frozen=True)
class InboxPage:
    items: InboxItems
    next_cursor: str | None


class FeedInbox:
    def __init__(
        self,
        items: FeedItemStore,
        feeds: FeedStore,
        rules: RuleService,
        downloads: DownloadService,
        events: EventLog,
        clock: Clock = utc_now,
    ) -> None:
        self._items = items
        self._feeds = feeds
        self._rules = rules
        self._downloads = downloads
        self._events = events
        self._clock = clock

    def list(self, query: InboxQuery, cursor: str | None = None, limit: int = 50) -> InboxPage:
        """Items newest first. Matching runs here, so rule edits show up immediately."""
        matcher = self._rules.matcher()
        found = self._scan(query, decode_item_cursor(cursor) if cursor else None, limit, matcher)
        page = found[:limit]
        next_cursor = encode_item_cursor(page[-1][0]) if len(found) > limit else None
        return InboxPage(items=self._complete(page), next_cursor=next_cursor)

    def get(self, info_hash: str) -> InboxItem:
        return self.annotate([self._item(info_hash)])[0]

    def annotate(self, items: Sequence[FeedItem]) -> InboxItems:
        """Items with their rule match, job and feeds, e.g. for items not saved yet."""
        matcher = self._rules.matcher()
        return self._complete([(item, match_with(matcher, item.name)) for item in items])

    def download(self, info_hash: str, rule_id: str | None, actor: Actor = SYSTEM) -> Submission:
        """Download an item; if the torrent is already in Charon, link its existing job."""
        item = self._item(info_hash)
        submission = self._downloads.submit(item.magnet, rule_id, actor)
        self._items.update(info_hash, {"job_id": submission.job.id, "auto_error": None})
        if submission.created:
            self._events.record(
                EventType.FEED_ITEM_DOWNLOADED,
                info_hash,
                actor,
                job_id=submission.job.id,
                name=item.name,
                auto=False,
            )
        return submission

    def mark_seen(self, info_hashes: Collection[str]) -> int:
        """Mark exactly these items seen, e.g. the ones a list showed; returns how many."""
        return self._items.mark_seen(info_hashes, self._clock())

    def mark_all_seen(self, query: InboxQuery, up_to: datetime) -> int:
        """Mark every unseen item in this view seen, if Charon first saw it by `up_to`.

        The view's feed, match and search apply, so items it hides stay new, and so do items
        that arrived after `up_to` (e.g. after the list was loaded).
        """
        matcher = self._rules.matcher()
        filter = ItemFilter(query.feed_id, True, query.search, first_seen_until=up_to)
        shown = (i for i in self._each(filter) if match_with(matcher, i.name).passes(query.match))
        return self._items.mark_seen([item.info_hash for item in shown], self._clock())

    def unread(self) -> UnreadCounts:
        return self._items.unread_counts()

    def prune(self, max_age: timedelta) -> int:
        """Forget items no feed has listed for `max_age`.

        A feed's listings only age while it is being read: a paused or failing feed may well
        still list them, so its items are kept as of its last successful read.
        """
        oldest = self._clock() - max_age
        feeds = [feed for feed in self._feeds.list() if feed.items_seen_at is not None]
        return self._items.prune({f.id: min(oldest, f.items_seen_at) for f in feeds})

    def _item(self, info_hash: str) -> FeedItem:
        item = self._items.get_many([info_hash]).get(info_hash)
        if item is None:
            raise NotFoundError("feed_item_not_found", f"feed item {info_hash} does not exist")
        return item

    def _scan(
        self, query: InboxQuery, after: ItemCursor | None, limit: int, matcher: Matcher
    ) -> Matched:
        """Up to `limit` + 1 items passing the query, so the caller can tell if there's more."""
        filter = ItemFilter(query.feed_id, query.unseen_only, query.search)
        matched = ((item, match_with(matcher, item.name)) for item in self._each(filter, after))
        return list(islice((pair for pair in matched if pair[1].passes(query.match)), limit + 1))

    def _each(self, filter: ItemFilter, after: ItemCursor | None = None) -> Iterator[FeedItem]:
        """Every stored item passing `filter`, newest first, read a batch at a time."""
        while True:
            batch = self._items.list(filter, after, SCAN_BATCH)
            yield from batch
            if len(batch) < SCAN_BATCH:
                return
            after = (batch[-1].published_at, batch[-1].info_hash)

    def _complete(self, pairs: Sequence[tuple[FeedItem, Match]]) -> InboxItems:
        jobs = self._downloads.latest_by_hash([item.info_hash for item, _ in pairs])
        feeds = {feed.id: feed for feed in self._feeds.list()}
        return [
            InboxItem(
                item=item,
                match=match,
                job=jobs.get(item.info_hash),
                feeds=[feeds[f] for f in item.feed_ids if f in feeds],
            )
            for item, match in pairs
        ]


def encode_item_cursor(item: FeedItem) -> str:
    raw = f"{item.published_at.isoformat()}|{item.info_hash}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_item_cursor(cursor: str) -> ItemCursor:
    try:
        published_at, info_hash = base64.urlsafe_b64decode(cursor).decode().split("|", 1)
        return to_utc(datetime.fromisoformat(published_at)), info_hash
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        raise InvalidInputError("invalid_cursor", "cursor is malformed") from exc

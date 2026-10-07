"""Subscribing to feeds: add, change, preview, refresh and remove them."""

import logging
from dataclasses import dataclass
from datetime import datetime

from charon.domain.events import EventType
from charon.domain.feeds import Feed, FeedSpec, FeedUpdate, check_feed_url, feed_url_key
from charon.domain.models import SYSTEM, Actor
from charon.errors import ConflictError, FeedError, NotFoundError
from charon.ports.clock import Clock, IdFactory, new_uuid, utc_now
from charon.ports.events import EventLog
from charon.ports.feeds import FeedFetcher
from charon.ports.stores import FeedItemStore, FeedStore
from charon.services.feed_inbox import FeedInbox, InboxItem
from charon.services.feed_refresher import FeedRefresher, read_feed, to_items
from charon.services.keyed_lock import KeyedLock

log = logging.getLogger(__name__)

PREVIEW_ITEMS = 5
# Spelled out here because inside FeedService `list` is the method of that name.
Feeds = list[Feed]


@dataclass(frozen=True)
class FeedPreview:
    title: str | None
    item_count: int
    skipped_count: int
    newest_published_at: datetime | None
    # The newest few, checked against the rules.
    items: list[InboxItem]


class FeedService:
    def __init__(
        self,
        feeds: FeedStore,
        items: FeedItemStore,
        fetcher: FeedFetcher,
        refresher: FeedRefresher,
        inbox: FeedInbox,
        events: EventLog,
        new_id: IdFactory = new_uuid,
        clock: Clock = utc_now,
    ) -> None:
        self._feeds = feeds
        self._items = items
        self._fetcher = fetcher
        self._refresher = refresher
        self._inbox = inbox
        self._events = events
        self._new_id = new_id
        self._clock = clock
        self._subscribing = KeyedLock()

    def list(self) -> list[Feed]:
        return self._feeds.list()

    def get(self, feed_id: str) -> Feed:
        feed = self._feeds.get(feed_id)
        if feed is None:
            raise NotFoundError("feed_not_found", f"feed {feed_id} does not exist")
        return feed

    def create(self, spec: FeedSpec, actor: Actor = SYSTEM) -> Feed:
        """Subscribe and fetch the feed once. Auto-download skips what it lists already.

        Raises ConflictError if already subscribed to the same address.
        """
        now = self._clock()
        feed = Feed(
            id=self._new_id(),
            created_at=now,
            updated_at=now,
            created_by=actor,
            updated_by=actor,
            **spec.model_dump(),
        )
        with self._subscribing.hold(feed_url_key(spec.url)):
            self._check_not_subscribed(spec.url)
            self._feeds.add(feed)
        self._events.record(EventType.FEED_CREATED, feed.id, actor, name=feed.name)
        feed = self._refresher.refresh(feed)
        if feed.auto_download:
            feed = self._save(feed.id, auto_download_since=self._clock())
        return feed

    def update(self, feed_id: str, changes: FeedUpdate, actor: Actor = SYSTEM) -> Feed:
        current = self.get(feed_id)
        update = changes.model_dump(exclude={"url"}) | self._auto_download_change(current, changes)
        if changes.url is not None and changes.url != current.url:
            self._check_not_subscribed(changes.url, other_than=feed_id)
            update |= {"url": changes.url, "etag": None, "last_modified": None}
        feed = self._save(feed_id, **update, updated_at=self._clock(), updated_by=actor)
        changed = [
            name for name in FeedSpec.model_fields if getattr(current, name) != getattr(feed, name)
        ]
        self._events.record(EventType.FEED_UPDATED, feed.id, actor, name=feed.name, changed=changed)
        return feed

    def delete(self, feed_id: str, actor: Actor = SYSTEM) -> None:
        feed = self.get(feed_id)
        if not self._feeds.delete(feed_id):
            raise NotFoundError("feed_not_found", f"feed {feed_id} does not exist")
        self._items.unlink_feed(feed_id)
        self._events.record(EventType.FEED_DELETED, feed_id, actor, name=feed.name)

    def preview(self, url: str) -> FeedPreview:
        """Fetch and read a feed without subscribing, e.g. to check an address first."""
        try:
            url = check_feed_url(url)
        except ValueError as exc:
            raise FeedError("feed_invalid_url", f"the address {exc}") from exc
        fetched = self._fetcher.fetch(url)
        parsed = read_feed(fetched.body or b"")
        items = sorted(to_items(parsed.items, self._clock()), key=lambda i: i.published_at)
        return FeedPreview(
            title=parsed.title,
            item_count=len(items),
            skipped_count=parsed.skipped,
            newest_published_at=items[-1].published_at if items else None,
            items=self._inbox.annotate(items[::-1][:PREVIEW_ITEMS]),
        )

    def refresh(self, feed_id: str) -> Feed:
        """Fetch one feed now, even a paused one (paused feeds never auto-download)."""
        return self._refresher.refresh(self.get(feed_id))

    def refresh_all(self) -> Feeds:
        """Fetch every enabled feed now, one after another; paused feeds are left as they are."""
        return [self._refresh_isolated(feed) if feed.enabled else feed for feed in self.list()]

    def refresh_due(self) -> None:
        """Refresh every enabled feed whose interval has passed. For the background poller."""
        now = self._clock()
        for feed in self._feeds.list():
            if feed.is_due(now):
                self._refresh_isolated(feed)

    def _refresh_isolated(self, feed: Feed) -> Feed:
        """Refresh one feed so that a bug while refreshing it can't stop the others."""
        try:
            return self._refresher.refresh(feed)
        except Exception:
            # The URL is never logged: it may hold a passkey.
            log.exception("unexpected error while refreshing feed %s (%s)", feed.id, feed.name)
            return feed

    def _check_not_subscribed(self, url: str, other_than: str | None = None) -> None:
        key = feed_url_key(url)
        same = next(
            (f for f in self.list() if f.id != other_than and feed_url_key(f.url) == key), None
        )
        if same is not None:
            raise ConflictError("feed_exists", f"already subscribed to this feed as {same.name}")

    def _auto_download_change(self, current: Feed, changes: FeedUpdate) -> dict[str, object]:
        if not changes.auto_download:
            return {"auto_download_since": None}
        if current.auto_download:
            return {}
        return {"auto_download_since": self._clock()}

    def _save(self, feed_id: str, **changes: object) -> Feed:
        saved = self._feeds.update_fields(feed_id, changes)
        if saved is None:
            raise NotFoundError("feed_not_found", f"feed {feed_id} does not exist")
        return saved

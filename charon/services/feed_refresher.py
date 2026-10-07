"""Fetches a feed, records its items, and keeps track of whether it is healthy."""

import logging
from collections.abc import Sequence
from datetime import datetime

from charon.domain.events import EventType
from charon.domain.feeds import Feed, FeedFailure, FeedItem, feed_host
from charon.domain.models import SYSTEM
from charon.domain.rss import NotRssError, ParsedFeed, ParsedItem, parse_feed
from charon.errors import FeedError
from charon.ports.clock import Clock, utc_now
from charon.ports.events import EventLog
from charon.ports.feeds import FeedFetcher, FetchedFeed
from charon.ports.stores import FeedItemStore, FeedStore
from charon.services.auto_downloader import AutoDownloader

log = logging.getLogger(__name__)


def read_feed(body: bytes) -> ParsedFeed:
    """Parse a feed, insisting that it is RSS and lists at least one magnet if it lists anything."""
    try:
        parsed = parse_feed(body)
    except NotRssError as exc:
        raise FeedError("feed_not_rss", f"this isn't an RSS feed: {exc}") from exc
    except (ValueError, OverflowError) as exc:
        raise FeedError(
            "feed_unreadable", f"the feed has a value Charon can't read ({exc})"
        ) from exc
    if parsed.skipped and not parsed.items:
        raise FeedError("feed_no_magnets", f"none of the feed's {parsed.skipped} items is a magnet")
    return parsed


def to_items(parsed: Sequence[ParsedItem], now: datetime) -> list[FeedItem]:
    """Feed items first seen `now`; an item listed twice in one feed counts once."""
    unique: dict[str, ParsedItem] = {}
    for item in parsed:
        unique.setdefault(item.info_hash, item)
    return [_item(p, now) for p in unique.values()]


def _item(parsed: ParsedItem, now: datetime) -> FeedItem:
    return FeedItem(
        info_hash=parsed.info_hash,
        name=parsed.name,
        title=parsed.title,
        magnet=parsed.magnet,
        size_bytes=parsed.size_bytes,
        published_at=parsed.published_at or now,
        published_estimated=parsed.published_at is None,
        first_seen_at=now,
    )


def _failure(code: str, message: str) -> dict[str, object]:
    return {"last_error": FeedFailure(code=code, message=message)}


class FeedRefresher:
    def __init__(
        self,
        fetcher: FeedFetcher,
        feeds: FeedStore,
        items: FeedItemStore,
        auto: AutoDownloader,
        events: EventLog,
        clock: Clock = utc_now,
    ) -> None:
        self._fetcher = fetcher
        self._feeds = feeds
        self._items = items
        self._auto = auto
        self._events = events
        self._clock = clock

    def refresh(self, feed: Feed) -> Feed:
        """Fetch the feed now. Problems are recorded on the feed, not raised.

        A feed unsubscribed while it was being fetched is returned unchanged, and nothing the
        fetch found is kept.
        """
        now = self._clock()
        status = self._fetch(feed, now)
        # Only these fields: a rename or a toggle made during the fetch survives.
        refreshed = self._feeds.update_fields(feed.id, {"last_checked_at": now, **status})
        if refreshed is None:
            self._items.unlink_feed(feed.id)
            return feed
        self._note_health(feed, refreshed)
        if refreshed.last_error is None:
            self._auto.run(refreshed)
        return refreshed

    def _fetch(self, feed: Feed, now: datetime) -> dict[str, object]:
        try:
            fetched = self._fetcher.fetch(feed.url, feed.etag, feed.last_modified)
            return self._ingest(feed, fetched, now)
        except FeedError as exc:
            return _failure(exc.code, exc.message)
        except Exception:
            # Feeds are other people's content. Whatever breaks reading one must still be
            # recorded, or the feed would stay unchecked and be retried on every poll.
            log.exception("couldn't read feed %s (%s)", feed.id, feed.name)
            return _failure(
                "feed_unreadable", f"Charon couldn't read the feed from {feed_host(feed.url)}"
            )

    def _ingest(self, feed: Feed, fetched: FetchedFeed, now: datetime) -> dict[str, object]:
        healthy: dict[str, object] = {"last_error": None, "items_seen_at": now}
        if fetched.body is None:
            self._items.touch(feed.id, feed.items_seen_at or now, now)
            # A "not modified" answer often leaves out a validator; keep the one that got it.
            etag = fetched.etag or feed.etag
            last_modified = fetched.last_modified or feed.last_modified
            return {**healthy, "etag": etag, "last_modified": last_modified}
        parsed = read_feed(fetched.body)
        self._store(feed, to_items(parsed.items, now), now)
        validators = {"etag": fetched.etag, "last_modified": fetched.last_modified}
        return {**healthy, **validators, "title": parsed.title}

    def _store(self, feed: Feed, incoming: list[FeedItem], now: datetime) -> None:
        existing = self._items.get_many([item.info_hash for item in incoming])
        new = [item for item in incoming if item.info_hash not in existing]
        self._items.save(new)
        for item in incoming:
            stored = existing.get(item.info_hash)
            changes = stored.date_changes(item) if stored else None
            if changes:
                self._items.update(item.info_hash, changes)
        self._items.link(feed.id, [item.info_hash for item in incoming], now)
        for item in new:
            self._events.record(
                EventType.FEED_ITEM_ADDED, item.info_hash, SYSTEM, name=item.name, feed_id=feed.id
            )

    def _note_health(self, before: Feed, after: Feed) -> None:
        if (before.last_error is None) == (after.last_error is None):
            return
        error_code = after.last_error.code if after.last_error else None
        self._events.record(
            EventType.FEED_HEALTH_CHANGED,
            after.id,
            SYSTEM,
            healthy=after.last_error is None,
            error_code=error_code,
        )

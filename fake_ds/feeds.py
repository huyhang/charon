"""Fake RSS feeds of magnet links, for trying Charon's feeds without a real tracker.

Each feed starts with sample items dated relative to when the fake started. Control
endpoints publish new items, or break a feed to see how Charon reports problems.
"""

import hashlib
import itertools
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from enum import StrEnum
from typing import Any
from urllib.parse import quote
from xml.sax.saxutils import escape, quoteattr

GIB = 1024**3
TRACKER = "udp://tracker.fake.example:1337/announce"


class FeedMode(StrEnum):
    OK = "ok"
    HTTP_ERROR = "http_error"
    BAD_XML = "bad_xml"


@dataclass
class FakeFeedItem:
    name: str
    published_at: datetime | None
    size_bytes: int = GIB
    # A .torrent link instead of a magnet: Charon skips these.
    torrent_link: bool = False

    @property
    def info_hash(self) -> str:
        # Derived from the name, so the same sample always has the same hash (and feeds that
        # list the same name list the same torrent).
        return hashlib.sha1(self.name.encode()).hexdigest()

    @property
    def magnet(self) -> str:
        return (
            f"magnet:?xt=urn:btih:{self.info_hash}&dn={quote(self.name)}"
            f"&xl={self.size_bytes}&tr={quote(TRACKER, safe='')}"
        )


@dataclass
class FakeFeed:
    slug: str
    title: str
    items: list[FakeFeedItem]
    mode: FeedMode = FeedMode.OK
    published: itertools.count = field(default_factory=lambda: itertools.count(1))


def _ago(now: datetime, **delta: float) -> datetime:
    return now - timedelta(**delta)


def sample_feeds(now: datetime) -> dict[str, FakeFeed]:
    """Items that exercise every case: each sample rule, no rule, no date, and duplicates."""
    expanse = "The.Expanse.S02E06.1080p.WEB-DL.x264.mkv"
    tv = FakeFeed(
        "tv",
        "Fake Tracker · TV",
        [
            FakeFeedItem(expanse, _ago(now, minutes=20), int(2.1 * GIB)),
            FakeFeedItem("Severance.S02E04.1080p.WEB-DL.mkv", _ago(now, hours=2), int(1.8 * GIB)),
            FakeFeedItem("Andor.S01E02.1080p.WEB-DL.mkv", _ago(now, hours=5), int(2.4 * GIB)),
            FakeFeedItem("Dune.Part.Two.2024.2160p.BluRay.x265.mkv", _ago(now, days=1), 18 * GIB),
            FakeFeedItem("Some.Documentary.Special.1080p.mkv", _ago(now, days=1, hours=3)),
            FakeFeedItem("Linux.Weekly.Digest.720p.mkv", None, 700 * 1024**2),
            FakeFeedItem("Old.Show.Pack.torrent", _ago(now, days=2), torrent_link=True),
            FakeFeedItem("Shogun.2024.S01E05.2160p.mkv", _ago(now, days=3), int(6.2 * GIB)),
        ],
    )
    anime = FakeFeed(
        "anime",
        "Fake Tracker · Anime",
        [
            FakeFeedItem("[SubsPlease] Frieren - 13 (1080p).mkv", _ago(now, minutes=40)),
            FakeFeedItem(expanse, _ago(now, minutes=30), int(2.1 * GIB)),
            FakeFeedItem("[SubsPlease] Dandadan - 05 (1080p).mkv", _ago(now, hours=6)),
            FakeFeedItem("One.Piece.Film.Red.2022.1080p.mkv", _ago(now, days=2), 3 * GIB),
            # No sample rule files it; its canonical title is a lookup away (fake TMDB).
            FakeFeedItem("Kusuriya no Hitorigoto - 24 (1080p).mkv", _ago(now, days=2, hours=4)),
        ],
    )
    return {feed.slug: feed for feed in (tv, anime)}


def render(feed: FakeFeed) -> bytes:
    items = "".join(_render_item(item) for item in feed.items)
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<rss version="2.0"><channel>'
        f"<title>{escape(feed.title)}</title>"
        "<link>https://tracker.fake.example/</link>"
        f"<description>{escape(feed.title)} (fake)</description>"
        f"{items}</channel></rss>\n"
    ).encode()


def _render_item(item: FakeFeedItem) -> str:
    link = (
        f"https://tracker.fake.example/{item.info_hash}.torrent"
        if item.torrent_link
        else item.magnet
    )
    date = f"<pubDate>{format_datetime(item.published_at)}</pubDate>" if item.published_at else ""
    enclosure = (
        f'<enclosure url={quoteattr(link)} length="{item.size_bytes}" '
        'type="application/x-bittorrent"/>'
    )
    return (
        f"<item><title>{escape(item.name.replace('.', ' '))}</title>"
        f"<link>{escape(link)}</link>"
        f'<guid isPermaLink="false">{item.info_hash}</guid>'
        f"{date}{enclosure}</item>"
    )


class FakeFeeds:
    def __init__(self, clock: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self._clock = clock
        self._feeds = sample_feeds(clock())

    def get(self, slug: str) -> FakeFeed | None:
        return self._feeds.get(slug)

    def all(self) -> list[FakeFeed]:
        return list(self._feeds.values())

    def publish(self, slug: str, name: str | None = None) -> FakeFeedItem | None:
        """Add an item dated now at the top of the feed; None if there's no such feed."""
        feed = self._feeds.get(slug)
        if feed is None:
            return None
        item = FakeFeedItem(name or _fresh_name(feed), self._clock(), int(1.4 * GIB))
        feed.items.insert(0, item)
        return item

    def set_mode(self, slug: str, mode: FeedMode) -> FakeFeed | None:
        feed = self._feeds.get(slug)
        if feed is not None:
            feed.mode = mode
        return feed

    def reset(self) -> None:
        self._feeds = sample_feeds(self._clock())

    @staticmethod
    def snapshot(feed: FakeFeed) -> dict[str, Any]:
        return {
            "slug": feed.slug,
            "title": feed.title,
            "path": f"/feeds/{feed.slug}.xml",
            "mode": feed.mode,
            "items": [
                {"name": i.name, "info_hash": i.info_hash, "magnet": i.magnet} for i in feed.items
            ],
        }


def _fresh_name(feed: FakeFeed) -> str:
    episode = next(feed.published)
    if feed.slug == "anime":
        return f"[SubsPlease] Fresh Anime - {episode:02d} (1080p).mkv"
    return f"Fresh.Show.S01E{episode:02d}.1080p.WEB-DL.mkv"

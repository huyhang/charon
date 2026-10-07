"""Builders for RSS documents and feed objects used across feed tests."""

from datetime import datetime
from email.utils import format_datetime
from xml.sax.saxutils import escape

from charon.domain.feeds import Feed, FeedItem
from tests.unit.fakes import T0

FEED_URL = "https://tracker.example/rss?passkey=s3cret"


def hash_for(n: int) -> str:
    return f"{n:040x}"


def magnet(n: int, name: str | None = None) -> str:
    dn = f"&dn={name}" if name else ""
    return f"magnet:?xt=urn:btih:{hash_for(n)}{dn}"


def rss_item(
    title: str,
    link: str,
    published: datetime | None = None,
    extra: str = "",
) -> str:
    date = f"<pubDate>{format_datetime(published)}</pubDate>" if published else ""
    return f"<item><title>{escape(title)}</title><link>{escape(link)}</link>{date}{extra}</item>"


def rss(*items: str, title: str = "Test feed") -> bytes:
    body = "".join(items)
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<rss version="2.0"><channel><title>{escape(title)}</title>{body}</channel></rss>'
    ).encode()


def make_feed(**overrides: object) -> Feed:
    fields: dict[str, object] = {
        "id": "feed-1",
        "name": "TV",
        "url": FEED_URL,
        "created_at": T0,
        "updated_at": T0,
    }
    return Feed.model_validate({**fields, **overrides})


def make_item(n: int = 1, **overrides: object) -> FeedItem:
    fields: dict[str, object] = {
        "info_hash": hash_for(n),
        "name": f"Show.S01E{n:02d}.mkv",
        "title": f"Show S01E{n:02d}",
        "magnet": magnet(n, f"Show.S01E{n:02d}.mkv"),
        "published_at": T0,
        "first_seen_at": T0,
    }
    return FeedItem.model_validate({**fields, **overrides})

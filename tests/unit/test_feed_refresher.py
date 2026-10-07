from collections.abc import Callable
from datetime import timedelta

import pytest

from charon.domain.events import EventType
from charon.domain.feeds import FeedFailure
from charon.domain.rss import ParsedItem
from charon.errors import FeedError
from charon.ports.feeds import FetchedFeed
from charon.services import feed_refresher
from charon.services.feed_refresher import read_feed, to_items
from tests.unit.fakes import T0
from tests.unit.feed_harness import FeedHarness
from tests.unit.feed_samples import FEED_URL, hash_for, magnet, make_feed, make_item, rss, rss_item

LATER = T0 + timedelta(hours=1)


def parsed(n: int, published=T0) -> ParsedItem:
    return ParsedItem(hash_for(n), magnet(n), f"t{n}", f"n{n}", published, None)


@pytest.mark.parametrize(
    ("document", "code"),
    [
        (b"<html/>", "feed_not_rss"),
        (rss(rss_item("x", "https://t.example/x.torrent")), "feed_no_magnets"),
    ],
)
def test_read_feed_reports_unusable_feeds(document: bytes, code: str) -> None:
    with pytest.raises(FeedError) as exc_info:
        read_feed(document)
    assert exc_info.value.code == code


def test_read_feed_accepts_an_empty_feed() -> None:
    assert read_feed(rss()).items == []


def test_to_items_dedupes_and_estimates_missing_dates() -> None:
    items = to_items([parsed(1), parsed(2, None), parsed(1, LATER)], LATER)
    assert [(i.info_hash, i.published_at, i.published_estimated) for i in items] == [
        (hash_for(1), T0, False),
        (hash_for(2), LATER, True),
    ]
    assert {i.first_seen_at for i in items} == {LATER}


def subscribed(h: FeedHarness, document: bytes, **feed) -> None:
    h.feeds.add(make_feed(**feed))
    h.fetcher.documents[FEED_URL] = document


def test_refresh_stores_and_links_new_items_and_records_them() -> None:
    h = FeedHarness()
    subscribed(h, rss(rss_item("A", magnet(1, "Show.S01E01.mkv"), T0), title="Tracker"))
    feed = h.refresher.refresh(h.feeds.get("feed-1"))
    assert (feed.title, feed.last_checked_at, feed.last_error, feed.etag) == (
        "Tracker",
        T0,
        None,
        '"v1"',
    )
    [item] = h.items.get_many([hash_for(1)]).values()
    assert (item.name, item.feed_ids) == ("Show.S01E01.mkv", ["feed-1"])
    assert h.events.types() == [EventType.FEED_ITEM_ADDED]
    assert h.feeds.get("feed-1") == feed


def test_refresh_keeps_item_state_and_the_earliest_date_across_feeds() -> None:
    h = FeedHarness()
    h.items.save([make_item(1, published_at=LATER, seen_at=T0, job_id="job-9")])
    h.items.link("other", [hash_for(1)], T0)
    subscribed(h, rss(rss_item("A", magnet(1), T0), rss_item("B", magnet(2), LATER)))
    h.refresher.refresh(h.feeds.get("feed-1"))
    item = h.items.get_many([hash_for(1)])[hash_for(1)]
    assert (item.published_at, item.seen_at, item.job_id, item.feed_ids) == (
        T0,
        T0,
        "job-9",
        ["feed-1", "other"],
    )
    assert [e.subject_id for e in h.events.recorded] == [hash_for(2)]


def test_refresh_sends_cache_validators_and_touches_items_when_unchanged() -> None:
    h = FeedHarness()
    validators = {"etag": '"v0"', "last_modified": "Wed, 01 Oct 2026 10:00:00 GMT"}
    subscribed(h, rss(rss_item("A", magnet(1), T0)), items_seen_at=T0, **validators)
    h.items.save([make_item(1)])
    h.items.link("feed-1", [hash_for(1)], T0)
    h.fetcher.unchanged.add(FEED_URL)
    h.clock.advance(60)
    feed = h.refresher.refresh(h.feeds.get("feed-1"))
    assert h.items.sources[(hash_for(1), "feed-1")] == h.clock()
    assert (feed.items_seen_at, feed.last_error) == (h.clock(), None)
    # A bare "not modified" keeps the validators, so the next check is conditional too.
    assert (feed.etag, feed.last_modified) == (validators["etag"], validators["last_modified"])
    h.refresher.refresh(feed)
    assert h.fetcher.fetches == [(FEED_URL, *validators.values())] * 2


def test_refresh_records_failures_on_the_feed_and_health_changes_once() -> None:
    h = FeedHarness()
    subscribed(h, b"")
    h.fetcher.errors[FEED_URL] = FeedError("feed_http_error", "t.example answered 403")
    failed = h.refresher.refresh(h.feeds.get("feed-1"))
    again = h.refresher.refresh(failed)
    assert again.last_error == FeedFailure(code="feed_http_error", message="t.example answered 403")
    del h.fetcher.errors[FEED_URL]
    h.fetcher.documents[FEED_URL] = rss()
    healed = h.refresher.refresh(again)
    assert healed.last_error is None
    health = [e.data for e in h.events.recorded if e.type is EventType.FEED_HEALTH_CHANGED]
    assert health == [
        {"healthy": False, "error_code": "feed_http_error"},
        {"healthy": True, "error_code": None},
    ]


def test_refresh_records_unreadable_content_as_a_failure() -> None:
    h = FeedHarness()
    subscribed(h, b"<html>login</html>")
    feed = h.refresher.refresh(h.feeds.get("feed-1"))
    assert feed.last_error.code == "feed_not_rss"


def while_fetching(monkeypatch, h: FeedHarness, meanwhile: Callable[[], None]) -> None:
    """Make the next fetches run `meanwhile` first, as a user's request could."""
    fetch = h.fetcher.fetch

    def interrupted(*args: object) -> FetchedFeed:
        meanwhile()
        return fetch(*args)

    monkeypatch.setattr(h.fetcher, "fetch", interrupted)


def test_refresh_keeps_edits_made_while_fetching(monkeypatch) -> None:
    h = FeedHarness()
    subscribed(h, rss(), auto_download=True, auto_download_since=T0)
    edit = {"name": "Renamed", "auto_download": False}
    while_fetching(monkeypatch, h, lambda: h.feeds.update_fields("feed-1", edit))
    feed = h.refresher.refresh(h.feeds.get("feed-1"))
    assert (feed.name, feed.auto_download) == ("Renamed", False)
    assert (h.feeds.get("feed-1").name, feed.last_checked_at) == ("Renamed", T0)


def test_refresh_of_a_feed_unsubscribed_meanwhile_keeps_nothing(monkeypatch) -> None:
    h = FeedHarness()
    subscribed(
        h,
        rss(rss_item("A", magnet(1, "Show.S01E01.mkv"), T0)),
        auto_download=True,
        auto_download_since=T0 - timedelta(hours=1),
    )
    while_fetching(monkeypatch, h, lambda: h.feeds.delete("feed-1"))
    h.refresher.refresh(h.feeds.get("feed-1"))
    assert (h.items.items, h.items.sources, h.downloader.added) == ({}, {}, [])


def test_refresh_records_unexpected_errors_as_failures() -> None:
    h = FeedHarness()
    subscribed(h, rss())
    h.fetcher.errors[FEED_URL] = RuntimeError("bug")  # type: ignore[assignment]
    feed = h.refresher.refresh(h.feeds.get("feed-1"))
    assert (feed.last_error.code, feed.last_checked_at) == ("feed_unreadable", T0)
    assert "tracker.example" in feed.last_error.message
    assert "passkey" not in feed.last_error.message


def test_read_feed_reports_values_it_cant_read(monkeypatch) -> None:
    def broken(_: bytes) -> None:
        raise ValueError("bad number")

    monkeypatch.setattr(feed_refresher, "parse_feed", broken)
    with pytest.raises(FeedError) as exc_info:
        read_feed(rss())
    assert exc_info.value.code == "feed_unreadable"


def test_refresh_runs_auto_download_only_when_healthy() -> None:
    h = FeedHarness()
    since = T0 - timedelta(hours=1)
    subscribed(
        h,
        rss(rss_item("A", magnet(1, "Show.S01E01.mkv"), T0)),
        auto_download=True,
        auto_download_since=since,
    )
    h.refresher.refresh(h.feeds.get("feed-1"))
    assert len(h.downloader.added) == 1
    h.fetcher.errors[FEED_URL] = FeedError("feed_unreachable", "down")
    h.refresher.refresh(h.feeds.get("feed-1"))
    assert len(h.downloader.added) == 1

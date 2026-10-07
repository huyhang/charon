from datetime import timedelta

import pytest

from charon.domain.events import EventType
from charon.domain.feeds import FeedSpec, FeedUpdate
from charon.domain.models import Actor
from charon.errors import FeedError, NotFoundError
from tests.unit.fakes import T0
from tests.unit.feed_harness import FeedHarness
from tests.unit.feed_samples import FEED_URL, hash_for, magnet, make_feed, rss, rss_item

PHONE = Actor(name="phone", key_id="key-1")
OTHER_URL = "https://other.example/rss"


def spec(**overrides) -> FeedSpec:
    return FeedSpec.model_validate({"name": "TV", "url": FEED_URL, **overrides})


def backlog() -> bytes:
    return rss(*(rss_item(f"Show {n}", magnet(n, f"Show.S01E0{n}.mkv"), T0) for n in (1, 2)))


def test_create_subscribes_fetches_once_and_credits_the_actor() -> None:
    h = FeedHarness()
    h.fetcher.documents[FEED_URL] = backlog()
    feed = h.service.create(spec(), PHONE)
    assert (feed.id, feed.created_by, feed.last_checked_at, feed.auto_download_since) == (
        "feed-1",
        PHONE,
        T0,
        None,
    )
    assert len(h.items.items) == 2
    assert h.events.types()[0] is EventType.FEED_CREATED


def test_create_with_auto_download_skips_the_backlog() -> None:
    h = FeedHarness()
    h.fetcher.documents[FEED_URL] = backlog()
    feed = h.service.create(spec(auto_download=True))
    assert h.downloader.added == []
    assert feed.auto_download_since == T0
    h.clock.advance(60)
    h.fetcher.documents[FEED_URL] = rss(rss_item("New", magnet(3, "Show.S01E03.mkv"), h.clock()))
    h.service.refresh(feed.id)
    assert h.downloader.added == [magnet(3, "Show.S01E03.mkv")]


def test_create_keeps_a_feed_that_cant_be_fetched_yet() -> None:
    h = FeedHarness()
    feed = h.service.create(spec())
    assert feed.last_error.code == "feed_unreachable"
    assert h.service.list() == [feed]


@pytest.mark.parametrize(
    ("before", "after", "since"),
    [
        (False, True, "now"),
        (True, True, "kept"),
        (True, False, None),
        (False, False, None),
    ],
    ids=["turned-on", "left-on", "turned-off", "left-off"],
)
def test_update_tracks_when_auto_download_was_turned_on(before, after, since) -> None:
    h = FeedHarness(
        feeds=[make_feed(auto_download=before, auto_download_since=T0 if before else None)]
    )
    h.clock.advance(60)
    feed = h.service.update("feed-1", FeedUpdate(name="TV", auto_download=after), PHONE)
    expected = {"now": h.clock(), "kept": T0, None: None}[since]
    assert (feed.auto_download_since, feed.updated_by, feed.updated_at) == (
        expected,
        PHONE,
        h.clock(),
    )


@pytest.mark.parametrize(
    ("url", "expected_url", "etag"),
    [(None, FEED_URL, '"v1"'), (FEED_URL, FEED_URL, '"v1"'), (OTHER_URL, OTHER_URL, None)],
    ids=["kept", "same", "changed"],
)
def test_update_resets_cache_validators_only_when_the_url_changes(url, expected_url, etag) -> None:
    h = FeedHarness(feeds=[make_feed(etag='"v1"')])
    feed = h.service.update("feed-1", FeedUpdate(name="Renamed", url=url))
    assert (feed.name, feed.url, feed.etag) == ("Renamed", expected_url, etag)
    assert h.events.types() == [EventType.FEED_UPDATED]


def test_delete_forgets_items_only_it_listed() -> None:
    h = FeedHarness(feeds=[make_feed(id="feed-1"), make_feed(id="feed-2")])
    h.fetcher.documents[FEED_URL] = backlog()
    h.service.refresh("feed-1")
    h.items.link("feed-2", [hash_for(1)], T0)
    h.service.delete("feed-1", PHONE)
    assert list(h.items.items) == [hash_for(1)]
    assert h.events.recorded[-1].type is EventType.FEED_DELETED
    with pytest.raises(NotFoundError):
        h.service.get("feed-1")


def test_delete_reports_a_feed_deleted_meanwhile() -> None:
    h = FeedHarness(feeds=[make_feed()])
    h.feeds.delete = lambda feed_id: False
    with pytest.raises(NotFoundError):
        h.service.delete("feed-1")


def test_unknown_feeds_are_not_found() -> None:
    h = FeedHarness()
    for action in (
        lambda: h.service.get("nope"),
        lambda: h.service.update("nope", FeedUpdate(name="x")),
        lambda: h.service.refresh("nope"),
    ):
        with pytest.raises(NotFoundError) as exc_info:
            action()
        assert exc_info.value.code == "feed_not_found"


def test_preview_reads_without_subscribing() -> None:
    h = FeedHarness()
    h.fetcher.documents[FEED_URL] = rss(
        *(
            rss_item(f"S{n}", magnet(n, f"Show.S01E0{n}.mkv"), T0 + timedelta(hours=n))
            for n in range(7)
        ),
        rss_item("torrent", "https://t.example/x.torrent"),
        title="Tracker",
    )
    preview = h.service.preview(f"  {FEED_URL} ")
    assert (preview.title, preview.item_count, preview.skipped_count) == ("Tracker", 7, 1)
    assert preview.newest_published_at == T0 + timedelta(hours=6)
    assert [e.item.name for e in preview.items][:2] == ["Show.S01E06.mkv", "Show.S01E05.mkv"]
    assert len(preview.items) == 5
    assert preview.items[0].match.rule.id == "tv"
    assert h.service.list() == [] and h.items.items == {}


@pytest.mark.parametrize("url", ["ftp://x", "not a url"])
def test_preview_rejects_unusable_addresses(url: str) -> None:
    with pytest.raises(FeedError) as exc_info:
        FeedHarness().service.preview(url)
    assert exc_info.value.code == "feed_invalid_url"


def test_preview_passes_fetch_problems_on() -> None:
    with pytest.raises(FeedError) as exc_info:
        FeedHarness().service.preview(FEED_URL)
    assert exc_info.value.code == "feed_unreachable"


def test_refresh_due_refreshes_only_due_feeds_and_isolates_failures(caplog) -> None:
    due = make_feed(id="due", url="https://due.example/rss")
    broken = make_feed(id="broken", url="https://broken.example/rss")
    recent = make_feed(id="recent", url="https://recent.example/rss", last_checked_at=T0)
    off = make_feed(id="off", url="https://off.example/rss", enabled=False)
    h = FeedHarness(feeds=[broken, due, recent, off])
    h.fetcher.documents["https://due.example/rss"] = rss()
    h.fetcher.errors["https://broken.example/rss"] = RuntimeError("bug")  # type: ignore[assignment]
    h.service.refresh_due()
    assert [url for url, _, _ in h.fetcher.fetches] == [
        "https://broken.example/rss",
        "https://due.example/rss",
    ]
    assert h.feeds.get("due").last_checked_at == T0
    assert "broken.example" not in caplog.text and "broken" in caplog.text

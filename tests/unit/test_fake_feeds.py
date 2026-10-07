"""The fake feeds, including a contract test: Charon's own parser must read them."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from charon.domain.rss import parse_feed
from fake_ds.app import create_app
from fake_ds.feeds import FakeFeeds, FeedMode
from fake_ds.simulator import Simulator
from fake_ds.station import FakeStation

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


@pytest.fixture
def feeds() -> FakeFeeds:
    return FakeFeeds(clock=lambda: NOW)


@pytest.fixture
def client(feeds: FakeFeeds, tmp_path: Path) -> TestClient:
    station = FakeStation(Simulator(tmp_path), "admin", "admin")
    return TestClient(create_app(station, feeds))


@pytest.mark.parametrize("slug", ["tv", "anime"])
def test_charon_reads_every_sample_feed(client: TestClient, slug: str) -> None:
    response = client.get(f"/feeds/{slug}.xml")
    assert response.headers["content-type"].startswith("application/rss+xml")
    parsed = parse_feed(response.content)
    assert parsed.title.startswith("Fake Tracker")
    assert parsed.items and all(i.size_bytes for i in parsed.items)


def test_samples_cover_undated_skipped_and_duplicate_items(client: TestClient) -> None:
    tv = parse_feed(client.get("/feeds/tv.xml").content)
    anime = parse_feed(client.get("/feeds/anime.xml").content)
    assert tv.skipped == 1
    assert any(i.published_at is None for i in tv.items)
    assert {i.info_hash for i in tv.items} & {i.info_hash for i in anime.items}
    newest = max(i.published_at for i in tv.items if i.published_at)
    assert newest == NOW - timedelta(minutes=20)


def test_unchanged_feed_answers_not_modified(client: TestClient) -> None:
    etag = client.get("/feeds/tv.xml").headers["ETag"]
    assert client.get("/feeds/tv.xml", headers={"If-None-Match": etag}).status_code == 304
    client.post("/_control/feeds/tv/publish")
    assert client.get("/feeds/tv.xml", headers={"If-None-Match": etag}).status_code == 200


@pytest.mark.parametrize(
    ("body", "expected_name"),
    [(None, "Fresh.Show.S01E01.1080p.WEB-DL.mkv"), ({"name": "Custom.mkv"}, "Custom.mkv")],
)
def test_publish_adds_an_item_dated_now(client: TestClient, body, expected_name: str) -> None:
    published = client.post("/_control/feeds/tv/publish", json=body).json()
    [first, *_] = parse_feed(client.get("/feeds/tv.xml").content).items
    assert (first.name, first.info_hash, first.published_at) == (
        expected_name,
        published["info_hash"],
        NOW,
    )


def test_anime_feed_publishes_anime_names(feeds: FakeFeeds) -> None:
    assert feeds.publish("anime").name == "[SubsPlease] Fresh Anime - 01 (1080p).mkv"


@pytest.mark.parametrize(
    ("mode", "status", "readable"),
    [("http_error", 503, False), ("bad_xml", 200, False)],
)
def test_broken_feeds_until_healed(client: TestClient, mode: str, status: int, readable) -> None:
    client.post("/_control/feeds/tv/break", json={"mode": mode})
    response = client.get("/feeds/tv.xml")
    assert response.status_code == status
    assert b"<rss" not in response.content
    healed = client.post("/_control/feeds/tv/heal").json()
    assert healed["mode"] == FeedMode.OK
    assert parse_feed(client.get("/feeds/tv.xml").content).items


def test_break_defaults_to_an_http_error(client: TestClient) -> None:
    assert client.post("/_control/feeds/tv/break").json()["mode"] == "http_error"


def test_control_lists_feeds_and_reset_restores_samples(client: TestClient) -> None:
    client.post("/_control/feeds/tv/publish")
    client.post("/_control/feeds/anime/break")
    client.post("/_control/reset")
    listed = {f["slug"]: f for f in client.get("/_control/feeds").json()}
    assert listed["tv"]["path"] == "/feeds/tv.xml"
    assert listed["anime"]["mode"] == "ok"
    assert not any(i["name"].startswith("Fresh") for i in listed["tv"]["items"])


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/feeds/nope.xml"),
        ("post", "/_control/feeds/nope/publish"),
        ("post", "/_control/feeds/nope/break"),
        ("post", "/_control/feeds/nope/heal"),
    ],
)
def test_unknown_feeds_are_404(client: TestClient, method: str, path: str) -> None:
    assert getattr(client, method)(path).status_code == 404


def test_publish_to_an_unknown_feed_returns_none(feeds: FakeFeeds) -> None:
    assert feeds.publish("nope") is None
    assert feeds.set_mode("nope", FeedMode.OK) is None

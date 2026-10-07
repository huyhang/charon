from datetime import timedelta

import pytest

from tests.unit.api_harness import Harness
from tests.unit.fakes import T0
from tests.unit.feed_samples import FEED_URL, hash_for, magnet, rss, rss_item

ADMIN = {"X-API-Key": "admin-secret"}
RULE = {"name": "TV", "pattern": "Show.*", "destination": "/tv"}
DOCUMENT = rss(
    rss_item("Show 1", magnet(1, "Show.S01E01.mkv"), T0),
    rss_item("Movie", magnet(2, "Movie.2024.mkv"), T0 - timedelta(hours=1)),
    title="Tracker",
)


@pytest.fixture
def h() -> Harness:
    harness = Harness(admin_key="admin-secret")
    harness.fetcher.documents[FEED_URL] = DOCUMENT
    harness.client.post("/rules", json=RULE, headers=ADMIN)
    return harness


def client_key(h: Harness) -> dict:
    issued = h.client.post("/api-keys", json={"name": "phone"}, headers=ADMIN).json()
    return {"X-API-Key": issued["key"]}


def subscribe(h: Harness, headers: dict = ADMIN, **body) -> dict:
    response = h.client.post(
        "/feeds", json={"name": "TV", "url": FEED_URL, **body}, headers=headers
    )
    assert response.status_code == 201
    return response.json()


def test_subscribe_masks_the_url_and_fetches_right_away(h: Harness) -> None:
    feed = subscribe(h, headers=client_key(h))
    assert feed["url"] == "https://tracker.example/rss?passkey=••••"
    assert (feed["title"], feed["last_error"], feed["created_by"]["name"]) == (
        "Tracker",
        None,
        "phone",
    )
    assert feed["next_check_at"] == (T0 + timedelta(minutes=15)).isoformat().replace("+00:00", "Z")
    listed = h.client.get("/feeds", headers=ADMIN).json()
    assert [f["url"] for f in listed] == [feed["url"]]
    assert "s3cret" not in h.client.get(f"/feeds/{feed['id']}", headers=ADMIN).text


def test_a_feed_that_cant_be_fetched_reports_why_with_a_hint(h: Harness) -> None:
    feed = subscribe(h, url="https://down.example/rss")
    assert feed["last_error"]["code"] == "feed_unreachable"
    assert feed["last_error"]["hint"]


@pytest.mark.parametrize(("admin", "status"), [(True, 200), (False, 403)])
def test_only_admins_can_reveal_the_url(h: Harness, admin: bool, status: int) -> None:
    feed = subscribe(h)
    headers = ADMIN if admin else client_key(h)
    response = h.client.get(f"/feeds/{feed['id']}/url", headers=headers)
    assert response.status_code == status
    if admin:
        assert response.json() == {"url": FEED_URL}


@pytest.mark.parametrize(
    ("admin", "body", "status"),
    [
        (False, {"name": "Renamed", "refresh_minutes": 30}, 200),
        (False, {"name": "Renamed", "url": "https://other.example/rss"}, 403),
        (True, {"name": "Renamed", "url": "https://other.example/rss"}, 200),
        (True, {"name": "Renamed", "refresh_minutes": 1}, 422),
    ],
    ids=["client-settings", "client-url", "admin-url", "too-frequent"],
)
def test_update_feed(h: Harness, admin: bool, body: dict, status: int) -> None:
    feed = subscribe(h)
    headers = ADMIN if admin else client_key(h)
    response = h.client.put(f"/feeds/{feed['id']}", json=body, headers=headers)
    assert response.status_code == status


def test_delete_and_refresh(h: Harness) -> None:
    feed = subscribe(h)
    refreshed = h.client.post(f"/feeds/{feed['id']}/refresh", headers=ADMIN)
    assert refreshed.status_code == 200
    assert h.client.delete(f"/feeds/{feed['id']}", headers=ADMIN).status_code == 204
    assert h.client.get(f"/feeds/{feed['id']}", headers=ADMIN).status_code == 404
    assert h.client.get("/feeds/items", headers=ADMIN).json()["items"] == []


def test_preview_without_subscribing(h: Harness) -> None:
    preview = h.client.post("/feeds/preview", json={"url": FEED_URL}, headers=ADMIN).json()
    assert (preview["title"], preview["item_count"], preview["skipped_count"]) == ("Tracker", 2, 0)
    assert [i["match"]["rule_name"] if i["match"] else None for i in preview["items"]] == [
        "TV",
        None,
    ]
    assert h.client.get("/feeds", headers=ADMIN).json() == []


@pytest.mark.parametrize(
    ("url", "code"),
    [("ftp://x", "feed_invalid_url"), ("https://down.example/rss", "feed_unreachable")],
)
def test_preview_errors(h: Harness, url: str, code: str) -> None:
    response = h.client.post("/feeds/preview", json={"url": url}, headers=ADMIN)
    assert response.status_code == 422
    error = response.json()["error"]
    assert (error["code"], bool(error["hint"])) == (code, True)


def test_items_are_checked_against_rules_and_filterable(h: Harness) -> None:
    feed = subscribe(h)
    items = h.client.get("/feeds/items", headers=ADMIN).json()["items"]
    show, movie = items
    assert show["match"] == {
        "rule_id": "rule-1",
        "rule_name": "TV",
        "new_name": "Show.S01E01.mkv",
        "final_path": "/tv/Show.S01E01.mkv",
    }
    assert (show["feeds"], show["seen"], show["job"]) == (
        [{"id": feed["id"], "name": "TV"}],
        False,
        None,
    )
    assert movie["match"] is None
    unmatched = h.client.get("/feeds/items", params={"match": "unmatched"}, headers=ADMIN).json()
    assert [i["name"] for i in unmatched["items"]] == ["Movie.2024.mkv"]
    searched = h.client.get("/feeds/items", params={"q": "show"}, headers=ADMIN).json()
    assert [i["name"] for i in searched["items"]] == ["Show.S01E01.mkv"]


def test_items_page_with_a_cursor(h: Harness) -> None:
    subscribe(h)
    first = h.client.get("/feeds/items", params={"limit": 1}, headers=ADMIN).json()
    params = {"limit": 1, "cursor": first["next_cursor"]}
    second = h.client.get("/feeds/items", params=params, headers=ADMIN).json()
    assert [i["name"] for i in first["items"] + second["items"]] == [
        "Show.S01E01.mkv",
        "Movie.2024.mkv",
    ]
    assert second["next_cursor"] is None


def test_download_an_item_then_again(h: Harness) -> None:
    subscribe(h)
    path = f"/feeds/items/{hash_for(1)}/download"
    first = h.client.post(path, json={}, headers=ADMIN)
    again = h.client.post(path, json={}, headers=ADMIN)
    assert (first.status_code, again.status_code) == (202, 200)
    assert again.json()["id"] == first.json()["id"]
    item = h.client.get(f"/feeds/items/{hash_for(1)}", headers=ADMIN).json()
    assert item["job"] == {
        "id": first.json()["id"],
        "status": "queued",
        "percent": 0.0,
        "error_code": None,
    }


def test_unknown_item_is_404(h: Harness) -> None:
    response = h.client.post("/feeds/items/nope/download", json={}, headers=ADMIN)
    assert (response.status_code, response.json()["error"]["code"]) == (404, "feed_item_not_found")


def test_mark_seen_and_summary(h: Harness) -> None:
    feed = subscribe(h)
    assert h.client.get("/feeds/summary", headers=ADMIN).json() == {
        "unread": 2,
        "feeds": {feed["id"]: 2},
    }
    marked = h.client.post("/feeds/items/seen-all", json={"up_to": T0.isoformat()}, headers=ADMIN)
    assert marked.json() == {"marked": 2}
    assert h.client.get("/feeds/summary", headers=ADMIN).json() == {"unread": 0, "feeds": {}}
    unseen = h.client.get("/feeds/items", params={"unseen": True}, headers=ADMIN).json()
    assert unseen["items"] == []


def test_subscribe_with_an_idempotency_key_once(h: Harness) -> None:
    headers = {**ADMIN, "Idempotency-Key": "feed-1"}
    body = {"name": "TV", "url": FEED_URL}
    first = h.client.post("/feeds", json=body, headers=headers)
    again = h.client.post("/feeds", json=body, headers=headers)
    assert (first.status_code, again.status_code) == (201, 200)
    assert len(h.client.get("/feeds", headers=ADMIN).json()) == 1


def test_feed_events_are_recorded(h: Harness) -> None:
    subscribe(h)
    types = [e["type"] for e in h.client.get("/events", headers=ADMIN).json()["items"]]
    assert types[-3:] == ["feed.created", "feed_item.added", "feed_item.added"]


@pytest.mark.parametrize("path", ["/feeds", "/feeds/items", "/feeds/summary"])
def test_feeds_require_a_key(h: Harness, path: str) -> None:
    assert h.client.get(path).status_code == 401


@pytest.mark.parametrize(
    "url",
    ["http://t.example:99999/rss", "http://t.example:abc/rss", "http://a..b/rss"],
    ids=["port-out-of-range", "port-not-a-number", "empty-host-label"],
)
def test_an_unusable_address_is_refused_and_the_feed_list_stays_readable(
    h: Harness, url: str
) -> None:
    for path in ("/feeds", "/feeds/preview"):
        response = h.client.post(path, json={"name": "Bad", "url": url}, headers=ADMIN)
        assert response.status_code == 422, path
    listed = h.client.get("/feeds", headers=ADMIN)
    assert (listed.status_code, listed.json()) == (200, [])


@pytest.mark.parametrize(
    "same_feed",
    [FEED_URL, FEED_URL.replace("https://tracker", "HTTPS://TRACKER"), FEED_URL + "#latest"],
    ids=["same-address", "different-case", "with-fragment"],
)
def test_subscribing_twice_to_one_feed_is_refused(h: Harness, same_feed: str) -> None:
    subscribe(h)
    response = h.client.post("/feeds", json={"name": "Again", "url": same_feed}, headers=ADMIN)
    assert response.status_code == 409
    error = response.json()["error"]
    assert (error["code"], error["message"]) == (
        "feed_exists",
        "already subscribed to this feed as TV",
    )
    assert len(h.client.get("/feeds", headers=ADMIN).json()) == 1


def test_moving_a_feed_to_another_feeds_address_is_refused(h: Harness) -> None:
    h.fetcher.documents["https://other.example/rss"] = DOCUMENT
    subscribe(h)
    other = subscribe(h, name="Other", url="https://other.example/rss")
    response = h.client.put(
        f"/feeds/{other['id']}", json={"name": "Other", "url": FEED_URL}, headers=ADMIN
    )
    assert (response.status_code, response.json()["error"]["code"]) == (409, "feed_exists")


def test_content_that_breaks_reading_is_recorded_not_a_server_error(h: Harness) -> None:
    h.fetcher.errors[FEED_URL] = RuntimeError("bug")  # type: ignore[assignment]
    feed = subscribe(h)
    assert feed["last_error"]["code"] == "feed_unreadable"
    assert feed["last_checked_at"] is not None


def test_refreshing_all_feeds_skips_paused_ones(h: Harness) -> None:
    h.fetcher.documents["https://paused.example/rss"] = DOCUMENT
    subscribe(h)
    paused = subscribe(h, name="Paused", url="https://paused.example/rss", enabled=False)
    h.fetcher.fetches.clear()
    response = h.client.post("/feeds/refresh", headers=ADMIN)
    assert response.status_code == 200
    assert [f["name"] for f in response.json()] == ["TV", "Paused"]
    assert [url for url, *_ in h.fetcher.fetches] == [FEED_URL]
    assert h.client.get(f"/feeds/{paused['id']}", headers=ADMIN).json()["enabled"] is False


def test_mark_seen_marks_only_the_items_sent(h: Harness) -> None:
    subscribe(h)
    marked = h.client.post(
        "/feeds/items/seen", json={"info_hashes": [hash_for(1), "unknown"]}, headers=ADMIN
    )
    assert marked.json() == {"marked": 1}
    unseen = h.client.get("/feeds/items", params={"unseen": True}, headers=ADMIN).json()
    assert [item["info_hash"] for item in unseen["items"]] == [hash_for(2)]


def test_mark_all_seen_leaves_what_the_view_hides(h: Harness) -> None:
    subscribe(h)
    body = {"up_to": T0.isoformat(), "match": "matched"}
    assert h.client.post("/feeds/items/seen-all", json=body, headers=ADMIN).json() == {"marked": 1}
    unseen = h.client.get("/feeds/items", params={"unseen": True}, headers=ADMIN).json()
    assert [item["name"] for item in unseen["items"]] == ["Movie.2024.mkv"]


@pytest.mark.parametrize(
    "body",
    [{"up_to": "0001-01-01T00:00:00+01:00"}, {"info_hashes": []}],
    ids=["impossible-time", "nothing-to-mark"],
)
def test_mark_seen_rejects_bad_requests_cleanly(h: Harness, body: dict) -> None:
    path = "/feeds/items/seen-all" if "up_to" in body else "/feeds/items/seen"
    response = h.client.post(path, json=body, headers=ADMIN)
    assert (response.status_code, response.json()["error"]["code"]) == (422, "invalid_request")


def test_feed_update_events_name_the_changed_fields_but_never_the_address(h: Harness) -> None:
    feed = subscribe(h)
    new_url = "https://tracker.example/rss?passkey=n3w"
    h.fetcher.documents[new_url] = DOCUMENT
    body = {"name": "TV", "url": new_url, "refresh_minutes": 30}
    h.client.put(f"/feeds/{feed['id']}", json=body, headers=ADMIN)
    events = h.client.get("/events", params={"type": "feed.updated"}, headers=ADMIN).json()
    [event] = events["items"]
    assert event["data"]["changed"] == ["refresh_minutes", "url"]
    assert "n3w" not in str(event)

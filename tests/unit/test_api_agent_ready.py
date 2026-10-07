"""Attribution, duplicate-safe creates, rule versions, error hints and the event stream."""

import base64
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from charon.ports.downloader import BackendStatus, BackendTask
from tests.unit.api_harness import Harness
from tests.unit.fakes import HeldAdds

ADMIN = {"X-API-Key": "admin-secret"}
HASH = "c12fe1c06bba254a9dc9f519b335aa7c1367a88a"
MAGNET = f"magnet:?xt=urn:btih:{HASH}&dn=Show.S01E01.mkv"
RULE = {"name": "tv", "pattern": "*S01*", "destination": "/tv"}


@pytest.fixture
def h() -> Harness:
    return Harness(admin_key="admin-secret")


def key_for(h: Harness, name: str) -> dict:
    issued = h.client.post("/api-keys", json={"name": name}, headers=ADMIN).json()
    return {"X-API-Key": issued["key"], "id": issued["id"]}


def test_jobs_and_rules_credit_the_key_that_made_them(h: Harness) -> None:
    phone = key_for(h, "phone")
    headers = {"X-API-Key": phone["X-API-Key"]}
    job = h.client.post("/downloads", json={"magnet": MAGNET}, headers=headers).json()
    rule = h.client.post("/rules", json=RULE, headers=headers).json()
    edited = h.client.put(f"/rules/{rule['id']}", json=RULE, headers=ADMIN).json()
    actor = {"name": "phone", "key_id": phone["id"]}
    assert (job["created_by"], job["info_hash"]) == (actor, HASH)
    assert (rule["created_by"], rule["updated_by"]) == (actor, actor)
    assert edited["updated_by"] == {"name": "bootstrap-admin", "key_id": None}


@pytest.mark.parametrize(
    ("second_magnet", "status", "jobs"),
    [
        (MAGNET, 200, 1),
        (f"magnet:?xt=urn:btih:{HASH.upper()}&tr=udp://t", 200, 1),
        ("magnet:?xt=urn:btih:" + "d" * 40, 202, 2),
    ],
    ids=["same-magnet", "same-torrent", "other-torrent"],
)
def test_submitting_a_torrent_twice_returns_the_first_job(h, second_magnet, status, jobs) -> None:
    first = h.client.post("/downloads", json={"magnet": MAGNET}, headers=ADMIN)
    second = h.client.post("/downloads", json={"magnet": second_magnet}, headers=ADMIN)
    assert (first.status_code, second.status_code) == (202, status)
    assert (second.json()["id"] == first.json()["id"]) is (status == 200)
    assert len(h.downloader.added) == jobs


@pytest.mark.parametrize(
    ("path", "body", "created"),
    [("/downloads", {"magnet": "magnet:?xt=urn:btih:nohash"}, 202), ("/rules", RULE, 201)],
)
def test_idempotency_key_replays_the_first_result(h, path, body, created) -> None:
    headers = {**ADMIN, "Idempotency-Key": "k-1"}
    first = h.client.post(path, json=body, headers=headers)
    again = h.client.post(path, json=body, headers=headers)
    other_key = h.client.post(path, json=body, headers={**ADMIN, "Idempotency-Key": "k-2"})
    assert (first.status_code, again.status_code, other_key.status_code) == (created, 200, created)
    assert again.json()["id"] == first.json()["id"] != other_key.json()["id"]


def test_idempotency_keys_belong_to_the_api_key_that_sent_them(h: Harness) -> None:
    agents = [key_for(h, name) for name in ("agent-a", "agent-b")]
    responses = [
        h.client.post(
            "/rules",
            json={**RULE, "name": f"rule of {agent['id']}"},
            headers={"X-API-Key": agent["X-API-Key"], "Idempotency-Key": "same-key"},
        )
        for agent in agents
    ]
    assert [r.status_code for r in responses] == [201, 201]
    assert [r.json()["created_by"]["key_id"] for r in responses] == [a["id"] for a in agents]


def test_concurrent_retries_with_one_idempotency_key_create_once(h: Harness) -> None:
    adds = HeldAdds(h.downloader)
    headers = {**ADMIN, "Idempotency-Key": "k-1"}
    # No info hash, so only the key can tell the two requests are one.
    body = {"magnet": "magnet:?xt=urn:btih:nohash"}
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(h.client.post, "/downloads", json=body, headers=headers)
        assert adds.wait_for(1, timeout=5)
        second = pool.submit(h.client.post, "/downloads", json=body, headers=headers)
        # Unchecked, the retry would reach the downloader too: give it time to.
        adds.wait_for(2, timeout=0.3)
        adds.release()
        statuses = sorted([first.result().status_code, second.result().status_code])
    assert statuses == [200, 202]
    assert len(h.jobs.jobs) == 1


def test_idempotency_key_reused_for_another_request_is_rejected(h: Harness) -> None:
    headers = {**ADMIN, "Idempotency-Key": "k-1"}
    h.client.post("/rules", json=RULE, headers=headers)
    response = h.client.post("/rules", json={**RULE, "name": "movies"}, headers=headers)
    assert response.status_code == 409
    error = response.json()["error"]
    assert (error["code"], error["retryable"]) == ("idempotency_key_reused", False)
    assert error["hint"]


def test_rule_update_with_a_stale_version_is_rejected(h: Harness) -> None:
    rule = h.client.post("/rules", json=RULE, headers=ADMIN).json()
    assert rule["version"] == 1
    first = h.client.put(f"/rules/{rule['id']}", json={**RULE, "version": 1}, headers=ADMIN)
    stale = h.client.put(
        f"/rules/{rule['id']}", json={**RULE, "name": "late", "version": 1}, headers=ADMIN
    )
    assert (first.status_code, first.json()["version"]) == (200, 2)
    assert (stale.status_code, stale.json()["error"]["code"]) == (409, "rule_changed")
    assert h.client.get(f"/rules/{rule['id']}", headers=ADMIN).json()["name"] == "tv"


def test_rule_description_round_trips(h: Harness) -> None:
    body = {**RULE, "description": "Season one of everything"}
    rule = h.client.post("/rules", json=body, headers=ADMIN).json()
    assert rule["description"] == "Season one of everything"
    too_long = h.client.post("/rules", json={**RULE, "description": "x" * 501}, headers=ADMIN)
    assert too_long.status_code == 422


@pytest.mark.parametrize(
    ("if_match", "status"),
    [('"1"', 200), ('W/"1"', 200), ("*", 200), ('"7"', 409), ("soon", 422)],
    ids=["current", "weak", "any", "stale", "garbage"],
)
def test_rule_update_honours_if_match(h: Harness, if_match: str, status: int) -> None:
    created = h.client.post("/rules", json=RULE, headers=ADMIN)
    assert created.headers["ETag"] == '"1"'
    rule_id = created.json()["id"]
    response = h.client.put(f"/rules/{rule_id}", json=RULE, headers={**ADMIN, "If-Match": if_match})
    assert response.status_code == status
    if status == 200:
        assert response.headers["ETag"] == '"2"'
        assert h.client.get(f"/rules/{rule_id}", headers=ADMIN).headers["ETag"] == '"2"'


@pytest.mark.parametrize(
    ("order", "status", "details"),
    [
        ([2, 0, 1], 200, None),
        ([0, 1], 409, {"unknown_ids": [], "missing_ids": ["rule-3"]}),
        ([0, 0, 1, 2], 422, None),
    ],
    ids=["all-rules", "missing-one", "duplicate"],
)
def test_reorder_rules_in_one_request(h: Harness, order: list[int], status: int, details) -> None:
    ids = [
        h.client.post("/rules", json={**RULE, "name": n}, headers=ADMIN).json()["id"] for n in "abc"
    ]
    response = h.client.post("/rules/reorder", json={"ids": [ids[i] for i in order]}, headers=ADMIN)
    assert response.status_code == status
    if status == 200:
        assert [r["name"] for r in response.json()] == ["c", "a", "b"]
        assert [r["priority"] for r in response.json()] == [10, 20, 30]
    else:
        assert response.json()["error"].get("details") == details


def test_submitting_a_known_torrent_with_another_rule_says_which_job_has_it(h: Harness) -> None:
    rule = h.client.post("/rules", json=RULE, headers=ADMIN).json()
    job = h.client.post("/downloads", json={"magnet": MAGNET}, headers=ADMIN).json()
    response = h.client.post(
        "/downloads", json={"magnet": MAGNET, "rule_id": rule["id"]}, headers=ADMIN
    )
    assert response.status_code == 409
    error = response.json()["error"]
    assert (error["code"], error["details"]) == ("torrent_exists", {"job_id": job["id"]})
    assert error["hint"]


@pytest.mark.parametrize("path", ["/downloads", "/feeds/items"])
def test_a_cursor_with_an_impossible_time_is_rejected_cleanly(h: Harness, path: str) -> None:
    cursor = base64.urlsafe_b64encode(b"0001-01-01T00:00:00+01:00|x").decode()
    response = h.client.get(path, params={"cursor": cursor}, headers=ADMIN)
    assert (response.status_code, response.json()["error"]["code"]) == (422, "invalid_cursor")


def test_unexpected_errors_answer_with_the_usual_json_body(h: Harness) -> None:
    h.downloader.fail_with = None
    h.jobs.list = lambda *args, **kwargs: 1 / 0
    client = TestClient(h.app, base_url="http://testserver/api/v1", raise_server_exceptions=False)
    response = client.get("/downloads", headers=ADMIN)
    assert response.status_code == 500
    error = response.json()["error"]
    assert (error["code"], error["retryable"]) == ("internal_error", True)
    assert error["hint"]


def test_job_errors_carry_a_hint(h: Harness) -> None:
    job = h.client.post("/downloads", json={"magnet": MAGNET}, headers=ADMIN).json()
    h.downloader.tasks["task-1"] = BackendTask(
        id="task-1", status=BackendStatus.ERROR, error_message="dead link"
    )
    h.watcher.tick()
    error = h.client.get(f"/downloads/{job['id']}", headers=ADMIN).json()["error"]
    assert (error["code"], error["message"]) == ("backend_error", "dead link")
    assert "Download Station" in error["hint"]


def test_validation_errors_carry_hint_and_details(h: Harness) -> None:
    error = h.client.post("/downloads", json={}, headers=ADMIN).json()["error"]
    assert (error["code"], error["retryable"]) == ("invalid_request", False)
    assert error["hint"] and error["details"]


def test_events_follow_what_happens_from_a_cursor(h: Harness) -> None:
    start = h.client.get("/events", headers=ADMIN).json()
    h.client.post("/rules", json=RULE, headers=ADMIN)
    job = h.client.post("/downloads", json={"magnet": MAGNET}, headers=ADMIN).json()
    h.client.delete(f"/downloads/{job['id']}", headers=ADMIN)

    page = h.client.get("/events", params={"after": start["cursor"]}, headers=ADMIN).json()
    assert [e["type"] for e in page["items"]] == [
        "rule.created",
        "job.created",
        "job.status_changed",
    ]
    assert page["items"][-1]["data"] == {
        "status": "cancelled",
        "previous": "queued",
    }
    assert page["items"][-1]["actor"] == {"name": "bootstrap-admin", "key_id": None}
    caught_up = h.client.get("/events", params={"after": page["cursor"]}, headers=ADMIN).json()
    assert caught_up == {"items": [], "cursor": page["cursor"]}


def test_events_can_be_filtered_by_type(h: Harness) -> None:
    h.client.post("/rules", json=RULE, headers=ADMIN)
    h.client.post("/downloads", json={"magnet": MAGNET}, headers=ADMIN)
    page = h.client.get("/events", params={"type": "job.created"}, headers=ADMIN).json()
    assert [e["type"] for e in page["items"]] == ["job.created"]


@pytest.mark.parametrize(("headers", "status"), [({}, 401), (ADMIN, 200)])
def test_events_require_a_key(h: Harness, headers: dict, status: int) -> None:
    assert h.client.get("/events", headers=headers).status_code == status

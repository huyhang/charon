from pathlib import PurePosixPath

import pytest

from charon.domain.destinations import DestinationPolicy
from charon.domain.models import JobStatus
from charon.errors import DownloaderError
from charon.hints import hint_for
from charon.ports.downloader import BackendStatus, BackendTask
from tests.unit.api_harness import Harness

MAGNET = "magnet:?xt=urn:btih:abc"
RULE = {
    "name": "xyz",
    "pattern": "*XYZ*",
    "destination": "/d/e/f",
    "steps": [{"op": "replace", "find": "XYZ", "replace": "ABC"}],
}


@pytest.fixture
def h() -> Harness:
    return Harness()


def test_submit_returns_job_view(h: Harness) -> None:
    response = h.client.post("/downloads", json={"magnet": MAGNET})
    assert response.status_code == 202
    body = response.json()
    assert body["id"] == "job-1"
    assert body["status"] == "queued"
    assert body["processing"] == {"rule_id": None, "final_path": None}
    assert body["progress"]["percent"] == 0.0
    assert "backend_task_id" not in body
    assert "forced_rule_id" not in body


def test_full_flow_through_watcher(h: Harness) -> None:
    rule_id = h.client.post("/rules", json=RULE).json()["id"]
    job_id = h.client.post("/downloads", json={"magnet": MAGNET}).json()["id"]
    h.downloader.tasks["task-1"] = BackendTask(
        id="task-1", name="Show.XYZ.mkv", status=BackendStatus.FINISHED
    )
    h.files.paths.add(PurePosixPath("/downloads/Show.XYZ.mkv"))

    h.watcher.tick()

    body = h.client.get(f"/downloads/{job_id}").json()
    assert body["status"] == "done"
    assert body["processing"] == {"rule_id": rule_id, "final_path": "/d/e/f/Show.ABC.mkv"}


def test_list_downloads_with_status_filter_and_cursor(h: Harness) -> None:
    for _ in range(3):
        h.client.post("/downloads", json={"magnet": MAGNET})
    first = h.client.get("/downloads", params={"limit": 2, "status": ["queued"]}).json()
    second = h.client.get("/downloads", params={"limit": 2, "cursor": first["next_cursor"]}).json()
    assert len(first["items"]) == 2
    assert len(second["items"]) == 1
    assert second["next_cursor"] is None


def test_download_summary_counts_all_jobs_not_one_page(h: Harness) -> None:
    for _ in range(3):
        h.client.post("/downloads", json={"magnet": MAGNET})
    h.client.delete("/downloads/job-2")
    body = h.client.get("/downloads/summary").json()
    expected = {status.value: 0 for status in JobStatus} | {"queued": 2, "cancelled": 1}
    assert body == {"counts": expected, "download_speed_bps": 0}


@pytest.mark.parametrize(
    ("headers", "status"),
    [({}, 401), ({"X-API-Key": "wrong"}, 401), ({"X-API-Key": "admin-secret"}, 200)],
)
def test_download_summary_requires_a_key(headers: dict, status: int) -> None:
    h = Harness(admin_key="admin-secret")
    assert h.client.get("/downloads/summary", headers=headers).status_code == status


def test_cancel_and_retry_endpoints(h: Harness) -> None:
    job_id = h.client.post("/downloads", json={"magnet": MAGNET}).json()["id"]
    assert h.client.delete(f"/downloads/{job_id}").json()["status"] == "cancelled"
    response = h.client.post(f"/downloads/{job_id}/retry")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "job_not_retryable"


def test_rule_crud_and_preview(h: Harness) -> None:
    created = h.client.post("/rules", json=RULE)
    assert created.status_code == 201
    rule_id = created.json()["id"]
    assert h.client.put(f"/rules/{rule_id}", json={**RULE, "priority": 5}).json()["priority"] == 5
    assert [r["id"] for r in h.client.get("/rules").json()] == [rule_id]
    preview = h.client.post("/rules/preview", json={"name": "Show.XYZ.mkv"}).json()
    assert preview == {
        "rule_id": rule_id,
        "new_name": "Show.ABC.mkv",
        "final_path": "/d/e/f/Show.ABC.mkv",
    }
    assert h.client.delete(f"/rules/{rule_id}").status_code == 204
    assert h.client.get(f"/rules/{rule_id}").status_code == 404


@pytest.mark.parametrize(
    ("body", "status", "expected"),
    [
        (
            {"name": "Show.XYZ.mkv", "rule": RULE},
            200,
            {"rule_id": None, "new_name": "Show.ABC.mkv", "final_path": "/d/e/f/Show.ABC.mkv"},
        ),
        (
            {"name": "Show.mp4", "rule": RULE},
            200,
            {"rule_id": None, "new_name": "Show.mp4", "final_path": None},
        ),
        ({"name": "x", "rule": RULE, "rule_id": "r"}, 422, None),
        ({"name": "x", "rule": {**RULE, "match_type": "regex", "pattern": "("}}, 422, None),
    ],
)
def test_preview_draft_rule(h: Harness, body: dict, status: int, expected: dict | None) -> None:
    response = h.client.post("/rules/preview", json=body)
    assert response.status_code == status
    if expected is not None:
        assert response.json() == expected


@pytest.mark.parametrize(
    ("method", "path", "payload", "status", "code"),
    [
        ("get", "/downloads/nope", None, 404, "job_not_found"),
        ("get", "/rules/nope", None, 404, "rule_not_found"),
        ("post", "/downloads", {"magnet": "http://x"}, 422, "invalid_magnet"),
        ("post", "/downloads", {"magnet": MAGNET, "rule_id": "nope"}, 422, "unknown_rule"),
        ("post", "/downloads", {}, 422, "invalid_request"),
        ("post", "/rules", {**RULE, "destination": "relative"}, 422, "invalid_request"),
        ("get", "/downloads?cursor=!!!", None, 422, "invalid_cursor"),
        ("get", "/downloads?status=bogus", None, 422, "invalid_request"),
        ("delete", "/downloads/nope", None, 404, "job_not_found"),
    ],
)
def test_error_responses(h: Harness, method, path, payload, status, code) -> None:
    kwargs = {"json": payload} if payload is not None else {}
    response = getattr(h.client, method)(path, **kwargs)
    assert response.status_code == status
    assert response.json()["error"]["code"] == code


def test_downloader_failure_maps_to_502(h: Harness) -> None:
    h.downloader.fail_with = DownloaderError("NAS offline", "downloader_unreachable")
    response = h.client.post("/downloads", json={"magnet": MAGNET})
    assert response.status_code == 502
    assert response.json() == {
        "error": {
            "code": "downloader_unreachable",
            "message": "NAS offline",
            "hint": hint_for("downloader_unreachable"),
            "retryable": True,
        }
    }


def test_health_is_public_and_reports_downloader() -> None:
    harness = Harness(admin_key="secret")
    harness.downloader.available = False
    response = harness.client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "downloader": "unreachable"}


def test_job_status_values_are_documented(h: Harness) -> None:
    schema = h.client.get("/openapi.json").json()
    assert set(schema["components"]["schemas"]["JobStatus"]["enum"]) == {s.value for s in JobStatus}


def test_rule_with_disallowed_destination_is_rejected() -> None:
    client = Harness(policy=DestinationPolicy.of(["/media"], ["/data"])).client
    response = client.post("/rules", json={**RULE, "destination": "/data"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "destination_not_allowed"

"""Scripted API flows against Charon backed by the fake Download Station."""

import time
import uuid

import httpx
import pytest

from tests.e2e.conftest import Stack

pytestmark = pytest.mark.e2e

TERMINAL = {"done", "failed", "cancelled"}


def unique_token() -> str:
    return uuid.uuid4().hex[:8]


def magnet(name: str) -> str:
    return f"magnet:?xt=urn:btih:{uuid.uuid4().hex}&dn={name}"


def wait_for(stack: Stack, job_id: str, statuses: set[str], timeout: float = 20) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = stack.charon.get(f"/downloads/{job_id}").json()
        if job["status"] in statuses:
            return job
        time.sleep(0.2)
    raise AssertionError(f"job {job_id} stuck in {job['status']}")


def backend_task_id(stack: Stack, magnet_uri: str) -> str:
    tasks = stack.fake.get("/_control/tasks").json()
    return next(t["id"] for t in tasks if t["additional"]["detail"]["uri"] == magnet_uri)


def create_rule(stack: Stack, token: str, **overrides) -> dict:
    rule = {
        "name": f"rule-{token}",
        "pattern": f"*{token}*",
        "destination": f"{stack.library_service}/{token}",
        "steps": [{"op": "replace", "find": "XYZ", "replace": "ABC"}],
        **overrides,
    }
    response = stack.charon.post("/rules", json=rule)
    assert response.status_code == 201, response.text
    return response.json()


def submit(stack: Stack, magnet_uri: str, **extra) -> dict:
    response = stack.charon.post("/downloads", json={"magnet": magnet_uri, **extra})
    assert response.status_code == 202, response.text
    return response.json()


def test_download_is_renamed_and_moved(stack: Stack) -> None:
    token = unique_token()
    rule = create_rule(stack, token)
    uri = magnet(f"Show.{token}.XYZ.mkv")
    job = submit(stack, uri)

    seen = wait_for(stack, job["id"], {"downloading"} | TERMINAL)
    done = wait_for(stack, job["id"], TERMINAL)

    assert seen["status"] in {"downloading", "done"}
    assert done["status"] == "done", done
    assert done["processing"] == {
        "rule_id": rule["id"],
        "final_path": f"{stack.library_service}/{token}/Show.{token}.ABC.mkv",
    }
    assert done["progress"]["percent"] == 100.0
    assert (stack.library_local / token / f"Show.{token}.ABC.mkv").exists()
    assert all(
        t["additional"]["detail"]["uri"] != uri for t in stack.fake.get("/_control/tasks").json()
    )


def test_forced_rule_overrides_matching(stack: Stack) -> None:
    token = unique_token()
    forced = create_rule(stack, token, pattern="never-matches", steps=[])
    uri = magnet(f"Other.{token}.mkv")
    job = submit(stack, uri, rule_id=forced["id"])
    stack.fake.post(f"/_control/tasks/{backend_task_id(stack, uri)}/complete")

    done = wait_for(stack, job["id"], TERMINAL)

    assert done["processing"]["rule_id"] == forced["id"]
    assert (stack.library_local / token / f"Other.{token}.mkv").exists()


def test_unmatched_download_stays_in_place(stack: Stack) -> None:
    name = f"Unmatched.{unique_token()}.bin"
    uri = magnet(name)
    job = submit(stack, uri)
    stack.fake.post(f"/_control/tasks/{backend_task_id(stack, uri)}/complete")

    done = wait_for(stack, job["id"], TERMINAL)

    assert done["status"] == "done"
    assert done["processing"]["rule_id"] is None
    assert done["processing"]["final_path"].endswith(f"/{name}")


def test_download_failure_then_retry(stack: Stack) -> None:
    token = unique_token()
    create_rule(stack, token)
    uri = magnet(f"Flaky.{token}.XYZ.mkv")
    job = submit(stack, uri)
    failed_task_id = backend_task_id(stack, uri)
    stack.fake.post(f"/_control/tasks/{failed_task_id}/fail", json={"detail": "tracker_down"})

    failed = wait_for(stack, job["id"], TERMINAL)
    assert failed["status"] == "failed"
    error = failed["error"]
    assert (error["stage"], error["code"], error["message"]) == (
        "download",
        "backend_error",
        "tracker_down",
    )
    assert error["hint"]

    assert stack.charon.post(f"/downloads/{job['id']}/retry").status_code == 202
    assert all(t["id"] != failed_task_id for t in stack.fake.get("/_control/tasks").json())
    assert wait_for(stack, job["id"], TERMINAL)["status"] == "done"


def test_destination_conflict_then_retry(stack: Stack) -> None:
    token = unique_token()
    create_rule(stack, token)
    target = stack.library_local / token / f"Clash.{token}.ABC.mkv"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("already here")
    uri = magnet(f"Clash.{token}.XYZ.mkv")
    job = submit(stack, uri)
    stack.fake.post(f"/_control/tasks/{backend_task_id(stack, uri)}/complete")

    failed = wait_for(stack, job["id"], TERMINAL)
    assert (failed["status"], failed["error"]["code"]) == ("failed", "destination_exists")
    assert target.read_text() == "already here"

    target.unlink()
    stack.charon.post(f"/downloads/{job['id']}/retry")
    assert wait_for(stack, job["id"], TERMINAL)["status"] == "done"
    assert target.read_text().startswith("fake download of")


def test_cancel_removes_backend_task(stack: Stack) -> None:
    uri = magnet(f"Cancel.{unique_token()}.mkv")
    job = submit(stack, uri)
    task_id = backend_task_id(stack, uri)

    cancelled = stack.charon.delete(f"/downloads/{job['id']}").json()

    assert cancelled["status"] == "cancelled"
    assert all(t["id"] != task_id for t in stack.fake.get("/_control/tasks").json())


def test_charon_recovers_from_expired_session(stack: Stack) -> None:
    stack.fake.post("/_control/sessions/expire")
    job = submit(stack, magnet(f"Session.{unique_token()}.mkv"))
    assert job["status"] == "queued"


def test_rule_preview(stack: Stack) -> None:
    token = unique_token()
    rule = create_rule(stack, token)
    preview = stack.charon.post("/rules/preview", json={"name": f"A.{token}.XYZ.mkv"}).json()
    assert preview["rule_id"] == rule["id"]
    assert preview["new_name"] == f"A.{token}.ABC.mkv"


def test_listing_includes_submitted_job(stack: Stack) -> None:
    job = submit(stack, magnet(f"List.{unique_token()}.mkv"))
    page = stack.charon.get("/downloads", params={"limit": 200}).json()
    assert job["id"] in {j["id"] for j in page["items"]}


def test_requests_without_api_key_are_rejected(stack: Stack) -> None:
    if not stack.charon.headers.get("X-API-Key"):
        pytest.skip("service is running without an API key")
    assert httpx.get(stack.charon.base_url.join("downloads")).status_code == 401


def test_health_reports_reachable_downloader(stack: Stack) -> None:
    assert stack.charon.get("/health").json() == {"status": "ok", "downloader": "reachable"}


def test_issued_key_works_until_revoked(stack: Stack) -> None:
    if not stack.charon.headers.get("X-API-Key"):
        pytest.skip("service is running without an API key")
    issued = stack.charon.post("/api-keys", json={"name": f"e2e-{unique_token()}"}).json()
    client_key = {"X-API-Key": issued["key"]}
    downloads_url = stack.charon.base_url.join("downloads")
    keys_url = stack.charon.base_url.join("api-keys")

    assert httpx.get(downloads_url, headers=client_key).status_code == 200
    assert httpx.get(keys_url, headers=client_key).status_code == 403

    assert stack.charon.delete(f"/api-keys/{issued['id']}").json()["revoked_at"] is not None
    assert httpx.get(downloads_url, headers=client_key).status_code == 401


def test_auth_me_identifies_caller(stack: Stack) -> None:
    me = stack.charon.get("/auth/me").json()
    assert me["role"] == "admin"


def test_rules_cannot_target_directories_outside_the_allowed_roots(stack: Stack) -> None:
    for destination in ("/etc", f"{stack.library_service}/../data", "/"):
        response = stack.charon.post(
            "/rules", json={"name": "escape", "pattern": "*", "destination": destination}
        )
        assert response.status_code == 422, destination
        assert response.json()["error"]["code"] == "destination_not_allowed"

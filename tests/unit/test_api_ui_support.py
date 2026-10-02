"""API features that exist to support a browser UI."""

import pytest
from fastapi.testclient import TestClient

from tests.unit.api_harness import Harness

ADMIN = {"X-API-Key": "admin-secret"}


@pytest.mark.parametrize(
    ("admin_key", "role", "expected"),
    [
        (None, None, {"name": "anonymous", "role": "admin", "key_id": None, "auth_enabled": False}),
        (
            "admin-secret",
            None,
            {"name": "bootstrap-admin", "role": "admin", "key_id": None, "auth_enabled": True},
        ),
        (
            "admin-secret",
            "client",
            {"name": "phone", "role": "client", "key_id": "key-1", "auth_enabled": True},
        ),
    ],
)
def test_auth_me(admin_key: str | None, role: str | None, expected: dict) -> None:
    h = Harness(admin_key=admin_key)
    headers = ADMIN if admin_key else {}
    if role is not None:
        created = h.client.post("/api-keys", json={"name": "phone", "role": role}, headers=ADMIN)
        headers = {"X-API-Key": created.json()["key"]}
    assert h.client.get("/auth/me", headers=headers).json() == expected


def test_auth_me_rejects_bad_key() -> None:
    response = Harness(admin_key="admin-secret").client.get("/auth/me", headers={"X-API-Key": "x"})
    assert response.status_code == 401


@pytest.mark.parametrize(
    ("origin", "allowed"),
    [("http://localhost:5173", True), ("http://evil.example", False)],
)
def test_cors_preflight(origin: str, allowed: bool) -> None:
    client = Harness(cors_origins=["http://localhost:5173"]).client
    response = client.options(
        "/downloads",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "X-API-Key, Content-Type",
        },
    )
    assert (response.headers.get("access-control-allow-origin") == origin) is allowed


def test_no_cors_headers_by_default() -> None:
    response = Harness().client.get("/downloads", headers={"Origin": "http://localhost:5173"})
    assert "access-control-allow-origin" not in response.headers


@pytest.fixture
def ui_client(tmp_path) -> TestClient:
    (tmp_path / "index.html").write_text("<html>charon ui</html>")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log('ui')")
    return TestClient(Harness(ui_dir=tmp_path).app)


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/", "<html>charon ui</html>"),
        ("/assets/app.js", "console.log('ui')"),
        ("/downloads/123", "<html>charon ui</html>"),
    ],
)
def test_ui_is_served_with_spa_fallback(ui_client: TestClient, path: str, body: str) -> None:
    response = ui_client.get(path)
    assert (response.status_code, response.text) == (200, body)


@pytest.mark.parametrize(
    ("path", "status", "code"),
    [("/api/v1/downloads", 200, None), ("/api/v1/nope", 404, "not_found")],
)
def test_api_paths_win_over_ui(ui_client: TestClient, path: str, status: int, code) -> None:
    response = ui_client.get(path)
    assert response.status_code == status
    if code:
        assert response.json()["error"]["code"] == code


@pytest.mark.parametrize("ui_dir_has_index", [False, None])
def test_no_ui_when_unconfigured_or_empty(tmp_path, ui_dir_has_index) -> None:
    ui_dir = tmp_path if ui_dir_has_index is False else None
    client = TestClient(Harness(ui_dir=ui_dir).app)
    assert client.get("/").status_code == 404


@pytest.mark.parametrize(
    ("method", "path", "status", "code"),
    [
        ("get", "/api/v1/unknown", 404, "not_found"),
        ("put", "/api/v1/downloads", 405, "method_not_allowed"),
        ("get", "/downloads", 404, "not_found"),
    ],
)
def test_unknown_routes_use_standard_error_body(method, path, status, code) -> None:
    client = TestClient(Harness().app)
    response = getattr(client, method)(path)
    assert response.status_code == status
    assert response.json()["error"]["code"] == code

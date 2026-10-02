import pytest

from tests.unit.api_harness import Harness

ADMIN = {"X-API-Key": "admin-secret"}


@pytest.fixture
def h() -> Harness:
    return Harness(admin_key="admin-secret")


def issue(h: Harness, name: str = "phone", role: str = "client") -> dict:
    response = h.client.post("/api-keys", json={"name": name, "role": role}, headers=ADMIN)
    assert response.status_code == 201, response.text
    return response.json()


def test_create_returns_secret_once(h: Harness) -> None:
    issued = issue(h)
    assert issued["key"].startswith("chk_")
    assert issued["prefix"] == issued["key"][:12]
    assert (issued["name"], issued["role"], issued["revoked_at"]) == ("phone", "client", None)
    listed = h.client.get("/api-keys", headers=ADMIN).json()
    fetched = h.client.get(f"/api-keys/{issued['id']}", headers=ADMIN).json()
    for view in (listed[0], fetched):
        assert "key" not in view
        assert "key_hash" not in view
        assert issued["key"] not in str(view)


@pytest.mark.parametrize(
    ("path", "method"),
    [("/downloads", "get"), ("/rules", "get")],
)
def test_issued_client_key_works_until_revoked(h: Harness, path: str, method: str) -> None:
    issued = issue(h)
    headers = {"X-API-Key": issued["key"]}
    assert getattr(h.client, method)(path, headers=headers).status_code == 200

    revoked = h.client.delete(f"/api-keys/{issued['id']}", headers=ADMIN)

    assert revoked.status_code == 200
    assert revoked.json()["revoked_at"] is not None
    response = getattr(h.client, method)(path, headers=headers)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


@pytest.mark.parametrize(
    ("role", "list_status", "create_status"),
    [("client", 403, 403), ("admin", 200, 201)],
)
def test_only_admin_keys_manage_keys(
    h: Harness, role: str, list_status: int, create_status: int
) -> None:
    caller = {"X-API-Key": issue(h, name="caller", role=role)["key"]}
    assert h.client.get("/api-keys", headers=caller).status_code == list_status
    response = h.client.post("/api-keys", json={"name": "x"}, headers=caller)
    assert response.status_code == create_status


def test_admin_key_can_revoke_itself(h: Harness) -> None:
    issued = issue(h, name="ops", role="admin")
    own = {"X-API-Key": issued["key"]}
    assert h.client.delete(f"/api-keys/{issued['id']}", headers=own).status_code == 200
    assert h.client.get("/api-keys", headers=own).status_code == 401


@pytest.mark.parametrize(
    ("headers", "status"),
    [({}, 401), ({"X-API-Key": "wrong"}, 401), (ADMIN, 200)],
)
def test_auth_is_enforced_when_admin_key_configured(h: Harness, headers: dict, status: int) -> None:
    for path in ("/downloads", "/rules", "/api-keys"):
        assert h.client.get(path, headers=headers).status_code == status


@pytest.mark.parametrize(
    ("method", "path", "payload", "status", "code"),
    [
        ("get", "/api-keys/nope", None, 404, "api_key_not_found"),
        ("delete", "/api-keys/nope", None, 404, "api_key_not_found"),
        ("post", "/api-keys", {"name": ""}, 422, "invalid_request"),
        ("post", "/api-keys", {"name": "x", "role": "root"}, 422, "invalid_request"),
    ],
)
def test_key_endpoint_errors(h: Harness, method, path, payload, status, code) -> None:
    kwargs = {"json": payload} if payload is not None else {}
    response = getattr(h.client, method)(path, headers=ADMIN, **kwargs)
    assert response.status_code == status
    assert response.json()["error"]["code"] == code


def test_auth_disabled_leaves_api_open_but_refuses_key_management() -> None:
    client = Harness(admin_key=None).client
    assert client.get("/downloads").status_code == 200
    response = client.post("/api-keys", json={"name": "phone"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "auth_disabled"

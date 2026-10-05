from pathlib import PurePosixPath

import pytest

from charon.domain.destinations import DestinationPolicy
from tests.unit.api_harness import Harness

ADMIN = {"X-API-Key": "admin-secret"}


@pytest.fixture
def h() -> Harness:
    harness = Harness(
        admin_key="admin-secret",
        policy=DestinationPolicy.of(["/library"], ["/data"]),
        roots=("/library",),
    )
    harness.files.folders = {
        PurePosixPath("/library"): ["tv", "movies"],
        PurePosixPath("/library/tv"): [],
    }
    return harness


@pytest.mark.parametrize(
    ("path", "params"),
    [("/destinations/roots", {}), ("/destinations/folders", {"path": "/library"})],
)
def test_destinations_require_a_key(h: Harness, path: str, params: dict) -> None:
    assert h.client.get(path, params=params).status_code == 401


def test_roots(h: Harness) -> None:
    response = h.client.get("/destinations/roots", headers=ADMIN)
    assert response.json() == {"roots": ["/library"]}


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        (
            "/library",
            {
                "path": "/library",
                "parent": None,
                "folders": [
                    {"name": "movies", "path": "/library/movies"},
                    {"name": "tv", "path": "/library/tv"},
                ],
            },
        ),
        ("/library/tv", {"path": "/library/tv", "parent": "/library", "folders": []}),
    ],
)
def test_folders(h: Harness, path: str, expected: dict) -> None:
    response = h.client.get("/destinations/folders", params={"path": path}, headers=ADMIN)
    assert response.status_code == 200
    assert response.json() == expected


@pytest.mark.parametrize(
    ("params", "status", "code"),
    [
        ({"path": "/etc"}, 422, "destination_not_allowed"),
        ({"path": "/library/missing"}, 404, "folder_not_found"),
        ({"path": "library"}, 422, "invalid_path"),
        ({}, 422, "invalid_request"),
    ],
)
def test_folders_errors(h: Harness, params: dict, status: int, code: str) -> None:
    response = h.client.get("/destinations/folders", params=params, headers=ADMIN)
    assert response.status_code == status
    assert response.json()["error"]["code"] == code

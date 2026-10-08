"""The fake TMDB, including a contract test: Charon's own TMDB adapter must read it."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from charon.adapters.tmdb.provider import TmdbProvider
from charon.errors import MetadataError, RateLimitedError
from fake_ds.app import create_app
from fake_ds.simulator import Simulator
from fake_ds.station import FakeStation
from fake_ds.tmdb import DEV_TOKEN, FakeTmdb
from tests.unit.fakes import FakeTime

AUTH = {"Authorization": f"Bearer {DEV_TOKEN}"}
SEARCH = "/tmdb/3/search/multi"


@pytest.fixture
def time() -> FakeTime:
    return FakeTime()


@pytest.fixture
def tmdb(time: FakeTime) -> FakeTmdb:
    return FakeTmdb(limit=3, window_seconds=10.0, clock=time)


@pytest.fixture
def client(tmdb: FakeTmdb, tmp_path: Path) -> TestClient:
    station = FakeStation(Simulator(tmp_path), "admin", "admin")
    return TestClient(create_app(station, tmdb=tmdb))


def adapter(client: TestClient) -> TmdbProvider:
    http = TestClient(client.app, base_url="http://testserver/tmdb")
    return TmdbProvider(http, lambda: DEV_TOKEN)


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("Kusuriya no Hitorigoto", ["The Apothecary Diaries"]),
        ("kusuriya", ["The Apothecary Diaries"]),
        ("Sousou no Frieren", ["Frieren: Beyond Journey's End"]),
        ("frieren", ["Frieren: Beyond Journey's End"]),
        ("Dandadan", ["DAN DA DAN"]),
        ("Dune", ["Dune: Part Two", "Dune"]),
        ("Shogun", ["Shōgun"]),
        ("One Piece Film Red", ["One Piece Film Red"]),
        ("nothing like this", []),
    ],
)
def test_charon_reads_the_fakes_answers(client: TestClient, query: str, expected: list) -> None:
    assert [match.title for match in adapter(client).search(query)] == expected


def test_multi_search_lists_people_too_in_tmdb_shapes(client: TestClient) -> None:
    body = client.get(SEARCH, params={"query": "Kusuriya"}, headers=AUTH).json()
    assert (body["page"], body["total_pages"], body["total_results"]) == (1, 1, 2)
    assert [r["media_type"] for r in body["results"]] == ["tv", "person"]
    assert body["results"][0]["first_air_date"] == "2023-10-22"


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer wrong"}])
def test_searches_need_the_token(client: TestClient, headers: dict) -> None:
    response = client.get(SEARCH, params={"query": "dune"}, headers=headers)
    assert response.status_code == 401
    assert response.json()["status_code"] == 7


@pytest.mark.parametrize(
    ("control", "status", "error", "code"),
    [
        ("throttle", 429, RateLimitedError, "metadata_rate_limited"),
        ("down", 503, MetadataError, "metadata_unavailable"),
    ],
)
def test_control_endpoints_break_and_heal_it(
    client: TestClient, control: str, status: int, error: type, code: str
) -> None:
    client.post(f"/_control/tmdb/{control}")
    assert client.get(SEARCH, params={"query": "dune"}, headers=AUTH).status_code == status
    with pytest.raises(error) as caught:
        adapter(client).search("dune")
    assert caught.value.code == code
    client.post("/_control/tmdb/heal")
    assert client.get(SEARCH, params={"query": "dune"}, headers=AUTH).status_code == 200


def test_it_refuses_requests_over_its_limit_and_records_the_busiest_window(
    client: TestClient, time: FakeTime
) -> None:
    def search(headers: dict) -> int:
        return client.get(SEARCH, params={"query": "x"}, headers=headers).status_code

    statuses = [search(AUTH), search({}), search({}), search(AUTH)]
    assert statuses == [200, 401, 401, 429]  # refused requests count too
    time.now += 10.0
    assert client.get(SEARCH, params={"query": "x"}, headers=AUTH).status_code == 200
    state = client.get("/_control/tmdb").json()
    assert state == {
        "mode": "ok",
        "requests": 5,
        "busiest_window": 4,
        "limit": 3,
        "window_seconds": 10.0,
    }


def test_reset_restores_it(client: TestClient) -> None:
    client.post("/_control/tmdb/down")
    client.get(SEARCH, params={"query": "dune"}, headers=AUTH)
    client.post("/_control/reset")
    state = client.get("/_control/tmdb").json()
    assert (state["mode"], state["requests"], state["busiest_window"]) == ("ok", 0, 0)

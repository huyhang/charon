import pytest

from charon.domain.titles import TitleKind
from charon.errors import MetadataError, RateLimitedError
from charon.services.metadata_service import MetadataService
from charon.services.provider_keys import ProviderKeys
from tests.unit.api_harness import Harness
from tests.unit.fakes import InMemorySettingsStore, make_title

KEY = {"X-API-Key": "admin-secret"}
NOTICE = (
    "This product uses TMDB and the TMDB APIs but is not endorsed, certified, "
    "or otherwise approved by TMDB."
)
ATTRIBUTION = {"id": "tmdb", "name": "TMDB", "url": "https://www.themoviedb.org", "notice": NOTICE}


@pytest.fixture
def h() -> Harness:
    harness = Harness(admin_key="admin-secret")
    harness.titles.matches = [
        make_title(),
        make_title(id="693134", kind=TitleKind.MOVIE, title="Dune: Part Two", year=2024),
    ]
    return harness


@pytest.mark.parametrize(
    ("path", "params"), [("/metadata/providers", {}), ("/metadata/search", {"q": "dune"})]
)
def test_metadata_requires_a_key(h: Harness, path: str, params: dict) -> None:
    assert h.client.get(path, params=params).status_code == 401


@pytest.mark.parametrize(
    ("tmdb_key", "configured"), [("env-token-1234567890", True), (None, False)]
)
def test_providers_lists_tmdb_with_its_attribution_and_whether_it_has_a_key(
    tmdb_key: str | None, configured: bool
) -> None:
    harness = Harness(admin_key="admin-secret", tmdb_key=tmdb_key)
    response = harness.client.get("/metadata/providers", headers=KEY)
    assert response.json() == [{**ATTRIBUTION, "configured": configured}]


def test_providers_is_empty_when_charon_knows_none(h: Harness) -> None:
    keys = ProviderKeys(InMemorySettingsStore())
    h.app.state.container.metadata_service = MetadataService([], keys)
    assert h.client.get("/metadata/providers", headers=KEY).json() == []


def test_search_without_a_key_says_how_to_add_one() -> None:
    harness = Harness(admin_key="admin-secret", tmdb_key=None)
    response = harness.client.get("/metadata/search", params={"q": "dune"}, headers=KEY)
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "metadata_not_configured"
    assert "Settings" in error["hint"]
    assert harness.titles.queries == []


def test_search_returns_matches_with_attribution(h: Harness) -> None:
    response = h.client.get("/metadata/search", params={"q": "Kusuriya"}, headers=KEY)
    assert response.status_code == 200
    body = response.json()
    assert body["attribution"] == ATTRIBUTION
    assert body["results"][0] == {
        "provider": "tmdb",
        "id": "220542",
        "kind": "tv",
        "title": "The Apothecary Diaries",
        "original_title": "薬屋のひとりごと",
        "year": 2023,
        "overview": "",
        "url": "https://www.themoviedb.org/tv/220542",
    }
    assert h.titles.queries == ["Kusuriya"]


@pytest.mark.parametrize(("kind", "expected"), [("tv", ["220542"]), ("movie", ["693134"])])
def test_search_filters_by_kind(h: Harness, kind: str, expected: list[str]) -> None:
    params = {"q": "dune", "kind": kind}
    results = h.client.get("/metadata/search", params=params, headers=KEY).json()["results"]
    assert [r["id"] for r in results] == expected


@pytest.mark.parametrize(
    ("params", "code"),
    [
        ({"q": " a "}, "invalid_query"),
        ({}, "invalid_request"),
        ({"q": "x" * 201}, "invalid_request"),
        ({"q": "dune", "kind": "person"}, "invalid_request"),
        ({"q": "dune", "limit": 0}, "invalid_request"),
        ({"q": "dune", "limit": 21}, "invalid_request"),
    ],
)
def test_search_rejects_bad_requests(h: Harness, params: dict, code: str) -> None:
    response = h.client.get("/metadata/search", params=params, headers=KEY)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == code
    assert h.titles.queries == []


def test_search_with_an_unknown_provider_is_404_with_a_hint(h: Harness) -> None:
    response = h.client.get("/metadata/search", params={"q": "x1", "provider": "imdb"}, headers=KEY)
    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "metadata_provider_not_found"
    assert "/metadata/providers" in error["hint"]


@pytest.mark.parametrize(
    ("error", "status", "retry_after_header", "retryable"),
    [
        (RateLimitedError("metadata_rate_limited", "slow down", 2.2), 429, "3", True),
        (RateLimitedError("metadata_rate_limited", "slow down", 0.1), 429, "1", True),
        (RateLimitedError("metadata_rate_limited", "slow down"), 429, None, True),
        (MetadataError("metadata_unavailable", "TMDB is down"), 502, None, True),
        (MetadataError("metadata_auth_failed", "bad token"), 502, None, False),
    ],
)
def test_search_failures_say_whether_to_retry(
    h: Harness, error: Exception, status: int, retry_after_header: str | None, retryable: bool
) -> None:
    h.titles.error = error
    response = h.client.get("/metadata/search", params={"q": "dune"}, headers=KEY)
    assert response.status_code == status
    assert response.headers.get("Retry-After") == retry_after_header
    body = response.json()["error"]
    assert body["retryable"] is retryable
    assert body["hint"]


@pytest.mark.parametrize(
    ("params", "refresh"), [({"q": "dune"}, False), ({"q": "dune", "refresh": "true"}, True)]
)
def test_search_asks_again_only_when_told_to(h: Harness, params: dict, refresh: bool) -> None:
    assert h.client.get("/metadata/search", params=params, headers=KEY).status_code == 200
    assert h.titles.refreshes == [refresh]


@pytest.mark.parametrize(
    ("stale", "age", "expected"), [(False, 0.0, (False, 0)), (True, 3600.4, (True, 3600))]
)
def test_search_says_when_an_older_answer_stands_in(
    h: Harness, stale: bool, age: float, expected: tuple
) -> None:
    h.titles.stale, h.titles.age_seconds = stale, age
    body = h.client.get("/metadata/search", params={"q": "dune"}, headers=KEY).json()
    assert (body["stale"], body["age_seconds"]) == expected


def client_key(h: Harness) -> dict[str, str]:
    issued = h.client.post("/api-keys", json={"name": "phone", "role": "client"}, headers=KEY)
    return {"X-API-Key": issued.json()["key"]}


@pytest.mark.parametrize(("who", "status", "cleared"), [("admin", 204, 1), ("client", 403, 0)])
def test_only_admins_clear_the_cache(h: Harness, who: str, status: int, cleared: int) -> None:
    headers = KEY if who == "admin" else client_key(h)
    assert h.client.delete("/metadata/cache", headers=headers).status_code == status
    assert h.titles.cleared == cleared


def test_the_cache_can_be_cleared_with_auth_off() -> None:
    harness = Harness()
    assert harness.client.delete("/metadata/cache").status_code == 204
    assert harness.titles.cleared == 1


KEY_PATH = "/metadata/providers/tmdb/key"
SAVED = "eyJhbGciOiJIUzI1NiJ9.eyJhdWQiOiJjaGFyb24ifQ.c2lnbmF0dXJlLTQzMjE"


def test_key_status_says_where_the_key_comes_from_but_never_what_it_is(h: Harness) -> None:
    response = h.client.get(KEY_PATH, headers=KEY)
    assert response.json() == {
        "provider": "tmdb",
        "configured": True,
        "source": "environment",
        "hint": "0001",
    }


def test_a_saved_key_takes_the_environments_place_until_it_is_removed(h: Harness) -> None:
    saved = h.client.put(KEY_PATH, json={"key": SAVED}, headers=KEY)
    assert saved.status_code == 200
    assert saved.json() == {
        "provider": "tmdb",
        "configured": True,
        "source": "settings",
        "hint": SAVED[-4:],
    }
    assert SAVED not in saved.text
    assert SAVED not in h.client.get(KEY_PATH, headers=KEY).text
    assert h.metadata_keys.get("tmdb") == SAVED

    removed = h.client.delete(KEY_PATH, headers=KEY).json()
    assert (removed["configured"], removed["source"]) == (True, "environment")


def test_removing_the_last_key_stops_lookups_and_forgets_tmdbs_answers() -> None:
    harness = Harness(admin_key="admin-secret", tmdb_key=None)
    harness.client.put(KEY_PATH, json={"key": SAVED}, headers=KEY)
    assert harness.client.delete(KEY_PATH, headers=KEY).json()["configured"] is False
    assert harness.titles.cleared == 1
    search = harness.client.get("/metadata/search", params={"q": "dune"}, headers=KEY)
    assert search.status_code == 409


@pytest.mark.parametrize(
    ("key", "code"),
    [
        ("", "invalid_request"),
        ("   ", "invalid_metadata_key"),
        ("0123456789abcdef0123456789abcdef", "metadata_key_wrong_kind"),
    ],
    ids=["empty", "blank", "short-api-key"],
)
def test_keys_that_cant_be_right_are_refused_with_a_hint(h: Harness, key: str, code: str) -> None:
    response = h.client.put(KEY_PATH, json={"key": key}, headers=KEY)
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == code
    assert error["hint"]
    assert h.metadata_keys.status("tmdb").source == "environment"


@pytest.mark.parametrize(
    ("method", "body"), [("get", None), ("put", {"key": SAVED}), ("delete", None)]
)
def test_only_admins_manage_keys(h: Harness, method: str, body: dict | None) -> None:
    kwargs = {"json": body} if body else {}
    assert getattr(h.client, method)(KEY_PATH, **kwargs).status_code == 401
    response = getattr(h.client, method)(KEY_PATH, headers=client_key(h), **kwargs)
    assert response.status_code == 403


@pytest.mark.parametrize(
    ("method", "body"), [("get", None), ("put", {"key": SAVED}), ("delete", None)]
)
def test_keys_can_be_managed_with_auth_off(method: str, body: dict | None) -> None:
    """With auth off everyone is an admin; key management must still work then."""
    harness = Harness()
    kwargs = {"json": body} if body else {}
    assert getattr(harness.client, method)(KEY_PATH, **kwargs).status_code == 200


@pytest.mark.parametrize("method", ["get", "delete"])
def test_keys_of_unknown_providers_are_404(h: Harness, method: str) -> None:
    response = getattr(h.client, method)("/metadata/providers/imdb/key", headers=KEY)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "metadata_provider_not_found"

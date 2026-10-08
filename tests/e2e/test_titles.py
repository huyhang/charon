"""Title lookup through Charon, against the fake TMDB."""

import secrets
import time
from concurrent.futures import ThreadPoolExecutor

import httpx

from tests.e2e.conftest import Stack

# Long enough for a budget used up by an earlier test to free up again.
BUDGET_WAIT_SECONDS = 15.0


def search_within_budget(stack: Stack, params: dict) -> httpx.Response:
    """Searches, waiting as Charon asks (Retry-After) while its TMDB budget is used up."""
    deadline = time.monotonic() + BUDGET_WAIT_SECONDS
    response = stack.charon.get("/metadata/search", params=params)
    while response.status_code == 429 and time.monotonic() < deadline:
        time.sleep(float(response.headers["Retry-After"]))
        response = stack.charon.get("/metadata/search", params=params)
    return response


def test_providers_credit_tmdb(stack: Stack) -> None:
    [tmdb] = stack.charon.get("/metadata/providers").json()
    assert tmdb["id"] == "tmdb"
    assert "not endorsed, certified, or otherwise approved by TMDB" in tmdb["notice"]


def test_looks_up_a_canonical_title(stack: Stack) -> None:
    response = stack.charon.get("/metadata/search", params={"q": "Kusuriya no Hitorigoto"})
    assert response.status_code == 200
    body = response.json()
    assert body["attribution"]["name"] == "TMDB"
    # The fake also lists a person for this search; Charon leaves people out.
    assert [(r["title"], r["year"], r["kind"]) for r in body["results"]] == [
        ("The Apothecary Diaries", 2023, "tv")
    ]


def test_a_burst_of_searches_never_sends_tmdb_more_than_40_in_10_seconds(stack: Stack) -> None:
    run = secrets.token_hex(4)  # distinct searches, so the cache can't answer them
    queries = [f"burst {run} {n}" for n in range(70)]
    with ThreadPoolExecutor(max_workers=24) as pool:
        responses = list(
            pool.map(lambda q: stack.charon.get("/metadata/search", params={"q": q}), queries)
        )
    statuses = [r.status_code for r in responses]
    assert set(statuses) == {200, 429}
    refused = next(r for r in responses if r.status_code == 429)
    assert refused.json()["error"]["code"] == "metadata_rate_limited"
    assert refused.headers["Retry-After"]
    assert stack.fake.get("/_control/tmdb").json()["busiest_window"] <= 40


def test_a_token_saved_in_settings_is_used_until_it_is_removed(stack: Stack) -> None:
    key_path = "/metadata/providers/tmdb/key"
    query = {"q": f"Frieren {secrets.token_hex(4)}"}  # new each run, so nothing is cached
    saved = stack.charon.put(key_path, json={"key": "a-token-tmdb-will-refuse"})
    try:
        assert saved.json()["source"] == "settings"
        refused = search_within_budget(stack, query)
        assert refused.status_code == 502
        assert refused.json()["error"]["code"] == "metadata_auth_failed"
    finally:
        removed = stack.charon.delete(key_path).json()
    assert (removed["configured"], removed["source"]) == (True, "environment")
    assert search_within_budget(stack, query).status_code == 200

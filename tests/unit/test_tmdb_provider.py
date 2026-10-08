from collections.abc import Callable

import httpx
import pytest

from charon.adapters.tmdb.provider import TmdbProvider, TokenSource, build_http_client, check_token
from charon.errors import ConflictError, InvalidInputError, MetadataError, RateLimitedError

Handler = Callable[[httpx.Request], httpx.Response]

SHOW = {
    "id": 220542,
    "media_type": "tv",
    "name": "The Apothecary Diaries",
    "original_name": "薬屋のひとりごと",
    "first_air_date": "2023-10-22",
}


def provider(
    handler: Handler, language: str = "en-US", token: TokenSource = lambda: "s3cret-token"
) -> TmdbProvider:
    http = build_http_client("https://tmdb.test/base", 5.0, httpx.MockTransport(handler))
    return TmdbProvider(http, token, language)


def answer(status: int = 200, **kwargs: object) -> Handler:
    return lambda request: httpx.Response(status, **kwargs)  # type: ignore[arg-type]


def test_search_sends_one_multi_search_with_the_token_in_a_header() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"page": 1, "results": [SHOW]})

    matches = provider(handler, "fr-FR").search("Kusuriya no Hitorigoto")

    assert [m.title for m in matches] == ["The Apothecary Diaries"]
    [request] = seen
    assert request.url.path == "/base/3/search/multi"
    assert dict(request.url.params) == {
        "query": "Kusuriya no Hitorigoto",
        "language": "fr-FR",
        "include_adult": "false",
        "page": "1",
    }
    assert request.headers["Authorization"] == "Bearer s3cret-token"
    assert "s3cret-token" not in str(request.url)


@pytest.mark.parametrize(
    ("status", "headers", "error", "code", "retry_after"),
    [
        (429, {"Retry-After": "3"}, RateLimitedError, "metadata_rate_limited", 3.0),
        (429, {}, RateLimitedError, "metadata_rate_limited", None),
        (401, {}, MetadataError, "metadata_auth_failed", None),
        (404, {}, MetadataError, "metadata_error", None),
        (500, {}, MetadataError, "metadata_unavailable", None),
        (503, {}, MetadataError, "metadata_unavailable", None),
    ],
)
def test_error_statuses_become_charon_errors(
    status: int, headers: dict, error: type, code: str, retry_after: float | None
) -> None:
    with pytest.raises(error) as caught:
        provider(answer(status, headers=headers, json={})).search("dune")
    assert caught.value.code == code
    assert getattr(caught.value, "retry_after", None) == retry_after


@pytest.mark.parametrize(
    ("raised", "message"),
    [
        (httpx.ConnectTimeout("slow"), "TMDB took too long to answer"),
        (httpx.ConnectError("refused"), "couldn't reach TMDB (ConnectError)"),
    ],
)
def test_network_failures_are_unavailable(raised: Exception, message: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise raised

    with pytest.raises(MetadataError) as caught:
        provider(handler).search("dune")
    assert (caught.value.code, caught.value.message) == ("metadata_unavailable", message)


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, content=b"<html>not json</html>"),
        httpx.Response(200, json={"status_message": "no results here"}),
    ],
)
def test_unreadable_answers_are_metadata_errors(response: httpx.Response) -> None:
    with pytest.raises(MetadataError) as caught:
        provider(lambda request: response).search("dune")
    assert caught.value.code == "metadata_error"


def test_the_current_token_is_sent_with_every_request() -> None:
    tokens = iter(["first-token", "replaced-token"])
    current = {"token": next(tokens)}
    sent: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request.headers["Authorization"])
        return httpx.Response(200, json={"results": []})

    tmdb = provider(handler, token=lambda: current["token"])
    tmdb.search("dune")
    current["token"] = next(tokens)  # e.g. an admin saved a new token meanwhile
    tmdb.search("dune")
    assert sent == ["Bearer first-token", "Bearer replaced-token"]


@pytest.mark.parametrize("token", [None, ""])
def test_without_a_token_nothing_is_sent(token: str | None) -> None:
    sent: list[httpx.Request] = []
    tmdb = provider(
        lambda request: sent.append(request) or httpx.Response(200), token=lambda: token
    )
    with pytest.raises(ConflictError) as caught:
        tmdb.search("dune")
    assert caught.value.code == "metadata_not_configured"
    assert sent == []


@pytest.mark.parametrize(
    ("token", "code"),
    [
        ("eyJhbGciOiJIUzI1NiJ9.eyJhdWQiOiJ4In0.c2lnbmF0dXJl", None),
        ("dev-tmdb-token", None),
        ("0123456789abcdef0123456789ABCDEF", "metadata_key_wrong_kind"),
        ("eyJhbGci OiJIUzI1NiJ9", "invalid_metadata_key"),
    ],
    ids=["read-access-token", "other-shape", "short-api-key", "has-a-space"],
)
def test_check_token_refuses_what_cant_be_a_read_access_token(token: str, code: str | None) -> None:
    if code is None:
        check_token(token)
    else:
        with pytest.raises(InvalidInputError) as caught:
            check_token(token)
        assert caught.value.code == code

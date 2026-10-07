import httpx
import pytest

from charon.adapters.http_feed_fetcher import HttpFeedFetcher, build_http_client
from charon.errors import FeedError

URL = "https://tracker.example/rss?passkey=s3cret"


def fetcher(handler, max_bytes: int = 1000) -> HttpFeedFetcher:
    return HttpFeedFetcher(httpx.Client(transport=httpx.MockTransport(handler)), max_bytes)


def test_fetch_returns_the_body_and_cache_validators() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200, content=b"<rss/>", headers={"ETag": '"v2"', "Last-Modified": "Wed"}
        )

    fetched = fetcher(handler).fetch(URL, etag='"v1"', last_modified="Tue")
    assert (fetched.body, fetched.etag, fetched.last_modified) == (b"<rss/>", '"v2"', "Wed")
    assert seen[0].headers["If-None-Match"] == '"v1"'
    assert seen[0].headers["If-Modified-Since"] == "Tue"


def test_fetch_without_validators_sends_no_conditional_headers() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=b"x")

    fetcher(handler).fetch(URL)
    assert "If-None-Match" not in seen[0].headers
    assert "If-Modified-Since" not in seen[0].headers


def test_not_modified_has_no_body() -> None:
    fetched = fetcher(lambda r: httpx.Response(304, headers={"ETag": '"v1"'})).fetch(URL, '"v1"')
    assert (fetched.body, fetched.etag) == (None, '"v1"')


def raise_(error: Exception):
    def handler(request: httpx.Request) -> httpx.Response:
        raise error

    return handler


@pytest.mark.parametrize(
    ("handler", "code", "message"),
    [
        (
            lambda r: httpx.Response(403),
            "feed_http_error",
            "tracker.example answered 403 Forbidden",
        ),
        (lambda r: httpx.Response(200, content=b"x" * 1001), "feed_too_large", "over 0 MB"),
        (raise_(httpx.ConnectTimeout("slow")), "feed_unreachable", "took too long"),
        (
            raise_(httpx.ConnectError(f"refused {URL}")),
            "feed_unreachable",
            "couldn't reach tracker.example (ConnectError)",
        ),
        (raise_(httpx.UnsupportedProtocol("ftp")), "feed_invalid_url", "isn't a usable"),
    ],
    ids=["http-error", "too-large", "timeout", "connect", "protocol"],
)
def test_failures_name_only_the_host(handler, code: str, message: str) -> None:
    with pytest.raises(FeedError) as exc_info:
        fetcher(handler).fetch(URL)
    assert exc_info.value.code == code
    assert message in exc_info.value.message
    assert "s3cret" not in exc_info.value.message


def test_a_host_that_cant_be_encoded_is_an_invalid_address() -> None:
    with pytest.raises(FeedError) as exc_info:
        fetcher(lambda request: httpx.Response(200)).fetch("http://xn--zz.example/rss")
    assert exc_info.value.code == "feed_invalid_url"


def test_build_http_client_follows_redirects_and_identifies_itself() -> None:
    client = build_http_client(5)
    assert client.follow_redirects is True
    assert client.headers["User-Agent"].startswith("Charon")
    client.close()

"""Fetches feeds over HTTP(S) with a size cap and cache validators."""

import httpx

from charon.domain.feeds import feed_host
from charon.errors import FeedError
from charon.ports.feeds import FetchedFeed

USER_AGENT = "Charon (feed reader)"


class HttpFeedFetcher:
    def __init__(self, http: httpx.Client, max_bytes: int) -> None:
        self._http = http
        self._max_bytes = max_bytes

    def fetch(
        self, url: str, etag: str | None = None, last_modified: str | None = None
    ) -> FetchedFeed:
        host = feed_host(url)
        try:
            with self._http.stream("GET", url, headers=_conditional(etag, last_modified)) as r:
                return self._read(r, host)
        except httpx.TimeoutException as exc:
            raise FeedError("feed_unreachable", f"{host} took too long to answer") from exc
        # ValueError covers hosts httpx can't encode (UnicodeError, idna.IDNAError).
        except (httpx.InvalidURL, httpx.UnsupportedProtocol, ValueError) as exc:
            raise FeedError("feed_invalid_url", "the address isn't a usable http(s) URL") from exc
        except httpx.HTTPError as exc:
            reason = type(exc).__name__
            raise FeedError("feed_unreachable", f"couldn't reach {host} ({reason})") from exc

    def _read(self, response: httpx.Response, host: str) -> FetchedFeed:
        if response.status_code == 304:
            return FetchedFeed(body=None, **_validators(response))
        if response.status_code >= 400:
            status = f"{response.status_code} {response.reason_phrase}".strip()
            raise FeedError("feed_http_error", f"{host} answered {status}")
        return FetchedFeed(body=self._body(response, host), **_validators(response))

    def _body(self, response: httpx.Response, host: str) -> bytes:
        chunks: list[bytes] = []
        size = 0
        for chunk in response.iter_bytes():
            size += len(chunk)
            if size > self._max_bytes:
                limit = self._max_bytes // (1024 * 1024)
                raise FeedError("feed_too_large", f"the feed from {host} is over {limit} MB")
            chunks.append(chunk)
        return b"".join(chunks)


def build_http_client(timeout_seconds: float) -> httpx.Client:
    return httpx.Client(
        timeout=timeout_seconds,
        follow_redirects=True,
        max_redirects=5,
        headers={"User-Agent": USER_AGENT},
    )


def _conditional(etag: str | None, last_modified: str | None) -> dict[str, str]:
    headers = {}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified
    return headers


def _validators(response: httpx.Response) -> dict[str, str | None]:
    return {
        "etag": response.headers.get("ETag"),
        "last_modified": response.headers.get("Last-Modified"),
    }

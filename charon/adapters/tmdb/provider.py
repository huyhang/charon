"""Searches The Movie Database (TMDB) over its v3 HTTP API."""

import re
from collections.abc import Callable
from typing import Any

import httpx

from charon.adapters.tmdb.mapping import retry_after, to_matches
from charon.domain.titles import TitleMatch
from charon.errors import ConflictError, InvalidInputError, MetadataError, RateLimitedError

# The current API Read Access Token, or None if none is set. Read on every request, so a token
# changed while Charon runs is used at once.
TokenSource = Callable[[], str | None]

USER_AGENT = "Charon (title lookup)"
# One request finds movies and shows alike; only its first page (up to 20 results) is read,
# so every search costs exactly one request.
SEARCH_PATH = "/3/search/multi"
# TMDB's other credential, the short "API Key", only works as a URL parameter, where it would
# end up in logs. Charon only takes the Read Access Token, which goes in a header.
_API_KEY = re.compile(r"[0-9a-fA-F]{32}")


class TmdbProvider:
    def __init__(self, http: httpx.Client, token: TokenSource, language: str = "en-US") -> None:
        self._http = http
        self._token = token
        self._language = language

    def search(self, query: str) -> list[TitleMatch]:
        payload = self._get(
            SEARCH_PATH,
            {"query": query, "language": self._language, "include_adult": "false", "page": "1"},
        )
        try:
            return to_matches(payload)
        except ValueError as exc:
            raise _unreadable() from exc

    def _get(self, path: str, params: dict[str, str]) -> Any:
        response = self._send(path, params)
        check_status(response)
        try:
            return response.json()
        except ValueError as exc:
            raise _unreadable() from exc

    def _send(self, path: str, params: dict[str, str]) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self._current_token()}"}
        try:
            return self._http.get(path, params=params, headers=headers)
        except httpx.TimeoutException as exc:
            raise MetadataError("metadata_unavailable", "TMDB took too long to answer") from exc
        except httpx.HTTPError as exc:
            reason = type(exc).__name__
            raise MetadataError("metadata_unavailable", f"couldn't reach TMDB ({reason})") from exc

    def _current_token(self) -> str:
        token = self._token()
        if not token:
            raise ConflictError("metadata_not_configured", "no TMDB token is set")
        return token


def check_token(token: str) -> None:
    """Raises InvalidInputError for something that can't be an API Read Access Token."""
    if _API_KEY.fullmatch(token):
        raise InvalidInputError(
            "metadata_key_wrong_kind",
            "that is TMDB's short API Key; paste the API Read Access Token instead",
        )
    if any(char.isspace() for char in token):
        raise InvalidInputError("invalid_metadata_key", "a TMDB token has no spaces in it")


def check_status(response: httpx.Response) -> None:
    """Raises the Charon error for a TMDB error status; does nothing for a success."""
    status = response.status_code
    if status < 400:
        return
    if status == 429:
        wait = retry_after(response.headers.get("Retry-After"))
        raise RateLimitedError("metadata_rate_limited", "TMDB asked Charon to slow down", wait)
    if status == 401:
        raise MetadataError("metadata_auth_failed", "TMDB rejected Charon's token")
    code = "metadata_unavailable" if status >= 500 else "metadata_error"
    raise MetadataError(code, f"TMDB answered {status} {response.reason_phrase}".strip())


def build_http_client(
    base_url: str, timeout_seconds: float, transport: httpx.BaseTransport | None = None
) -> httpx.Client:
    """The token isn't part of the client: it may change while Charon runs (see TokenSource)."""
    return httpx.Client(
        base_url=base_url,
        timeout=timeout_seconds,
        transport=transport,
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
    )


def _unreadable() -> MetadataError:
    return MetadataError("metadata_error", "TMDB answered with something Charon couldn't read")

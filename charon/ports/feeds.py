"""Port for fetching feeds over the network."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class FetchedFeed:
    # None when the server says the feed hasn't changed since `etag` / `last_modified`.
    body: bytes | None
    etag: str | None = None
    last_modified: str | None = None


class FeedFetcher(Protocol):
    def fetch(
        self, url: str, etag: str | None = None, last_modified: str | None = None
    ) -> FetchedFeed:
        """Raises charon.errors.FeedError when the feed can't be fetched.

        Error messages name only the host: the rest of the URL may hold a passkey.
        """
        ...

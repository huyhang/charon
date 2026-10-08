"""Port for metadata providers that know canonical titles (TMDB, ...)."""

from typing import Protocol

from charon.domain.titles import Answer, TitleMatch


class MetadataProvider(Protocol):
    def search(self, query: str) -> list[TitleMatch]:
        """Movies and shows matching `query`, best first.

        Raises charon.errors.MetadataError when the provider fails, and
        charon.errors.RateLimitedError when it (or Charon, on its behalf) says to slow down.
        """
        ...


class TitleLookup(Protocol):
    """Answers for queries, however they are got: from a provider, or remembered."""

    def lookup(self, query: str, refresh: bool = False) -> Answer:
        """Matches for `query`; `refresh` asks the provider again even if an answer is fresh.

        Raises as MetadataProvider.search does when there is no answer at all to give.
        """
        ...

    def clear(self) -> None:
        """Forget every remembered answer."""
        ...

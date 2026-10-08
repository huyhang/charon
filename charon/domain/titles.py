"""Canonical titles from metadata providers (e.g. TMDB). Pure data and logic, no I/O."""

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from charon.errors import InvalidInputError

MIN_QUERY_LENGTH = 2
MAX_QUERY_LENGTH = 200


class TitleKind(StrEnum):
    MOVIE = "movie"
    TV = "tv"


class KindFilter(StrEnum):
    ANY = "any"
    MOVIE = "movie"
    TV = "tv"


class TitleMatch(BaseModel):
    """A movie or show a provider knows, under its canonical name."""

    # Frozen, so a remembered answer can be handed out without anyone changing it.
    model_config = ConfigDict(frozen=True)

    provider: str = Field(description="Which provider it came from, e.g. tmdb.")
    id: str = Field(description="The provider's id for it.")
    kind: TitleKind
    title: str = Field(description="The canonical name, in the provider's configured language.")
    original_title: str = Field(description="The name in its original language.")
    year: int | None = Field(description="Release or first-air year, if known.")
    overview: str = ""
    url: str = Field(description="Its page on the provider's site.")


@dataclass(frozen=True)
class Answer:
    """A provider's matches for a query, and how old they are."""

    matches: list[TitleMatch]
    age_seconds: float = 0.0
    # The provider couldn't be asked again just now, so an older answer stands in.
    stale: bool = False


class ProviderInfo(BaseModel):
    """Who a provider is, and how to credit it wherever its data is shown."""

    id: str
    name: str
    url: str
    notice: str = Field(description="The attribution notice the provider requires.")


def normalize_query(query: str) -> str:
    """The query with whitespace collapsed. Raises InvalidInputError if it is too short or long."""
    normalized = " ".join(query.split())
    if len(normalized) < MIN_QUERY_LENGTH:
        raise InvalidInputError(
            "invalid_query", f"search for at least {MIN_QUERY_LENGTH} characters"
        )
    if len(normalized) > MAX_QUERY_LENGTH:
        raise InvalidInputError(
            "invalid_query", f"search for at most {MAX_QUERY_LENGTH} characters"
        )
    return normalized


def of_kind(matches: Iterable[TitleMatch], kind: KindFilter) -> list[TitleMatch]:
    if kind is KindFilter.ANY:
        return list(matches)
    return [match for match in matches if match.kind.value == kind.value]

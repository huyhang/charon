"""Translate TMDB search results into provider-agnostic title matches."""

from typing import Any

from charon.domain.titles import ProviderInfo, TitleKind, TitleMatch

SITE = "https://www.themoviedb.org"

TMDB = ProviderInfo(
    id="tmdb",
    name="TMDB",
    url=SITE,
    # Worded as TMDB's API terms of use require.
    notice=(
        "This product uses TMDB and the TMDB APIs but is not endorsed, certified, "
        "or otherwise approved by TMDB."
    ),
)

# Movies and shows name the same things differently: (title, original title, date).
_FIELDS = {
    TitleKind.MOVIE: ("title", "original_title", "release_date"),
    TitleKind.TV: ("name", "original_name", "first_air_date"),
}


def to_matches(payload: Any) -> list[TitleMatch]:
    """The movies and shows in a search response. Raises ValueError if it has no results."""
    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list):
        raise ValueError("TMDB's answer has no results list")
    return [match for raw in results if (match := to_match(raw)) is not None]


def to_match(raw: Any) -> TitleMatch | None:
    """None for anything but a movie or show: multi search finds people too."""
    kind = _kind(raw)
    if kind is None or raw.get("id") is None:
        return None
    title_key, original_key, date_key = _FIELDS[kind]
    title = raw.get(title_key) or raw.get(original_key)
    if not title:
        return None
    return TitleMatch(
        provider=TMDB.id,
        id=str(raw["id"]),
        kind=kind,
        title=title,
        original_title=raw.get(original_key) or title,
        year=year_of(raw.get(date_key)),
        overview=raw.get("overview") or "",
        url=f"{SITE}/{kind}/{raw['id']}",
    )


def year_of(date: Any) -> int | None:
    """The year of a TMDB date ("2023-10-22"); None if it is missing or blank."""
    if isinstance(date, str) and date[:4].isdigit() and len(date) >= 4:
        return int(date[:4])
    return None


def retry_after(value: str | None) -> float | None:
    """Seconds from a Retry-After header, if it holds a usable number of seconds."""
    try:
        seconds = float(value) if value is not None else None
    except ValueError:
        return None
    return seconds if seconds is not None and 0 <= seconds < float("inf") else None


def _kind(raw: Any) -> TitleKind | None:
    media_type = raw.get("media_type") if isinstance(raw, dict) else None
    return TitleKind(media_type) if media_type in iter(TitleKind) else None

from typing import Any

import pytest

from charon.adapters.tmdb.mapping import retry_after, to_match, to_matches, year_of
from charon.domain.titles import TitleKind, TitleMatch

SHOW = {
    "id": 220542,
    "media_type": "tv",
    "name": "The Apothecary Diaries",
    "original_name": "薬屋のひとりごと",
    "first_air_date": "2023-10-22",
    "overview": "Maomao is sold into service at the palace.",
}
FILM = {
    "id": 693134,
    "media_type": "movie",
    "title": "Dune: Part Two",
    "original_title": "Dune: Part Two",
    "release_date": "2024-02-27",
    "overview": "",
}
PERSON = {"id": 1, "media_type": "person", "name": "Natsu Hyuuga"}


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            SHOW,
            TitleMatch(
                provider="tmdb",
                id="220542",
                kind=TitleKind.TV,
                title="The Apothecary Diaries",
                original_title="薬屋のひとりごと",
                year=2023,
                overview="Maomao is sold into service at the palace.",
                url="https://www.themoviedb.org/tv/220542",
            ),
        ),
        (
            FILM,
            TitleMatch(
                provider="tmdb",
                id="693134",
                kind=TitleKind.MOVIE,
                title="Dune: Part Two",
                original_title="Dune: Part Two",
                year=2024,
                overview="",
                url="https://www.themoviedb.org/movie/693134",
            ),
        ),
    ],
)
def test_to_match_reads_movies_and_shows_by_their_own_field_names(
    raw: dict, expected: TitleMatch
) -> None:
    assert to_match(raw) == expected


@pytest.mark.parametrize(
    ("raw", "field", "expected"),
    [
        ({**SHOW, "name": ""}, "title", "薬屋のひとりごと"),
        ({**SHOW, "original_name": None}, "original_title", "The Apothecary Diaries"),
        ({**SHOW, "first_air_date": ""}, "year", None),
        ({**SHOW, "overview": None}, "overview", ""),
        ({**FILM, "release_date": None}, "year", None),
    ],
)
def test_to_match_fills_gaps(raw: dict, field: str, expected: Any) -> None:
    match = to_match(raw)
    assert match is not None
    assert getattr(match, field) == expected


@pytest.mark.parametrize(
    "raw",
    [
        PERSON,
        {**SHOW, "media_type": "collection"},
        {k: v for k, v in SHOW.items() if k != "media_type"},
        {k: v for k, v in SHOW.items() if k != "id"},
        {**SHOW, "name": "", "original_name": ""},
        "not an object",
        None,
    ],
)
def test_to_match_skips_anything_but_a_usable_movie_or_show(raw: Any) -> None:
    assert to_match(raw) is None


def test_to_matches_keeps_order_and_drops_people() -> None:
    matches = to_matches({"page": 1, "results": [SHOW, PERSON, FILM]})
    assert [m.id for m in matches] == ["220542", "693134"]


@pytest.mark.parametrize("payload", [{}, {"results": None}, [], "nope", None])
def test_to_matches_refuses_an_answer_without_results(payload: Any) -> None:
    with pytest.raises(ValueError):
        to_matches(payload)


@pytest.mark.parametrize(
    ("date", "expected"),
    [("2023-10-22", 2023), ("1999", 1999), ("", None), (None, None), ("soon", None), (2023, None)],
)
def test_year_of(date: Any, expected: int | None) -> None:
    assert year_of(date) == expected


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("5", 5.0),
        ("0.5", 0.5),
        ("0", 0.0),
        (None, None),
        ("", None),
        ("-1", None),
        ("inf", None),
        ("nan", None),
        ("Wed, 21 Oct 2015 07:28:00 GMT", None),
    ],
)
def test_retry_after(header: str | None, expected: float | None) -> None:
    assert retry_after(header) == expected

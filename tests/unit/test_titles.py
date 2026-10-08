import pytest

from charon.domain.titles import KindFilter, TitleKind, normalize_query, of_kind
from charon.errors import InvalidInputError
from tests.unit.fakes import make_title

SHOW = make_title(id="1", kind=TitleKind.TV)
FILM = make_title(id="2", kind=TitleKind.MOVIE)


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("Kusuriya no Hitorigoto", "Kusuriya no Hitorigoto"),
        ("  Kusuriya \t no\nHitorigoto ", "Kusuriya no Hitorigoto"),
        ("ab", "ab"),
        ("x" * 200, "x" * 200),
    ],
)
def test_normalize_query_collapses_whitespace(query: str, expected: str) -> None:
    assert normalize_query(query) == expected


@pytest.mark.parametrize("query", ["", "   ", "a", " a ", "x" * 201])
def test_normalize_query_refuses_too_short_or_long(query: str) -> None:
    with pytest.raises(InvalidInputError) as caught:
        normalize_query(query)
    assert caught.value.code == "invalid_query"


@pytest.mark.parametrize(
    ("kind", "expected"),
    [(KindFilter.ANY, [SHOW, FILM]), (KindFilter.TV, [SHOW]), (KindFilter.MOVIE, [FILM])],
)
def test_of_kind_keeps_the_wanted_kind_in_order(kind: KindFilter, expected: list) -> None:
    assert of_kind([SHOW, FILM], kind) == expected

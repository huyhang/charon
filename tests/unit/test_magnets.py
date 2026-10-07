import pytest

from charon.domain.magnets import (
    display_name,
    exact_length,
    info_hash,
    is_magnet,
    normalize_magnet,
)

HEX = "c12fe1c06bba254a9dc9f519b335aa7c1367a88a"
BASE32 = "YEX6DQDLXISUVHOJ6UM3GNNKPQJWPKEK"


@pytest.mark.parametrize(
    ("magnet", "expected"),
    [
        (f"magnet:?xt=urn:btih:{HEX}", HEX),
        (f"magnet:?xt=urn:btih:{HEX.upper()}&dn=x", HEX),
        (f"magnet:?xt=urn:btih:{BASE32}", HEX),
        (f"magnet:?xt=urn:btih:{BASE32.lower()}", HEX),
        (f"MAGNET:?dn=x&xt=URN:BTIH:{HEX}", HEX),
        (f"magnet:?xt=urn:btmh:1220abc&xt=urn:btih:{HEX}", HEX),
        ("magnet:?xt=urn:btih:abc", None),
        ("magnet:?xt=urn:btih:" + "1" * 32, None),
        ("magnet:?xt=urn:btih:" + "g" * 40, None),
        ("magnet:?dn=no-hash", None),
        (f"http://example.com/?xt=urn:btih:{HEX}", None),
    ],
    ids=[
        "hex",
        "upper-hex",
        "base32",
        "lower-base32",
        "case-insensitive-scheme",
        "second-xt",
        "too-short",
        "bad-base32",
        "not-hex",
        "no-xt",
        "not-a-magnet",
    ],
)
def test_info_hash(magnet: str, expected: str | None) -> None:
    assert info_hash(magnet) == expected


@pytest.mark.parametrize(
    ("magnet", "expected"),
    [
        ("magnet:?xt=urn:btih:x&dn=Some.Show.S01E01.mkv", "Some.Show.S01E01.mkv"),
        ("magnet:?dn=%5BGroup%5D%20Show%20-%2001", "[Group] Show - 01"),
        ("magnet:?dn=A+B", "A B"),
        ("magnet:?dn=%20%20", None),
        ("magnet:?xt=urn:btih:x", None),
        ("not a magnet", None),
    ],
)
def test_display_name(magnet: str, expected: str | None) -> None:
    assert display_name(magnet) == expected


@pytest.mark.parametrize(
    ("magnet", "expected"),
    [
        ("magnet:?xl=1234", 1234),
        ("magnet:?xl=big", None),
        ("magnet:?dn=x", None),
        ("magnet:?xl=²", None),
    ],
)
def test_exact_length(magnet: str, expected: int | None) -> None:
    assert exact_length(magnet) == expected


@pytest.mark.parametrize(
    ("text", "expected"), [("magnet:?x", True), ("Magnet:?x", True), ("magnet:x", False)]
)
def test_is_magnet(text: str, expected: bool) -> None:
    assert is_magnet(text) is expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [("MAGNET:?xt=urn:btih:AB", "magnet:?xt=urn:btih:AB"), ("magnet:?x", "magnet:?x"), ("x", "x")],
    ids=["upper-case-scheme", "already-normal", "not-a-magnet"],
)
def test_normalize_magnet(text: str, expected: str) -> None:
    assert normalize_magnet(text) == expected

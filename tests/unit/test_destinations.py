from pathlib import PurePosixPath

import pytest

from charon.domain.destinations import DestinationPolicy, is_within, normalize

POLICY = DestinationPolicy.of(["/media", "/video/tv"], ["/data"])


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("/media/tv", "/media/tv"),
        ("/media/tv/", "/media/tv"),
        ("/media//tv", "/media/tv"),
        ("/media/./tv", "/media/tv"),
        ("/media/../data", "/data"),
        ("/media/tv/../../../data", "/data"),
    ],
)
def test_normalize(raw: str, expected: str) -> None:
    assert normalize(raw) == PurePosixPath(expected)


@pytest.mark.parametrize(
    ("path", "base", "expected"),
    [
        ("/media", "/media", True),
        ("/media/tv", "/media", True),
        ("/mediaX", "/media", False),
        ("/med", "/media", False),
        ("/", "/media", False),
    ],
)
def test_is_within(path: str, base: str, expected: bool) -> None:
    assert is_within(PurePosixPath(path), PurePosixPath(base)) is expected


@pytest.mark.parametrize(
    ("destination", "allowed"),
    [
        ("/media", True),
        ("/media/tv/season 1", True),
        ("/video/tv", True),
        ("/video", False),
        ("/media-other", False),
        ("/media/../data", False),
        ("/media/../etc", False),
        ("/data", False),
        ("/tmp", False),
    ],
)
def test_violation(destination: str, allowed: bool) -> None:
    assert (POLICY.violation(destination) is None) is allowed


@pytest.mark.parametrize("destination", ["/data", "/data/sub", "/data/../data/x"])
def test_protected_beats_broad_root(destination: str) -> None:
    policy = DestinationPolicy.of(["/"], ["/data"])
    assert "protected" in policy.violation(destination)


def test_no_roots_allows_nothing() -> None:
    assert "CHARON_RULE_ROOTS" in DestinationPolicy.of([]).violation("/media")

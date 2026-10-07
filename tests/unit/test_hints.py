import pytest

from charon.hints import HINTS, RETRYABLE, hint_for, is_retryable


@pytest.mark.parametrize(
    ("code", "has_hint", "retryable"),
    [
        ("destination_exists", True, False),
        ("downloader_unreachable", True, True),
        ("feed_unreachable", True, True),
        ("rule_changed", True, False),
        ("no_such_code", False, False),
    ],
)
def test_hint_and_retryable(code: str, has_hint: bool, retryable: bool) -> None:
    assert (hint_for(code) is not None) is has_hint
    assert is_retryable(code) is retryable


def test_every_retryable_code_has_a_hint() -> None:
    assert RETRYABLE <= HINTS.keys()

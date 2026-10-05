import pytest
from pydantic import ValidationError

from charon.domain.models import RenameStep, RuleSpec


def _step(find: str, replace: str = "", op: str = "regex_replace") -> dict:
    return {"steps": [{"op": op, "find": find, "replace": replace}]}


# The location matters: the UI shows each error next to the field it names.
@pytest.mark.parametrize(
    ("overrides", "loc"),
    [
        ({"destination": "relative/path"}, ("destination",)),
        ({"match_type": "regex", "pattern": "("}, ("pattern",)),
        ({"pattern": ""}, ("pattern",)),
        ({"name": ""}, ("name",)),
        (_step("["), ("steps", 0, "find")),
        (_step("a", r"\2"), ("steps", 0, "replace")),
        (_step("a", r"\q"), ("steps", 0, "replace")),
        (_step(r"(?P<n>a)", r"\g<nope>"), ("steps", 0, "replace")),
        (_step("", "x", op="replace"), ("steps", 0, "find")),
    ],
)
def test_rule_spec_rejects_invalid_input_at_the_field(overrides: dict, loc: tuple) -> None:
    fields = {"name": "r", "pattern": "*", "destination": "/library", **overrides}
    with pytest.raises(ValidationError) as exc_info:
        RuleSpec.model_validate(fields)
    assert [error["loc"] for error in exc_info.value.errors()] == [loc]


def _error_locs(fields: dict) -> list[tuple]:
    try:
        RuleSpec.model_validate(fields)
    except ValidationError as exc:
        return [error["loc"] for error in exc.errors()]
    return []


@pytest.mark.parametrize(
    ("overrides", "locs"),
    [
        ({"match_type": "glob", "pattern": "("}, []),
        (_step("[", r"\9", op="replace"), []),
        # An invalid find is reported once, not again for the replacement.
        (_step("[", r"\1"), [("steps", 0, "find")]),
    ],
    ids=["glob-is-not-a-regex", "plain-replace-is-literal", "find-error-only"],
)
def test_regex_checks_apply_only_to_regex_fields(overrides: dict, locs: list) -> None:
    fields = {"name": "r", "pattern": "*", "destination": "/library", **overrides}
    assert _error_locs(fields) == locs


@pytest.mark.parametrize(
    "step",
    [
        {"op": "replace", "find": "XYZ", "replace": "ABC"},
        {"op": "regex_replace", "find": r"(\d+)", "replace": r"\1"},
        {"op": "regex_replace", "find": r"(?P<n>\d+)", "replace": r"\g<n>"},
        {"op": "regex_replace", "find": r"\p{L}++", "replace": "x"},
        # Can never match, so its replacement can never run or fail.
        {"op": "regex_replace", "find": "(?!)", "replace": r"\9"},
    ],
)
def test_rename_step_accepts_valid_input(step: dict) -> None:
    assert RenameStep.model_validate(step).find == step["find"]

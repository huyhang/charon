import pytest
from pydantic import ValidationError

from charon.domain.models import RenameStep, RuleSpec


@pytest.mark.parametrize(
    "overrides",
    [
        {"destination": "relative/path"},
        {"match_type": "regex", "pattern": "("},
        {"pattern": ""},
        {"name": ""},
        {"steps": [{"op": "regex_replace", "find": "[", "replace": ""}]},
        {"steps": [{"op": "regex_replace", "find": "a", "replace": r"\2"}]},
        {"steps": [{"op": "regex_replace", "find": "a", "replace": r"\q"}]},
        {"steps": [{"op": "regex_replace", "find": r"(?P<n>a)", "replace": r"\g<nope>"}]},
        {"steps": [{"op": "replace", "find": "", "replace": "x"}]},
    ],
)
def test_rule_spec_rejects_invalid_input(overrides: dict) -> None:
    fields = {"name": "r", "pattern": "*", "destination": "/library", **overrides}
    with pytest.raises(ValidationError):
        RuleSpec.model_validate(fields)


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

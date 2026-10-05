import json
from pathlib import Path

import pytest

from charon.openapi import main, render

SPEC = Path(__file__).resolve().parents[2] / "docs" / "openapi.json"


def test_committed_openapi_spec_is_current() -> None:
    assert SPEC.read_text() == render(), "API changed: run `make openapi` and commit the result"


def test_every_operation_has_a_camel_case_id() -> None:
    spec = json.loads(render())
    ids = [op["operationId"] for ops in spec["paths"].values() for op in ops.values()]
    assert len(ids) == len(set(ids))
    assert all("_" not in i and i[0].islower() for i in ids)


@pytest.mark.parametrize("argv", [[], ["a.json", "b.json"]], ids=["none", "two"])
def test_export_needs_exactly_one_output_path(argv: list[str]) -> None:
    with pytest.raises(SystemExit, match="usage"):
        main(argv)


def test_export_writes_the_spec_creating_folders(tmp_path) -> None:
    output = tmp_path / "nested" / "openapi.json"
    main([str(output)])
    assert output.read_text() == render()

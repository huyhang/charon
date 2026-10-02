import threading
import time
from datetime import timedelta
from pathlib import PurePosixPath

import pytest

from charon.domain import rename
from charon.domain.models import MatchType, RenameOp, RenameStep
from charon.domain.rename import (
    RegexTimeoutError,
    apply_step,
    apply_steps,
    is_safe_name,
    matches,
    select_rule,
    target_path,
)
from tests.unit.fakes import T0, make_rule

REPLACE = RenameOp.REPLACE
REGEX = RenameOp.REGEX_REPLACE
LATER = T0 + timedelta(minutes=1)


@pytest.mark.parametrize(
    ("name", "op", "find", "replace", "expected"),
    [
        ("Show.XYZ.mkv", REPLACE, "XYZ", "ABC", "Show.ABC.mkv"),
        ("XYZ.XYZ", REPLACE, "XYZ", "ABC", "ABC.ABC"),
        ("Show.mkv", REPLACE, "XYZ", "ABC", "Show.mkv"),
        ("Show.1080p.mkv", REPLACE, ".1080p", "", "Show.mkv"),
        ("Show.S01E02.mkv", REGEX, r"S(\d+)E(\d+)", r"\1x\2", "Show.01x02.mkv"),
        ("a  b   c", REGEX, r"\s+", " ", "a b c"),
    ],
)
def test_apply_step(name: str, op: RenameOp, find: str, replace: str, expected: str) -> None:
    assert apply_step(name, RenameStep(op=op, find=find, replace=replace)) == expected


@pytest.mark.parametrize(
    ("steps", "expected"),
    [
        ([], "Show.XYZ.1080p.mkv"),
        ([("XYZ", "ABC")], "Show.ABC.1080p.mkv"),
        ([("XYZ", "ABC"), ("ABC", "DEF")], "Show.DEF.1080p.mkv"),
        ([("ABC", "DEF"), ("XYZ", "ABC")], "Show.ABC.1080p.mkv"),
    ],
)
def test_apply_steps_runs_in_order(steps: list[tuple[str, str]], expected: str) -> None:
    rename_steps = [RenameStep(op=REPLACE, find=f, replace=r) for f, r in steps]
    assert apply_steps("Show.XYZ.1080p.mkv", rename_steps) == expected


@pytest.mark.parametrize(
    ("match_type", "pattern", "name", "expected"),
    [
        (MatchType.GLOB, "*.mkv", "Show.mkv", True),
        (MatchType.GLOB, "*.mkv", "Show.mp4", False),
        (MatchType.GLOB, "Show.*", "show.mkv", False),
        (MatchType.REGEX, r"S\d{2}E\d{2}", "Show.S01E02.mkv", True),
        (MatchType.REGEX, r"^Show", "My.Show", False),
        (MatchType.REGEX, r"(?i)^show", "SHOW.mkv", True),
        (MatchType.REGEX, r"^\w+\.2001", "Amélie.2001.mkv", True),
        (MatchType.REGEX, r"^\w+\.mkv$", "千と千尋.mkv", True),
    ],
)
def test_matches(match_type: MatchType, pattern: str, name: str, expected: bool) -> None:
    assert matches(make_rule(match_type=match_type, pattern=pattern), name) is expected


@pytest.mark.parametrize(
    ("rules", "name", "expected_id"),
    [
        ([], "x.mkv", None),
        ([make_rule(id="a", pattern="*.mp4")], "x.mkv", None),
        ([make_rule(id="a", priority=2), make_rule(id="b", priority=1)], "x.mkv", "b"),
        ([make_rule(id="a", priority=1, enabled=False), make_rule(id="b", priority=2)], "x", "b"),
        ([make_rule(id="a", priority=1, pattern="*.mp4"), make_rule(id="b", priority=5)], "x", "b"),
        ([make_rule(id="new", created_at=LATER), make_rule(id="old", created_at=T0)], "x", "old"),
        ([make_rule(id="old", created_at=T0), make_rule(id="new", created_at=LATER)], "x", "old"),
        ([make_rule(id="new", priority=1, created_at=LATER), make_rule(id="old")], "x", "new"),
    ],
)
def test_select_rule(rules: list, name: str, expected_id: str | None) -> None:
    selected = select_rule(rules, name)
    assert (selected.id if selected else None) == expected_id


@pytest.mark.parametrize(
    ("name", "expected"),
    [("file.mkv", True), ("", False), (".", False), ("..", False), ("a/b", False), ("a\0b", False)],
)
def test_is_safe_name(name: str, expected: bool) -> None:
    assert is_safe_name(name) is expected


def test_target_path_joins_destination_and_new_name() -> None:
    rule = make_rule(
        destination="/d/e/f", steps=[{"op": "replace", "find": "XYZ", "replace": "ABC"}]
    )
    assert target_path(rule, "XYZ.mkv") == PurePosixPath("/d/e/f/ABC.mkv")


@pytest.mark.parametrize("replacement", ["", "../x", "a/b"])
def test_target_path_rejects_unsafe_names(replacement: str) -> None:
    rule = make_rule(steps=[{"op": "regex_replace", "find": ".*", "replace": replacement}])
    with pytest.raises(ValueError):
        target_path(rule, "file.mkv")


RUNAWAY = r"(a|aa)+$"
RUNAWAY_NAME = "a" * 40 + "!"


@pytest.mark.parametrize(
    "run",
    [
        lambda: matches(make_rule(match_type=MatchType.REGEX, pattern=RUNAWAY), RUNAWAY_NAME),
        lambda: apply_step(RUNAWAY_NAME, RenameStep(op=REGEX, find=RUNAWAY, replace="x")),
    ],
)
def test_runaway_regex_is_cut_off(monkeypatch, run) -> None:
    monkeypatch.setattr(rename, "REGEX_TIMEOUT_SECONDS", 0.05)
    with pytest.raises(RegexTimeoutError):
        run()


def test_runaway_regex_does_not_freeze_other_threads(monkeypatch) -> None:
    monkeypatch.setattr(rename, "REGEX_TIMEOUT_SECONDS", 0.5)
    rule = make_rule(match_type=MatchType.REGEX, pattern=RUNAWAY)

    def run() -> None:
        with pytest.raises(RegexTimeoutError):
            matches(rule, RUNAWAY_NAME)

    worker = threading.Thread(target=run)
    gaps, last = [], time.perf_counter()
    worker.start()
    while worker.is_alive():
        time.sleep(0.01)
        now = time.perf_counter()
        gaps.append(now - last)
        last = now
    worker.join()
    assert max(gaps) < 0.25

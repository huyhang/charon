"""Pure rule-matching and renaming logic."""

from collections.abc import Callable, Iterable
from fnmatch import fnmatchcase
from functools import reduce
from pathlib import PurePosixPath
from typing import Any

import regex

from charon.domain.models import MatchType, RenameOp, RenameStep, Rule

# Caps catastrophic backtracking (e.g. `(a|aa)+$`), which would otherwise run for hours.
# Real rules finish on a file name in microseconds, even on a slow NAS CPU.
REGEX_TIMEOUT_SECONDS = 1.0


class RegexTimeoutError(Exception):
    """A rule's regex ran longer than REGEX_TIMEOUT_SECONDS."""


def apply_step(name: str, step: RenameStep) -> str:
    if step.op is RenameOp.REGEX_REPLACE:
        return _bounded(regex.sub, step.find, step.replace, name)
    return name.replace(step.find, step.replace)


def apply_steps(name: str, steps: Iterable[RenameStep]) -> str:
    return reduce(apply_step, steps, name)


def matches(rule: Rule, name: str) -> bool:
    if rule.match_type is MatchType.REGEX:
        return _bounded(regex.search, rule.pattern, name) is not None
    return fnmatchcase(name, rule.pattern)


def _bounded(run: Callable[..., Any], pattern: str, *args: str) -> Any:
    # Match without holding the GIL (`regex`'s default for str, spelled out because it
    # matters): otherwise a slow match would freeze every thread, the API included.
    try:
        return run(pattern, *args, timeout=REGEX_TIMEOUT_SECONDS, concurrent=True)
    except TimeoutError as exc:
        raise RegexTimeoutError(
            f"regex {pattern!r} took over {REGEX_TIMEOUT_SECONDS:g}s on this name; simplify it"
        ) from exc


def select_rule(rules: Iterable[Rule], name: str) -> Rule | None:
    """Return the first enabled matching rule: lowest priority value, then oldest."""
    candidates = sorted((r for r in rules if r.enabled), key=lambda r: (r.priority, r.created_at))
    return next((r for r in candidates if matches(r, name)), None)


def is_safe_name(name: str) -> bool:
    """A name is safe if it cannot escape its destination directory."""
    return name not in ("", ".", "..") and "/" not in name and "\0" not in name


def target_path(rule: Rule, name: str) -> PurePosixPath:
    """Where `name` ends up under `rule`. Raises ValueError if the new name is unsafe."""
    new_name = apply_steps(name, rule.steps)
    if not is_safe_name(new_name):
        raise ValueError(f"rename produced an unsafe name: {new_name!r}")
    return PurePosixPath(rule.destination) / new_name

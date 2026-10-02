import pytest

from charon.domain import rename
from charon.domain.destinations import DestinationPolicy
from charon.domain.models import RuleSpec
from charon.errors import InvalidInputError, NotFoundError
from charon.services.rule_service import RuleService
from tests.unit.fakes import (
    ALLOW_ALL,
    T0,
    FakeClock,
    InMemoryRuleStore,
    SequentialIds,
    make_rule,
)

SPEC = RuleSpec(name="tv", pattern="*.mkv", destination="/tv")


def make_service(*rules, clock: FakeClock | None = None) -> tuple[RuleService, InMemoryRuleStore]:
    store = InMemoryRuleStore(rules)
    clock = clock or FakeClock()
    service = RuleService(store, ALLOW_ALL, new_id=SequentialIds("rule"), clock=clock)
    return service, store


def test_create_assigns_id_and_creation_time_and_persists() -> None:
    clock = FakeClock()
    clock.advance(30)
    service, store = make_service(clock=clock)
    rule = service.create(SPEC)
    assert (rule.id, rule.created_at) == ("rule-1", clock())
    assert store.rules["rule-1"] == rule


def test_update_replaces_rule_but_keeps_creation_time() -> None:
    clock = FakeClock()
    clock.advance(30)
    service, store = make_service(make_rule(id="r", created_at=T0), clock=clock)
    service.update("r", SPEC)
    assert (store.rules["r"].destination, store.rules["r"].created_at) == ("/tv", T0)


@pytest.mark.parametrize(
    "action",
    [
        lambda s: s.get("missing"),
        lambda s: s.update("missing", SPEC),
        lambda s: s.delete("missing"),
        lambda s: s.select_for("x", "missing"),
    ],
)
def test_unknown_rule_raises_not_found(action) -> None:
    service, _ = make_service()
    with pytest.raises(NotFoundError):
        action(service)


def test_delete_removes_rule() -> None:
    service, store = make_service(make_rule(id="r"))
    service.delete("r")
    assert store.rules == {}


@pytest.mark.parametrize(
    ("name", "forced", "expected_id"),
    [
        ("show.mkv", None, "mkv"),
        ("show.mp4", None, None),
        ("show.mp4", "mkv", "mkv"),
    ],
)
def test_select_for(name: str, forced: str | None, expected_id: str | None) -> None:
    service, _ = make_service(make_rule(id="mkv", pattern="*.mkv"))
    rule = service.select_for(name, forced)
    assert (rule.id if rule else None) == expected_id


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Show.XYZ.mkv", ("r", "Show.ABC.mkv", "/d/e/f/Show.ABC.mkv")),
        ("Show.XYZ.mp4", (None, "Show.XYZ.mp4", None)),
    ],
)
def test_preview(name: str, expected: tuple) -> None:
    rule = make_rule(
        id="r",
        pattern="*.mkv",
        destination="/d/e/f",
        steps=[{"op": "replace", "find": "XYZ", "replace": "ABC"}],
    )
    service, _ = make_service(rule)
    preview = service.preview(name)
    assert (
        preview.rule.id if preview.rule else None,
        preview.new_name,
        preview.final_path,
    ) == expected


def test_preview_rejects_unsafe_result() -> None:
    rule = make_rule(steps=[{"op": "replace", "find": "a", "replace": "/"}])
    service, _ = make_service(rule)
    with pytest.raises(InvalidInputError):
        service.preview("a.mkv")


STRICT = DestinationPolicy.of(["/media"], ["/data"])


@pytest.mark.parametrize("destination", ["/data", "/media/../data", "/etc", "/mediax"])
def test_create_and_update_reject_disallowed_destinations(destination: str) -> None:
    store = InMemoryRuleStore([make_rule(id="r", destination="/media")])
    service = RuleService(store, STRICT)
    spec = SPEC.model_copy(update={"destination": destination})
    for action in (lambda: service.create(spec), lambda: service.update("r", spec)):
        with pytest.raises(InvalidInputError) as exc_info:
            action()
        assert exc_info.value.code == "destination_not_allowed"
    assert store.rules["r"].destination == "/media"


def test_preview_rejects_rule_outside_current_roots() -> None:
    service = RuleService(InMemoryRuleStore([make_rule(destination="/old")]), STRICT)
    with pytest.raises(InvalidInputError):
        service.preview("x.mkv")


RUNAWAY = r"(a|aa)+$"
RUNAWAY_NAME = "a" * 40 + "!"


@pytest.mark.parametrize(
    ("rule", "action"),
    [
        (make_rule(match_type="regex", pattern=RUNAWAY), lambda s: s.select_for(RUNAWAY_NAME)),
        (make_rule(match_type="regex", pattern=RUNAWAY), lambda s: s.preview(RUNAWAY_NAME)),
        (
            make_rule(steps=[{"op": "regex_replace", "find": RUNAWAY, "replace": "x"}]),
            lambda s: s.preview(RUNAWAY_NAME),
        ),
    ],
)
def test_runaway_regex_is_reported_as_rule_timeout(monkeypatch, rule, action) -> None:
    monkeypatch.setattr(rename, "REGEX_TIMEOUT_SECONDS", 0.05)
    service, _ = make_service(rule)
    with pytest.raises(InvalidInputError) as exc_info:
        action(service)
    assert exc_info.value.code == "rule_timeout"

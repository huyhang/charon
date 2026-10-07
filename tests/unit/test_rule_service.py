import pytest

from charon.domain import rename
from charon.domain.destinations import DestinationPolicy
from charon.domain.events import EventType
from charon.domain.models import SYSTEM, Actor, RuleSpec
from charon.errors import ConflictError, InvalidInputError, NotFoundError
from charon.services.rule_service import RuleService
from tests.unit.fakes import (
    ALLOW_ALL,
    T0,
    FakeClock,
    InMemoryRuleStore,
    Recorded,
    RecordingEventLog,
    SequentialIds,
    make_rule,
)

SPEC = RuleSpec(name="tv", pattern="*.mkv", destination="/tv")
PHONE = Actor(name="phone", key_id="key-1")


def make_service(
    *rules, clock: FakeClock | None = None, events: RecordingEventLog | None = None
) -> tuple[RuleService, InMemoryRuleStore]:
    store = InMemoryRuleStore(rules)
    clock = clock or FakeClock()
    events = events or RecordingEventLog()
    service = RuleService(store, ALLOW_ALL, events, new_id=SequentialIds("rule"), clock=clock)
    return service, store


def test_create_assigns_id_and_creation_time_and_persists() -> None:
    clock = FakeClock()
    clock.advance(30)
    service, store = make_service(clock=clock)
    rule = service.create(SPEC)
    assert (rule.id, rule.created_at) == ("rule-1", clock())
    assert store.rules["rule-1"] == rule


def test_create_credits_the_actor_and_records_an_event() -> None:
    events = RecordingEventLog()
    service, _ = make_service(events=events)
    rule = service.create(SPEC.model_copy(update={"description": "Keeps TV tidy"}), PHONE)
    assert (rule.description, rule.version, rule.created_by, rule.updated_by) == (
        "Keeps TV tidy",
        1,
        PHONE,
        PHONE,
    )
    assert events.recorded == [Recorded(EventType.RULE_CREATED, "rule-1", PHONE, {"name": "tv"})]


@pytest.mark.parametrize(
    ("expected_version", "saved"),
    [(None, True), (3, True), (2, False), (4, False)],
    ids=["unchecked", "current", "stale", "future"],
)
def test_update_checks_the_expected_version(expected_version: int | None, saved: bool) -> None:
    events = RecordingEventLog()
    service, store = make_service(make_rule(id="r", version=3, created_by=SYSTEM), events=events)
    if saved:
        rule = service.update("r", SPEC, expected_version, PHONE)
        assert (rule.version, rule.created_by, rule.updated_by) == (4, SYSTEM, PHONE)
        assert events.types() == [EventType.RULE_UPDATED]
    else:
        with pytest.raises(ConflictError) as exc_info:
            service.update("r", SPEC, expected_version, PHONE)
        assert exc_info.value.code == "rule_changed"
        assert events.recorded == []
    assert store.rules["r"].version == (4 if saved else 3)


def test_update_fails_if_the_rule_changes_while_saving() -> None:
    service, store = make_service(make_rule(id="r"))
    store.update = lambda rule, expected_version: False
    with pytest.raises(ConflictError) as exc_info:
        service.update("r", SPEC)
    assert exc_info.value.code == "rule_changed"


def test_update_records_which_fields_changed() -> None:
    events = RecordingEventLog()
    current = make_rule(id="r", name="tv", pattern="*.mkv", destination="/tv")
    service, _ = make_service(current, events=events)
    service.update("r", SPEC.model_copy(update={"pattern": "*.mp4", "enabled": False}))
    [recorded] = events.recorded
    assert recorded.data == {"name": "tv", "changed": ["enabled", "pattern"]}


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
    events = RecordingEventLog()
    service, store = make_service(make_rule(id="r"), events=events)
    service.delete("r", PHONE)
    assert store.rules == {}
    assert events.recorded == [Recorded(EventType.RULE_DELETED, "r", PHONE, {"name": "rule"})]


def test_delete_reports_a_rule_deleted_meanwhile() -> None:
    service, store = make_service(make_rule(id="r"))
    store.delete = lambda rule_id: False
    with pytest.raises(NotFoundError):
        service.delete("r")


def _three_rules():
    return (
        make_rule(id="a", priority=10),
        make_rule(id="b", priority=20),
        make_rule(id="c", priority=30),
    )


@pytest.mark.parametrize(
    ("order", "changed"),
    [(["c", "a", "b"], {"a", "b", "c"}), (["b", "a", "c"], {"a", "b"}), (["a", "b", "c"], set())],
    ids=["rotate", "swap-first-two", "unchanged"],
)
def test_reorder_respaces_priorities_and_bumps_only_moved_rules(order, changed) -> None:
    events = RecordingEventLog()
    service, store = make_service(*_three_rules(), events=events)
    result = service.reorder(order, PHONE)
    assert [(r.id, r.priority) for r in result] == list(zip(order, [10, 20, 30], strict=True))
    assert {r.id for r in store.rules.values() if r.version == 2} == changed
    assert {r.id for r in store.rules.values() if r.updated_by == PHONE} == changed
    assert events.recorded == [
        Recorded(EventType.RULES_REORDERED, "rules", PHONE, {"order": order})
    ]


@pytest.mark.parametrize(
    ("order", "error", "code", "details"),
    [
        (["a", "b"], ConflictError, "rules_changed", {"unknown_ids": [], "missing_ids": ["c"]}),
        (
            ["a", "b", "c", "d"],
            ConflictError,
            "rules_changed",
            {"unknown_ids": ["d"], "missing_ids": []},
        ),
        (["a", "a", "b", "c"], InvalidInputError, "duplicate_rule_ids", None),
    ],
    ids=["missing-one", "unknown-one", "duplicate"],
)
def test_reorder_rejects_an_order_that_isnt_the_current_set(order, error, code, details) -> None:
    service, store = make_service(*_three_rules())
    with pytest.raises(error) as exc_info:
        service.reorder(order)
    assert (exc_info.value.code, exc_info.value.details) == (code, details)
    assert [r.priority for r in store.list()] == [10, 20, 30]


def test_reorder_fails_when_a_rule_changes_meanwhile() -> None:
    service, store = make_service(*_three_rules())
    store.update_all = lambda rules, snapshot: False
    with pytest.raises(ConflictError) as exc_info:
        service.reorder(["c", "b", "a"])
    assert exc_info.value.code == "rules_changed"


def test_reorder_notices_an_edit_to_a_rule_it_doesnt_move() -> None:
    service, store = make_service(*_three_rules())
    update_all = store.update_all

    def after_an_edit_to_a(rules, snapshot) -> bool:
        store.rules["a"] = store.rules["a"].model_copy(update={"priority": 999, "version": 2})
        return update_all(rules, snapshot)

    store.update_all = after_an_edit_to_a
    with pytest.raises(ConflictError):
        service.reorder(["a", "c", "b"])
    assert [(r.id, r.priority) for r in store.list()] == [("b", 20), ("c", 30), ("a", 999)]


def test_matcher_previews_many_names_against_one_snapshot() -> None:
    service, store = make_service(make_rule(id="mkv", pattern="*.mkv", destination="/tv"))
    match = service.matcher()
    store.rules.clear()
    assert match("a.mkv").final_path == "/tv/a.mkv"
    assert match("a.mp4").rule is None


def test_matcher_raises_for_a_rule_that_cant_apply() -> None:
    rule = make_rule(steps=[{"op": "replace", "find": "a", "replace": "/"}])
    service, _ = make_service(rule)
    with pytest.raises(InvalidInputError) as exc_info:
        service.matcher()("a.mkv")
    assert exc_info.value.code == "unsafe_name"


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


@pytest.mark.parametrize(
    ("draft", "name", "expected"),
    [
        ({"pattern": "*.mkv"}, "Show.XYZ.mkv", ("Show.ABC.mkv", "/d/Show.ABC.mkv")),
        ({"pattern": "*.mkv"}, "Show.XYZ.mp4", ("Show.XYZ.mp4", None)),
        ({"pattern": "XYZ", "match_type": "regex"}, "A.XYZ.mp4", ("A.ABC.mp4", "/d/A.ABC.mp4")),
        ({"pattern": "*", "enabled": False}, "Show.XYZ.mkv", ("Show.ABC.mkv", "/d/Show.ABC.mkv")),
    ],
    ids=["match", "no-match", "regex", "disabled-still-previews"],
)
def test_preview_draft_applies_only_the_draft(draft: dict, name: str, expected: tuple) -> None:
    service, _ = make_service(make_rule(id="saved", pattern="*", destination="/other"))
    spec = RuleSpec(
        name="draft",
        destination="/d",
        steps=[{"op": "replace", "find": "XYZ", "replace": "ABC"}],
        **draft,
    )
    preview = service.preview_draft(name, spec)
    assert (preview.rule, preview.new_name, preview.final_path) == (None, *expected)


@pytest.mark.parametrize(
    ("draft", "name", "code"),
    [
        ({"destination": "/etc"}, "x.mkv", "destination_not_allowed"),
        ({"steps": [{"op": "replace", "find": "a", "replace": "/"}]}, "a.mkv", "unsafe_name"),
        ({"match_type": "regex", "pattern": r"(a|aa)+$"}, "a" * 40 + "!", "rule_timeout"),
    ],
)
def test_preview_draft_errors(monkeypatch, draft: dict, name: str, code: str) -> None:
    monkeypatch.setattr(rename, "REGEX_TIMEOUT_SECONDS", 0.05)
    service = RuleService(InMemoryRuleStore(), STRICT, RecordingEventLog())
    spec = RuleSpec.model_validate({"name": "d", "pattern": "*", "destination": "/media", **draft})
    with pytest.raises(InvalidInputError) as exc_info:
        service.preview_draft(name, spec)
    assert exc_info.value.code == code


def test_preview_rejects_unsafe_result() -> None:
    rule = make_rule(steps=[{"op": "replace", "find": "a", "replace": "/"}])
    service, _ = make_service(rule)
    with pytest.raises(InvalidInputError):
        service.preview("a.mkv")


STRICT = DestinationPolicy.of(["/media"], ["/data"])


@pytest.mark.parametrize("destination", ["/data", "/media/../data", "/etc", "/mediax"])
def test_create_and_update_reject_disallowed_destinations(destination: str) -> None:
    store = InMemoryRuleStore([make_rule(id="r", destination="/media")])
    service = RuleService(store, STRICT, RecordingEventLog())
    spec = SPEC.model_copy(update={"destination": destination})
    for action in (lambda: service.create(spec), lambda: service.update("r", spec)):
        with pytest.raises(InvalidInputError) as exc_info:
            action()
        assert exc_info.value.code == "destination_not_allowed"
    assert store.rules["r"].destination == "/media"


def test_preview_rejects_rule_outside_current_roots() -> None:
    service = RuleService(
        InMemoryRuleStore([make_rule(destination="/old")]), STRICT, RecordingEventLog()
    )
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

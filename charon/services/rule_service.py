from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass, replace
from pathlib import PurePosixPath

from charon.domain.destinations import DestinationPolicy
from charon.domain.events import EventType, changed_fields
from charon.domain.models import SYSTEM, Actor, Rule, RuleSpec
from charon.domain.rename import RegexTimeoutError, matches, select_rule, target_path
from charon.errors import ConflictError, InvalidInputError, NotFoundError
from charon.ports.clock import Clock, IdFactory, new_uuid, utc_now
from charon.ports.events import EventLog
from charon.ports.stores import RuleStore

# Reordering spaces priorities this far apart, leaving room to slot a rule in between.
PRIORITY_STEP = 10


@dataclass(frozen=True)
class Preview:
    rule: Rule | None
    new_name: str
    final_path: str | None


Matcher = Callable[[str], Preview]
# Spelled out here because inside RuleService `list` is the method of that name.
Rules = list[Rule]


class RuleService:
    def __init__(
        self,
        rules: RuleStore,
        policy: DestinationPolicy,
        events: EventLog,
        new_id: IdFactory = new_uuid,
        clock: Clock = utc_now,
    ) -> None:
        self._rules = rules
        self._policy = policy
        self._events = events
        self._new_id = new_id
        self._clock = clock

    def list(self) -> list[Rule]:
        return self._rules.list()

    def get(self, rule_id: str) -> Rule:
        rule = self._rules.get(rule_id)
        if rule is None:
            raise NotFoundError("rule_not_found", f"rule {rule_id} does not exist")
        return rule

    def create(self, spec: RuleSpec, actor: Actor = SYSTEM) -> Rule:
        self._check_destination(spec.destination)
        rule = Rule(
            id=self._new_id(),
            created_at=self._clock(),
            created_by=actor,
            updated_by=actor,
            **spec.model_dump(),
        )
        self._rules.add(rule)
        self._events.record(EventType.RULE_CREATED, rule.id, actor, name=rule.name)
        return rule

    def update(
        self,
        rule_id: str,
        spec: RuleSpec,
        expected_version: int | None = None,
        actor: Actor = SYSTEM,
    ) -> Rule:
        """Replace a rule. With `expected_version`, fail rather than overwrite a newer change."""
        self._check_destination(spec.destination)
        current = self.get(rule_id)
        if expected_version is not None and expected_version != current.version:
            raise _changed(rule_id)
        rule = self._revised(current, actor, **spec.model_dump())
        if not self._rules.update(rule, expected_version=current.version):
            raise _changed(rule_id)
        changed = changed_fields(current, spec)
        self._events.record(EventType.RULE_UPDATED, rule.id, actor, name=rule.name, changed=changed)
        return rule

    def delete(self, rule_id: str, actor: Actor = SYSTEM) -> None:
        rule = self.get(rule_id)
        if not self._rules.delete(rule_id):
            raise NotFoundError("rule_not_found", f"rule {rule_id} does not exist")
        self._events.record(EventType.RULE_DELETED, rule_id, actor, name=rule.name)

    def reorder(self, ordered_ids: Sequence[str], actor: Actor = SYSTEM) -> Rules:
        """Give every rule a new place at once. `ordered_ids` must list each rule exactly once."""
        current = {rule.id: rule for rule in self._rules.list()}
        _check_order(ordered_ids, current.keys())
        changes = [
            self._revised(current[rule_id], actor, priority=priority)
            for rule_id, priority in _spaced(ordered_ids)
            if current[rule_id].priority != priority
        ]
        # Every rule is checked, not just the moved ones: an edit to any of them meanwhile
        # could otherwise leave an order nobody asked for.
        snapshot = {rule.id: rule.version for rule in current.values()}
        if not self._rules.update_all(changes, snapshot):
            raise ConflictError("rules_changed", "the rules changed meanwhile; reload them")
        self._events.record(EventType.RULES_REORDERED, "rules", actor, order=list(ordered_ids))
        return self._rules.list()

    def select_for(self, name: str, forced_rule_id: str | None = None) -> Rule | None:
        if forced_rule_id is not None:
            return self.get(forced_rule_id)
        return self._select(self._rules.list(), name)

    def target_for(self, rule: Rule, name: str) -> PurePosixPath:
        """Where `name` ends up under `rule`."""
        try:
            return target_path(rule, name)
        except RegexTimeoutError as exc:
            raise InvalidInputError("rule_timeout", str(exc)) from exc
        except ValueError as exc:
            raise InvalidInputError("unsafe_name", str(exc)) from exc

    def preview(self, name: str, rule_id: str | None = None) -> Preview:
        return self._preview(self.select_for(name, rule_id), name)

    def matcher(self) -> Matcher:
        """Previews names against one snapshot of the saved rules, for checking many at once.

        Like `preview`, the returned function raises InvalidInputError for a rule that
        can't be applied to a name.
        """
        rules = self._rules.list()
        return lambda name: self._preview(self._select(rules, name), name)

    def preview_draft(self, name: str, spec: RuleSpec) -> Preview:
        """Preview an unsaved rule as if it were the only one, e.g. while editing it.

        It applies only if its pattern matches. `rule` stays None since it isn't saved.
        """
        draft = Rule(id="draft", created_at=self._clock(), **spec.model_dump())
        preview = self._preview(draft if self._matches(draft, name) else None, name)
        return replace(preview, rule=None)

    def _revised(self, rule: Rule, actor: Actor, **changes: object) -> Rule:
        # Keep the creation time so editing a rule doesn't change which one wins a tie.
        revised = {**rule.model_dump(), **changes, "version": rule.version + 1, "updated_by": actor}
        return Rule.model_validate(revised)

    def _select(self, rules: Rules, name: str) -> Rule | None:
        try:
            return select_rule(rules, name)
        except RegexTimeoutError as exc:
            raise InvalidInputError("rule_timeout", str(exc)) from exc

    def _preview(self, rule: Rule | None, name: str) -> Preview:
        if rule is None:
            return Preview(rule=None, new_name=name, final_path=None)
        self._check_destination(rule.destination)
        path = self.target_for(rule, name)
        return Preview(rule=rule, new_name=path.name, final_path=str(path))

    def _matches(self, rule: Rule, name: str) -> bool:
        try:
            return matches(rule, name)
        except RegexTimeoutError as exc:
            raise InvalidInputError("rule_timeout", str(exc)) from exc

    def _check_destination(self, destination: str) -> None:
        problem = self._policy.violation(destination)
        if problem is not None:
            raise InvalidInputError("destination_not_allowed", problem)


def _changed(rule_id: str) -> ConflictError:
    return ConflictError("rule_changed", f"rule {rule_id} changed since you loaded it; reload it")


def _check_order(ordered_ids: Sequence[str], existing: Collection[str]) -> None:
    if len(set(ordered_ids)) != len(ordered_ids):
        raise InvalidInputError("duplicate_rule_ids", "each rule must appear exactly once")
    unknown, missing = set(ordered_ids) - set(existing), set(existing) - set(ordered_ids)
    if unknown or missing:
        raise ConflictError(
            "rules_changed",
            "the ids don't match the current rules; reload them",
            details={"unknown_ids": sorted(unknown), "missing_ids": sorted(missing)},
        )


def _spaced(ordered_ids: Sequence[str]) -> list[tuple[str, int]]:
    return [(rule_id, (index + 1) * PRIORITY_STEP) for index, rule_id in enumerate(ordered_ids)]

from dataclasses import dataclass
from pathlib import PurePosixPath

from charon.domain.destinations import DestinationPolicy
from charon.domain.models import Rule, RuleSpec
from charon.domain.rename import RegexTimeoutError, select_rule, target_path
from charon.errors import InvalidInputError, NotFoundError
from charon.ports.clock import Clock, IdFactory, new_uuid, utc_now
from charon.ports.stores import RuleStore


@dataclass(frozen=True)
class Preview:
    rule: Rule | None
    new_name: str
    final_path: str | None


class RuleService:
    def __init__(
        self,
        rules: RuleStore,
        policy: DestinationPolicy,
        new_id: IdFactory = new_uuid,
        clock: Clock = utc_now,
    ) -> None:
        self._rules = rules
        self._policy = policy
        self._new_id = new_id
        self._clock = clock

    def list(self) -> list[Rule]:
        return self._rules.list()

    def get(self, rule_id: str) -> Rule:
        rule = self._rules.get(rule_id)
        if rule is None:
            raise NotFoundError("rule_not_found", f"rule {rule_id} does not exist")
        return rule

    def create(self, spec: RuleSpec) -> Rule:
        self._check_destination(spec.destination)
        rule = Rule(id=self._new_id(), created_at=self._clock(), **spec.model_dump())
        self._rules.add(rule)
        return rule

    def update(self, rule_id: str, spec: RuleSpec) -> Rule:
        self._check_destination(spec.destination)
        # Keep the creation time so editing a rule doesn't change which one wins a tie.
        rule = Rule(id=rule_id, created_at=self.get(rule_id).created_at, **spec.model_dump())
        if not self._rules.update(rule):
            raise NotFoundError("rule_not_found", f"rule {rule_id} does not exist")
        return rule

    def delete(self, rule_id: str) -> None:
        if not self._rules.delete(rule_id):
            raise NotFoundError("rule_not_found", f"rule {rule_id} does not exist")

    def select_for(self, name: str, forced_rule_id: str | None = None) -> Rule | None:
        if forced_rule_id is not None:
            return self.get(forced_rule_id)
        try:
            return select_rule(self._rules.list(), name)
        except RegexTimeoutError as exc:
            raise InvalidInputError("rule_timeout", str(exc)) from exc

    def target_for(self, rule: Rule, name: str) -> PurePosixPath:
        """Where `name` ends up under `rule`."""
        try:
            return target_path(rule, name)
        except RegexTimeoutError as exc:
            raise InvalidInputError("rule_timeout", str(exc)) from exc
        except ValueError as exc:
            raise InvalidInputError("unsafe_name", str(exc)) from exc

    def preview(self, name: str, rule_id: str | None = None) -> Preview:
        rule = self.select_for(name, rule_id)
        if rule is None:
            return Preview(rule=None, new_name=name, final_path=None)
        self._check_destination(rule.destination)
        path = self.target_for(rule, name)
        return Preview(rule=rule, new_name=path.name, final_path=str(path))

    def _check_destination(self, destination: str) -> None:
        problem = self._policy.violation(destination)
        if problem is not None:
            raise InvalidInputError("destination_not_allowed", problem)

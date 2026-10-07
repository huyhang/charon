from typing import Annotated

from fastapi import APIRouter, Depends, Header, Response

from charon.api.deps import current_actor, get_idempotency_service, get_rule_service
from charon.api.idempotency import IdempotencyKey, Outcome, caller_scope, run_once
from charon.api.schemas import (
    PreviewRequest,
    PreviewView,
    ReorderRulesRequest,
    RuleUpdate,
    error_responses,
)
from charon.domain.models import Actor, Rule, RuleSpec
from charon.errors import InvalidInputError
from charon.services.idempotency_service import IdempotencyService
from charon.services.rule_service import RuleService

router = APIRouter(prefix="/rules", tags=["rules"], responses=error_responses(401, 422))

IfMatch = Annotated[
    str | None,
    Header(
        alias="If-Match",
        description='The rule\'s ETag, e.g. "3": an alternative to sending `version`.',
    ),
]


def tag_version(response: Response, rule: Rule) -> Rule:
    """Send the rule's version as its ETag, for clients that use If-Match."""
    response.headers["ETag"] = f'"{rule.version}"'
    return rule


def expected_version(version: int | None, if_match: str | None) -> int | None:
    """The version a save must find, from the body's `version` or an If-Match header."""
    tag = None if if_match is None else if_match.strip().removeprefix("W/").strip('"')
    if tag in (None, "*"):
        return version
    if not (tag.isascii() and tag.isdigit()):
        raise InvalidInputError("invalid_if_match", 'If-Match must be a rule\'s ETag, e.g. "3"')
    if version is not None and version != int(tag):
        raise InvalidInputError("invalid_if_match", "If-Match and version disagree")
    return int(tag)


@router.get("")
def list_rules(service: RuleService = Depends(get_rule_service)) -> list[Rule]:
    """Every rule, in the order they are tried."""
    return service.list()


@router.post(
    "",
    status_code=201,
    responses={200: {"model": Rule, "description": "Repeated request"}, **error_responses(409)},
)
def create_rule(
    spec: RuleSpec,
    response: Response,
    idempotency_key: IdempotencyKey = None,
    service: RuleService = Depends(get_rule_service),
    idempotency: IdempotencyService = Depends(get_idempotency_service),
    actor: Actor = Depends(current_actor),
) -> Rule:
    outcome = run_once(
        idempotency,
        caller_scope("rules", actor),
        idempotency_key,
        spec,
        create=lambda: Outcome(service.create(spec, actor), created=True),
        load=service.get,
        id_of=lambda rule: rule.id,
    )
    response.status_code = 201 if outcome.created else 200
    return tag_version(response, outcome.value)


@router.post("/preview", responses=error_responses(404))
def preview_rule(
    body: PreviewRequest, service: RuleService = Depends(get_rule_service)
) -> PreviewView:
    """Dry run: what `name` would become, under the saved rules or an unsaved draft `rule`."""
    if body.rule is not None:
        return PreviewView.from_preview(service.preview_draft(body.name, body.rule))
    return PreviewView.from_preview(service.preview(body.name, body.rule_id))


@router.post("/reorder", responses=error_responses(409))
def reorder_rules(
    body: ReorderRulesRequest,
    service: RuleService = Depends(get_rule_service),
    actor: Actor = Depends(current_actor),
) -> list[Rule]:
    """Put every rule in a new order at once; priorities are re-spaced 10, 20, 30…

    Fails with 409 rules_changed if `ids` isn't exactly the current set of rules.
    """
    return service.reorder(body.ids, actor)


@router.get("/{rule_id}", responses=error_responses(404))
def get_rule(
    rule_id: str, response: Response, service: RuleService = Depends(get_rule_service)
) -> Rule:
    return tag_version(response, service.get(rule_id))


@router.put("/{rule_id}", responses=error_responses(404, 409))
def update_rule(
    rule_id: str,
    body: RuleUpdate,
    response: Response,
    if_match: IfMatch = None,
    service: RuleService = Depends(get_rule_service),
    actor: Actor = Depends(current_actor),
) -> Rule:
    """Replace a rule. Send the `version` you loaded (or If-Match) to refuse a newer edit."""
    expected = expected_version(body.version, if_match)
    return tag_version(response, service.update(rule_id, body.spec(), expected, actor))


@router.delete("/{rule_id}", status_code=204, responses=error_responses(404))
def delete_rule(
    rule_id: str,
    service: RuleService = Depends(get_rule_service),
    actor: Actor = Depends(current_actor),
) -> Response:
    service.delete(rule_id, actor)
    return Response(status_code=204)

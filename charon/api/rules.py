from fastapi import APIRouter, Depends, Response

from charon.api.deps import get_rule_service
from charon.api.schemas import PreviewRequest, PreviewView, error_responses
from charon.domain.models import Rule, RuleSpec
from charon.services.rule_service import RuleService

router = APIRouter(prefix="/rules", tags=["rules"], responses=error_responses(401, 422))


@router.get("")
def list_rules(service: RuleService = Depends(get_rule_service)) -> list[Rule]:
    return service.list()


@router.post("", status_code=201)
def create_rule(spec: RuleSpec, service: RuleService = Depends(get_rule_service)) -> Rule:
    return service.create(spec)


@router.post("/preview", responses=error_responses(404))
def preview_rule(
    body: PreviewRequest, service: RuleService = Depends(get_rule_service)
) -> PreviewView:
    return PreviewView.from_preview(service.preview(body.name, body.rule_id))


@router.get("/{rule_id}", responses=error_responses(404))
def get_rule(rule_id: str, service: RuleService = Depends(get_rule_service)) -> Rule:
    return service.get(rule_id)


@router.put("/{rule_id}", responses=error_responses(404))
def update_rule(
    rule_id: str, spec: RuleSpec, service: RuleService = Depends(get_rule_service)
) -> Rule:
    return service.update(rule_id, spec)


@router.delete("/{rule_id}", status_code=204, responses=error_responses(404))
def delete_rule(rule_id: str, service: RuleService = Depends(get_rule_service)) -> Response:
    service.delete(rule_id)
    return Response(status_code=204)

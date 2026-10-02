from fastapi import APIRouter, Depends

from charon.api.deps import get_api_key_service, require_admin
from charon.api.schemas import ApiKeyView, CreateApiKeyRequest, IssuedApiKeyView, error_responses
from charon.services.api_key_service import ApiKeyService

router = APIRouter(
    prefix="/api-keys",
    tags=["api-keys"],
    dependencies=[Depends(require_admin)],
    responses=error_responses(401, 403, 409, 422),
)


@router.post("", status_code=201)
def create_api_key(
    body: CreateApiKeyRequest, service: ApiKeyService = Depends(get_api_key_service)
) -> IssuedApiKeyView:
    return IssuedApiKeyView.from_issued(service.create(body.name, body.role))


@router.get("")
def list_api_keys(service: ApiKeyService = Depends(get_api_key_service)) -> list[ApiKeyView]:
    return [ApiKeyView.from_key(k) for k in service.list()]


@router.get("/{key_id}", responses=error_responses(404))
def get_api_key(key_id: str, service: ApiKeyService = Depends(get_api_key_service)) -> ApiKeyView:
    return ApiKeyView.from_key(service.get(key_id))


@router.delete("/{key_id}", responses=error_responses(404))
def revoke_api_key(
    key_id: str, service: ApiKeyService = Depends(get_api_key_service)
) -> ApiKeyView:
    return ApiKeyView.from_key(service.revoke(key_id))

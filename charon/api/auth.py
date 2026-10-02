from fastapi import APIRouter, Depends

from charon.api.deps import authenticate, get_api_key_service
from charon.api.schemas import PrincipalView, error_responses
from charon.domain.models import Principal
from charon.services.api_key_service import ApiKeyService

router = APIRouter(prefix="/auth", tags=["auth"], responses=error_responses(401))


@router.get("/me")
def get_current_principal(
    principal: Principal = Depends(authenticate),
    service: ApiKeyService = Depends(get_api_key_service),
) -> PrincipalView:
    """Who the presented key belongs to. Lets a UI validate a key and adapt to its role."""
    return PrincipalView(**principal.model_dump(), auth_enabled=service.auth_enabled)

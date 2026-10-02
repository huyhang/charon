from fastapi import Depends, Request, Security
from fastapi.security import APIKeyHeader

from charon.container import Container
from charon.domain.models import Principal
from charon.services.api_key_service import ApiKeyService
from charon.services.download_service import DownloadService
from charon.services.rule_service import RuleService

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_container(request: Request) -> Container:
    return request.app.state.container


def get_download_service(container: Container = Depends(get_container)) -> DownloadService:
    return container.download_service


def get_rule_service(container: Container = Depends(get_container)) -> RuleService:
    return container.rule_service


def get_api_key_service(container: Container = Depends(get_container)) -> ApiKeyService:
    return container.api_key_service


def authenticate(
    x_api_key: str | None = Security(api_key_header),
    service: ApiKeyService = Depends(get_api_key_service),
) -> Principal:
    return service.authenticate(x_api_key)


def require_admin(
    principal: Principal = Depends(authenticate),
    service: ApiKeyService = Depends(get_api_key_service),
) -> Principal:
    service.authorize_admin(principal)
    return principal

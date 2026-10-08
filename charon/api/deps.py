from fastapi import Depends, Request, Security
from fastapi.security import APIKeyHeader

from charon.container import Container
from charon.domain.models import Actor, Principal, Role
from charon.errors import ForbiddenError
from charon.services.api_key_service import ApiKeyService
from charon.services.destination_service import DestinationService
from charon.services.download_service import DownloadService
from charon.services.event_service import EventService
from charon.services.feed_inbox import FeedInbox
from charon.services.feed_service import FeedService
from charon.services.idempotency_service import IdempotencyService
from charon.services.metadata_service import MetadataService
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


def get_destination_service(container: Container = Depends(get_container)) -> DestinationService:
    return container.destination_service


def get_event_service(container: Container = Depends(get_container)) -> EventService:
    return container.event_service


def get_idempotency_service(container: Container = Depends(get_container)) -> IdempotencyService:
    return container.idempotency_service


def get_feed_service(container: Container = Depends(get_container)) -> FeedService:
    return container.feed_service


def get_feed_inbox(container: Container = Depends(get_container)) -> FeedInbox:
    return container.feed_inbox


def get_metadata_service(container: Container = Depends(get_container)) -> MetadataService:
    return container.metadata_service


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


def require_admin_role(principal: Principal = Depends(authenticate)) -> Principal:
    """An admin key, or anyone while auth is off (everyone is an admin then).

    Unlike require_admin, this works without API keys: for settings, not for managing keys.
    """
    if principal.role is not Role.ADMIN:
        raise ForbiddenError("forbidden", "this action requires an admin key")
    return principal


def current_actor(principal: Principal = Depends(authenticate)) -> Actor:
    """Who to credit with a change made by this request."""
    return principal.actor

from fastapi import APIRouter, Depends, Path, Query

from charon.api.deps import get_metadata_service, require_admin_role
from charon.api.schemas import (
    MetadataProviderView,
    ProviderKeyView,
    SetProviderKeyRequest,
    TitleSearchView,
    error_responses,
)
from charon.domain.titles import MAX_QUERY_LENGTH, KindFilter
from charon.services.metadata_service import DEFAULT_LIMIT, MetadataService

router = APIRouter(prefix="/metadata", tags=["metadata"], responses=error_responses(401, 422))

# Admin keys, or anyone while auth is off: these are settings, not API key management.
admin_only = [Depends(require_admin_role)]
ProviderId = Path(description="A provider id from /metadata/providers, e.g. tmdb.")


@router.get("/providers")
def list_metadata_providers(
    service: MetadataService = Depends(get_metadata_service),
) -> list[MetadataProviderView]:
    """The providers Charon can look canonical titles up on, and whether each has a key."""
    return [MetadataProviderView.from_summary(summary) for summary in service.providers()]


@router.get("/search", responses=error_responses(404, 409, 429, 502))
def search_titles(
    q: str = Query(max_length=MAX_QUERY_LENGTH, description="A title, in any language."),
    provider: str = Query(default="tmdb", description="A provider id from /metadata/providers."),
    kind: KindFilter = KindFilter.ANY,
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=20),
    refresh: bool = Query(
        default=False, description="Ask the provider again, even if Charon remembers an answer."
    ),
    service: MetadataService = Depends(get_metadata_service),
) -> TitleSearchView:
    """Movies and shows matching `q`, best first, under their canonical names.

    Show `attribution` wherever you show the results: providers require it. Answers are
    remembered; when the provider can't be asked, an older one may come back with `stale`.
    """
    found = service.search(provider, q, kind, limit, refresh)
    return TitleSearchView(
        attribution=found.attribution,
        results=found.results,
        stale=found.stale,
        age_seconds=round(found.age_seconds),
    )


@router.get(
    "/providers/{provider_id}/key", dependencies=admin_only, responses=error_responses(403, 404)
)
def get_provider_key(
    provider_id: str = ProviderId, service: MetadataService = Depends(get_metadata_service)
) -> ProviderKeyView:
    """Whether the provider has a key, and where it comes from. Never the key itself."""
    return ProviderKeyView.from_status(provider_id, service.key_status(provider_id))


@router.put(
    "/providers/{provider_id}/key", dependencies=admin_only, responses=error_responses(403, 404)
)
def set_provider_key(
    body: SetProviderKeyRequest,
    provider_id: str = ProviderId,
    service: MetadataService = Depends(get_metadata_service),
) -> ProviderKeyView:
    """Save the provider's key in Charon. It takes the place of one from the environment."""
    return ProviderKeyView.from_status(provider_id, service.set_key(provider_id, body.key))


@router.delete(
    "/providers/{provider_id}/key", dependencies=admin_only, responses=error_responses(403, 404)
)
def clear_provider_key(
    provider_id: str = ProviderId, service: MetadataService = Depends(get_metadata_service)
) -> ProviderKeyView:
    """Forget the saved key. One from the environment applies again; without it, lookups stop."""
    return ProviderKeyView.from_status(provider_id, service.clear_key(provider_id))


@router.delete("/cache", status_code=204, dependencies=admin_only, responses=error_responses(403))
def clear_metadata_cache(service: MetadataService = Depends(get_metadata_service)) -> None:
    """Forget every remembered answer, so the next searches ask the providers again."""
    service.clear_cache()

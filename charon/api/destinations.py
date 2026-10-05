from fastapi import APIRouter, Depends, Query

from charon.api.deps import get_destination_service
from charon.api.schemas import DestinationRootsView, FolderListingView, error_responses
from charon.services.destination_service import DestinationService

router = APIRouter(
    prefix="/destinations", tags=["destinations"], responses=error_responses(401, 422)
)


@router.get("/roots")
def list_destination_roots(
    service: DestinationService = Depends(get_destination_service),
) -> DestinationRootsView:
    """The folders rule destinations must sit inside (CHARON_RULE_ROOTS)."""
    return DestinationRootsView(roots=service.roots())


@router.get("/folders", responses=error_responses(404))
def list_destination_folders(
    path: str = Query(min_length=1, description="An absolute folder inside a root."),
    service: DestinationService = Depends(get_destination_service),
) -> FolderListingView:
    """The folders directly inside `path`, for picking a rule destination. Never lists files."""
    return FolderListingView.from_listing(service.folders(path))

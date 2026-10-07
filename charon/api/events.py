from fastapi import APIRouter, Depends, Query

from charon.api.deps import get_event_service
from charon.api.schemas import EventListView, error_responses
from charon.domain.events import EventType
from charon.services.event_service import EventService

router = APIRouter(prefix="/events", tags=["events"], responses=error_responses(401, 422))


@router.get("")
def list_events(
    after: int = Query(default=0, ge=0, description="The `cursor` from the previous call."),
    limit: int = Query(default=100, ge=1, le=500),
    type: list[EventType] | None = Query(default=None, description="Only these types."),
    service: EventService = Depends(get_event_service),
) -> EventListView:
    """What happened since `after`, oldest first: job status changes, rule edits, feed items…

    Poll with the returned `cursor` to follow along. Events are kept for 30 days.
    """
    return EventListView.from_page(service.list(after, limit, type))

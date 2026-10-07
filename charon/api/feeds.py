from fastapi import APIRouter, Depends, Query, Response

from charon.api.deps import (
    authenticate,
    current_actor,
    get_feed_inbox,
    get_feed_service,
    get_idempotency_service,
)
from charon.api.downloads import submission_outcome
from charon.api.feed_schemas import (
    DownloadItemRequest,
    FeedItemListView,
    FeedItemView,
    FeedPreviewRequest,
    FeedPreviewView,
    FeedSummaryView,
    FeedUrlView,
    FeedView,
    MarkAllSeenRequest,
    MarkSeenRequest,
    MarkSeenView,
)
from charon.api.idempotency import IdempotencyKey, Outcome, caller_scope, run_once
from charon.api.schemas import JobView, error_responses
from charon.domain.feeds import FeedSpec, FeedUpdate
from charon.domain.models import Actor, Principal, Role
from charon.errors import ForbiddenError
from charon.services.feed_inbox import FeedInbox, InboxQuery, MatchFilter
from charon.services.feed_service import FeedService
from charon.services.idempotency_service import IdempotencyService

router = APIRouter(prefix="/feeds", tags=["feeds"], responses=error_responses(401, 422))


def require_url_access(principal: Principal = Depends(authenticate)) -> Principal:
    """Feed addresses may hold passkeys, so only admins may read or change them."""
    if principal.role is not Role.ADMIN:
        raise ForbiddenError("forbidden", "only admin keys can see or change a feed's address")
    return principal


@router.get("")
def list_feeds(service: FeedService = Depends(get_feed_service)) -> list[FeedView]:
    return [FeedView.from_feed(feed) for feed in service.list()]


@router.post(
    "",
    status_code=201,
    responses={200: {"model": FeedView, "description": "Repeated request"}, **error_responses(409)},
)
def create_feed(
    spec: FeedSpec,
    response: Response,
    idempotency_key: IdempotencyKey = None,
    service: FeedService = Depends(get_feed_service),
    idempotency: IdempotencyService = Depends(get_idempotency_service),
    actor: Actor = Depends(current_actor),
) -> FeedView:
    """Subscribe, and fetch the feed once right away.

    A feed that can't be fetched is still added, with `last_error` saying why.
    """
    outcome = run_once(
        idempotency,
        caller_scope("feeds", actor),
        idempotency_key,
        spec,
        create=lambda: Outcome(service.create(spec, actor), created=True),
        load=service.get,
        id_of=lambda feed: feed.id,
    )
    response.status_code = 201 if outcome.created else 200
    return FeedView.from_feed(outcome.value)


@router.post("/preview")
def preview_feed(
    body: FeedPreviewRequest, service: FeedService = Depends(get_feed_service)
) -> FeedPreviewView:
    """Fetch and read a feed without subscribing: its title, counts and newest items."""
    return FeedPreviewView.from_preview(service.preview(body.url))


@router.post("/refresh")
def refresh_all_feeds(service: FeedService = Depends(get_feed_service)) -> list[FeedView]:
    """Fetch every enabled feed now; paused ones are skipped. Problems go in `last_error`."""
    return [FeedView.from_feed(feed) for feed in service.refresh_all()]


@router.get("/summary")
def summarize_feeds(inbox: FeedInbox = Depends(get_feed_inbox)) -> FeedSummaryView:
    """How many items nobody has seen yet, in total and per feed."""
    return FeedSummaryView.from_counts(inbox.unread())


@router.get("/items")
def list_feed_items(
    feed_id: str | None = None,
    match: MatchFilter = MatchFilter.ALL,
    unseen: bool = Query(default=False, description="Only items nobody has seen yet."),
    q: str | None = Query(default=None, max_length=200, description="Text the name contains."),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = None,
    inbox: FeedInbox = Depends(get_feed_inbox),
) -> FeedItemListView:
    """Items from every feed, newest published first, each checked against the current rules."""
    query = InboxQuery(feed_id=feed_id, match=match, unseen_only=unseen, search=q or None)
    return FeedItemListView.from_page(inbox.list(query, cursor, limit))


@router.post("/items/seen")
def mark_feed_items_seen(
    body: MarkSeenRequest, inbox: FeedInbox = Depends(get_feed_inbox)
) -> MarkSeenView:
    """Mark exactly these items seen, e.g. the ones a list showed. Unknown ones are ignored."""
    return MarkSeenView(marked=inbox.mark_seen(body.info_hashes))


@router.post("/items/seen-all")
def mark_all_feed_items_seen(
    body: MarkAllSeenRequest, inbox: FeedInbox = Depends(get_feed_inbox)
) -> MarkSeenView:
    """Mark every unseen item in a view seen ("Mark all seen"), up to `up_to`.

    The view's `feed_id`, `match` and `q` apply, so items it hides stay new.
    """
    query = InboxQuery(feed_id=body.feed_id, match=body.match, search=body.q or None)
    return MarkSeenView(marked=inbox.mark_all_seen(query, body.up_to))


@router.get("/items/{info_hash}", responses=error_responses(404))
def get_feed_item(info_hash: str, inbox: FeedInbox = Depends(get_feed_inbox)) -> FeedItemView:
    return FeedItemView.from_inbox(inbox.get(info_hash))


@router.post(
    "/items/{info_hash}/download",
    status_code=202,
    responses={
        200: {"model": JobView, "description": "Already in Charon"},
        **error_responses(404, 502),
    },
)
def download_feed_item(
    info_hash: str,
    body: DownloadItemRequest,
    response: Response,
    inbox: FeedInbox = Depends(get_feed_inbox),
    actor: Actor = Depends(current_actor),
) -> JobView:
    """Download an item. Answers 200 with the existing job if the torrent is already in Charon."""
    outcome = submission_outcome(inbox.download(info_hash, body.rule_id, actor))
    response.status_code = 202 if outcome.created else 200
    return JobView.from_job(outcome.value)


@router.get("/{feed_id}", responses=error_responses(404))
def get_feed(feed_id: str, service: FeedService = Depends(get_feed_service)) -> FeedView:
    return FeedView.from_feed(service.get(feed_id))


@router.get(
    "/{feed_id}/url",
    responses=error_responses(403, 404),
    dependencies=[Depends(require_url_access)],
)
def reveal_feed_url(feed_id: str, service: FeedService = Depends(get_feed_service)) -> FeedUrlView:
    """The feed's whole address, passkey included. Admins only."""
    return FeedUrlView(url=service.get(feed_id).url)


@router.put("/{feed_id}", responses=error_responses(403, 404))
def update_feed(
    feed_id: str,
    body: FeedUpdate,
    service: FeedService = Depends(get_feed_service),
    principal: Principal = Depends(authenticate),
) -> FeedView:
    """Change a feed's settings. Changing its address (`url`) takes an admin key."""
    if body.url is not None:
        require_url_access(principal)
    return FeedView.from_feed(service.update(feed_id, body, principal.actor))


@router.delete("/{feed_id}", status_code=204, responses=error_responses(404))
def delete_feed(
    feed_id: str,
    service: FeedService = Depends(get_feed_service),
    actor: Actor = Depends(current_actor),
) -> Response:
    """Unsubscribe. Items only this feed listed are forgotten; downloads are untouched."""
    service.delete(feed_id, actor)
    return Response(status_code=204)


@router.post("/{feed_id}/refresh", responses=error_responses(404))
def refresh_feed(feed_id: str, service: FeedService = Depends(get_feed_service)) -> FeedView:
    """Fetch the feed now. Problems are reported in `last_error`, not as an error response."""
    return FeedView.from_feed(service.refresh(feed_id))

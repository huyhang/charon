from fastapi import APIRouter, Depends, Query, Response

from charon.api.deps import current_actor, get_download_service, get_idempotency_service
from charon.api.idempotency import IdempotencyKey, Outcome, caller_scope, run_once
from charon.api.schemas import (
    DownloadSummaryView,
    JobListView,
    JobView,
    SubmitDownloadRequest,
    error_responses,
)
from charon.domain.models import Actor, Job, JobStatus
from charon.services.download_service import DownloadService, Submission
from charon.services.idempotency_service import IdempotencyService

router = APIRouter(prefix="/downloads", tags=["downloads"], responses=error_responses(401, 422))


def submission_outcome(submission: Submission) -> Outcome[Job]:
    return Outcome(submission.job, submission.created)


@router.post(
    "",
    status_code=202,
    responses={
        200: {"model": JobView, "description": "Already in Charon"},
        **error_responses(409, 502),
    },
)
def submit_download(
    body: SubmitDownloadRequest,
    response: Response,
    idempotency_key: IdempotencyKey = None,
    service: DownloadService = Depends(get_download_service),
    idempotency: IdempotencyService = Depends(get_idempotency_service),
    actor: Actor = Depends(current_actor),
) -> JobView:
    """Start downloading a magnet.

    Answers 202 with a new job, or 200 with the existing job when the same torrent (same info
    hash) is already in Charon and not cancelled, or when `Idempotency-Key` repeats a request.
    """
    outcome = run_once(
        idempotency,
        caller_scope("downloads", actor),
        idempotency_key,
        body,
        create=lambda: submission_outcome(service.submit(body.magnet, body.rule_id, actor)),
        load=service.get,
        id_of=lambda job: job.id,
    )
    response.status_code = 202 if outcome.created else 200
    return JobView.from_job(outcome.value)


@router.get("")
def list_downloads(
    status: list[JobStatus] | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = None,
    service: DownloadService = Depends(get_download_service),
) -> JobListView:
    page = service.list(status, limit, cursor)
    items = [JobView.from_job(j) for j in page.items]
    return JobListView(items=items, next_cursor=page.next_cursor)


# Declared before /{job_id}, which would otherwise capture "summary" as an id.
@router.get("/summary")
def summarize_downloads(
    service: DownloadService = Depends(get_download_service),
) -> DownloadSummaryView:
    """How many jobs are in each status, and the combined download speed."""
    return DownloadSummaryView.from_summary(service.summary())


@router.get("/{job_id}", responses=error_responses(404))
def get_download(job_id: str, service: DownloadService = Depends(get_download_service)) -> JobView:
    return JobView.from_job(service.get(job_id))


@router.delete("/{job_id}", responses=error_responses(404, 409))
def cancel_download(
    job_id: str,
    service: DownloadService = Depends(get_download_service),
    actor: Actor = Depends(current_actor),
) -> JobView:
    return JobView.from_job(service.cancel(job_id, actor))


@router.post("/{job_id}/retry", status_code=202, responses=error_responses(404, 409, 502))
def retry_download(
    job_id: str,
    service: DownloadService = Depends(get_download_service),
    actor: Actor = Depends(current_actor),
) -> JobView:
    return JobView.from_job(service.retry(job_id, actor))

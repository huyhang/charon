from fastapi import APIRouter, Depends, Query

from charon.api.deps import get_download_service
from charon.api.schemas import (
    DownloadSummaryView,
    JobListView,
    JobView,
    SubmitDownloadRequest,
    error_responses,
)
from charon.domain.models import JobStatus
from charon.services.download_service import DownloadService

router = APIRouter(prefix="/downloads", tags=["downloads"], responses=error_responses(401, 422))


@router.post("", status_code=202, responses=error_responses(502))
def submit_download(
    body: SubmitDownloadRequest, service: DownloadService = Depends(get_download_service)
) -> JobView:
    return JobView.from_job(service.submit(body.magnet, body.rule_id))


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
    job_id: str, service: DownloadService = Depends(get_download_service)
) -> JobView:
    return JobView.from_job(service.cancel(job_id))


@router.post("/{job_id}/retry", status_code=202, responses=error_responses(404, 409, 502))
def retry_download(
    job_id: str, service: DownloadService = Depends(get_download_service)
) -> JobView:
    return JobView.from_job(service.retry(job_id))

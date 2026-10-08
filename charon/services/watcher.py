"""Keeps jobs in sync with the download backend and triggers post-processing."""

import asyncio
import logging
from collections.abc import Callable
from contextlib import suppress
from datetime import datetime

from charon.domain.models import (
    ACTIVE_STATUSES,
    SYSTEM,
    TASK_MISSING,
    ErrorStage,
    Job,
    JobError,
    JobStatus,
    Progress,
)
from charon.errors import DownloaderError
from charon.ports.clock import Clock, utc_now
from charon.ports.downloader import BackendStatus, BackendTask, Downloader
from charon.ports.events import EventLog
from charon.ports.stores import JobStore
from charon.services.download_folder import DownloadFolder, complete_progress
from charon.services.job_events import record_status_change
from charon.services.post_processor import PostProcessor

log = logging.getLogger(__name__)

# How many checks in a row the backend must say it has no such task before Charon believes it.
# Download Station can briefly answer "invalid task id" for a task that is finishing.
MISSING_CHECKS = 3

_STATUS_MAP = {
    BackendStatus.WAITING: JobStatus.QUEUED,
    BackendStatus.DOWNLOADING: JobStatus.DOWNLOADING,
    BackendStatus.FINISHED: JobStatus.COMPLETED,
}


class Watcher:
    def __init__(
        self,
        jobs: JobStore,
        downloader: Downloader,
        processor: PostProcessor,
        folder: DownloadFolder,
        events: EventLog,
        clock: Clock = utc_now,
        missing_checks: int = MISSING_CHECKS,
    ) -> None:
        self._jobs = jobs
        self._downloader = downloader
        self._processor = processor
        self._folder = folder
        self._events = events
        self._clock = clock
        self._missing_checks = missing_checks
        # How many checks in a row each active job's task has been missing for.
        self._misses: dict[str, int] = {}

    def tick(self) -> None:
        active = self._jobs.list(ACTIVE_STATUSES)
        self._forget_misses_except({job.id for job in active})
        for job in active:
            _isolated(self._sync, job)
        for job in self._jobs.list([JobStatus.COMPLETED]):
            _isolated(self._processor.process, job)

    def recover(self) -> None:
        """Requeue jobs left mid-processing by a previous run."""
        for job in self._jobs.list([JobStatus.PROCESSING]):
            requeued = job.model_copy(
                update={"status": JobStatus.COMPLETED, "updated_at": self._clock()}
            )
            self._jobs.update(requeued, expected=JobStatus.PROCESSING)

    def _sync(self, job: Job) -> None:
        try:
            task = self._fetch(job)
        except DownloaderError as exc:
            log.warning("could not fetch task for job %s: %s", job.id, exc)
            return
        updated = self._reconcile(job, task)
        if updated is not job and self._jobs.update(updated, expected=job.status):
            record_status_change(self._events, job, updated, SYSTEM)

    def _reconcile(self, job: Job, task: BackendTask | None) -> Job:
        if task is None:
            return self._missing(job)
        self._misses.pop(job.id, None)
        return reconcile(job, task, self._clock())

    def _missing(self, job: Job) -> Job:
        """The job, once its task has been missing long enough to believe it.

        If its whole download is then in the download folder, the backend (or someone using
        it) just dropped a finished task, so the job carries on to post-processing.
        """
        misses = self._misses.get(job.id, 0) + 1
        if misses < self._missing_checks:
            self._misses[job.id] = misses
            log.warning(
                "task %s of job %s is missing from the backend (check %d of %d)",
                job.backend_task_id,
                job.id,
                misses,
                self._missing_checks,
            )
            return job
        self._misses.pop(job.id, None)
        if self._folder.has_complete(job):
            log.warning(
                "task %s of job %s is gone, but its download is complete; processing it",
                job.backend_task_id,
                job.id,
            )
            return found_complete(job, self._clock())
        log.warning("task %s of job %s is gone from the backend", job.backend_task_id, job.id)
        return reconcile(job, None, self._clock())

    def _forget_misses_except(self, job_ids: set[str]) -> None:
        """Jobs that stopped being active (e.g. cancelled) need no count."""
        for job_id in self._misses.keys() - job_ids:
            del self._misses[job_id]

    def _fetch(self, job: Job) -> BackendTask | None:
        if job.backend_task_id is None:
            return None
        return self._downloader.get(job.backend_task_id)


def _isolated(step: Callable[[Job], object], job: Job) -> None:
    """Run one job's step so that an unexpected failure can't stall every other job."""
    try:
        step(job)
    except Exception:
        log.exception("unexpected error while handling job %s", job.id)


def reconcile(job: Job, task: BackendTask | None, now: datetime) -> Job:
    """Return the job updated from the backend task, or the same object if unchanged."""
    if task is None:
        return _failed(job, TASK_MISSING, "download task no longer exists in the backend", now)
    if task.status is BackendStatus.ERROR:
        return _failed(job, "backend_error", task.error_message or "download failed", now)
    status = _STATUS_MAP[task.status]
    updated = job.model_copy(
        update={"status": status, "name": task.name or job.name, "progress": to_progress(task)}
    )
    if updated == job:
        return job
    completed_at = now if status is JobStatus.COMPLETED else None
    return updated.model_copy(update={"updated_at": now, "completed_at": completed_at})


def found_complete(job: Job, now: datetime) -> Job:
    """The job completed, as its download folder shows after the backend dropped its task."""
    return job.model_copy(
        update={
            "status": JobStatus.COMPLETED,
            "progress": complete_progress(job),
            "updated_at": now,
            "completed_at": now,
        }
    )


def to_progress(task: BackendTask) -> Progress:
    finished = task.status is BackendStatus.FINISHED
    downloading = task.status is BackendStatus.DOWNLOADING
    return Progress(
        percent=100.0 if finished else _percent(task),
        size_bytes=task.size_bytes,
        downloaded_bytes=task.downloaded_bytes,
        download_speed_bps=task.speed_bps if downloading else None,
        eta_seconds=_eta(task) if downloading else None,
    )


def _percent(task: BackendTask) -> float:
    if not task.size_bytes:
        return 0.0
    return round(task.downloaded_bytes * 100 / task.size_bytes, 1)


def _eta(task: BackendTask) -> int | None:
    if not task.size_bytes or not task.speed_bps:
        return None
    return max(task.size_bytes - task.downloaded_bytes, 0) // task.speed_bps


def _failed(job: Job, code: str, message: str, now: datetime) -> Job:
    error = JobError(stage=ErrorStage.DOWNLOAD, code=code, message=message)
    return job.model_copy(update={"status": JobStatus.FAILED, "error": error, "updated_at": now})


async def run_periodically(
    task: Callable[[], None], interval_seconds: float, stop: asyncio.Event
) -> None:
    """Run `task` in a worker thread every interval until `stop` is set.

    Stopping is cooperative so an in-flight run always finishes before this returns;
    cancelling instead would leave the thread running against closed resources.
    """
    while not stop.is_set():
        try:
            await asyncio.to_thread(task)
        except Exception:
            log.exception("periodic task failed")
        with suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), interval_seconds)

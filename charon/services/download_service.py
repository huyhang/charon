import base64
import binascii
from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime

from charon.domain.models import (
    CANCELLABLE_STATUSES,
    ErrorStage,
    Job,
    JobStatus,
    Progress,
)
from charon.errors import ConflictError, InvalidInputError, NotFoundError
from charon.ports.clock import Clock, IdFactory, new_uuid, utc_now
from charon.ports.downloader import Downloader
from charon.ports.stores import JobCursor, JobStore
from charon.services.backend import remove_task_best_effort
from charon.services.rule_service import RuleService

MAGNET_PREFIX = "magnet:?"


@dataclass(frozen=True)
class JobPage:
    items: list[Job]
    next_cursor: str | None


class DownloadService:
    def __init__(
        self,
        jobs: JobStore,
        rules: RuleService,
        downloader: Downloader,
        clock: Clock = utc_now,
        new_id: IdFactory = new_uuid,
    ) -> None:
        self._jobs = jobs
        self._rules = rules
        self._downloader = downloader
        self._clock = clock
        self._new_id = new_id

    def submit(self, magnet: str, rule_id: str | None = None) -> Job:
        _validate_magnet(magnet)
        self._validate_rule(rule_id)
        task_id = self._downloader.add(magnet)
        now = self._clock()
        job = Job(
            id=self._new_id(),
            magnet=magnet,
            backend_task_id=task_id,
            forced_rule_id=rule_id,
            created_at=now,
            updated_at=now,
        )
        self._jobs.add(job)
        return job

    def get(self, job_id: str) -> Job:
        job = self._jobs.get(job_id)
        if job is None:
            raise NotFoundError("job_not_found", f"job {job_id} does not exist")
        return job

    def list(
        self,
        statuses: Collection[JobStatus] | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> JobPage:
        after = decode_cursor(cursor) if cursor else None
        jobs = self._jobs.list(statuses, limit + 1, after)
        page = jobs[:limit]
        has_more = len(jobs) > limit
        return JobPage(items=page, next_cursor=encode_cursor(page[-1]) if has_more else None)

    def cancel(self, job_id: str) -> Job:
        job = self.get(job_id)
        if job.status not in CANCELLABLE_STATUSES:
            raise ConflictError("job_not_cancellable", f"job is {job.status}")
        cancelled = self._save(job, status=JobStatus.CANCELLED)
        remove_task_best_effort(self._downloader, job.backend_task_id)
        return cancelled

    def retry(self, job_id: str) -> Job:
        job = self.get(job_id)
        if job.status is not JobStatus.FAILED:
            raise ConflictError("job_not_retryable", f"job is {job.status}")
        if job.error is not None and job.error.stage is ErrorStage.PROCESSING:
            return self._save(job, status=JobStatus.COMPLETED, error=None, rule_id=None)
        # The failed task would otherwise linger in the backend next to its replacement.
        remove_task_best_effort(self._downloader, job.backend_task_id)
        return self._save(
            job,
            status=JobStatus.QUEUED,
            error=None,
            backend_task_id=self._downloader.add(job.magnet),
            progress=Progress(),
            completed_at=None,
        )

    def _save(self, job: Job, **changes: object) -> Job:
        updated = job.model_copy(update={**changes, "updated_at": self._clock()})
        if not self._jobs.update(updated, expected=job.status):
            raise ConflictError("job_changed", "job changed concurrently, try again")
        return updated

    def _validate_rule(self, rule_id: str | None) -> None:
        if rule_id is None:
            return
        try:
            self._rules.get(rule_id)
        except NotFoundError as exc:
            raise InvalidInputError("unknown_rule", exc.message) from exc


def _validate_magnet(magnet: str) -> None:
    if not magnet.startswith(MAGNET_PREFIX):
        raise InvalidInputError("invalid_magnet", f"magnet link must start with {MAGNET_PREFIX}")


def encode_cursor(job: Job) -> str:
    raw = f"{job.created_at.isoformat()}|{job.id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(cursor: str) -> JobCursor:
    try:
        created_at, job_id = base64.urlsafe_b64decode(cursor).decode().split("|", 1)
        return datetime.fromisoformat(created_at), job_id
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        raise InvalidInputError("invalid_cursor", "cursor is malformed") from exc

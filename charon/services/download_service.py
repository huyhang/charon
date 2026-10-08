import base64
import binascii
from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime

from charon.domain.events import EventType
from charon.domain.magnets import (
    MAGNET_PREFIX,
    display_name,
    info_hash,
    is_magnet,
    normalize_magnet,
)
from charon.domain.models import (
    CANCELLABLE_STATUSES,
    SYSTEM,
    TASK_MISSING,
    Actor,
    ErrorStage,
    Job,
    JobStatus,
    Progress,
)
from charon.domain.times import to_utc
from charon.errors import ConflictError, InvalidInputError, NotFoundError
from charon.ports.clock import Clock, IdFactory, new_uuid, utc_now
from charon.ports.downloader import Downloader
from charon.ports.events import EventLog
from charon.ports.stores import JobCursor, JobStore
from charon.services.backend import remove_task_best_effort
from charon.services.download_folder import DownloadFolder, complete_progress
from charon.services.job_events import record_status_change
from charon.services.keyed_lock import KeyedLock
from charon.services.rule_service import RuleService

# A torrent whose job ended like this starts again when submitted, rather than being reused.
RESTARTABLE_STATUSES = frozenset({JobStatus.CANCELLED, JobStatus.FAILED})


@dataclass(frozen=True)
class JobPage:
    items: list[Job]
    next_cursor: str | None


@dataclass(frozen=True)
class Submission:
    job: Job
    # False when the torrent was already in Charon and `job` is the existing one.
    created: bool


@dataclass(frozen=True)
class JobSummary:
    # Every status is present, with zero for statuses that have no jobs.
    counts: dict[JobStatus, int]
    download_speed_bps: int


class DownloadService:
    def __init__(
        self,
        jobs: JobStore,
        rules: RuleService,
        downloader: Downloader,
        folder: DownloadFolder,
        events: EventLog,
        clock: Clock = utc_now,
        new_id: IdFactory = new_uuid,
    ) -> None:
        self._jobs = jobs
        self._rules = rules
        self._downloader = downloader
        self._folder = folder
        self._events = events
        self._clock = clock
        self._new_id = new_id
        self._submitting = KeyedLock()

    def submit(self, magnet: str, rule_id: str | None = None, actor: Actor = SYSTEM) -> Submission:
        """Start a download, unless the same torrent is already in Charon.

        A torrent whose job was cancelled or failed starts afresh. Asking for another rule
        than the existing job's raises ConflictError instead of quietly ignoring the rule.
        """
        magnet = _validated_magnet(magnet)
        self._validate_rule(rule_id)
        # Two submissions of one torrent at once would otherwise both pass the check.
        with self._submitting.hold(info_hash(magnet) or magnet):
            existing = self._existing(magnet)
            if existing is not None:
                return Submission(job=_reusable(existing, rule_id), created=False)
            job = self._start(magnet, rule_id, actor)
            self._jobs.add(job)
        self._events.record(
            EventType.JOB_CREATED,
            job.id,
            actor,
            name=display_name(magnet),
            info_hash=job.info_hash,
        )
        return Submission(job=job, created=True)

    def latest_by_hash(self, info_hashes: Collection[str]) -> dict[str, Job]:
        """The newest job for each info hash that has one."""
        return self._jobs.latest_by_hash(info_hashes) if info_hashes else {}

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

    def summary(self) -> JobSummary:
        """Totals across every job, not just one page of the list."""
        stored = self._jobs.count_by_status()
        counts = {status: stored.get(status, 0) for status in JobStatus}
        downloading = self._jobs.list([JobStatus.DOWNLOADING])
        speed = sum(job.progress.download_speed_bps or 0 for job in downloading)
        return JobSummary(counts=counts, download_speed_bps=speed)

    def cancel(self, job_id: str, actor: Actor = SYSTEM) -> Job:
        job = self.get(job_id)
        if job.status not in CANCELLABLE_STATUSES:
            raise ConflictError("job_not_cancellable", f"job is {job.status}")
        cancelled = self._save(job, actor, status=JobStatus.CANCELLED)
        remove_task_best_effort(self._downloader, job.backend_task_id)
        return cancelled

    def retry(self, job_id: str, actor: Actor = SYSTEM) -> Job:
        job = self.get(job_id)
        if job.status is not JobStatus.FAILED:
            raise ConflictError("job_not_retryable", f"job is {job.status}")
        if job.error is not None and job.error.stage is ErrorStage.PROCESSING:
            return self._save(job, actor, status=JobStatus.COMPLETED, error=None, rule_id=None)
        if self._already_downloaded(job):
            # Its task vanished, but the download is all there: post-process it, don't fetch it
            # again. Post-processing also removes the task, in case the backend still has it.
            return self._save(
                job,
                actor,
                status=JobStatus.COMPLETED,
                error=None,
                progress=complete_progress(job),
                completed_at=self._clock(),
            )
        # The failed task would otherwise linger in the backend next to its replacement.
        remove_task_best_effort(self._downloader, job.backend_task_id)
        return self._save(
            job,
            actor,
            status=JobStatus.QUEUED,
            error=None,
            backend_task_id=self._downloader.add(job.magnet),
            progress=Progress(),
            completed_at=None,
        )

    def _already_downloaded(self, job: Job) -> bool:
        missing = job.error is not None and job.error.code == TASK_MISSING
        return missing and self._folder.has_complete(job)

    def _existing(self, magnet: str) -> Job | None:
        hash_ = info_hash(magnet)
        job = self.latest_by_hash([hash_]).get(hash_) if hash_ else None
        return job if job is not None and job.status not in RESTARTABLE_STATUSES else None

    def _start(self, magnet: str, rule_id: str | None, actor: Actor) -> Job:
        task_id = self._downloader.add(magnet)
        now = self._clock()
        return Job(
            id=self._new_id(),
            magnet=magnet,
            backend_task_id=task_id,
            forced_rule_id=rule_id,
            created_at=now,
            updated_at=now,
            created_by=actor,
        )

    def _save(self, job: Job, actor: Actor, **changes: object) -> Job:
        updated = job.model_copy(update={**changes, "updated_at": self._clock()})
        if not self._jobs.update(updated, expected=job.status):
            raise ConflictError("job_changed", "job changed concurrently, try again")
        record_status_change(self._events, job, updated, actor)
        return updated

    def _validate_rule(self, rule_id: str | None) -> None:
        if rule_id is None:
            return
        try:
            self._rules.get(rule_id)
        except NotFoundError as exc:
            raise InvalidInputError("unknown_rule", exc.message) from exc


def _validated_magnet(magnet: str) -> str:
    if not is_magnet(magnet):
        raise InvalidInputError("invalid_magnet", f"magnet link must start with {MAGNET_PREFIX}")
    return normalize_magnet(magnet)


def _reusable(existing: Job, rule_id: str | None) -> Job:
    if rule_id is not None and rule_id != existing.forced_rule_id:
        raise ConflictError(
            "torrent_exists",
            "the torrent is already in Charon with another rule; cancel that job to use this one",
            details={"job_id": existing.id},
        )
    return existing


def encode_cursor(job: Job) -> str:
    raw = f"{job.created_at.isoformat()}|{job.id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(cursor: str) -> JobCursor:
    try:
        created_at, job_id = base64.urlsafe_b64decode(cursor).decode().split("|", 1)
        return to_utc(datetime.fromisoformat(created_at)), job_id
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        raise InvalidInputError("invalid_cursor", "cursor is malformed") from exc

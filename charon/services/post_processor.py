"""Renames and moves a completed download according to the matching rule."""

import logging
from pathlib import PurePosixPath

from charon.domain.destinations import DestinationPolicy
from charon.domain.models import ErrorStage, Job, JobError, JobStatus, Rule
from charon.domain.rename import is_safe_name
from charon.errors import CharonError
from charon.ports.clock import Clock, utc_now
from charon.ports.downloader import Downloader
from charon.ports.files import FileOps
from charon.ports.stores import JobStore
from charon.services.backend import remove_task_best_effort
from charon.services.rule_service import RuleService

log = logging.getLogger(__name__)


class ProcessingError(CharonError):
    pass


class PostProcessor:
    def __init__(
        self,
        jobs: JobStore,
        rules: RuleService,
        downloader: Downloader,
        files: FileOps,
        download_dir: PurePosixPath,
        policy: DestinationPolicy,
        clock: Clock = utc_now,
    ) -> None:
        self._jobs = jobs
        self._rules = rules
        self._downloader = downloader
        self._files = files
        self._download_dir = download_dir
        self._policy = policy
        self._clock = clock

    def process(self, job: Job) -> Job | None:
        """Process a completed job. Returns None if another worker claimed it first.

        A claimed job always leaves `processing`, even on an unexpected error: nothing
        else would move it on, and the API can neither cancel nor retry it there.
        """
        claimed = self._with(job, status=JobStatus.PROCESSING)
        if not self._jobs.update(claimed, expected=JobStatus.COMPLETED):
            return None
        try:
            result = self._run(claimed)
        except Exception:
            log.exception("unexpected error while processing job %s", job.id)
            result = self._failed(claimed, "internal_error", "unexpected error, see the log")
        self._jobs.update(result, expected=JobStatus.PROCESSING)
        return result

    def _run(self, job: Job) -> Job:
        try:
            rule = self._rules.select_for(job.name or "", job.forced_rule_id)
            if rule is not None:
                job = job.model_copy(update={"rule_id": rule.id})
            final_path = self._relocate(job, rule)
        except CharonError as exc:
            return self._failed(job, exc.code, exc.message)
        except OSError as exc:
            # e.g. a destination folder Charon's user can't search.
            return self._failed(job, "filesystem_error", str(exc))
        return self._with(job, status=JobStatus.DONE, final_path=str(final_path))

    def _failed(self, job: Job, code: str, message: str) -> Job:
        error = JobError(stage=ErrorStage.PROCESSING, code=code, message=message)
        return self._with(job, status=JobStatus.FAILED, error=error)

    def _relocate(self, job: Job, rule: Rule | None) -> PurePosixPath:
        source = self._source(job)
        if rule is None:
            return source
        destination = self._destination(rule, source.name)
        self._move(source, destination)
        remove_task_best_effort(self._downloader, job.backend_task_id)
        return destination

    def _source(self, job: Job) -> PurePosixPath:
        if job.name is None or not is_safe_name(job.name):
            raise ProcessingError("invalid_name", f"download name {job.name!r} is unusable")
        source = self._download_dir / job.name
        if not self._files.exists(source):
            raise ProcessingError("source_missing", f"{source} does not exist")
        return source

    def _destination(self, rule: Rule, name: str) -> PurePosixPath:
        destination = self._rules.target_for(rule, name)
        # Re-checked here, after following symlinks, because rules may predate a
        # config change and a root may contain symlinks pointing elsewhere.
        problem = self._policy.violation(self._files.resolve(destination.parent))
        if problem is not None:
            raise ProcessingError("destination_not_allowed", problem)
        if self._files.exists(destination):
            raise ProcessingError("destination_exists", f"{destination} already exists")
        return destination

    def _move(self, source: PurePosixPath, destination: PurePosixPath) -> None:
        try:
            self._files.move(source, destination)
        except OSError as exc:
            raise ProcessingError("move_failed", str(exc)) from exc

    def _with(self, job: Job, **changes: object) -> Job:
        return job.model_copy(update={**changes, "updated_at": self._clock()})

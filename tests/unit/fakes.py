"""In-memory implementations of every port, for fast isolated tests."""

import itertools
from collections.abc import Collection
from datetime import UTC, datetime, timedelta
from pathlib import PurePosixPath

from charon.domain.destinations import DestinationPolicy, normalize
from charon.domain.models import ApiKey, Job, JobStatus, Rule
from charon.errors import DownloaderError
from charon.ports.downloader import BackendTask
from charon.ports.stores import JobCursor

T0 = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)

# Permits every destination except a stand-in database directory.
ALLOW_ALL = DestinationPolicy.of(["/"], ["/data"])


class FakeClock:
    def __init__(self, start: datetime = T0) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float = 1) -> None:
        self.now += timedelta(seconds=seconds)


class SequentialIds:
    def __init__(self, prefix: str = "id") -> None:
        self._counter = itertools.count(1)
        self._prefix = prefix

    def __call__(self) -> str:
        return f"{self._prefix}-{next(self._counter)}"


class InMemoryJobStore:
    def __init__(self, jobs: Collection[Job] = ()) -> None:
        self.jobs = {job.id: job for job in jobs}

    def add(self, job: Job) -> None:
        self.jobs[job.id] = job

    def get(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id)

    def update(self, job: Job, expected: JobStatus) -> bool:
        current = self.jobs.get(job.id)
        if current is None or current.status is not expected:
            return False
        self.jobs[job.id] = job
        return True

    def list(
        self,
        statuses: Collection[JobStatus] | None = None,
        limit: int | None = None,
        after: JobCursor | None = None,
    ) -> list[Job]:
        jobs = sorted(self.jobs.values(), key=lambda j: (j.created_at, j.id), reverse=True)
        jobs = [j for j in jobs if not statuses or j.status in statuses]
        if after is not None:
            jobs = [j for j in jobs if (j.created_at, j.id) < after]
        return jobs[:limit]


class InMemoryRuleStore:
    def __init__(self, rules: Collection[Rule] = ()) -> None:
        self.rules = {rule.id: rule for rule in rules}

    def add(self, rule: Rule) -> None:
        self.rules[rule.id] = rule

    def get(self, rule_id: str) -> Rule | None:
        return self.rules.get(rule_id)

    def update(self, rule: Rule) -> bool:
        if rule.id not in self.rules:
            return False
        self.rules[rule.id] = rule
        return True

    def delete(self, rule_id: str) -> bool:
        return self.rules.pop(rule_id, None) is not None

    def list(self) -> list[Rule]:
        return sorted(self.rules.values(), key=lambda r: (r.priority, r.created_at, r.id))


class InMemoryApiKeyStore:
    def __init__(self) -> None:
        self.keys: dict[str, ApiKey] = {}

    def add(self, key: ApiKey) -> None:
        self.keys[key.id] = key

    def get(self, key_id: str) -> ApiKey | None:
        return self.keys.get(key_id)

    def find_by_hash(self, key_hash: str) -> ApiKey | None:
        return next((k for k in self.keys.values() if k.key_hash == key_hash), None)

    def update(self, key: ApiKey) -> bool:
        if key.id not in self.keys:
            return False
        self.keys[key.id] = key
        return True

    def list(self) -> list[ApiKey]:
        return list(self.keys.values())


class FakeDownloader:
    def __init__(self) -> None:
        self.tasks: dict[str, BackendTask | None] = {}
        self.added: list[str] = []
        self.removed: list[str] = []
        self.available = True
        self.fail_with: DownloaderError | None = None
        # Per-task errors raised by `get`, for exercising unexpected failures.
        self.broken: dict[str, Exception] = {}
        self._ids = SequentialIds("task")

    def add(self, magnet: str) -> str:
        self._maybe_fail()
        self.added.append(magnet)
        return self._ids()

    def get(self, task_id: str) -> BackendTask | None:
        self._maybe_fail()
        if task_id in self.broken:
            raise self.broken[task_id]
        return self.tasks.get(task_id)

    def remove(self, task_id: str) -> None:
        self._maybe_fail()
        self.removed.append(task_id)

    def is_available(self) -> bool:
        return self.available

    def _maybe_fail(self) -> None:
        if self.fail_with is not None:
            raise self.fail_with


class FakeFileOps:
    def __init__(self, existing: Collection[str] = ()) -> None:
        self.paths = {PurePosixPath(p) for p in existing}
        self.moves: list[tuple[PurePosixPath, PurePosixPath]] = []
        self.fail_with: OSError | None = None
        # Errors raised by `exists` or `resolve`, keyed by method name.
        self.fail_on: dict[str, Exception] = {}
        self.symlinks: dict[PurePosixPath, PurePosixPath] = {}

    def exists(self, path: PurePosixPath) -> bool:
        self._maybe_fail("exists")
        return path in self.paths

    def move(self, source: PurePosixPath, destination: PurePosixPath) -> None:
        if self.fail_with is not None:
            raise self.fail_with
        self.paths.discard(source)
        self.paths.add(destination)
        self.moves.append((source, destination))

    def resolve(self, path: PurePosixPath) -> PurePosixPath:
        self._maybe_fail("resolve")
        path = normalize(path)
        for link, target in self.symlinks.items():
            if path == link or link in path.parents:
                return target / path.relative_to(link)
        return path

    def _maybe_fail(self, method: str) -> None:
        if method in self.fail_on:
            raise self.fail_on[method]


def make_job(**overrides: object) -> Job:
    fields: dict[str, object] = {
        "id": "job-1",
        "magnet": "magnet:?xt=urn:btih:abc",
        "backend_task_id": "task-1",
        "created_at": T0,
        "updated_at": T0,
    }
    return Job.model_validate({**fields, **overrides})


def make_rule(**overrides: object) -> Rule:
    fields: dict[str, object] = {
        "id": "rule-1",
        "name": "rule",
        "pattern": "*",
        "destination": "/library",
        "created_at": T0,
    }
    return Rule.model_validate({**fields, **overrides})

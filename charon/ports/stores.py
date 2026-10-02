"""Persistence ports for jobs and rules."""

from collections.abc import Collection
from datetime import datetime
from typing import Protocol

from charon.domain.models import ApiKey, Job, JobStatus, Rule

# (created_at, id) of the last item already seen; listing resumes after it.
JobCursor = tuple[datetime, str]


class JobStore(Protocol):
    def add(self, job: Job) -> None: ...

    def get(self, job_id: str) -> Job | None: ...

    def update(self, job: Job, expected: JobStatus) -> bool:
        """Save the job only if its stored status is still `expected`."""
        ...

    def list(
        self,
        statuses: Collection[JobStatus] | None = None,
        limit: int | None = None,
        after: JobCursor | None = None,
    ) -> list[Job]:
        """Return jobs newest first."""
        ...


class RuleStore(Protocol):
    def add(self, rule: Rule) -> None: ...

    def get(self, rule_id: str) -> Rule | None: ...

    def update(self, rule: Rule) -> bool: ...

    def delete(self, rule_id: str) -> bool: ...

    def list(self) -> list[Rule]:
        """Return rules ordered by priority, then creation time."""
        ...


class ApiKeyStore(Protocol):
    def add(self, key: ApiKey) -> None: ...

    def get(self, key_id: str) -> ApiKey | None: ...

    def find_by_hash(self, key_hash: str) -> ApiKey | None: ...

    def update(self, key: ApiKey) -> bool: ...

    def list(self) -> list[ApiKey]:
        """Return keys oldest first."""
        ...

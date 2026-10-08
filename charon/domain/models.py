"""Core domain models. Pure data with validation, no I/O."""

from datetime import datetime
from enum import StrEnum
from pathlib import PurePosixPath

import regex
from pydantic import BaseModel, Field, ValidationInfo, field_validator

from charon.domain.destinations import normalize
from charon.domain.magnets import info_hash


class JobStatus(StrEnum):
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


ACTIVE_STATUSES = frozenset({JobStatus.QUEUED, JobStatus.DOWNLOADING})
CANCELLABLE_STATUSES = ACTIVE_STATUSES | {JobStatus.COMPLETED}


class ErrorStage(StrEnum):
    DOWNLOAD = "download"
    PROCESSING = "processing"


# The error code of a job whose backend task is gone. Retrying it may skip the download.
TASK_MISSING = "task_missing"


class JobError(BaseModel):
    stage: ErrorStage
    code: str
    message: str


class Progress(BaseModel):
    percent: float = 0.0
    size_bytes: int | None = None
    downloaded_bytes: int = 0
    download_speed_bps: int | None = None
    eta_seconds: int | None = None


class Actor(BaseModel):
    """Who made a change: whoever holds an API key, or Charon itself."""

    name: str
    key_id: str | None = Field(
        default=None, description="Null for Charon itself and the bootstrap key."
    )


SYSTEM = Actor(name="charon")


class Job(BaseModel):
    id: str
    magnet: str
    status: JobStatus = JobStatus.QUEUED
    backend_task_id: str | None = None
    name: str | None = None
    progress: Progress = Field(default_factory=Progress)
    forced_rule_id: str | None = None
    rule_id: str | None = None
    final_path: str | None = None
    error: JobError | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    created_by: Actor | None = None

    @property
    def info_hash(self) -> str | None:
        return info_hash(self.magnet)


class MatchType(StrEnum):
    GLOB = "glob"
    REGEX = "regex"


class RenameOp(StrEnum):
    REPLACE = "replace"
    REGEX_REPLACE = "regex_replace"


class RenameStep(BaseModel):
    op: RenameOp
    find: str = Field(min_length=1)
    replace: str = ""

    # Field validators (fields validate in declaration order, so earlier ones are in
    # `info.data`) so that errors point at the offending field, e.g. steps.0.replace.
    @field_validator("find")
    @classmethod
    def _check_find(cls, value: str, info: ValidationInfo) -> str:
        if info.data.get("op") is RenameOp.REGEX_REPLACE:
            _compile(value)
        return value

    @field_validator("replace")
    @classmethod
    def _check_replace(cls, value: str, info: ValidationInfo) -> str:
        find = info.data.get("find")
        if info.data.get("op") is RenameOp.REGEX_REPLACE and find is not None:
            _check_template(_compile(find), value)
        return value


class RuleSpec(BaseModel):
    """A rule as supplied by a client, before it has an identity."""

    name: str = Field(min_length=1)
    description: str = Field(
        default="", max_length=500, description="Why the rule exists, in plain words."
    )
    priority: int = 100
    enabled: bool = True
    match_type: MatchType = MatchType.GLOB
    pattern: str = Field(min_length=1)
    steps: list[RenameStep] = Field(default_factory=list)
    destination: str

    @field_validator("destination")
    @classmethod
    def _check_destination(cls, value: str) -> str:
        if not PurePosixPath(value).is_absolute():
            raise ValueError("destination must be an absolute path")
        return str(normalize(value))

    @field_validator("pattern")
    @classmethod
    def _check_pattern(cls, value: str, info: ValidationInfo) -> str:
        if info.data.get("match_type") is MatchType.REGEX:
            _compile(value)
        return value


class Rule(RuleSpec):
    id: str
    # Breaks priority ties: the older rule wins.
    created_at: datetime
    version: int = Field(default=1, description="Goes up by one on every change.")
    created_by: Actor | None = None
    updated_by: Actor | None = None


# Rules use the `regex` module (a superset of `re`) because it can time out a runaway match.
def _compile(pattern: str) -> regex.Pattern[str]:
    try:
        return regex.compile(pattern)
    except regex.error as exc:
        raise ValueError(f"invalid regex {pattern!r}: {exc}") from exc


def _check_template(pattern: regex.Pattern[str], template: str) -> None:
    # `regex` only parses a replacement once something matches, so expand it against an
    # empty partial match. No partial match means the pattern can never match, so its
    # replacement can never run.
    match = pattern.search("", partial=True)
    if match is None:
        return
    try:
        match.expand(template)
    except (regex.error, IndexError) as exc:
        raise ValueError(f"invalid replacement {template!r}: {exc}") from exc


class Role(StrEnum):
    ADMIN = "admin"
    CLIENT = "client"


class ApiKey(BaseModel):
    """A stored API key. Only the hash of the secret is kept."""

    id: str
    name: str
    role: Role
    prefix: str
    key_hash: str
    created_at: datetime
    revoked_at: datetime | None = None

    @property
    def revoked(self) -> bool:
        return self.revoked_at is not None


class Principal(BaseModel):
    """The caller a request was authenticated as."""

    name: str
    role: Role
    key_id: str | None = None

    @property
    def actor(self) -> Actor:
        return Actor(name=self.name, key_id=self.key_id)


class IdempotencyRecord(BaseModel):
    """What an earlier request carrying the same Idempotency-Key created."""

    scope: str
    key: str
    # Hash of the request body, so reusing a key for a different request is caught.
    fingerprint: str
    resource_id: str
    created_at: datetime

"""HTTP request/response shapes. Kept separate from domain models on purpose."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from charon.domain.events import Event, EventType
from charon.domain.models import (
    Actor,
    ApiKey,
    ErrorStage,
    Job,
    JobError,
    JobStatus,
    Progress,
    Role,
    RuleSpec,
)
from charon.hints import hint_for
from charon.services.api_key_service import IssuedKey
from charon.services.destination_service import FolderListing
from charon.services.download_service import JobSummary
from charon.services.event_service import EventPage
from charon.services.rule_service import Preview


class SubmitDownloadRequest(BaseModel):
    magnet: str
    rule_id: str | None = None


class JobErrorView(BaseModel):
    stage: ErrorStage
    code: str
    message: str
    hint: str | None = Field(description="What to do about it, in plain language.")

    @classmethod
    def from_error(cls, error: JobError) -> "JobErrorView":
        return cls(hint=hint_for(error.code), **error.model_dump())


class ProcessingView(BaseModel):
    rule_id: str | None
    final_path: str | None


class JobView(BaseModel):
    id: str
    status: JobStatus
    name: str | None
    magnet: str
    progress: Progress
    processing: ProcessingView
    error: JobErrorView | None
    info_hash: str | None = Field(
        description="Lowercase hex; the same for every magnet of a torrent."
    )
    created_by: Actor | None = Field(
        description="Who added it; null for jobs added before Charon recorded this."
    )
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None

    @classmethod
    def from_job(cls, job: Job) -> "JobView":
        return cls(
            processing=ProcessingView(rule_id=job.rule_id, final_path=job.final_path),
            error=JobErrorView.from_error(job.error) if job.error else None,
            info_hash=job.info_hash,
            **job.model_dump(include=set(cls.model_fields) - {"processing", "error", "info_hash"}),
        )


class JobListView(BaseModel):
    items: list[JobView]
    next_cursor: str | None


class DownloadSummaryView(BaseModel):
    counts: dict[JobStatus, int] = Field(description="Jobs per status; every status is present.")
    download_speed_bps: int = Field(description="Combined speed of every downloading job.")

    @classmethod
    def from_summary(cls, summary: JobSummary) -> "DownloadSummaryView":
        return cls(counts=summary.counts, download_speed_bps=summary.download_speed_bps)


class RuleUpdate(RuleSpec):
    version: int | None = Field(
        default=None,
        description=(
            "The version you loaded. If the rule has changed since, the save fails with "
            "409 rule_changed instead of overwriting that change. Omit to overwrite."
        ),
    )

    def spec(self) -> RuleSpec:
        return RuleSpec.model_validate(self.model_dump(exclude={"version"}))


class ReorderRulesRequest(BaseModel):
    ids: list[str] = Field(description="Every rule's id, in the new order, highest priority first.")


class PreviewRequest(BaseModel):
    name: str = Field(min_length=1)
    rule_id: str | None = Field(default=None, description="Force this saved rule.")
    rule: RuleSpec | None = Field(default=None, description="Preview this unsaved rule instead.")

    @model_validator(mode="after")
    def _one_rule_source(self) -> "PreviewRequest":
        if self.rule_id is not None and self.rule is not None:
            raise ValueError("give rule_id or rule, not both")
        return self


class PreviewView(BaseModel):
    rule_id: str | None = Field(description="The saved rule that applied, if any.")
    new_name: str
    final_path: str | None = Field(description="Null when no rule applies.")

    @classmethod
    def from_preview(cls, preview: Preview) -> "PreviewView":
        rule_id = preview.rule.id if preview.rule else None
        return cls(rule_id=rule_id, new_name=preview.new_name, final_path=preview.final_path)


class HealthView(BaseModel):
    status: Literal["ok"] = "ok"
    downloader: Literal["reachable", "unreachable"]


class DestinationRootsView(BaseModel):
    roots: list[str]


class FolderView(BaseModel):
    name: str
    path: str


class FolderListingView(BaseModel):
    path: str
    parent: str | None = Field(description="Null when going up would leave the allowed roots.")
    folders: list[FolderView]

    @classmethod
    def from_listing(cls, listing: FolderListing) -> "FolderListingView":
        folders = [FolderView(name=f.name, path=f.path) for f in listing.folders]
        return cls(path=listing.path, parent=listing.parent, folders=folders)


class CreateApiKeyRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    role: Role = Role.CLIENT


class ApiKeyView(BaseModel):
    id: str
    name: str
    role: Role
    prefix: str
    created_at: datetime
    revoked_at: datetime | None

    @classmethod
    def from_key(cls, key: ApiKey) -> "ApiKeyView":
        return cls.model_validate(key.model_dump(exclude={"key_hash"}))


class IssuedApiKeyView(ApiKeyView):
    key: str = Field(description="The secret. Shown only once; store it now.")

    @classmethod
    def from_issued(cls, issued: IssuedKey) -> "IssuedApiKeyView":
        return cls(key=issued.secret, **ApiKeyView.from_key(issued.api_key).model_dump())


class ErrorDetail(BaseModel):
    code: str = Field(description="Stable machine-readable error code.")
    message: str
    hint: str | None = Field(
        default=None, description="What to do about it, in plain language, when Charon knows."
    )
    retryable: bool = Field(
        default=False, description="Whether sending the same request again later may succeed."
    )
    details: list[dict[str, Any]] | None = Field(
        default=None, description="Field-level problems, for request validation errors."
    )


class ErrorBody(BaseModel):
    error: ErrorDetail


_ERROR_DESCRIPTIONS = {
    401: "Missing, invalid or revoked API key",
    403: "The key's role does not allow this action",
    404: "Resource not found",
    409: "Conflicts with the resource's current state",
    422: "Invalid request",
    502: "The download backend failed or is unreachable",
}


def error_responses(*status_codes: int) -> dict[int | str, dict[str, Any]]:
    """OpenAPI `responses` entries documenting Charon's error body."""
    return {
        code: {"model": ErrorBody, "description": _ERROR_DESCRIPTIONS[code]}
        for code in status_codes
    }


class PrincipalView(BaseModel):
    name: str
    role: Role
    key_id: str | None = Field(description="Null for the bootstrap admin key or when auth is off.")
    auth_enabled: bool


class EventView(BaseModel):
    id: int = Field(description="Increases with every event. Use the last one seen as `after`.")
    type: EventType
    subject_id: str = Field(description="The job, rule, feed or feed item it is about.")
    actor: Actor
    data: dict[str, Any]
    created_at: datetime

    @classmethod
    def from_event(cls, event: Event) -> "EventView":
        return cls.model_validate(event.model_dump())


class EventListView(BaseModel):
    items: list[EventView]
    cursor: int = Field(
        description="Pass as `after` to get the events that happen next. "
        "Unchanged when nothing new matched."
    )

    @classmethod
    def from_page(cls, page: EventPage) -> "EventListView":
        return cls(items=[EventView.from_event(e) for e in page.items], cursor=page.cursor)

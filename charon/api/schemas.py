"""HTTP request/response shapes. Kept separate from domain models on purpose."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from charon.domain.models import ApiKey, Job, JobError, JobStatus, Progress, Role
from charon.services.api_key_service import IssuedKey
from charon.services.rule_service import Preview


class SubmitDownloadRequest(BaseModel):
    magnet: str
    rule_id: str | None = None


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
    error: JobError | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None

    @classmethod
    def from_job(cls, job: Job) -> "JobView":
        return cls(
            processing=ProcessingView(rule_id=job.rule_id, final_path=job.final_path),
            **job.model_dump(include=set(cls.model_fields) - {"processing"}),
        )


class JobListView(BaseModel):
    items: list[JobView]
    next_cursor: str | None


class PreviewRequest(BaseModel):
    name: str = Field(min_length=1)
    rule_id: str | None = None


class PreviewView(BaseModel):
    rule_id: str | None
    new_name: str
    final_path: str | None

    @classmethod
    def from_preview(cls, preview: Preview) -> "PreviewView":
        rule_id = preview.rule.id if preview.rule else None
        return cls(rule_id=rule_id, new_name=preview.new_name, final_path=preview.final_path)


class HealthView(BaseModel):
    status: Literal["ok"] = "ok"
    downloader: Literal["reachable", "unreachable"]


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

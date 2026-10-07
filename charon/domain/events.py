"""What happened in Charon, kept so that clients can catch up from a cursor."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from charon.domain.models import Actor


class EventType(StrEnum):
    JOB_CREATED = "job.created"
    JOB_STATUS_CHANGED = "job.status_changed"
    RULE_CREATED = "rule.created"
    RULE_UPDATED = "rule.updated"
    RULE_DELETED = "rule.deleted"
    RULES_REORDERED = "rules.reordered"
    FEED_CREATED = "feed.created"
    FEED_UPDATED = "feed.updated"
    FEED_DELETED = "feed.deleted"
    FEED_HEALTH_CHANGED = "feed.health_changed"
    FEED_ITEM_ADDED = "feed_item.added"
    FEED_ITEM_DOWNLOADED = "feed_item.downloaded"


class Event(BaseModel):
    id: int = Field(default=0, description="Increases with every event; 0 until stored.")
    type: EventType
    subject_id: str = Field(description="The job, rule, feed or feed item it is about.")
    actor: Actor
    data: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


def changed_fields(before: BaseModel, after: BaseModel) -> list[str]:
    """Names of `after`'s fields whose value differs in `before`, so events say what changed."""
    old = before.model_dump()
    return sorted(name for name, value in after.model_dump().items() if old.get(name) != value)

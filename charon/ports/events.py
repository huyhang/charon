"""Port through which services report what they did."""

from typing import Protocol

from charon.domain.events import EventType
from charon.domain.models import Actor


class EventLog(Protocol):
    def record(self, type: EventType, subject_id: str, actor: Actor, **data: object) -> None:
        """Note that `actor` did something to `subject_id`; `data` must be JSON-friendly."""
        ...

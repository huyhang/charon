"""Records what happens in Charon and lets clients catch up from a cursor."""

from collections.abc import Collection
from dataclasses import dataclass
from datetime import timedelta

from charon.domain.events import Event, EventType
from charon.domain.models import Actor
from charon.ports.clock import Clock, utc_now
from charon.ports.stores import EventStore


@dataclass(frozen=True)
class EventPage:
    items: list[Event]
    # Pass as `after` to get what happens next; unchanged when nothing new matched.
    cursor: int


class EventService:
    def __init__(self, events: EventStore, clock: Clock = utc_now) -> None:
        self._events = events
        self._clock = clock

    def record(self, type: EventType, subject_id: str, actor: Actor, **data: object) -> None:
        event = Event(
            type=type, subject_id=subject_id, actor=actor, data=data, created_at=self._clock()
        )
        self._events.append(event)

    def list(
        self, after: int = 0, limit: int = 100, types: Collection[EventType] | None = None
    ) -> EventPage:
        items = self._events.list(after, limit, types)
        return EventPage(items=items, cursor=items[-1].id if items else after)

    def prune(self, max_age: timedelta) -> int:
        return self._events.prune(self._clock() - max_age)

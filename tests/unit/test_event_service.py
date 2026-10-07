from datetime import timedelta

import pytest

from charon.domain.events import EventType
from charon.domain.models import SYSTEM, Actor
from charon.services.event_service import EventService
from tests.unit.fakes import T0, FakeClock, InMemoryEventStore

PHONE = Actor(name="phone", key_id="key-1")


def make_service() -> tuple[EventService, InMemoryEventStore, FakeClock]:
    store, clock = InMemoryEventStore(), FakeClock()
    return EventService(store, clock), store, clock


def test_record_stamps_time_and_keeps_data() -> None:
    service, store, _ = make_service()
    service.record(EventType.JOB_CREATED, "job-1", PHONE, name="Show.mkv")
    [event] = store.events
    assert (event.type, event.subject_id, event.actor, event.data, event.created_at) == (
        EventType.JOB_CREATED,
        "job-1",
        PHONE,
        {"name": "Show.mkv"},
        T0,
    )


@pytest.mark.parametrize(
    ("after", "limit", "types", "ids", "cursor"),
    [
        (0, 10, None, [1, 2, 3], 3),
        (1, 1, None, [2], 2),
        (3, 10, None, [], 3),
        (0, 10, [EventType.RULE_CREATED], [2], 2),
        (2, 10, [EventType.RULE_CREATED], [], 2),
    ],
    ids=["all", "page", "caught-up", "filtered", "filtered-nothing-new"],
)
def test_list_returns_a_cursor_to_resume_from(after, limit, types, ids, cursor) -> None:
    service, _, _ = make_service()
    for type in (EventType.JOB_CREATED, EventType.RULE_CREATED, EventType.JOB_CREATED):
        service.record(type, "x", SYSTEM)
    page = service.list(after, limit, types)
    assert ([e.id for e in page.items], page.cursor) == (ids, cursor)


def test_prune_drops_events_older_than_max_age() -> None:
    service, store, clock = make_service()
    service.record(EventType.JOB_CREATED, "old", SYSTEM)
    clock.advance(3600)
    service.record(EventType.JOB_CREATED, "new", SYSTEM)
    assert service.prune(timedelta(minutes=30)) == 1
    assert [e.subject_id for e in store.events] == ["new"]

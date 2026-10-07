import logging
from datetime import timedelta

from charon.domain.events import EventType
from charon.domain.models import SYSTEM
from charon.services.event_service import EventService
from charon.services.housekeeper import Housekeeper
from charon.services.idempotency_service import IdempotencyService
from tests.unit.fakes import InMemoryEventStore, InMemoryIdempotencyStore
from tests.unit.feed_harness import FeedHarness
from tests.unit.feed_samples import hash_for, make_feed, make_item


def test_tick_prunes_old_events_keys_and_feed_items(caplog) -> None:
    h = FeedHarness(feeds=[make_feed(items_seen_at=None)])
    events = EventService(InMemoryEventStore(), h.clock)
    idempotency = IdempotencyService(InMemoryIdempotencyStore(), h.clock)
    events.record(EventType.JOB_CREATED, "job-1", SYSTEM)
    idempotency.remember("downloads", "k", "{}", "job-1")
    h.items.save([make_item(1)])
    h.items.link("feed-1", [hash_for(1)], h.clock())
    housekeeper = Housekeeper(events, idempotency, h.inbox)

    housekeeper.tick()
    assert events.list().items and idempotency.recall("downloads", "k", "{}") == "job-1"

    h.clock.advance(timedelta(days=31).total_seconds())
    # Read just now, and the item wasn't in it.
    h.feeds.update_fields("feed-1", {"items_seen_at": h.clock()})
    with caplog.at_level(logging.INFO):
        housekeeper.tick()
    assert events.list().items == []
    assert idempotency.recall("downloads", "k", "{}") is None
    assert h.items.items == {}
    assert "pruned 1 events, 1 idempotency keys, 1 feed items" in caplog.text

"""Forgets what Charon no longer needs: old events, idempotency keys and feed items."""

import logging
from datetime import timedelta

from charon.services.event_service import EventService
from charon.services.feed_inbox import FeedInbox
from charon.services.idempotency_service import IdempotencyService

log = logging.getLogger(__name__)

EVENT_RETENTION = timedelta(days=30)
IDEMPOTENCY_RETENTION = timedelta(days=1)
# How long an item stays after its feeds stop listing it.
FEED_ITEM_RETENTION = timedelta(days=30)


class Housekeeper:
    def __init__(
        self, events: EventService, idempotency: IdempotencyService, inbox: FeedInbox
    ) -> None:
        self._events = events
        self._idempotency = idempotency
        self._inbox = inbox

    def tick(self) -> None:
        events = self._events.prune(EVENT_RETENTION)
        keys = self._idempotency.prune(IDEMPOTENCY_RETENTION)
        items = self._inbox.prune(FEED_ITEM_RETENTION)
        if events or keys or items:
            log.info("pruned %d events, %d idempotency keys, %d feed items", events, keys, items)

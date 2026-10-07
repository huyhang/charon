"""Remembers what requests carrying an Idempotency-Key created, so retries don't repeat them."""

import hashlib
from contextlib import AbstractContextManager
from datetime import timedelta

from charon.domain.models import IdempotencyRecord
from charon.errors import ConflictError
from charon.ports.clock import Clock, utc_now
from charon.ports.stores import IdempotencyStore
from charon.services.keyed_lock import KeyedLock


def fingerprint(body: str) -> str:
    return hashlib.sha256(body.encode()).hexdigest()


class IdempotencyService:
    def __init__(self, records: IdempotencyStore, clock: Clock = utc_now) -> None:
        self._records = records
        self._clock = clock
        self._locks = KeyedLock()

    def exclusive(self, scope: str, key: str) -> AbstractContextManager[None]:
        """Hold while recalling, creating and remembering, so concurrent retries create once."""
        return self._locks.hold((scope, key))

    def recall(self, scope: str, key: str, body: str) -> str | None:
        """The id of what an earlier request with this key created, if there was one.

        Raises ConflictError if the key was used before for a different request.
        """
        record = self._records.get(scope, key)
        if record is None:
            return None
        if record.fingerprint != fingerprint(body):
            raise ConflictError(
                "idempotency_key_reused", "this Idempotency-Key was used for a different request"
            )
        return record.resource_id

    def remember(self, scope: str, key: str, body: str, resource_id: str) -> None:
        record = IdempotencyRecord(
            scope=scope,
            key=key,
            fingerprint=fingerprint(body),
            resource_id=resource_id,
            created_at=self._clock(),
        )
        self._records.add(record)

    def prune(self, max_age: timedelta) -> int:
        return self._records.prune(self._clock() - max_age)

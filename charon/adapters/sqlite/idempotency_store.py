from datetime import datetime

from charon.adapters.sqlite.database import Database, sortable_time
from charon.domain.models import IdempotencyRecord


class SqliteIdempotencyStore:
    def __init__(self, db: Database) -> None:
        self._db = db

    def get(self, scope: str, key: str) -> IdempotencyRecord | None:
        with self._db.transaction() as conn:
            row = conn.execute(
                "SELECT data FROM idempotency_keys WHERE scope = ? AND key = ?", (scope, key)
            ).fetchone()
        return IdempotencyRecord.model_validate_json(row[0]) if row else None

    def add(self, record: IdempotencyRecord) -> None:
        # A concurrent duplicate keeps the first record, like the request that made it.
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO idempotency_keys (scope, key, created_at, data) "
                "VALUES (?, ?, ?, ?)",
                (
                    record.scope,
                    record.key,
                    sortable_time(record.created_at),
                    record.model_dump_json(),
                ),
            )

    def prune(self, before: datetime) -> int:
        with self._db.transaction() as conn:
            cursor = conn.execute(
                "DELETE FROM idempotency_keys WHERE created_at < ?", (sortable_time(before),)
            )
        return cursor.rowcount

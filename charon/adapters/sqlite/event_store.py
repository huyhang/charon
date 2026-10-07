from collections.abc import Collection
from datetime import datetime

from charon.adapters.sqlite.database import Database, sortable_time
from charon.domain.events import Event, EventType


class SqliteEventStore:
    def __init__(self, db: Database) -> None:
        self._db = db

    def append(self, event: Event) -> Event:
        with self._db.transaction() as conn:
            cursor = conn.execute(
                "INSERT INTO events (type, created_at, data) VALUES (?, ?, ?)",
                (event.type, sortable_time(event.created_at), event.model_dump_json()),
            )
        return event.model_copy(update={"id": cursor.lastrowid})

    def list(
        self, after: int, limit: int, types: Collection[EventType] | None = None
    ) -> list[Event]:
        sql = "SELECT id, data FROM events WHERE id > ?"
        params: list[object] = [after]
        if types:
            sql += f" AND type IN ({', '.join('?' * len(types))})"
            params.extend(types)
        sql += " ORDER BY id LIMIT ?"
        params.append(limit)
        with self._db.transaction() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [
            Event.model_validate_json(data).model_copy(update={"id": id_}) for id_, data in rows
        ]

    def prune(self, before: datetime) -> int:
        with self._db.transaction() as conn:
            cursor = conn.execute(
                "DELETE FROM events WHERE created_at < ?", (sortable_time(before),)
            )
        return cursor.rowcount

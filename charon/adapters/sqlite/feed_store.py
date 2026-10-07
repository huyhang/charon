from collections.abc import Mapping

from charon.adapters.sqlite.database import Database, sortable_time
from charon.domain.feeds import Feed


class SqliteFeedStore:
    def __init__(self, db: Database) -> None:
        self._db = db

    def add(self, feed: Feed) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT INTO feeds (id, created_at, data) VALUES (?, ?, ?)",
                (feed.id, sortable_time(feed.created_at), feed.model_dump_json()),
            )

    def get(self, feed_id: str) -> Feed | None:
        with self._db.transaction() as conn:
            row = conn.execute("SELECT data FROM feeds WHERE id = ?", (feed_id,)).fetchone()
        return Feed.model_validate_json(row[0]) if row else None

    def update_fields(self, feed_id: str, changes: Mapping[str, object]) -> Feed | None:
        with self._db.transaction() as conn:
            row = conn.execute("SELECT data FROM feeds WHERE id = ?", (feed_id,)).fetchone()
            if row is None:
                return None
            feed = Feed.model_validate_json(row[0]).model_copy(update=changes)
            conn.execute(
                "UPDATE feeds SET data = ? WHERE id = ?", (feed.model_dump_json(), feed_id)
            )
        return feed

    def delete(self, feed_id: str) -> bool:
        with self._db.transaction() as conn:
            cursor = conn.execute("DELETE FROM feeds WHERE id = ?", (feed_id,))
        return cursor.rowcount == 1

    def list(self) -> list[Feed]:
        with self._db.transaction() as conn:
            rows = conn.execute("SELECT data FROM feeds ORDER BY created_at, id").fetchall()
        return [Feed.model_validate_json(row[0]) for row in rows]

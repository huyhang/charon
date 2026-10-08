from charon.adapters.sqlite.database import Database


class SqliteSettingsStore:
    def __init__(self, db: Database) -> None:
        self._db = db

    def get(self, name: str) -> str | None:
        with self._db.transaction() as conn:
            row = conn.execute("SELECT value FROM settings WHERE name = ?", (name,)).fetchone()
        return row[0] if row else None

    def set(self, name: str, value: str) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT INTO settings (name, value) VALUES (?, ?) "
                "ON CONFLICT(name) DO UPDATE SET value = excluded.value",
                (name, value),
            )

    def delete(self, name: str) -> bool:
        with self._db.transaction() as conn:
            cursor = conn.execute("DELETE FROM settings WHERE name = ?", (name,))
        return cursor.rowcount == 1

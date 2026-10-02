from charon.adapters.sqlite.database import Database
from charon.domain.models import ApiKey


class SqliteApiKeyStore:
    def __init__(self, db: Database) -> None:
        self._db = db

    def add(self, key: ApiKey) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT INTO api_keys (id, key_hash, data) VALUES (?, ?, ?)",
                (key.id, key.key_hash, key.model_dump_json()),
            )

    def get(self, key_id: str) -> ApiKey | None:
        return self._fetch_one("SELECT data FROM api_keys WHERE id = ?", key_id)

    def find_by_hash(self, key_hash: str) -> ApiKey | None:
        return self._fetch_one("SELECT data FROM api_keys WHERE key_hash = ?", key_hash)

    def update(self, key: ApiKey) -> bool:
        with self._db.transaction() as conn:
            cursor = conn.execute(
                "UPDATE api_keys SET data = ? WHERE id = ?", (key.model_dump_json(), key.id)
            )
        return cursor.rowcount == 1

    def list(self) -> list[ApiKey]:
        with self._db.transaction() as conn:
            rows = conn.execute("SELECT data FROM api_keys ORDER BY rowid").fetchall()
        return [ApiKey.model_validate_json(row[0]) for row in rows]

    def _fetch_one(self, sql: str, param: str) -> ApiKey | None:
        with self._db.transaction() as conn:
            row = conn.execute(sql, (param,)).fetchone()
        return ApiKey.model_validate_json(row[0]) if row else None

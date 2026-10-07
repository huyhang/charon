import sqlite3
from collections.abc import Mapping, Sequence

from charon.adapters.sqlite.database import Database, sortable_time
from charon.domain.models import Rule


class _StaleVersion(Exception):
    """Raised inside a transaction to roll it back."""


class SqliteRuleStore:
    def __init__(self, db: Database) -> None:
        self._db = db

    def add(self, rule: Rule) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT INTO rules (id, priority, created_at, version, data) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    rule.id,
                    rule.priority,
                    sortable_time(rule.created_at),
                    rule.version,
                    rule.model_dump_json(),
                ),
            )

    def get(self, rule_id: str) -> Rule | None:
        with self._db.transaction() as conn:
            row = conn.execute("SELECT data FROM rules WHERE id = ?", (rule_id,)).fetchone()
        return Rule.model_validate_json(row[0]) if row else None

    def update(self, rule: Rule, expected_version: int) -> bool:
        with self._db.transaction() as conn:
            return _update(conn, rule, expected_version)

    def update_all(self, rules: Sequence[Rule], snapshot: Mapping[str, int]) -> bool:
        try:
            with self._db.transaction() as conn:
                stored = dict(conn.execute("SELECT id, version FROM rules").fetchall())
                if stored != dict(snapshot):
                    raise _StaleVersion
                for rule in rules:
                    _update(conn, rule, snapshot[rule.id])
        except _StaleVersion:
            return False
        return True

    def delete(self, rule_id: str) -> bool:
        with self._db.transaction() as conn:
            cursor = conn.execute("DELETE FROM rules WHERE id = ?", (rule_id,))
        return cursor.rowcount == 1

    def list(self) -> list[Rule]:
        with self._db.transaction() as conn:
            rows = conn.execute(
                "SELECT data FROM rules ORDER BY priority, created_at, id"
            ).fetchall()
        return [Rule.model_validate_json(row[0]) for row in rows]


def _update(conn: sqlite3.Connection, rule: Rule, expected_version: int) -> bool:
    cursor = conn.execute(
        "UPDATE rules SET priority = ?, version = ?, data = ? WHERE id = ? AND version = ?",
        (rule.priority, rule.version, rule.model_dump_json(), rule.id, expected_version),
    )
    return cursor.rowcount == 1

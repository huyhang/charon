from charon.adapters.sqlite.database import Database, sortable_time
from charon.domain.models import Rule


class SqliteRuleStore:
    def __init__(self, db: Database) -> None:
        self._db = db

    def add(self, rule: Rule) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT INTO rules (id, priority, created_at, data) VALUES (?, ?, ?, ?)",
                (rule.id, rule.priority, sortable_time(rule.created_at), rule.model_dump_json()),
            )

    def get(self, rule_id: str) -> Rule | None:
        with self._db.transaction() as conn:
            row = conn.execute("SELECT data FROM rules WHERE id = ?", (rule_id,)).fetchone()
        return Rule.model_validate_json(row[0]) if row else None

    def update(self, rule: Rule) -> bool:
        with self._db.transaction() as conn:
            cursor = conn.execute(
                "UPDATE rules SET priority = ?, data = ? WHERE id = ?",
                (rule.priority, rule.model_dump_json(), rule.id),
            )
        return cursor.rowcount == 1

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

from collections.abc import Collection

from charon.adapters.sqlite.database import Database, sortable_time
from charon.domain.models import Job, JobStatus
from charon.ports.stores import JobCursor


class SqliteJobStore:
    def __init__(self, db: Database) -> None:
        self._db = db

    def add(self, job: Job) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT INTO jobs (id, status, created_at, data) VALUES (?, ?, ?, ?)",
                (job.id, job.status, sortable_time(job.created_at), job.model_dump_json()),
            )

    def get(self, job_id: str) -> Job | None:
        with self._db.transaction() as conn:
            row = conn.execute("SELECT data FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return Job.model_validate_json(row[0]) if row else None

    def update(self, job: Job, expected: JobStatus) -> bool:
        with self._db.transaction() as conn:
            cursor = conn.execute(
                "UPDATE jobs SET status = ?, data = ? WHERE id = ? AND status = ?",
                (job.status, job.model_dump_json(), job.id, expected),
            )
        return cursor.rowcount == 1

    def list(
        self,
        statuses: Collection[JobStatus] | None = None,
        limit: int | None = None,
        after: JobCursor | None = None,
    ) -> list[Job]:
        where, params = _filters(statuses, after)
        sql = f"SELECT data FROM jobs {where} ORDER BY created_at DESC, id DESC"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        with self._db.transaction() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [Job.model_validate_json(row[0]) for row in rows]


def _filters(
    statuses: Collection[JobStatus] | None, after: JobCursor | None
) -> tuple[str, list[object]]:
    clauses: list[str] = []
    params: list[object] = []
    if statuses:
        clauses.append(f"status IN ({', '.join('?' * len(statuses))})")
        params.extend(statuses)
    if after is not None:
        clauses.append("(created_at < ? OR (created_at = ? AND id < ?))")
        created_at = sortable_time(after[0])
        params.extend([created_at, created_at, after[1]])
    return ("WHERE " + " AND ".join(clauses) if clauses else ""), params

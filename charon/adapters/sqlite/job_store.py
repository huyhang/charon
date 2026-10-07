from collections.abc import Collection, Iterator
from itertools import batched

from charon.adapters.sqlite.database import Database, sortable_time
from charon.domain.models import Job, JobStatus
from charon.ports.stores import JobCursor


class SqliteJobStore:
    def __init__(self, db: Database) -> None:
        self._db = db

    def add(self, job: Job) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT INTO jobs (id, status, created_at, info_hash, data) VALUES (?, ?, ?, ?, ?)",
                (
                    job.id,
                    job.status,
                    sortable_time(job.created_at),
                    job.info_hash,
                    job.model_dump_json(),
                ),
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

    def count_by_status(self) -> dict[JobStatus, int]:
        with self._db.transaction() as conn:
            rows = conn.execute("SELECT status, COUNT(*) FROM jobs GROUP BY status").fetchall()
        return {JobStatus(status): count for status, count in rows}

    def latest_by_hash(self, info_hashes: Collection[str]) -> dict[str, Job]:
        # Oldest first, so each hash ends up mapped to its newest job.
        return {hash_: job for hash_, job in self._by_hash(info_hashes)}

    def _by_hash(self, info_hashes: Collection[str]) -> Iterator[tuple[str, Job]]:
        # Batched to stay under SQLite's limit on query parameters.
        for batch in batched(info_hashes, 500):
            marks = ", ".join("?" * len(batch))
            sql = (
                f"SELECT info_hash, data FROM jobs WHERE info_hash IN ({marks}) "
                "ORDER BY created_at, id"
            )
            with self._db.transaction() as conn:
                rows = conn.execute(sql, batch).fetchall()
            yield from ((hash_, Job.model_validate_json(data)) for hash_, data in rows)


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

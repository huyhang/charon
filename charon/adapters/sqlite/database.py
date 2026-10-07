import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from charon.adapters.sqlite.migrations import migrate

# The first release's schema. Later changes are migrations.
SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS jobs_status ON jobs (status);
CREATE INDEX IF NOT EXISTS jobs_created ON jobs (created_at DESC, id DESC);
CREATE TABLE IF NOT EXISTS rules (
    id TEXT PRIMARY KEY,
    priority INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS api_keys (
    id TEXT PRIMARY KEY,
    key_hash TEXT NOT NULL UNIQUE,
    data TEXT NOT NULL
);
"""


class Database:
    """A single shared SQLite connection, serialized with a lock."""

    def __init__(self, path: Path | str) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(SCHEMA)
            migrate(self._conn)

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock, self._conn:
            yield self._conn

    def close(self) -> None:
        self._conn.close()


def sortable_time(value: datetime) -> str:
    """Fixed-width UTC timestamp so string order matches time order."""
    utc = value.astimezone(UTC)
    # strftime's %Y doesn't pad years before 1000, which would break the ordering.
    return f"{utc.year:04d}{utc.strftime('-%m-%dT%H:%M:%S.%fZ')}"

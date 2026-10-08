"""Schema changes made after the first release, applied once each, in order.

`PRAGMA user_version` counts how many have run, so an existing database picks up only
the ones it is missing. Never edit or reorder a released migration; append a new one.
"""

import json
import sqlite3
from collections.abc import Callable

from charon.domain.magnets import info_hash

Migration = Callable[[sqlite3.Connection], None]


def _job_info_hash(conn: sqlite3.Connection) -> None:
    conn.execute("ALTER TABLE jobs ADD COLUMN info_hash TEXT")
    conn.execute("CREATE INDEX jobs_info_hash ON jobs (info_hash, created_at)")
    rows = conn.execute("SELECT id, data FROM jobs").fetchall()
    for job_id, data in rows:
        hash_ = info_hash(json.loads(data)["magnet"])
        conn.execute("UPDATE jobs SET info_hash = ? WHERE id = ?", (hash_, job_id))


def _rule_version(conn: sqlite3.Connection) -> None:
    conn.execute("ALTER TABLE rules ADD COLUMN version INTEGER NOT NULL DEFAULT 1")


def _events(conn: sqlite3.Connection) -> None:
    # AUTOINCREMENT: ids are cursors, so they must never be reused after old events are pruned.
    conn.execute(
        """CREATE TABLE events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            created_at TEXT NOT NULL,
            data TEXT NOT NULL
        )"""
    )
    conn.execute("CREATE INDEX events_created ON events (created_at)")


def _idempotency_keys(conn: sqlite3.Connection) -> None:
    conn.execute(
        """CREATE TABLE idempotency_keys (
            scope TEXT NOT NULL,
            key TEXT NOT NULL,
            created_at TEXT NOT NULL,
            data TEXT NOT NULL,
            PRIMARY KEY (scope, key)
        )"""
    )


def _feeds(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE feeds (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, data TEXT NOT NULL)"
    )
    conn.execute(
        """CREATE TABLE feed_items (
            info_hash TEXT PRIMARY KEY,
            published_at TEXT NOT NULL,
            first_seen_at TEXT NOT NULL,
            seen_at TEXT,
            job_id TEXT,
            -- The name, casefolded for case-insensitive search beyond ASCII.
            search_name TEXT NOT NULL,
            data TEXT NOT NULL
        )"""
    )
    conn.execute(
        "CREATE INDEX feed_items_published ON feed_items (published_at DESC, info_hash DESC)"
    )
    # Which feeds list each item, and when each first and last did; an item can be in several.
    conn.execute(
        """CREATE TABLE feed_item_sources (
            info_hash TEXT NOT NULL,
            feed_id TEXT NOT NULL,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            PRIMARY KEY (info_hash, feed_id)
        )"""
    )
    conn.execute("CREATE INDEX feed_item_sources_feed ON feed_item_sources (feed_id)")


def _settings(conn: sqlite3.Connection) -> None:
    # Small named settings changed while Charon runs, e.g. a metadata provider's API key.
    conn.execute("CREATE TABLE settings (name TEXT PRIMARY KEY, value TEXT NOT NULL)")


MIGRATIONS: tuple[Migration, ...] = (
    _job_info_hash,
    _rule_version,
    _events,
    _idempotency_keys,
    _feeds,
    _settings,
)


def migrate(conn: sqlite3.Connection) -> None:
    applied = conn.execute("PRAGMA user_version").fetchone()[0]
    for number, migration in enumerate(MIGRATIONS[applied:], start=applied + 1):
        with conn:
            conn.execute("BEGIN")
            migration(conn)
            conn.execute(f"PRAGMA user_version = {number}")

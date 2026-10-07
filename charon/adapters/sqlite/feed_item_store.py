import sqlite3
from collections.abc import Collection, Mapping, Sequence
from datetime import datetime
from itertools import batched

from charon.adapters.sqlite.database import Database, sortable_time
from charon.domain.feeds import FeedItem
from charon.ports.stores import ItemCursor, ItemFilter, UnreadCounts

_SELECT = """SELECT i.data,
    (SELECT group_concat(s.feed_id) FROM feed_item_sources s WHERE s.info_hash = i.info_hash)
    FROM feed_items i"""
_IN_FEED = (
    "EXISTS (SELECT 1 FROM feed_item_sources s WHERE s.info_hash = i.info_hash AND s.feed_id = ?)"
)
_LISTED_AFTER = """EXISTS (SELECT 1 FROM feed_item_sources s
    WHERE s.info_hash = i.info_hash AND (? IS NULL OR s.feed_id = ?) AND s.first_seen_at > ?)"""
_ORPHANS = """DELETE FROM feed_items WHERE NOT EXISTS
    (SELECT 1 FROM feed_item_sources s WHERE s.info_hash = feed_items.info_hash)"""
# Stays under SQLite's limit on query parameters.
_BATCH = 500


class SqliteFeedItemStore:
    def __init__(self, db: Database) -> None:
        self._db = db

    def get_many(self, info_hashes: Collection[str]) -> dict[str, FeedItem]:
        found: dict[str, FeedItem] = {}
        for batch in batched(info_hashes, _BATCH):
            with self._db.transaction() as conn:
                rows = conn.execute(f"{_SELECT} WHERE i.info_hash IN ({_marks(batch)})", batch)
                found.update((item.info_hash, item) for item in map(_item, rows.fetchall()))
        return found

    def save(self, items: Sequence[FeedItem]) -> None:
        with self._db.transaction() as conn:
            conn.executemany(
                "INSERT OR IGNORE INTO feed_items "
                "(info_hash, published_at, first_seen_at, seen_at, job_id, search_name, data) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                [(item.info_hash, *_columns(item)) for item in items],
            )

    def update(self, info_hash: str, changes: Mapping[str, object]) -> FeedItem | None:
        with self._db.transaction() as conn:
            row = conn.execute(f"{_SELECT} WHERE i.info_hash = ?", (info_hash,)).fetchone()
            if row is None:
                return None
            updated = _item(row).model_copy(update=changes)
            _replace(conn, [updated])
        return updated

    def link(self, feed_id: str, info_hashes: Collection[str], at: datetime) -> None:
        when = sortable_time(at)
        with self._db.transaction() as conn:
            conn.executemany(
                "INSERT INTO feed_item_sources (info_hash, feed_id, first_seen_at, last_seen_at) "
                "VALUES (?, ?, ?, ?) ON CONFLICT (info_hash, feed_id) "
                "DO UPDATE SET last_seen_at = excluded.last_seen_at",
                [(hash_, feed_id, when, when) for hash_ in info_hashes],
            )

    def touch(self, feed_id: str, since: datetime, at: datetime) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE feed_item_sources SET last_seen_at = ? "
                "WHERE feed_id = ? AND last_seen_at >= ?",
                (sortable_time(at), feed_id, sortable_time(since)),
            )

    def list(self, filter: ItemFilter, after: ItemCursor | None, limit: int) -> list[FeedItem]:
        where, params = _filters(filter, after)
        sql = f"{_SELECT} {where} ORDER BY i.published_at DESC, i.info_hash DESC LIMIT ?"
        with self._db.transaction() as conn:
            rows = conn.execute(sql, [*params, limit]).fetchall()
        return [_item(row) for row in rows]

    def mark_seen(self, info_hashes: Collection[str], at: datetime) -> int:
        marked = 0
        for batch in batched(info_hashes, _BATCH):
            sql = f"{_SELECT} WHERE i.seen_at IS NULL AND i.info_hash IN ({_marks(batch)})"
            with self._db.transaction() as conn:
                unseen = [_item(row) for row in conn.execute(sql, batch).fetchall()]
                _replace(conn, [item.model_copy(update={"seen_at": at}) for item in unseen])
            marked += len(unseen)
        return marked

    def unread_counts(self) -> UnreadCounts:
        with self._db.transaction() as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM feed_items WHERE seen_at IS NULL"
            ).fetchone()[0]
            rows = conn.execute(
                "SELECT s.feed_id, COUNT(*) FROM feed_item_sources s "
                "JOIN feed_items i ON i.info_hash = s.info_hash "
                "WHERE i.seen_at IS NULL GROUP BY s.feed_id"
            ).fetchall()
        return UnreadCounts(total=total, by_feed=dict(rows))

    def unlink_feed(self, feed_id: str) -> None:
        with self._db.transaction() as conn:
            conn.execute("DELETE FROM feed_item_sources WHERE feed_id = ?", (feed_id,))
            conn.execute(_ORPHANS)

    def prune(self, cutoffs: Mapping[str, datetime]) -> int:
        with self._db.transaction() as conn:
            conn.executemany(
                "DELETE FROM feed_item_sources WHERE feed_id = ? AND last_seen_at < ?",
                [(feed_id, sortable_time(cutoff)) for feed_id, cutoff in cutoffs.items()],
            )
            return conn.execute(_ORPHANS).rowcount


def _columns(item: FeedItem) -> tuple[object, ...]:
    """Every stored column but the key, in table order."""
    return (
        sortable_time(item.published_at),
        sortable_time(item.first_seen_at),
        sortable_time(item.seen_at) if item.seen_at else None,
        item.job_id,
        item.name.casefold(),
        item.model_dump_json(exclude={"feed_ids"}),
    )


def _replace(conn: sqlite3.Connection, items: Sequence[FeedItem]) -> None:
    conn.executemany(
        "UPDATE feed_items SET published_at = ?, first_seen_at = ?, seen_at = ?, job_id = ?, "
        "search_name = ?, data = ? WHERE info_hash = ?",
        [(*_columns(item), item.info_hash) for item in items],
    )


def _item(row: tuple[str, str | None]) -> FeedItem:
    data, feed_ids = row
    item = FeedItem.model_validate_json(data)
    return item.model_copy(update={"feed_ids": sorted(feed_ids.split(",")) if feed_ids else []})


def _marks(values: Sequence[object]) -> str:
    return ", ".join("?" * len(values))


def _filters(filter: ItemFilter, after: ItemCursor | None) -> tuple[str, list[object]]:
    clauses: list[str] = []
    params: list[object] = []
    if filter.feed_id is not None:
        clauses.append(_IN_FEED)
        params.append(filter.feed_id)
    if filter.unseen_only:
        clauses.append("i.seen_at IS NULL")
    if filter.search:
        clauses.append("i.search_name LIKE ? ESCAPE '\\'")
        params.append(f"%{_escape_like(filter.search.casefold())}%")
    if filter.listed_after is not None:
        clauses.append(_LISTED_AFTER)
        params.extend([filter.feed_id, filter.feed_id, sortable_time(filter.listed_after)])
    if filter.first_seen_until is not None:
        clauses.append("i.first_seen_at <= ?")
        params.append(sortable_time(filter.first_seen_until))
    if filter.without_job:
        clauses.append("i.job_id IS NULL")
    if after is not None:
        clauses.append("(i.published_at < ? OR (i.published_at = ? AND i.info_hash < ?))")
        published = sortable_time(after[0])
        params.extend([published, published, after[1]])
    return ("WHERE " + " AND ".join(clauses) if clauses else ""), params


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

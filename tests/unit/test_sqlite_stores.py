import sqlite3
from datetime import UTC, datetime, timedelta, timezone

import pytest

from charon.adapters.sqlite.api_key_store import SqliteApiKeyStore
from charon.adapters.sqlite.database import SCHEMA, Database, sortable_time
from charon.adapters.sqlite.event_store import SqliteEventStore
from charon.adapters.sqlite.idempotency_store import SqliteIdempotencyStore
from charon.adapters.sqlite.job_store import SqliteJobStore
from charon.adapters.sqlite.migrations import MIGRATIONS
from charon.adapters.sqlite.rule_store import SqliteRuleStore
from charon.adapters.sqlite.settings_store import SqliteSettingsStore
from charon.domain.events import Event, EventType
from charon.domain.models import SYSTEM, ApiKey, IdempotencyRecord, JobStatus, Role
from tests.unit.fakes import T0, InMemoryEventStore, make_job, make_rule

HASH_A = "c12fe1c06bba254a9dc9f519b335aa7c1367a88a"
HASH_B = "b" * 40


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "nested" / "charon.db")
    yield database
    database.close()


def test_job_round_trip(db) -> None:
    store = SqliteJobStore(db)
    job = make_job(name="Show.mkv")
    store.add(job)
    assert store.get(job.id) == job
    assert store.get("missing") is None


@pytest.mark.parametrize(
    ("expected", "saved"),
    [(JobStatus.QUEUED, True), (JobStatus.DOWNLOADING, False)],
)
def test_job_update_is_compare_and_set(db, expected: JobStatus, saved: bool) -> None:
    store = SqliteJobStore(db)
    store.add(make_job(status=JobStatus.QUEUED))
    updated = make_job(status=JobStatus.CANCELLED)
    assert store.update(updated, expected=expected) is saved
    assert store.get("job-1").status is (JobStatus.CANCELLED if saved else JobStatus.QUEUED)


def _seed(store: SqliteJobStore) -> None:
    statuses = [JobStatus.QUEUED, JobStatus.DONE, JobStatus.QUEUED, JobStatus.FAILED]
    for i, status in enumerate(statuses):
        store.add(make_job(id=f"j{i}", status=status, created_at=T0 + timedelta(seconds=i)))


@pytest.mark.parametrize(
    ("seeded", "expected"),
    [
        (False, {}),
        (True, {JobStatus.QUEUED: 2, JobStatus.DONE: 1, JobStatus.FAILED: 1}),
    ],
    ids=["empty", "seeded"],
)
def test_job_count_by_status(db, seeded: bool, expected: dict) -> None:
    store = SqliteJobStore(db)
    if seeded:
        _seed(store)
    assert store.count_by_status() == expected


@pytest.mark.parametrize(
    ("statuses", "limit", "after_index", "expected"),
    [
        (None, None, None, ["j3", "j2", "j1", "j0"]),
        ([JobStatus.QUEUED], None, None, ["j2", "j0"]),
        ([JobStatus.QUEUED, JobStatus.FAILED], None, None, ["j3", "j2", "j0"]),
        (None, 2, None, ["j3", "j2"]),
        (None, None, 2, ["j1", "j0"]),
        ([JobStatus.QUEUED], 1, 3, ["j2"]),
    ],
)
def test_job_list(db, statuses, limit, after_index, expected) -> None:
    store = SqliteJobStore(db)
    _seed(store)
    after = (
        (T0 + timedelta(seconds=after_index), f"j{after_index}")
        if after_index is not None
        else None
    )
    assert [j.id for j in store.list(statuses, limit, after)] == expected


def test_rule_crud(db) -> None:
    store = SqliteRuleStore(db)
    store.add(make_rule(id="b", priority=2))
    store.add(make_rule(id="a", priority=1))
    assert [r.id for r in store.list()] == ["a", "b"]
    assert store.update(make_rule(id="a", priority=3, version=2), expected_version=1) is True
    assert [r.id for r in store.list()] == ["b", "a"]
    assert store.get("a").version == 2
    assert store.update(make_rule(id="zzz"), expected_version=1) is False
    assert store.delete("a") is True
    assert store.delete("a") is False
    assert store.get("a") is None
    assert store.get("b") == make_rule(id="b", priority=2)


@pytest.mark.parametrize("insert_order", [["old", "new", "same"], ["same", "new", "old"]])
def test_rule_list_breaks_priority_ties_by_creation_time(db, insert_order: list[str]) -> None:
    rules = {
        "old": make_rule(id="old", created_at=T0),
        "new": make_rule(id="new", created_at=T0 + timedelta(microseconds=500)),
        "same": make_rule(id="same", created_at=T0 + timedelta(microseconds=500)),
    }
    store = SqliteRuleStore(db)
    for rule_id in insert_order:
        store.add(rules[rule_id])
    assert [r.id for r in store.list()] == ["old", "new", "same"]


@pytest.mark.parametrize(("expected_version", "saved"), [(1, True), (2, False)])
def test_rule_update_checks_version(db, expected_version: int, saved: bool) -> None:
    store = SqliteRuleStore(db)
    store.add(make_rule(id="a"))
    renamed = make_rule(id="a", name="renamed", version=2)
    assert store.update(renamed, expected_version=expected_version) is saved
    assert store.get("a").name == ("renamed" if saved else "rule")


def test_rule_update_all_is_all_or_nothing(db) -> None:
    store = SqliteRuleStore(db)
    store.add(make_rule(id="a", priority=1))
    store.add(make_rule(id="b", priority=2, version=5))
    moved = [make_rule(id="a", priority=3, version=2)]
    for stale in ({"a": 1, "b": 1}, {"a": 1}, {"a": 1, "b": 5, "c": 1}):
        assert store.update_all(moved, stale) is False
    assert [(r.id, r.priority) for r in store.list()] == [("a", 1), ("b", 2)]
    assert store.update_all(moved, {"a": 1, "b": 5}) is True
    assert [(r.id, r.priority, r.version) for r in store.list()] == [("b", 2, 5), ("a", 3, 2)]


@pytest.mark.parametrize(
    ("hashes", "expected"),
    [
        ([], {}),
        ([HASH_B], {}),
        ([HASH_A], {HASH_A: "newer"}),
        ([HASH_A, HASH_B], {HASH_A: "newer"}),
    ],
    ids=["none", "unknown", "newest-wins", "mixed"],
)
def test_job_latest_by_hash(db, hashes: list[str], expected: dict) -> None:
    store = SqliteJobStore(db)
    magnet = f"magnet:?xt=urn:btih:{HASH_A}"
    store.add(make_job(id="older", magnet=magnet, status=JobStatus.CANCELLED))
    store.add(make_job(id="newer", magnet=magnet, created_at=T0 + timedelta(seconds=1)))
    store.add(make_job(id="other"))
    found = store.latest_by_hash(hashes)
    assert {h: job.id for h, job in found.items()} == expected


# The in-memory fake must behave like the real store, so both run the same checks.
@pytest.fixture(params=["sqlite", "memory"])
def event_store(request, db):
    return SqliteEventStore(db) if request.param == "sqlite" else InMemoryEventStore()


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (
            datetime(2026, 10, 1, 14, tzinfo=timezone(timedelta(hours=2))),
            "2026-10-01T12:00:00.000000Z",
        ),
        (datetime(999, 1, 1, tzinfo=UTC), "0999-01-01T00:00:00.000000Z"),
    ],
    ids=["converted-to-utc", "padded-year"],
)
def test_sortable_time_is_fixed_width_utc(value: datetime, expected: str) -> None:
    assert sortable_time(value) == expected


def _event(type: EventType, seconds: int = 0) -> Event:
    return Event(
        type=type, subject_id="s", actor=SYSTEM, created_at=T0 + timedelta(seconds=seconds)
    )


@pytest.mark.parametrize(
    ("after", "limit", "types", "expected"),
    [
        (0, 10, None, [1, 2, 3]),
        (1, 10, None, [2, 3]),
        (0, 2, None, [1, 2]),
        (0, 10, [EventType.RULE_CREATED], [2]),
        (3, 10, None, []),
    ],
    ids=["all", "after-cursor", "limited", "by-type", "caught-up"],
)
def test_event_store_lists_oldest_first_after_cursor(
    event_store, after, limit, types, expected
) -> None:
    store = event_store
    for type in (EventType.JOB_CREATED, EventType.RULE_CREATED, EventType.JOB_STATUS_CHANGED):
        store.append(_event(type))
    assert [e.id for e in store.list(after, limit, types)] == expected


def test_event_store_never_reuses_ids_after_pruning(event_store) -> None:
    store = event_store
    old = store.append(_event(EventType.JOB_CREATED))
    assert store.prune(T0 + timedelta(seconds=1)) == 1
    new = store.append(_event(EventType.JOB_CREATED, seconds=2))
    assert (old.id, new.id) == (1, 2)
    assert [e.id for e in store.list(0, 10)] == [2]


def test_idempotency_store_keeps_first_record_and_prunes(db) -> None:
    store = SqliteIdempotencyStore(db)
    first = IdempotencyRecord(
        scope="downloads", key="k", fingerprint="f", resource_id="job-1", created_at=T0
    )
    store.add(first)
    store.add(first.model_copy(update={"resource_id": "job-2"}))
    assert store.get("downloads", "k") == first
    assert store.get("rules", "k") is None
    assert store.prune(T0 + timedelta(seconds=1)) == 1
    assert store.get("downloads", "k") is None


def test_migrations_upgrade_a_first_release_database(tmp_path) -> None:
    path = tmp_path / "charon.db"
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    job = make_job(magnet=f"magnet:?xt=urn:btih:{HASH_A.upper()}")
    conn.execute(
        "INSERT INTO jobs (id, status, created_at, data) VALUES (?, ?, ?, ?)",
        (job.id, job.status, "2026-10-01", job.model_dump_json()),
    )
    conn.execute(
        "INSERT INTO rules (id, priority, created_at, data) VALUES (?, ?, ?, ?)",
        ("r", 1, "2026-10-01", make_rule(id="r").model_dump_json(exclude={"version"})),
    )
    conn.commit()
    conn.close()

    db = Database(path)
    assert SqliteJobStore(db).latest_by_hash([HASH_A])[HASH_A].id == job.id
    assert SqliteRuleStore(db).update(make_rule(id="r", version=2), expected_version=1)
    with db.transaction() as c:
        assert c.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)
    db.close()


def test_data_survives_reopen(tmp_path) -> None:
    path = tmp_path / "charon.db"
    first = Database(path)
    SqliteJobStore(first).add(make_job())
    first.close()
    second = Database(path)
    assert SqliteJobStore(second).get("job-1") == make_job()
    second.close()


def test_api_key_store(db) -> None:
    store = SqliteApiKeyStore(db)
    first = ApiKey(id="k1", name="a", role=Role.CLIENT, prefix="p", key_hash="h1", created_at=T0)
    second = first.model_copy(update={"id": "k2", "key_hash": "h2"})
    store.add(first)
    store.add(second)
    assert store.get("k1") == first
    assert store.find_by_hash("h2") == second
    assert store.find_by_hash("nope") is None
    revoked = first.model_copy(update={"revoked_at": T0})
    assert store.update(revoked) is True
    assert store.update(revoked.model_copy(update={"id": "zzz"})) is False
    assert [k.id for k in store.list()] == ["k1", "k2"]
    assert store.get("k1").revoked


def test_api_key_hash_is_unique(db) -> None:
    store = SqliteApiKeyStore(db)
    key = ApiKey(id="k1", name="a", role=Role.CLIENT, prefix="p", key_hash="h", created_at=T0)
    store.add(key)
    with pytest.raises(sqlite3.IntegrityError):
        store.add(key.model_copy(update={"id": "k2"}))


@pytest.mark.parametrize(("first", "second"), [("one", "two"), ("same", "same")])
def test_settings_store_sets_overwrites_and_deletes(db, first: str, second: str) -> None:
    store = SqliteSettingsStore(db)
    assert store.get("metadata.tmdb.api_key") is None
    store.set("metadata.tmdb.api_key", first)
    store.set("metadata.tmdb.api_key", second)
    assert store.get("metadata.tmdb.api_key") == second
    assert store.delete("metadata.tmdb.api_key") is True
    assert store.delete("metadata.tmdb.api_key") is False
    assert store.get("metadata.tmdb.api_key") is None

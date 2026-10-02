import sqlite3
from datetime import timedelta

import pytest

from charon.adapters.sqlite.api_key_store import SqliteApiKeyStore
from charon.adapters.sqlite.database import Database
from charon.adapters.sqlite.job_store import SqliteJobStore
from charon.adapters.sqlite.rule_store import SqliteRuleStore
from charon.domain.models import ApiKey, JobStatus, Role
from tests.unit.fakes import T0, make_job, make_rule


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
    assert store.update(make_rule(id="a", priority=3)) is True
    assert [r.id for r in store.list()] == ["b", "a"]
    assert store.update(make_rule(id="zzz")) is False
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

from datetime import timedelta

import pytest

from charon.errors import ConflictError
from charon.services.idempotency_service import IdempotencyService
from tests.unit.fakes import FakeClock, InMemoryIdempotencyStore


def make_service() -> tuple[IdempotencyService, FakeClock]:
    clock = FakeClock()
    return IdempotencyService(InMemoryIdempotencyStore(), clock), clock


@pytest.mark.parametrize(
    ("scope", "key", "expected"),
    [("downloads", "k", "job-1"), ("downloads", "other", None), ("rules", "k", None)],
    ids=["same-key", "other-key", "other-scope"],
)
def test_recall_finds_what_the_same_key_created(scope: str, key: str, expected) -> None:
    service, _ = make_service()
    service.remember("downloads", "k", '{"magnet": "m"}', "job-1")
    assert service.recall(scope, key, '{"magnet": "m"}') == expected


def test_recall_rejects_a_key_reused_for_another_request() -> None:
    service, _ = make_service()
    service.remember("downloads", "k", '{"magnet": "m"}', "job-1")
    with pytest.raises(ConflictError) as exc_info:
        service.recall("downloads", "k", '{"magnet": "other"}')
    assert exc_info.value.code == "idempotency_key_reused"


def test_prune_forgets_old_keys() -> None:
    service, clock = make_service()
    service.remember("downloads", "k", "{}", "job-1")
    clock.advance(7200)
    assert service.prune(timedelta(hours=1)) == 1
    assert service.recall("downloads", "k", "{}") is None

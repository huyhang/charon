import time

import pytest
from fastapi.testclient import TestClient

from charon.api.app import background_work
from tests.unit.api_harness import Harness


@pytest.mark.parametrize(
    ("intervals", "expected"),
    [
        ((None, None, None), []),
        ((1.0, None, None), ["tick"]),
        ((1.0, 60.0, 3600.0), ["tick", "refresh_due", "tick"]),
        ((None, 60.0, 0), ["refresh_due"]),
    ],
    ids=["nothing", "watcher-only", "everything", "feeds-only"],
)
def test_background_work_skips_tasks_without_an_interval(intervals, expected) -> None:
    container = Harness().app.state.container
    (
        container.poll_interval_seconds,
        container.feed_poll_interval_seconds,
        container.housekeeping_interval_seconds,
    ) = intervals
    assert [task.__name__ for task, _ in background_work(container)] == expected


def test_lifespan_runs_background_work_until_shutdown() -> None:
    h = Harness()
    container = h.app.state.container
    calls: list[str] = []
    container.poll_interval_seconds = 0.01
    container.feed_poll_interval_seconds = 0.01
    container.housekeeping_interval_seconds = 0.01
    container.feed_service.refresh_due = lambda: calls.append("feeds")
    container.housekeeper.tick = lambda: calls.append("housekeeping")
    container.closers.append(lambda: calls.append("closed"))
    with TestClient(h.app):
        time.sleep(0.1)
    assert {"feeds", "housekeeping"} <= set(calls)
    assert calls[-1] == "closed"

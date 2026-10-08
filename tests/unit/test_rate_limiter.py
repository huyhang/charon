import random
import threading

import pytest

from charon.errors import RateLimitedError
from charon.services.rate_limiter import SlidingWindowLimiter, wait_needed
from tests.unit.fakes import FakeTime


def limiter(time: FakeTime, limit: int = 3, window: float = 10.0, max_wait: float = 60.0):
    return SlidingWindowLimiter(limit, window, max_wait, clock=time, sleep=time.sleep)


@pytest.mark.parametrize(
    ("sent", "now", "paused_until", "expected"),
    [
        ([], 100.0, 0.0, 0.0),
        ([99.0, 99.5], 100.0, 0.0, 0.0),  # under the limit
        ([95.0, 96.0, 97.0], 100.0, 0.0, 5.0),  # full: wait for the oldest to age out
        ([90.0, 96.0, 97.0], 100.0, 0.0, 0.0),  # the oldest left the window exactly now
        ([80.0, 85.0, 95.0, 96.0, 97.0], 100.0, 0.0, 5.0),  # long gone requests don't count
        ([91.0, 92.0, 93.0, 94.0], 100.0, 0.0, 2.0),  # over the limit: the 3rd newest decides
        ([], 100.0, 107.5, 7.5),  # paused
        ([95.0, 96.0, 97.0], 100.0, 103.0, 5.0),  # whichever is later
        ([95.0, 96.0, 97.0], 100.0, 108.0, 8.0),
        ([], 100.0, 50.0, 0.0),  # a pause in the past
    ],
)
def test_wait_needed(sent: list, now: float, paused_until: float, expected: float) -> None:
    assert wait_needed(sent, now, 3, 10.0, paused_until) == pytest.approx(expected)


def test_takes_the_limit_at_once_then_waits_for_the_oldest_to_age_out() -> None:
    time = FakeTime()
    budget = limiter(time)
    for _ in range(3):
        budget.acquire()
    assert time.slept == []
    budget.acquire()
    assert time.slept == [pytest.approx(10.0)]


@pytest.mark.parametrize("seed", range(5))
def test_never_more_than_the_limit_in_any_window(seed: int) -> None:
    """However requests arrive, no window of 10 s ever holds more than 40 sends."""
    rng = random.Random(seed)
    time = FakeTime()
    budget = limiter(time, limit=40, window=10.0)
    granted = []
    for _ in range(400):
        time.now += rng.choice([0.0, 0.0, 0.0, 0.0, 0.01, 0.1, 0.5, 3.0])
        budget.acquire()
        granted.append(time.now)
    busiest = max(sum(1 for at in granted if start - 10.0 < at <= start) for start in granted)
    assert busiest <= 40
    assert time.slept  # requests did arrive faster than the budget allows


def test_refuses_rather_than_waiting_longer_than_max_wait() -> None:
    time = FakeTime()
    budget = limiter(time, max_wait=2.0)
    for _ in range(3):
        budget.acquire()
    with pytest.raises(RateLimitedError) as caught:
        budget.acquire()
    assert caught.value.code == "metadata_rate_limited"
    assert caught.value.retry_after == pytest.approx(10.0)
    assert time.slept == []


def test_waits_when_a_slot_frees_within_max_wait() -> None:
    time = FakeTime()
    budget = limiter(time, max_wait=2.0)
    for _ in range(3):
        budget.acquire()
        time.now += 3.0
    budget.acquire()  # the first leaves the window 1 s from now
    assert time.slept == [pytest.approx(1.0)]


def test_a_pause_holds_back_the_next_request() -> None:
    time = FakeTime()
    budget = limiter(time)
    budget.pause(7.0)
    budget.acquire()
    assert time.slept == [pytest.approx(7.0)]


def test_a_shorter_pause_does_not_cut_a_longer_one() -> None:
    time = FakeTime()
    budget = limiter(time)
    budget.pause(7.0)
    budget.pause(2.0)
    budget.acquire()
    assert sum(time.slept) == pytest.approx(7.0)


def test_threads_never_share_a_slot() -> None:
    time = FakeTime()  # frozen: nobody may wait for a slot to free up
    budget = limiter(time, limit=40, max_wait=0.0)
    outcomes: list[bool] = []
    lock = threading.Lock()

    def attempt() -> None:
        try:
            budget.acquire()
            ok = True
        except RateLimitedError:
            ok = False
        with lock:
            outcomes.append(ok)

    threads = [threading.Thread(target=attempt) for _ in range(100)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert outcomes.count(True) == 40


@pytest.mark.parametrize(
    ("taken", "pause", "expected"),
    [(0, 0.0, True), (2, 0.0, True), (3, 0.0, False), (0, 5.0, False)],
    ids=["empty", "last-slot", "full", "paused"],
)
def test_try_acquire_takes_a_free_slot_or_refuses_without_waiting(
    taken: int, pause: float, expected: bool
) -> None:
    time = FakeTime()
    budget = limiter(time)  # 3 per 10 s
    for _ in range(taken):
        budget.acquire()
    budget.pause(pause)
    assert budget.try_acquire() is expected
    assert time.slept == []


def test_a_slot_taken_by_try_acquire_counts_against_the_limit() -> None:
    time = FakeTime()
    budget = limiter(time)
    assert [budget.try_acquire() for _ in range(4)] == [True, True, True, False]

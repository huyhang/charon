import threading
import time as real_time

import pytest
from pydantic import ValidationError

from charon.domain.titles import TitleMatch
from charon.errors import MetadataError, RateLimitedError
from charon.services.metadata_layers import (
    CachedProvider,
    CachePolicy,
    RateLimitedProvider,
    cache_key,
)
from charon.services.rate_limiter import SlidingWindowLimiter
from tests.unit.fakes import FakeTime, FakeTitleProvider, make_title

TITLE = make_title()
NEWER = make_title(title="The Apothecary Diaries (newer)")
POLICY = CachePolicy(fresh_seconds=100.0, empty_fresh_seconds=10.0, max_age_seconds=1000.0)
DOWN = MetadataError("metadata_unavailable", "down")
THROTTLED = RateLimitedError("metadata_rate_limited", "slow down", 5.0)


def cached(inner: FakeTitleProvider, time: FakeTime, size: int = 2) -> CachedProvider:
    return CachedProvider(inner, POLICY, size, clock=time)


@pytest.mark.parametrize(
    ("query", "expected"),
    [("Dune", "dune"), ("  DUNE  part\ttwo ", "dune part two"), ("Shōgun", "shōgun")],
)
def test_cache_key_ignores_case_and_spacing(query: str, expected: str) -> None:
    assert cache_key(query) == expected


@pytest.mark.parametrize(
    ("remembered", "age", "refresh", "budget_free", "error", "sent", "titles", "stale"),
    [
        pytest.param([TITLE], 50, False, True, None, [], [TITLE.title], False, id="fresh"),
        pytest.param(
            [TITLE], 150, False, True, None, ["search_now"], [NEWER.title], False, id="renewed"
        ),
        pytest.param(
            [TITLE], 150, False, False, None, ["search_now"], [TITLE.title], True, id="no-room"
        ),
        pytest.param(
            [TITLE], 150, False, True, DOWN, ["search_now"], [TITLE.title], True, id="down"
        ),
        pytest.param(
            [TITLE], 150, False, True, THROTTLED, ["search_now"], [TITLE.title], True, id="429"
        ),
        pytest.param([TITLE], 50, True, True, None, ["search"], [NEWER.title], False, id="refresh"),
        pytest.param(
            [TITLE], 50, True, True, DOWN, ["search"], [TITLE.title], True, id="refresh-down"
        ),
        pytest.param([], 5, False, True, None, [], [], False, id="nothing-found-fresh"),
        pytest.param(
            [], 15, False, True, None, ["search_now"], [NEWER.title], False, id="nothing-found-ages"
        ),
    ],
)
def test_what_a_lookup_serves(
    remembered: list[TitleMatch],
    age: float,
    refresh: bool,
    budget_free: bool,
    error: Exception | None,
    sent: list[str],
    titles: list[str],
    stale: bool,
) -> None:
    inner, time = FakeTitleProvider(remembered), FakeTime()
    cache = cached(inner, time)
    cache.lookup("kusuriya")
    inner.sent.clear()
    inner.matches, inner.budget_free, inner.error = [NEWER], budget_free, error
    time.now += age

    answer = cache.lookup("kusuriya", refresh)

    assert inner.sent == sent
    assert [match.title for match in answer.matches] == titles
    assert answer.stale is stale
    renewed = bool(sent) and not stale
    assert answer.age_seconds == pytest.approx(0.0 if renewed else age)


@pytest.mark.parametrize(("error", "titles"), [(None, [NEWER.title]), (DOWN, None)])
def test_answers_past_their_max_age_are_never_served(
    error: Exception | None, titles: list[str] | None
) -> None:
    inner, time = FakeTitleProvider([TITLE]), FakeTime()
    cache = cached(inner, time)
    cache.lookup("kusuriya")
    inner.matches, inner.error = [NEWER], error
    time.now += POLICY.max_age_seconds
    if titles is None:
        with pytest.raises(MetadataError):
            cache.lookup("kusuriya")
    else:
        assert [match.title for match in cache.lookup("kusuriya").matches] == titles
    assert inner.sent == ["search", "search"]  # waits for room, as for a new query


def test_a_renewed_answer_is_fresh_again() -> None:
    inner, time = FakeTitleProvider([TITLE]), FakeTime()
    cache = cached(inner, time)
    cache.lookup("dune")
    time.now += 150
    cache.lookup("dune")
    cache.lookup("dune")
    assert inner.sent == ["search", "search_now"]


def test_spelling_variants_share_an_answer() -> None:
    inner, time = FakeTitleProvider([TITLE]), FakeTime()
    cache = cached(inner, time)
    assert cache.lookup("Kusuriya").matches == [TITLE]
    assert cache.lookup("  kusuriya ").matches == [TITLE]
    assert inner.queries == ["Kusuriya"]


def test_failures_are_not_remembered() -> None:
    inner, time = FakeTitleProvider([TITLE]), FakeTime()
    cache = cached(inner, time)
    inner.error = DOWN
    with pytest.raises(MetadataError):
        cache.lookup("dune")
    inner.error = None
    assert cache.lookup("dune").matches == [TITLE]


def test_the_least_recently_used_answer_is_dropped_when_full() -> None:
    inner, time = FakeTitleProvider([TITLE]), FakeTime()
    cache = cached(inner, time, size=2)
    for query in ["a", "b", "a", "c", "a", "b"]:
        cache.lookup(query)
    # "a" was used again before "c" arrived, so "b" was dropped, then asked for again.
    assert inner.queries == ["a", "b", "c", "b"]


def test_remembered_answers_cannot_be_changed_by_callers() -> None:
    inner, time = FakeTitleProvider([TITLE]), FakeTime()
    cache = cached(inner, time)
    cache.lookup("dune").matches.clear()
    assert cache.lookup("dune").matches == [TITLE]
    with pytest.raises(ValidationError):
        TITLE.title = "Something else"


def test_clear_forgets_every_answer() -> None:
    inner, time = FakeTitleProvider([TITLE]), FakeTime()
    cache = cached(inner, time)
    cache.lookup("dune")
    cache.clear()
    cache.lookup("dune")
    assert inner.sent == ["search", "search"]


class GatedProvider(FakeTitleProvider):
    """Holds every search until released, so concurrent lookups overlap."""

    def __init__(self) -> None:
        super().__init__([TITLE])
        self.release = threading.Event()

    def search(self, query: str) -> list[TitleMatch]:
        self.release.wait(5)
        return super().search(query)


def test_concurrent_lookups_of_a_new_query_share_one_request() -> None:
    inner = GatedProvider()
    cache = CachedProvider(inner, POLICY, 10)
    answers = []

    def look_up() -> None:
        answers.append(cache.lookup("brand new"))

    threads = [threading.Thread(target=look_up) for _ in range(10)]
    for thread in threads:
        thread.start()
    real_time.sleep(0.2)
    inner.release.set()
    for thread in threads:
        thread.join()
    assert inner.sent == ["search"]
    assert [answer.matches for answer in answers] == [[TITLE]] * 10


def budgeted(inner: FakeTitleProvider, limiter: SlidingWindowLimiter) -> RateLimitedProvider:
    return RateLimitedProvider(inner, limiter, backoff_seconds=11.0, max_pause_seconds=60.0)


def make_limiter(time: FakeTime, limit: int = 2) -> SlidingWindowLimiter:
    return SlidingWindowLimiter(limit, 10.0, 60.0, clock=time, sleep=time.sleep)


def test_rate_limited_provider_takes_a_slot_per_search() -> None:
    inner, time = FakeTitleProvider([TITLE]), FakeTime()
    provider = budgeted(inner, make_limiter(time, limit=2))
    for query in ["a", "b", "c"]:
        assert provider.search(query) == [TITLE]
    assert time.slept == [pytest.approx(10.0)]


@pytest.mark.parametrize(
    ("retry_after", "expected_pause"),
    [(4.0, 4.0), (None, 11.0), (1e12, 60.0)],
    ids=["as-asked", "no-retry-after", "capped"],
)
def test_rate_limited_provider_backs_off_when_told_to(
    retry_after: float | None, expected_pause: float
) -> None:
    inner, time = FakeTitleProvider([TITLE]), FakeTime()
    provider = budgeted(inner, make_limiter(time, limit=40))
    inner.error = RateLimitedError("metadata_rate_limited", "slow down", retry_after)
    with pytest.raises(RateLimitedError) as caught:
        provider.search("a")
    assert caught.value.retry_after == pytest.approx(expected_pause)
    inner.error = None
    provider.search("b")
    assert time.slept == [pytest.approx(expected_pause)]


def test_rate_limited_provider_passes_other_failures_through() -> None:
    inner, time = FakeTitleProvider(), FakeTime()
    provider = budgeted(inner, make_limiter(time))
    inner.error = DOWN
    with pytest.raises(MetadataError):
        provider.search("a")
    inner.error = None
    provider.search("b")
    assert time.slept == []


@pytest.mark.parametrize(
    ("taken", "pause", "asks"),
    [(0, 0.0, True), (1, 0.0, True), (2, 0.0, False), (0, 5.0, False)],
    ids=["empty", "room-left", "full", "paused"],
)
def test_search_now_uses_only_room_there_is(taken: int, pause: float, asks: bool) -> None:
    inner, time = FakeTitleProvider([TITLE]), FakeTime()
    limiter = make_limiter(time, limit=2)
    provider = budgeted(inner, limiter)
    for n in range(taken):
        provider.search(f"earlier {n}")
    limiter.pause(pause)
    inner.queries.clear()
    if asks:
        assert provider.search_now("dune") == [TITLE]
    else:
        with pytest.raises(RateLimitedError):
            provider.search_now("dune")
    assert inner.queries == (["dune"] if asks else [])
    assert time.slept == []

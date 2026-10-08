import random
from collections.abc import Callable

import httpx
import pytest

from charon.adapters.tmdb.mapping import TMDB
from charon.bootstrap import (
    TMDB_CACHE,
    TMDB_REQUEST_LIMIT,
    TMDB_WINDOW_SECONDS,
    build_destination_policy,
    build_metadata,
    build_tmdb,
    metadata_key_defaults,
)
from charon.config import Settings
from charon.errors import InvalidInputError
from charon.services.metadata_layers import CachedProvider, RateLimitedProvider
from charon.services.metadata_service import MetadataSource, ProviderSummary
from charon.services.provider_keys import KeySource, ProviderKeys
from charon.services.rate_limiter import SlidingWindowLimiter
from tests.unit.fakes import FakeTime, FakeTitleProvider, InMemorySettingsStore


@pytest.mark.parametrize(
    ("ui", "destination", "allowed"),
    [
        (False, "media/tv", True),
        (False, "data", False),
        (False, "data/sub", False),
        (True, "ui", False),
        (True, "other", True),
    ],
)
def test_policy_protects_charon_directories_even_under_a_broad_root(
    tmp_path, ui: bool, destination: str, allowed: bool
) -> None:
    settings = Settings(
        _env_file=None,
        rule_roots=[tmp_path],
        db_path=tmp_path / "data" / "charon.db",
        ui_dir=tmp_path / "ui" if ui else None,
    )
    policy = build_destination_policy(settings)
    assert (policy.violation(tmp_path.resolve() / destination) is None) is allowed


@pytest.mark.parametrize(
    ("destination", "problem"),
    [
        ("real/tv", None),  # what the move-time check sees after resolving symlinks
        ("link/tv", None),  # what a client writes when the root is configured via the link
        ("link/data/sub", "protected"),  # Charon's data directory, written via the link
        ("real/data/sub", "protected"),
        ("elsewhere", "outside"),
    ],
)
def test_policy_accepts_paths_as_configured_and_resolved(
    tmp_path, destination: str, problem: str | None
) -> None:
    (tmp_path / "real").mkdir()
    (tmp_path / "link").symlink_to(tmp_path / "real")
    settings = Settings(
        _env_file=None,
        rule_roots=[tmp_path / "link"],
        db_path=tmp_path / "link" / "data" / "charon.db",
    )
    policy = build_destination_policy(settings)
    base = tmp_path if destination.startswith("link") else tmp_path.resolve()
    violation = policy.violation(base / destination)
    assert (violation is None) if problem is None else (problem in violation)


@pytest.mark.parametrize(
    ("env_token", "configured", "source"),
    [(None, False, None), ("env-token-1234567890", True, KeySource.ENVIRONMENT)],
)
def test_tmdb_is_always_offered_and_uses_the_environment_token_until_one_is_saved(
    env_token: str | None, configured: bool, source: KeySource | None
) -> None:
    closers: list = []
    settings = Settings(_env_file=None, tmdb_token=env_token)
    service = build_metadata(settings, InMemorySettingsStore(), closers)
    assert service.providers() == [ProviderSummary(TMDB, configured)]
    assert service.key_status("tmdb").source == source
    assert len(closers) == 1  # the HTTP client is closed on shutdown


def test_tmdb_sits_behind_a_cache_and_its_budget() -> None:
    keys = ProviderKeys(InMemorySettingsStore())
    source = build_tmdb(Settings(_env_file=None), keys, [])
    assert source.info == TMDB
    assert isinstance(source.provider, CachedProvider)
    assert isinstance(source.provider._inner, RateLimitedProvider)


@pytest.mark.parametrize(
    ("saved", "expected"),
    [
        (None, "Bearer env-token-1234567890"),
        ("saved-token-0987654321", "Bearer saved-token-0987654321"),
    ],
)
def test_tmdb_is_sent_the_saved_token_over_the_environments(
    saved: str | None, expected: str
) -> None:
    sent: list[str] = []

    def tmdb(request: httpx.Request) -> httpx.Response:
        sent.append(request.headers["Authorization"])
        return httpx.Response(200, json={"results": []})

    settings = Settings(_env_file=None, tmdb_token="env-token-1234567890")
    keys = ProviderKeys(InMemorySettingsStore(), metadata_key_defaults(settings))
    if saved:
        keys.set("tmdb", saved)
    build_tmdb(settings, keys, [], httpx.MockTransport(tmdb)).provider.lookup("dune")
    assert sent == [expected]


def test_a_saved_tmdb_key_must_be_a_read_access_token() -> None:
    service = build_metadata(Settings(_env_file=None), InMemorySettingsStore(), [])
    with pytest.raises(InvalidInputError) as caught:
        service.set_key("tmdb", "0123456789abcdef0123456789abcdef")
    assert caught.value.code == "metadata_key_wrong_kind"


def test_tmdb_answers_are_kept_within_tmdbs_terms() -> None:
    six_months = 182 * 24 * 3600.0
    assert TMDB_CACHE.empty_fresh_seconds <= TMDB_CACHE.fresh_seconds
    assert TMDB_CACHE.fresh_seconds <= TMDB_CACHE.max_age_seconds <= six_months


def test_tmdb_budget_is_never_more_than_40_per_10_seconds() -> None:
    assert TMDB_REQUEST_LIMIT <= 40
    assert TMDB_WINDOW_SECONDS >= 10.0


def busiest_10_seconds(arrivals: list[float]) -> int:
    return max(sum(1 for at in arrivals if start <= at < start + 10.0) for start in arrivals)


def cold_first_burst(n: int, rng: random.Random) -> float:
    # The first burst opens connections (a second's delay); later requests reuse them.
    return 1.0 if n < TMDB_REQUEST_LIMIT else 0.0


def jittery(n: int, rng: random.Random) -> float:
    return rng.uniform(0.0, 1.0)


@pytest.mark.parametrize("delay", [cold_first_burst, jittery])
def test_network_delays_cant_bunch_more_than_40_requests_into_10_seconds_at_tmdb(
    delay: Callable[[int, random.Random], float],
) -> None:
    """TMDB counts requests when they arrive. With up to a second's delay on the way, the
    padded window still keeps every 10 seconds of arrivals within 40."""
    time, rng = FakeTime(), random.Random(7)
    limiter = SlidingWindowLimiter(
        TMDB_REQUEST_LIMIT, TMDB_WINDOW_SECONDS, 60.0, clock=time, sleep=time.sleep
    )
    arrivals = []
    for n in range(200):
        limiter.acquire()
        arrivals.append(time.now + delay(n, rng))
    assert busiest_10_seconds(arrivals) <= 40


def test_build_metadata_offers_every_factorys_provider() -> None:
    source = MetadataSource(TMDB, FakeTitleProvider())
    service = build_metadata(
        Settings(_env_file=None), InMemorySettingsStore(), [], factories=[lambda s, k, c: source]
    )
    assert [summary.info for summary in service.providers()] == [TMDB]

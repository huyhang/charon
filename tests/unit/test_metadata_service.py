import pytest

from charon.adapters.tmdb.mapping import TMDB
from charon.domain.titles import KindFilter, TitleKind
from charon.errors import ConflictError, InvalidInputError, NotFoundError
from charon.services.metadata_service import MetadataService, MetadataSource, ProviderSummary
from charon.services.provider_keys import KeySource, KeyStatus, ProviderKeys
from tests.unit.fakes import FakeTitleProvider, InMemorySettingsStore, make_title

ENV_TOKEN = "env-token-1234567890"

SHOWS = [make_title(id=str(n), kind=TitleKind.TV) for n in range(12)]
FILM = make_title(id="film", kind=TitleKind.MOVIE)


@pytest.fixture
def provider() -> FakeTitleProvider:
    return FakeTitleProvider([FILM, *SHOWS])


def make_service(provider: FakeTitleProvider, env_token: str | None = ENV_TOKEN) -> MetadataService:
    keys = ProviderKeys(InMemorySettingsStore(), {"tmdb": env_token})
    return MetadataService([MetadataSource(TMDB, provider)], keys)


@pytest.fixture
def service(provider: FakeTitleProvider) -> MetadataService:
    return make_service(provider)


@pytest.mark.parametrize(("env_token", "configured"), [(ENV_TOKEN, True), (None, False)])
def test_providers_says_whether_each_has_a_key(
    provider: FakeTitleProvider, env_token: str | None, configured: bool
) -> None:
    assert make_service(provider, env_token).providers() == [ProviderSummary(TMDB, configured)]


def test_search_asks_with_the_normalized_query_and_credits_the_provider(
    service: MetadataService, provider: FakeTitleProvider
) -> None:
    found = service.search("tmdb", "  Kusuriya   no Hitorigoto ")
    assert provider.queries == ["Kusuriya no Hitorigoto"]
    assert found.attribution == TMDB


@pytest.mark.parametrize(
    ("kind", "limit", "expected_ids"),
    [
        (KindFilter.ANY, 3, ["film", "0", "1"]),
        (KindFilter.MOVIE, 10, ["film"]),
        (KindFilter.TV, 2, ["0", "1"]),
        (KindFilter.ANY, 10, ["film", *[str(n) for n in range(9)]]),
    ],
)
def test_search_filters_by_kind_then_limits(
    service: MetadataService, kind: KindFilter, limit: int, expected_ids: list[str]
) -> None:
    found = service.search("tmdb", "dune", kind, limit)
    assert [match.id for match in found.results] == expected_ids


def test_search_with_an_unknown_provider_is_not_found(service: MetadataService) -> None:
    with pytest.raises(NotFoundError) as caught:
        service.search("imdb", "dune")
    assert caught.value.code == "metadata_provider_not_found"


def test_search_refuses_a_blank_query_without_asking(
    service: MetadataService, provider: FakeTitleProvider
) -> None:
    with pytest.raises(InvalidInputError):
        service.search("tmdb", "  ")
    assert provider.queries == []


@pytest.mark.parametrize(("refresh", "stale", "age"), [(False, False, 0.0), (True, True, 42.5)])
def test_search_passes_refresh_on_and_says_how_fresh_the_answer_is(
    service: MetadataService, provider: FakeTitleProvider, refresh: bool, stale: bool, age: float
) -> None:
    provider.stale, provider.age_seconds = stale, age
    found = service.search("tmdb", "dune", refresh=refresh)
    assert provider.refreshes == [refresh]
    assert (found.stale, found.age_seconds) == (stale, age)


def test_clear_cache_clears_every_provider() -> None:
    first, second = FakeTitleProvider(), FakeTitleProvider()
    other = TMDB.model_copy(update={"id": "other"})
    sources = [MetadataSource(TMDB, first), MetadataSource(other, second)]
    MetadataService(sources, ProviderKeys(InMemorySettingsStore())).clear_cache()
    assert (first.cleared, second.cleared) == (1, 1)


def test_search_without_a_key_refuses_without_asking_even_the_cache(
    provider: FakeTitleProvider,
) -> None:
    with pytest.raises(ConflictError) as caught:
        make_service(provider, env_token=None).search("tmdb", "dune")
    assert caught.value.code == "metadata_not_configured"
    assert provider.queries == []


def test_a_saved_key_is_reported_by_its_hint_and_source(service: MetadataService) -> None:
    saved = service.set_key("tmdb", "  saved-token-0987654321  ")
    assert saved == KeyStatus(True, KeySource.SETTINGS, "4321")
    assert service.key_status("tmdb") == saved


@pytest.mark.parametrize(
    ("env_token", "after", "cache_cleared"),
    [
        (ENV_TOKEN, KeyStatus(True, KeySource.ENVIRONMENT, "7890"), 0),
        (None, KeyStatus(False), 1),
    ],
    ids=["environment-takes-over", "lookups-stop"],
)
def test_clearing_the_key_forgets_tmdbs_answers_only_once_lookups_stop(
    provider: FakeTitleProvider, env_token: str | None, after: KeyStatus, cache_cleared: int
) -> None:
    service = make_service(provider, env_token)
    service.set_key("tmdb", "saved-token-0987654321")
    assert service.clear_key("tmdb") == after
    assert provider.cleared == cache_cleared


@pytest.mark.parametrize("call", ["key_status", "set_key", "clear_key"])
def test_keys_of_unknown_providers_are_not_found(service: MetadataService, call: str) -> None:
    args = ("imdb", "some-key-1234567890") if call == "set_key" else ("imdb",)
    with pytest.raises(NotFoundError) as caught:
        getattr(service, call)(*args)
    assert caught.value.code == "metadata_provider_not_found"

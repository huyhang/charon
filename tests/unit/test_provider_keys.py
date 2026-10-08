import pytest

from charon.errors import InvalidInputError
from charon.services.provider_keys import KeySource, KeyStatus, ProviderKeys, key_hint
from tests.unit.fakes import InMemorySettingsStore

SAVED = "saved-token-0987654321"
ENV = "env-token-1234567890"


def keys(saved: str | None = None, env: str | None = None, **checks) -> ProviderKeys:
    store = InMemorySettingsStore({"metadata.tmdb.api_key": saved} if saved else {})
    return ProviderKeys(store, {"tmdb": env}, checks)


@pytest.mark.parametrize(
    ("saved", "env", "key", "status"),
    [
        (SAVED, ENV, SAVED, KeyStatus(True, KeySource.SETTINGS, "4321")),
        (None, ENV, ENV, KeyStatus(True, KeySource.ENVIRONMENT, "7890")),
        (SAVED, None, SAVED, KeyStatus(True, KeySource.SETTINGS, "4321")),
        (None, None, None, KeyStatus(False)),
    ],
    ids=["saved-wins", "environment", "saved-only", "none"],
)
def test_a_saved_key_wins_over_the_environments(
    saved: str | None, env: str | None, key: str | None, status: KeyStatus
) -> None:
    provider_keys = keys(saved, env)
    assert provider_keys.get("tmdb") == key
    assert provider_keys.status("tmdb") == status


@pytest.mark.parametrize(
    ("key", "hint"),
    [("saved-token-0987654321", "4321"), ("exactly16chars!!", "rs!!"), ("only15chars-key", None)],
    ids=["long", "shortest-hinted", "too-short"],
)
def test_only_the_last_characters_of_long_keys_are_hinted(key: str, hint: str | None) -> None:
    assert key_hint(key) == hint


def test_set_saves_the_key_trimmed() -> None:
    provider_keys = keys()
    assert provider_keys.set("tmdb", f"  {SAVED}\n") == KeyStatus(True, KeySource.SETTINGS, "4321")
    assert provider_keys.get("tmdb") == SAVED


@pytest.mark.parametrize("blank", ["", "   ", "\n"])
def test_a_blank_key_is_refused(blank: str) -> None:
    with pytest.raises(InvalidInputError) as caught:
        keys().set("tmdb", blank)
    assert caught.value.code == "invalid_metadata_key"


def test_the_providers_own_check_runs_before_saving() -> None:
    def refuse(key: str) -> None:
        raise InvalidInputError("metadata_key_wrong_kind", "not that one")

    provider_keys = keys(tmdb=refuse)
    with pytest.raises(InvalidInputError):
        provider_keys.set("tmdb", SAVED)
    assert provider_keys.get("tmdb") is None


@pytest.mark.parametrize(
    ("env", "after"),
    [(ENV, KeyStatus(True, KeySource.ENVIRONMENT, "7890")), (None, KeyStatus(False))],
)
def test_clear_forgets_the_saved_key_and_the_environment_applies_again(
    env: str | None, after: KeyStatus
) -> None:
    provider_keys = keys(SAVED, env)
    assert provider_keys.clear("tmdb") == after
    assert provider_keys.get("tmdb") == env

"""API keys for metadata providers: saved in Charon, or else taken from the environment."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum

from charon.errors import InvalidInputError
from charon.ports.stores import SettingsStore

# Only this many of a key's last characters are ever shown, and only for keys long enough that
# they give nothing useful away.
HINT_LENGTH = 4
MIN_HINTED_LENGTH = 16

# Raises InvalidInputError for a key that can't be right for its provider (e.g. the wrong kind).
KeyCheck = Callable[[str], None]


class KeySource(StrEnum):
    SETTINGS = "settings"
    ENVIRONMENT = "environment"


@dataclass(frozen=True)
class KeyStatus:
    configured: bool
    source: KeySource | None = None
    # The key's last characters, so admins can tell keys apart; never the key itself.
    hint: str | None = None


def key_hint(key: str) -> str | None:
    return key[-HINT_LENGTH:] if len(key) >= MIN_HINTED_LENGTH else None


class ProviderKeys:
    """Each provider's key: one saved here wins over the default from the environment."""

    def __init__(
        self,
        store: SettingsStore,
        defaults: Mapping[str, str | None] | None = None,
        checks: Mapping[str, KeyCheck] | None = None,
    ) -> None:
        self._store = store
        self._defaults = dict(defaults or {})
        self._checks = dict(checks or {})

    def get(self, provider_id: str) -> str | None:
        return self._store.get(_setting(provider_id)) or self._defaults.get(provider_id)

    def status(self, provider_id: str) -> KeyStatus:
        saved = self._store.get(_setting(provider_id))
        if saved:
            return KeyStatus(True, KeySource.SETTINGS, key_hint(saved))
        default = self._defaults.get(provider_id)
        if default:
            return KeyStatus(True, KeySource.ENVIRONMENT, key_hint(default))
        return KeyStatus(False)

    def set(self, provider_id: str, key: str) -> KeyStatus:
        clean = key.strip()
        if not clean:
            raise InvalidInputError("invalid_metadata_key", "the key can't be blank")
        self._checks.get(provider_id, _accept)(clean)
        self._store.set(_setting(provider_id), clean)
        return self.status(provider_id)

    def clear(self, provider_id: str) -> KeyStatus:
        """Forget the saved key; the environment's, if any, applies again."""
        self._store.delete(_setting(provider_id))
        return self.status(provider_id)


def _setting(provider_id: str) -> str:
    return f"metadata.{provider_id}.api_key"


def _accept(key: str) -> None:
    """No checks for providers that don't need any."""

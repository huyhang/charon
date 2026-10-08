from collections.abc import Sequence
from dataclasses import dataclass

from charon.domain.titles import KindFilter, ProviderInfo, TitleMatch, normalize_query, of_kind
from charon.errors import ConflictError, NotFoundError
from charon.ports.metadata import TitleLookup
from charon.services.provider_keys import KeyStatus, ProviderKeys

DEFAULT_LIMIT = 10


@dataclass(frozen=True)
class MetadataSource:
    """A provider Charon knows, with who it is for attribution."""

    info: ProviderInfo
    provider: TitleLookup


@dataclass(frozen=True)
class ProviderSummary:
    info: ProviderInfo
    # Whether it has a key, so lookups can work.
    configured: bool


@dataclass(frozen=True)
class TitleSearch:
    attribution: ProviderInfo
    results: list[TitleMatch]
    stale: bool = False
    age_seconds: float = 0.0


class MetadataService:
    """Looks up canonical titles, from providers that have a key, and manages those keys."""

    def __init__(self, sources: Sequence[MetadataSource], keys: ProviderKeys) -> None:
        self._sources = {source.info.id: source for source in sources}
        self._keys = keys

    def providers(self) -> list[ProviderSummary]:
        return [
            ProviderSummary(source.info, self._keys.status(provider_id).configured)
            for provider_id, source in self._sources.items()
        ]

    def search(
        self,
        provider_id: str,
        query: str,
        kind: KindFilter = KindFilter.ANY,
        limit: int = DEFAULT_LIMIT,
        refresh: bool = False,
    ) -> TitleSearch:
        source = self._source(provider_id)
        normalized = normalize_query(query)
        # Checked before the cache, so removing the key really switches lookups off.
        self._require_key(provider_id)
        answer = source.provider.lookup(normalized, refresh)
        results = of_kind(answer.matches, kind)[:limit]
        return TitleSearch(source.info, results, answer.stale, answer.age_seconds)

    def key_status(self, provider_id: str) -> KeyStatus:
        self._source(provider_id)
        return self._keys.status(provider_id)

    def set_key(self, provider_id: str, key: str) -> KeyStatus:
        self._source(provider_id)
        return self._keys.set(provider_id, key)

    def clear_key(self, provider_id: str) -> KeyStatus:
        """Forget the saved key. If no key is left, what the provider said is forgotten too."""
        source = self._source(provider_id)
        status = self._keys.clear(provider_id)
        if not status.configured:
            source.provider.clear()
        return status

    def clear_cache(self) -> None:
        """Forget every remembered answer, from every provider."""
        for source in self._sources.values():
            source.provider.clear()

    def _require_key(self, provider_id: str) -> None:
        if not self._keys.status(provider_id).configured:
            raise ConflictError(
                "metadata_not_configured", f"no key is set for metadata provider {provider_id!r}"
            )

    def _source(self, provider_id: str) -> MetadataSource:
        source = self._sources.get(provider_id)
        if source is None:
            raise NotFoundError(
                "metadata_provider_not_found", f"there is no metadata provider {provider_id!r}"
            )
        return source

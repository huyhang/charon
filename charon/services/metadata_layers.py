"""Layers that wrap any MetadataProvider: remembering answers, and keeping within a budget.

Stacked as Cache -> RateLimited -> real provider, so a remembered answer costs no budget.
"""

import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from charon.domain.titles import Answer, TitleMatch
from charon.errors import MetadataError, RateLimitedError
from charon.ports.metadata import MetadataProvider
from charon.services.rate_limiter import SlidingWindowLimiter
from charon.services.single_flight import SingleFlight

# However long a provider asks Charon to hold back, it holds back at most this long, so a
# garbled Retry-After can't switch lookups off until a restart.
DEFAULT_MAX_PAUSE_SECONDS = 60.0

Send = Callable[[str], list[TitleMatch]]


class RateLimitedProvider:
    """Takes a slot from `limiter` before every request, and backs off when told to."""

    def __init__(
        self,
        inner: MetadataProvider,
        limiter: SlidingWindowLimiter,
        backoff_seconds: float,
        max_pause_seconds: float = DEFAULT_MAX_PAUSE_SECONDS,
    ) -> None:
        self._inner = inner
        self._limiter = limiter
        # How long to send nothing after a 429 that doesn't say how long to wait.
        self._backoff = backoff_seconds
        self._max_pause = max_pause_seconds

    def search(self, query: str) -> list[TitleMatch]:
        """Waits (briefly) for a slot; raises RateLimitedError if none frees up in time."""
        self._limiter.acquire()
        return self._send(query)

    def search_now(self, query: str) -> list[TitleMatch]:
        """Only if a slot is free right now; otherwise RateLimitedError, without asking."""
        if not self._limiter.try_acquire():
            raise RateLimitedError("metadata_rate_limited", "no room in the budget right now")
        return self._send(query)

    def _send(self, query: str) -> list[TitleMatch]:
        try:
            return self._inner.search(query)
        except RateLimitedError as exc:
            pause = self.pause_for(exc.retry_after)
            self._limiter.pause(pause)
            raise RateLimitedError(exc.code, exc.message, pause) from exc

    def pause_for(self, retry_after: float | None) -> float:
        """As long as the provider said, or a full backoff if it didn't; never over the cap."""
        return min(retry_after or self._backoff, self._max_pause)


class BudgetedProvider(Protocol):
    """A provider that can either wait for room in its budget or only use room there is now."""

    def search(self, query: str) -> list[TitleMatch]: ...

    def search_now(self, query: str) -> list[TitleMatch]: ...


@dataclass(frozen=True)
class Entry:
    matches: tuple[TitleMatch, ...]
    fetched_at: float

    def answer(self, now: float, stale: bool = False) -> Answer:
        return Answer(list(self.matches), max(0.0, now - self.fetched_at), stale)


@dataclass(frozen=True)
class CachePolicy:
    """How long answers are trusted, and how long they may stand in when they can't be renewed."""

    fresh_seconds: float
    # Shorter for "nothing found": a new show may reach the provider later the same day.
    empty_fresh_seconds: float
    # Past this age an answer is never served, not even stale.
    max_age_seconds: float

    def is_fresh(self, entry: Entry, now: float) -> bool:
        ttl = self.fresh_seconds if entry.matches else self.empty_fresh_seconds
        return now - entry.fetched_at < ttl

    def is_usable(self, entry: Entry, now: float) -> bool:
        return now - entry.fetched_at < self.max_age_seconds


class CachedProvider:
    """Remembers answers, and keeps answering from them when the provider can't.

    - Fresh answers are served as they are.
    - Older ones (up to max_age) are renewed only if the budget has room right now, so renewing
      never queues behind or crowds out new lookups. If there's no room, or the provider fails,
      the older answer is served, marked stale.
    - With nothing usable remembered, the provider is asked (waiting briefly for room), and
      concurrent askers for the same query share that one request.
    - Failures aren't remembered. At most `max_entries` answers are kept, least recent dropped.
    """

    def __init__(
        self,
        inner: BudgetedProvider,
        policy: CachePolicy,
        max_entries: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._inner = inner
        self._policy = policy
        self._max_entries = max_entries
        self._clock = clock
        self._entries: OrderedDict[str, Entry] = OrderedDict()
        self._lock = threading.Lock()
        self._flight: SingleFlight[Entry] = SingleFlight()

    def lookup(self, query: str, refresh: bool = False) -> Answer:
        key = cache_key(query)
        entry, now = self._get(key), self._clock()
        if entry is not None and not refresh and self._policy.is_fresh(entry, now):
            return entry.answer(now)
        if entry is not None and self._policy.is_usable(entry, now):
            return self._renew(key, query, entry, refresh)
        return self._fetch(key, query, self._inner.search).answer(self._clock())

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def _renew(self, key: str, query: str, entry: Entry, refresh: bool) -> Answer:
        """A newer answer if the provider gives one; otherwise `entry`, marked stale.

        An explicit refresh may wait briefly for room; a routine renewal only uses room there is.
        """
        send = self._inner.search if refresh else self._inner.search_now
        try:
            return self._fetch(key, query, send).answer(self._clock())
        except (RateLimitedError, MetadataError):
            return entry.answer(self._clock(), stale=True)

    def _fetch(self, key: str, query: str, send: Send) -> Entry:
        return self._flight.run(key, lambda: self._remember(key, send(query)))

    def _remember(self, key: str, matches: list[TitleMatch]) -> Entry:
        entry = Entry(tuple(matches), self._clock())
        with self._lock:
            self._entries[key] = entry
            self._entries.move_to_end(key)
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)
        return entry

    def _get(self, key: str) -> Entry | None:
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None:
                self._entries.move_to_end(key)
            return entry


def cache_key(query: str) -> str:
    """Searches that differ only in case or spacing share an answer."""
    return " ".join(query.casefold().split())

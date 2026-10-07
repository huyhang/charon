"""Serializes work per key, e.g. per torrent, without blocking work on other keys."""

import threading
from collections.abc import Hashable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field


@dataclass
class _Entry:
    lock: threading.Lock = field(default_factory=threading.Lock)
    users: int = 0


class KeyedLock:
    """One lock per key, made on first use and dropped when nobody holds or waits for it.

    Charon runs as a single process, so this is enough to stop two requests for the same
    torrent (or Idempotency-Key) from both acting on a check made before either finished.
    """

    def __init__(self) -> None:
        self._guard = threading.Lock()
        self._entries: dict[Hashable, _Entry] = {}

    @contextmanager
    def hold(self, key: Hashable) -> Iterator[None]:
        entry = self._enter(key)
        try:
            with entry.lock:
                yield
        finally:
            self._leave(key, entry)

    def _enter(self, key: Hashable) -> _Entry:
        with self._guard:
            entry = self._entries.setdefault(key, _Entry())
            entry.users += 1
            return entry

    def _leave(self, key: Hashable, entry: _Entry) -> None:
        with self._guard:
            entry.users -= 1
            if entry.users == 0:
                del self._entries[key]

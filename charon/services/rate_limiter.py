"""Keeps calls to an outside service within a budget of requests per time window."""

import threading
import time
from collections import deque
from collections.abc import Callable, Sequence

from charon.errors import RateLimitedError

Clock = Callable[[], float]
Sleep = Callable[[float], None]


def wait_needed(
    sent: Sequence[float], now: float, limit: int, window: float, paused_until: float = 0.0
) -> float:
    """Seconds until one more request fits: fewer than `limit` sent in the last `window`.

    `sent` is when earlier requests went out, oldest first.
    """
    recent = [at for at in sent if at > now - window]
    slot = 0.0 if len(recent) < limit else recent[-limit] + window - now
    return max(slot, paused_until - now, 0.0)


class SlidingWindowLimiter:
    """At most `limit` requests in any `window` seconds, however they are spread.

    A sliding window rather than fixed time slots, which would allow up to twice the
    limit across a slot boundary. Thread-safe: API requests run on several threads.
    """

    def __init__(
        self,
        limit: int,
        window_seconds: float,
        max_wait_seconds: float,
        clock: Clock = time.monotonic,
        sleep: Sleep = time.sleep,
    ) -> None:
        self._limit = limit
        self._window = window_seconds
        self._max_wait = max_wait_seconds
        self._clock = clock
        self._sleep = sleep
        self._sent: deque[float] = deque()
        self._paused_until = 0.0
        self._lock = threading.Lock()

    def acquire(self) -> None:
        """Take a slot, waiting up to `max_wait_seconds` for one. Raises RateLimitedError."""
        deadline = self._clock() + self._max_wait
        while (wait := self._try_take()) > 0:
            if self._clock() + wait > deadline:
                raise RateLimitedError(
                    "metadata_rate_limited", "too many searches right now; try again shortly", wait
                )
            self._sleep(wait)

    def try_acquire(self) -> bool:
        """Take a slot only if one is free right now; never waits."""
        return self._try_take() == 0

    def pause(self, seconds: float) -> None:
        """Send nothing for `seconds`, e.g. because the service said to slow down."""
        with self._lock:
            self._paused_until = max(self._paused_until, self._clock() + seconds)

    def _try_take(self) -> float:
        """0 if a slot was taken; otherwise how long until one may be free."""
        with self._lock:
            now = self._clock()
            self._forget_before(now - self._window)
            wait = wait_needed(self._sent, now, self._limit, self._window, self._paused_until)
            if wait == 0:
                self._sent.append(now)
            return wait

    def _forget_before(self, cutoff: float) -> None:
        while self._sent and self._sent[0] <= cutoff:
            self._sent.popleft()

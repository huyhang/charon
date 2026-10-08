"""Lets concurrent callers asking for the same thing share one call's outcome."""

import threading
from collections.abc import Callable
from concurrent.futures import Future


class SingleFlight[T]:
    """While a call for a key runs, callers for the same key wait for it instead of repeating it.

    They all get its result, or its error. A later call, once it has finished, runs afresh.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._running: dict[str, Future[T]] = {}

    def run(self, key: str, call: Callable[[], T]) -> T:
        future, leading = self._join(key)
        if leading:
            self._settle(key, future, call)
        return future.result()

    def _join(self, key: str) -> tuple[Future[T], bool]:
        """The call running for `key`, or a new one this caller must make (True)."""
        with self._lock:
            if key in self._running:
                return self._running[key], False
            future: Future[T] = Future()
            self._running[key] = future
            return future, True

    def _settle(self, key: str, future: Future[T], call: Callable[[], T]) -> None:
        try:
            future.set_result(call())
        except Exception as exc:
            # Not swallowed: future.result() raises it for the leader and every waiter.
            future.set_exception(exc)
        finally:
            with self._lock:
                del self._running[key]

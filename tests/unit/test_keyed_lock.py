import threading
import time

import pytest

from charon.services.keyed_lock import KeyedLock


@pytest.mark.parametrize(
    ("second_key", "order"),
    [("torrent", ["first", "second"]), ("other-torrent", ["second", "first"])],
    ids=["same-key-waits", "other-key-doesnt"],
)
def test_a_key_is_held_by_one_caller_at_a_time(second_key: str, order: list[str]) -> None:
    lock, finished, holding = KeyedLock(), [], threading.Event()

    def first() -> None:
        with lock.hold("torrent"):
            holding.set()
            time.sleep(0.05)
            finished.append("first")

    def second() -> None:
        holding.wait()
        with lock.hold(second_key):
            finished.append("second")

    threads = [threading.Thread(target=first), threading.Thread(target=second)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert finished == order


def test_locks_are_dropped_once_nobody_needs_them() -> None:
    lock = KeyedLock()
    with lock.hold("torrent"):
        pass
    assert lock._entries == {}

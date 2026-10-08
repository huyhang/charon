import threading
import time

import pytest

from charon.services.single_flight import SingleFlight

# Long enough for every thread to have joined the running call before it is let finish.
JOIN_GRACE_SECONDS = 0.2


class GatedCall:
    """A call that blocks until released, counting how often it actually ran."""

    def __init__(self, outcome: object) -> None:
        self.outcome = outcome
        self.runs = 0
        self.release = threading.Event()

    def __call__(self) -> object:
        self.runs += 1
        self.release.wait(5)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def run_concurrently(flight: SingleFlight, call: GatedCall, callers: int) -> list[object]:
    outcomes: list[object] = []
    lock = threading.Lock()

    def attempt() -> None:
        try:
            result: object = flight.run("dune", call)
        except Exception as exc:
            result = exc
        with lock:
            outcomes.append(result)

    threads = [threading.Thread(target=attempt) for _ in range(callers)]
    for thread in threads:
        thread.start()
    time.sleep(JOIN_GRACE_SECONDS)
    call.release.set()
    for thread in threads:
        thread.join()
    return outcomes


@pytest.mark.parametrize("outcome", ["the answer", ValueError("provider down")])
def test_concurrent_callers_share_one_calls_outcome(outcome: object) -> None:
    call = GatedCall(outcome)
    outcomes = run_concurrently(SingleFlight(), call, callers=10)
    assert call.runs == 1
    assert len(outcomes) == 10
    assert all(result is outcome for result in outcomes)


@pytest.mark.parametrize(("first", "second"), [("dune", "dune"), ("dune", "andor")])
def test_calls_that_dont_overlap_each_run(first: str, second: str) -> None:
    flight: SingleFlight[int] = SingleFlight()
    runs: list[str] = []
    for key in (first, second):
        flight.run(key, lambda key=key: runs.append(key) or len(runs))
    assert runs == [first, second]


def test_a_failed_call_does_not_stick() -> None:
    flight: SingleFlight[str] = SingleFlight()

    def fail() -> str:
        raise ValueError("down")

    with pytest.raises(ValueError):
        flight.run("dune", fail)
    assert flight.run("dune", lambda: "back") == "back"

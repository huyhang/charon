import time

import pytest

from fake_ds.seed import SAMPLES, Seeder
from tests.e2e.conftest import Stack

# Where each sample settles. "downloading" samples may finish while we wait.
EXPECTED: dict[str, tuple[set[str], str | None]] = {
    "done": ({"done"}, None),
    "collides": ({"failed"}, "destination_exists"),
    "failed": ({"failed"}, "backend_error"),
    "cancelled": ({"cancelled"}, None),
    "downloading": ({"queued", "downloading", "completed", "processing", "done"}, None),
}

pytestmark = pytest.mark.e2e


def settled(stack: Stack, job_ids: dict[str, str]) -> dict[str, dict]:
    """Each sample's job, once it reaches an expected status (or after a timeout)."""
    deadline = time.monotonic() + 20
    while True:
        jobs = {name: stack.charon.get(f"/downloads/{i}").json() for name, i in job_ids.items()}
        pending = [s for s in SAMPLES if jobs[s.name]["status"] not in EXPECTED[s.outcome][0]]
        if not pending or time.monotonic() > deadline:
            return jobs
        time.sleep(0.2)


def test_seed_produces_every_state_and_files_downloads(stack: Stack) -> None:
    report = Seeder(stack.charon, stack.fake, stack.library_local).run()

    jobs = settled(stack, report.jobs)
    for sample in SAMPLES:
        statuses, code = EXPECTED[sample.outcome]
        job = jobs[sample.name]
        assert job["status"] in statuses, (sample.name, job)
        assert (job["error"] or {}).get("code") == code, (sample.name, job["error"])
    assert (stack.library_local / "tv" / "The.Expanse.S02E05.mkv").exists()
    assert (stack.library_local / "movies" / "Dune Part Two (2024).mkv").exists()
    assert (stack.library_local / "anime" / "Frieren - 12.mkv").exists()
    assert len(report.jobs) == len(SAMPLES)


def test_seed_is_idempotent_for_rules_and_keys(stack: Stack) -> None:
    Seeder(stack.charon, stack.fake, stack.library_local).run()
    again = Seeder(stack.charon, stack.fake, stack.library_local).run()
    assert (again.rules_created, again.keys_issued) == ([], [])
    names = [rule["name"] for rule in stack.charon.get("/rules").json()]
    assert names.count("TV episodes") == 1

import asyncio
import logging
import threading
import time
from pathlib import PurePosixPath

import pytest

from charon.domain.models import SYSTEM, ErrorStage, JobStatus, Progress
from charon.errors import DownloaderError
from charon.ports.downloader import BackendStatus, BackendTask
from charon.services.download_folder import DownloadFolder
from charon.services.post_processor import PostProcessor
from charon.services.rule_service import RuleService
from charon.services.watcher import (
    MISSING_CHECKS,
    Watcher,
    found_complete,
    reconcile,
    run_periodically,
    to_progress,
)
from tests.unit.fakes import (
    ALLOW_ALL,
    T0,
    FakeClock,
    FakeDownloader,
    FakeFileOps,
    InMemoryJobStore,
    InMemoryRuleStore,
    RecordingEventLog,
    make_job,
)


def task(status: BackendStatus, **overrides) -> BackendTask:
    return BackendTask(id="task-1", status=status, **overrides)


@pytest.mark.parametrize(
    ("backend_task", "expected"),
    [
        (
            task(BackendStatus.DOWNLOADING, size_bytes=1000, downloaded_bytes=250, speed_bps=50),
            Progress(
                percent=25.0,
                size_bytes=1000,
                downloaded_bytes=250,
                download_speed_bps=50,
                eta_seconds=15,
            ),
        ),
        (
            task(BackendStatus.DOWNLOADING, size_bytes=1000, downloaded_bytes=0, speed_bps=0),
            Progress(percent=0.0, size_bytes=1000, download_speed_bps=0, eta_seconds=None),
        ),
        (
            task(BackendStatus.WAITING),
            Progress(),
        ),
        (
            task(BackendStatus.FINISHED, size_bytes=1000, downloaded_bytes=1000, speed_bps=0),
            Progress(percent=100.0, size_bytes=1000, downloaded_bytes=1000),
        ),
    ],
)
def test_to_progress(backend_task: BackendTask, expected: Progress) -> None:
    assert to_progress(backend_task) == expected


@pytest.mark.parametrize(
    ("backend_task", "status", "error_code"),
    [
        (None, JobStatus.FAILED, "task_missing"),
        (
            task(BackendStatus.ERROR, error_message="tracker down"),
            JobStatus.FAILED,
            "backend_error",
        ),
        (task(BackendStatus.WAITING), JobStatus.QUEUED, None),
        (task(BackendStatus.DOWNLOADING), JobStatus.DOWNLOADING, None),
        (task(BackendStatus.FINISHED), JobStatus.COMPLETED, None),
    ],
)
def test_reconcile_status(backend_task, status: JobStatus, error_code: str | None) -> None:
    job = reconcile(make_job(status=JobStatus.DOWNLOADING), backend_task, T0)
    assert job.status is status
    assert (job.error.code if job.error else None) == error_code
    if job.error:
        assert job.error.stage is ErrorStage.DOWNLOAD


def test_reconcile_sets_name_and_completion_time() -> None:
    clock = FakeClock()
    clock.advance(60)
    job = reconcile(make_job(), task(BackendStatus.FINISHED, name="Show.mkv"), clock())
    assert (job.name, job.completed_at, job.updated_at) == ("Show.mkv", clock(), clock())


def test_reconcile_returns_same_object_when_unchanged() -> None:
    job = make_job(status=JobStatus.QUEUED)
    assert reconcile(job, task(BackendStatus.WAITING), T0) is job


class Harness:
    def __init__(self, *jobs) -> None:
        self.jobs = InMemoryJobStore(jobs)
        self.downloader = FakeDownloader()
        self.files = FakeFileOps(["/downloads/Show.mkv"])
        folder = DownloadFolder(self.files, PurePosixPath("/downloads"))
        processor = PostProcessor(
            self.jobs,
            RuleService(InMemoryRuleStore(), ALLOW_ALL, RecordingEventLog()),
            self.downloader,
            self.files,
            folder,
            ALLOW_ALL,
            RecordingEventLog(),
        )
        self.events = RecordingEventLog()
        self.watcher = Watcher(
            self.jobs, self.downloader, processor, folder, self.events, FakeClock()
        )


def test_tick_syncs_and_processes_finished_download_in_one_pass() -> None:
    h = Harness(make_job(status=JobStatus.DOWNLOADING))
    h.downloader.tasks["task-1"] = task(BackendStatus.FINISHED, name="Show.mkv")
    h.watcher.tick()
    job = h.jobs.jobs["job-1"]
    assert (job.status, job.final_path) == (JobStatus.DONE, "/downloads/Show.mkv")


@pytest.mark.parametrize(
    ("backend", "events"),
    [
        (task(BackendStatus.WAITING), []),
        (task(BackendStatus.DOWNLOADING, downloaded_bytes=5), [JobStatus.DOWNLOADING]),
        (task(BackendStatus.ERROR, error_message="dead"), [JobStatus.FAILED]),
    ],
    ids=["unchanged", "started", "failed"],
)
def test_tick_records_each_status_change(backend: BackendTask, events: list) -> None:
    h = Harness(make_job(status=JobStatus.QUEUED))
    h.downloader.tasks["task-1"] = backend
    h.watcher.tick()
    assert [e.data["status"] for e in h.events.recorded] == events
    assert all(e.actor == SYSTEM for e in h.events.recorded)


def test_tick_records_nothing_when_another_worker_saved_first() -> None:
    h = Harness(make_job(status=JobStatus.QUEUED))
    h.downloader.tasks["task-1"] = task(BackendStatus.DOWNLOADING)
    h.jobs.update = lambda job, expected: False
    h.watcher.tick()
    assert h.events.recorded == []


def test_tick_ignores_terminal_jobs() -> None:
    h = Harness(make_job(status=JobStatus.CANCELLED))
    h.watcher.tick()
    assert h.jobs.jobs["job-1"].status is JobStatus.CANCELLED


def test_tick_keeps_job_when_backend_unreachable() -> None:
    h = Harness(make_job(status=JobStatus.DOWNLOADING))
    h.downloader.fail_with = DownloaderError("down")
    h.watcher.tick()
    assert h.jobs.jobs["job-1"].status is JobStatus.DOWNLOADING


@pytest.mark.parametrize("error", [AttributeError("bad payload"), KeyError("id"), RuntimeError()])
def test_tick_isolates_unexpected_failure_to_one_job(error: Exception) -> None:
    broken = make_job(id="broken", backend_task_id="task-broken", status=JobStatus.DOWNLOADING)
    healthy = make_job(id="job-1", status=JobStatus.DOWNLOADING)
    h = Harness(broken, healthy)
    h.downloader.broken["task-broken"] = error
    h.downloader.tasks["task-1"] = task(BackendStatus.FINISHED, name="Show.mkv")
    h.watcher.tick()
    assert h.jobs.jobs["job-1"].status is JobStatus.DONE
    assert h.jobs.jobs["broken"].status is JobStatus.DOWNLOADING


SHOW = PurePosixPath("/downloads/Show.mkv")


def nearly_done(**overrides) -> object:
    """A job whose last check saw its download almost finished, as Download Station said."""
    progress = Progress(percent=96.0, size_bytes=1000, downloaded_bytes=960)
    return make_job(status=JobStatus.DOWNLOADING, name="Show.mkv", progress=progress, **overrides)


def tick_times(h: Harness, times: int) -> list[JobStatus]:
    statuses = []
    for _ in range(times):
        h.watcher.tick()
        statuses.append(h.jobs.jobs["job-1"].status)
    return statuses


def test_a_missing_task_is_only_believed_after_several_checks_in_a_row() -> None:
    h = Harness(nearly_done())
    statuses = tick_times(h, MISSING_CHECKS)
    assert statuses == [JobStatus.DOWNLOADING] * (MISSING_CHECKS - 1) + [JobStatus.FAILED]
    error = h.jobs.jobs["job-1"].error
    assert (error.stage, error.code) == (ErrorStage.DOWNLOAD, "task_missing")


def test_a_task_that_answers_again_starts_the_count_afresh() -> None:
    """Download Station can briefly say it has no such task while one finishes."""
    h = Harness(nearly_done())
    for answers in [False] * (MISSING_CHECKS - 1) + [True] + [False] * (MISSING_CHECKS - 1):
        h.downloader.tasks["task-1"] = task(BackendStatus.DOWNLOADING) if answers else None
        h.watcher.tick()
    assert h.jobs.jobs["job-1"].status is JobStatus.DOWNLOADING
    h.watcher.tick()
    assert h.jobs.jobs["job-1"].status is JobStatus.FAILED


@pytest.mark.parametrize(
    ("size_on_disk", "status", "final_path"),
    [(1000, JobStatus.DONE, str(SHOW)), (999, JobStatus.FAILED, None)],
    ids=["complete", "partial"],
)
def test_once_its_task_is_gone_a_complete_download_is_processed_anyway(
    size_on_disk: int, status: JobStatus, final_path: str | None
) -> None:
    h = Harness(nearly_done())
    h.files.sizes[SHOW] = size_on_disk
    tick_times(h, MISSING_CHECKS)
    job = h.jobs.jobs["job-1"]
    assert (job.status, job.final_path) == (status, final_path)
    expected_events = [JobStatus.COMPLETED] if status is JobStatus.DONE else [JobStatus.FAILED]
    assert [e.data["status"] for e in h.events.recorded] == expected_events


def test_found_complete_shows_all_of_the_download_and_when() -> None:
    clock = FakeClock()
    clock.advance(60)
    job = found_complete(nearly_done(), clock())
    assert job.status is JobStatus.COMPLETED
    assert job.progress == Progress(percent=100.0, size_bytes=1000, downloaded_bytes=1000)
    assert (job.completed_at, job.updated_at) == (clock(), clock())


def test_counts_are_dropped_for_jobs_that_stop_being_active() -> None:
    h = Harness(nearly_done())
    tick_times(h, MISSING_CHECKS - 1)
    job = h.jobs.jobs["job-1"]
    h.jobs.jobs["job-1"] = job.model_copy(update={"status": JobStatus.CANCELLED})
    h.watcher.tick()
    h.jobs.jobs["job-1"] = job
    assert tick_times(h, 1) == [JobStatus.DOWNLOADING]  # counting starts again


@pytest.mark.parametrize(
    ("size_on_disk", "last"),
    [
        (1000, "task task-1 of job job-1 is gone, but its download is complete; processing it"),
        (0, "task task-1 of job job-1 is gone from the backend"),
    ],
    ids=["complete", "not-there"],
)
def test_a_vanishing_task_is_logged_at_every_step(caplog, size_on_disk: int, last: str) -> None:
    h = Harness(nearly_done())
    h.files.sizes[SHOW] = size_on_disk
    with caplog.at_level(logging.WARNING, logger="charon.services.watcher"):
        tick_times(h, MISSING_CHECKS)
    logged = [r.getMessage() for r in caplog.records if r.name == "charon.services.watcher"]
    assert logged == [
        *(
            f"task task-1 of job job-1 is missing from the backend (check {n} of {MISSING_CHECKS})"
            for n in range(1, MISSING_CHECKS)
        ),
        last,
    ]


def test_recover_requeues_interrupted_processing() -> None:
    h = Harness(make_job(status=JobStatus.PROCESSING))
    h.watcher.recover()
    assert h.jobs.jobs["job-1"].status is JobStatus.COMPLETED


def test_run_periodically_finishes_in_flight_run_before_stopping() -> None:
    events: list[str] = []

    async def scenario() -> None:
        stop = asyncio.Event()
        started = threading.Event()

        def slow_task() -> None:
            events.append("start")
            started.set()
            time.sleep(0.2)
            events.append("end")

        runner = asyncio.create_task(run_periodically(slow_task, 10, stop))
        await asyncio.to_thread(started.wait)
        stop.set()
        await runner
        events.append("stopped")

    asyncio.run(scenario())
    assert events == ["start", "end", "stopped"]


def test_run_periodically_survives_task_errors() -> None:
    calls: list[int] = []

    async def scenario() -> None:
        stop = asyncio.Event()

        def flaky() -> None:
            calls.append(1)
            if len(calls) == 3:
                stop.set()
            raise RuntimeError("boom")

        await asyncio.wait_for(run_periodically(flaky, 0.01, stop), timeout=5)

    asyncio.run(scenario())
    assert len(calls) == 3

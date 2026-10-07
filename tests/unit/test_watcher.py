import asyncio
import threading
import time
from pathlib import PurePosixPath

import pytest

from charon.domain.models import SYSTEM, ErrorStage, JobStatus, Progress
from charon.errors import DownloaderError
from charon.ports.downloader import BackendStatus, BackendTask
from charon.services.post_processor import PostProcessor
from charon.services.rule_service import RuleService
from charon.services.watcher import Watcher, reconcile, run_periodically, to_progress
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
        processor = PostProcessor(
            self.jobs,
            RuleService(InMemoryRuleStore(), ALLOW_ALL, RecordingEventLog()),
            self.downloader,
            self.files,
            PurePosixPath("/downloads"),
            ALLOW_ALL,
            RecordingEventLog(),
        )
        self.events = RecordingEventLog()
        self.watcher = Watcher(self.jobs, self.downloader, processor, self.events, FakeClock())


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

import pytest

from charon.domain.models import ErrorStage, JobError, JobStatus
from charon.errors import ConflictError, DownloaderError, InvalidInputError, NotFoundError
from charon.services.download_service import DownloadService, decode_cursor, encode_cursor
from charon.services.rule_service import RuleService
from tests.unit.fakes import (
    ALLOW_ALL,
    FakeClock,
    FakeDownloader,
    InMemoryJobStore,
    InMemoryRuleStore,
    SequentialIds,
    make_job,
    make_rule,
)

MAGNET = "magnet:?xt=urn:btih:abc"


class Harness:
    def __init__(self, *jobs) -> None:
        self.jobs = InMemoryJobStore(jobs)
        self.rules = InMemoryRuleStore([make_rule(id="rule-1")])
        self.downloader = FakeDownloader()
        self.clock = FakeClock()
        self.service = DownloadService(
            self.jobs,
            RuleService(self.rules, ALLOW_ALL),
            self.downloader,
            clock=self.clock,
            new_id=SequentialIds("job"),
        )


def test_submit_creates_queued_job() -> None:
    h = Harness()
    job = h.service.submit(MAGNET, "rule-1")
    assert (job.id, job.status, job.backend_task_id, job.forced_rule_id) == (
        "job-1",
        JobStatus.QUEUED,
        "task-1",
        "rule-1",
    )
    assert h.jobs.jobs["job-1"] == job
    assert h.downloader.added == [MAGNET]


@pytest.mark.parametrize(
    ("magnet", "rule_id", "code"),
    [
        ("http://example.com/file.torrent", None, "invalid_magnet"),
        ("", None, "invalid_magnet"),
        (MAGNET, "missing", "unknown_rule"),
    ],
)
def test_submit_rejects_invalid_input(magnet: str, rule_id: str | None, code: str) -> None:
    h = Harness()
    with pytest.raises(InvalidInputError) as exc_info:
        h.service.submit(magnet, rule_id)
    assert exc_info.value.code == code
    assert h.downloader.added == []


def test_submit_propagates_downloader_failure_without_persisting() -> None:
    h = Harness()
    h.downloader.fail_with = DownloaderError("down")
    with pytest.raises(DownloaderError):
        h.service.submit(MAGNET)
    assert h.jobs.jobs == {}


def test_get_unknown_job_raises() -> None:
    with pytest.raises(NotFoundError):
        Harness().service.get("nope")


def test_list_paginates_newest_first() -> None:
    h = Harness()
    for _ in range(5):
        h.service.submit(MAGNET)
        h.clock.advance()
    first = h.service.list(limit=2)
    second = h.service.list(limit=2, cursor=first.next_cursor)
    third = h.service.list(limit=2, cursor=second.next_cursor)
    ids = [[j.id for j in page.items] for page in (first, second, third)]
    assert ids == [["job-5", "job-4"], ["job-3", "job-2"], ["job-1"]]
    assert third.next_cursor is None


def test_list_filters_by_status() -> None:
    h = Harness(make_job(id="a", status=JobStatus.DONE), make_job(id="b"))
    assert [j.id for j in h.service.list([JobStatus.DONE]).items] == ["a"]


def _downloading(job_id: str, speed: int | None):
    return make_job(id=job_id, status=JobStatus.DOWNLOADING, progress={"download_speed_bps": speed})


@pytest.mark.parametrize(
    ("jobs", "counts", "speed"),
    [
        ([], {}, 0),
        (
            [make_job(id="a", status=JobStatus.DONE), make_job(id="b", status=JobStatus.DONE)],
            {JobStatus.DONE: 2},
            0,
        ),
        (
            [_downloading("a", 1000), _downloading("b", None), _downloading("c", 500)],
            {JobStatus.DOWNLOADING: 3},
            1500,
        ),
        (
            [make_job(id="a", status=JobStatus.FAILED), _downloading("b", 42), make_job(id="c")],
            {JobStatus.FAILED: 1, JobStatus.DOWNLOADING: 1, JobStatus.QUEUED: 1},
            42,
        ),
    ],
    ids=["empty", "done-only", "speeds-summed-null-as-zero", "mixed"],
)
def test_summary_counts_every_status_and_sums_speed(jobs, counts, speed) -> None:
    summary = Harness(*jobs).service.summary()
    assert summary.counts == {status: counts.get(status, 0) for status in JobStatus}
    assert summary.download_speed_bps == speed


def test_cursor_round_trip() -> None:
    job = make_job()
    assert decode_cursor(encode_cursor(job)) == (job.created_at, job.id)


@pytest.mark.parametrize("cursor", ["!!!", "bm90LWEtY3Vyc29y"])
def test_decode_cursor_rejects_garbage(cursor: str) -> None:
    with pytest.raises(InvalidInputError):
        decode_cursor(cursor)


@pytest.mark.parametrize("status", [JobStatus.QUEUED, JobStatus.DOWNLOADING, JobStatus.COMPLETED])
def test_cancel_active_job_removes_backend_task(status: JobStatus) -> None:
    h = Harness(make_job(status=status))
    job = h.service.cancel("job-1")
    assert job.status is JobStatus.CANCELLED
    assert h.jobs.jobs["job-1"].status is JobStatus.CANCELLED
    assert h.downloader.removed == ["task-1"]


@pytest.mark.parametrize(
    "status", [JobStatus.PROCESSING, JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED]
)
def test_cancel_rejects_non_cancellable_job(status: JobStatus) -> None:
    h = Harness(make_job(status=status))
    with pytest.raises(ConflictError):
        h.service.cancel("job-1")


def test_cancel_succeeds_even_if_backend_removal_fails() -> None:
    h = Harness(make_job())
    h.downloader.fail_with = DownloaderError("down")
    assert h.service.cancel("job-1").status is JobStatus.CANCELLED


def test_retry_processing_failure_requeues_processing() -> None:
    error = JobError(stage=ErrorStage.PROCESSING, code="destination_exists", message="x")
    h = Harness(make_job(status=JobStatus.FAILED, error=error, rule_id="rule-1"))
    job = h.service.retry("job-1")
    assert (job.status, job.error, job.rule_id) == (JobStatus.COMPLETED, None, None)
    assert h.downloader.added == []


def test_retry_download_failure_replaces_backend_task() -> None:
    error = JobError(stage=ErrorStage.DOWNLOAD, code="backend_error", message="x")
    h = Harness(make_job(status=JobStatus.FAILED, error=error, backend_task_id="old"))
    job = h.service.retry("job-1")
    assert (job.status, job.error, job.backend_task_id) == (JobStatus.QUEUED, None, "task-1")
    assert (h.downloader.removed, h.downloader.added) == (["old"], [MAGNET])


@pytest.mark.parametrize("status", [JobStatus.QUEUED, JobStatus.DONE, JobStatus.CANCELLED])
def test_retry_rejects_non_failed_job(status: JobStatus) -> None:
    h = Harness(make_job(status=status))
    with pytest.raises(ConflictError):
        h.service.retry("job-1")

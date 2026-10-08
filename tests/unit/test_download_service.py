import base64
from concurrent.futures import ThreadPoolExecutor
from pathlib import PurePosixPath

import pytest

from charon.domain.events import EventType
from charon.domain.models import Actor, ErrorStage, Job, JobError, JobStatus, Progress
from charon.errors import ConflictError, DownloaderError, InvalidInputError, NotFoundError
from charon.services.download_folder import DownloadFolder
from charon.services.download_service import DownloadService, decode_cursor, encode_cursor
from charon.services.rule_service import RuleService
from tests.unit.fakes import (
    ALLOW_ALL,
    FakeClock,
    FakeDownloader,
    FakeFileOps,
    HeldAdds,
    InMemoryJobStore,
    InMemoryRuleStore,
    Recorded,
    RecordingEventLog,
    SequentialIds,
    make_job,
    make_rule,
)

MAGNET = "magnet:?xt=urn:btih:abc"
HASH = "c12fe1c06bba254a9dc9f519b335aa7c1367a88a"
HASH_BASE32 = "YEX6DQDLXISUVHOJ6UM3GNNKPQJWPKEK"
HASHED = f"magnet:?xt=urn:btih:{HASH}"
PHONE = Actor(name="phone", key_id="key-1")


class Harness:
    def __init__(self, *jobs) -> None:
        self.jobs = InMemoryJobStore(jobs)
        self.rules = InMemoryRuleStore([make_rule(id="rule-1")])
        self.downloader = FakeDownloader()
        self.clock = FakeClock()
        self.events = RecordingEventLog()
        self.files = FakeFileOps()
        self.service = DownloadService(
            self.jobs,
            RuleService(self.rules, ALLOW_ALL, RecordingEventLog()),
            self.downloader,
            DownloadFolder(self.files, PurePosixPath("/downloads")),
            self.events,
            clock=self.clock,
            new_id=SequentialIds("job"),
        )


def test_submit_creates_queued_job() -> None:
    h = Harness()
    submission = h.service.submit(MAGNET, "rule-1")
    job = submission.job
    assert submission.created is True
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


def test_submit_credits_the_actor_and_records_an_event() -> None:
    h = Harness()
    job = h.service.submit(f"{HASHED}&dn=Show.mkv", actor=PHONE).job
    assert job.created_by == PHONE
    assert h.events.recorded == [
        Recorded(EventType.JOB_CREATED, "job-1", PHONE, {"name": "Show.mkv", "info_hash": HASH})
    ]


@pytest.mark.parametrize(
    ("existing_status", "magnet", "created"),
    [
        (JobStatus.DOWNLOADING, HASHED, False),
        (JobStatus.DONE, f"{HASHED}&dn=Other.Name&tr=udp://tracker", False),
        (JobStatus.DONE, f"magnet:?xt=urn:btih:{HASH_BASE32}", False),
        (JobStatus.DONE, HASHED.replace("magnet:?", "MAGNET:?"), False),
        (JobStatus.CANCELLED, HASHED, True),
        (JobStatus.FAILED, HASHED, True),
        (JobStatus.DONE, "magnet:?xt=urn:btih:" + "d" * 40, True),
    ],
    ids=[
        "in-flight",
        "other-params",
        "base32-form",
        "upper-case-scheme",
        "cancelled-starts-afresh",
        "failed-starts-afresh",
        "different-torrent",
    ],
)
def test_submit_returns_existing_job_for_the_same_torrent(
    existing_status: JobStatus, magnet: str, created: bool
) -> None:
    h = Harness(make_job(id="old", magnet=HASHED, status=existing_status))
    submission = h.service.submit(magnet)
    assert submission.created is created
    assert (submission.job.id == "old") is not created
    assert len(h.downloader.added) == (1 if created else 0)


@pytest.mark.parametrize(
    ("forced", "requested", "conflict"),
    [(None, "rule-1", True), ("rule-1", "rule-1", False), ("rule-1", None, False)],
    ids=["another-rule", "same-rule", "no-rule-asked"],
)
def test_submit_never_ignores_a_rule_for_a_torrent_already_in_charon(
    forced: str | None, requested: str | None, conflict: bool
) -> None:
    h = Harness(make_job(id="old", magnet=HASHED, forced_rule_id=forced))
    if not conflict:
        assert h.service.submit(HASHED, requested).job.id == "old"
        return
    with pytest.raises(ConflictError) as exc_info:
        h.service.submit(HASHED, requested)
    assert (exc_info.value.code, exc_info.value.details) == ("torrent_exists", {"job_id": "old"})


def test_submit_normalizes_an_upper_case_magnet() -> None:
    h = Harness()
    job = h.service.submit(HASHED.replace("magnet:?", "MAGNET:?")).job
    assert (job.magnet, h.downloader.added) == (HASHED, [HASHED])


def test_simultaneous_submits_of_one_torrent_start_it_once() -> None:
    h = Harness()
    adds = HeldAdds(h.downloader)
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(h.service.submit, HASHED)
        assert adds.wait_for(1, timeout=5)
        second = pool.submit(h.service.submit, HASHED)
        # Unchecked, the second submission would reach the downloader too: give it time to.
        adds.wait_for(2, timeout=0.3)
        adds.release()
        submissions = [first.result(), second.result()]
    assert [s.created for s in submissions] == [True, False]
    assert len(h.jobs.jobs) == 1


def test_latest_by_hash_skips_the_store_for_no_hashes() -> None:
    h = Harness(make_job(magnet=HASHED))
    assert h.service.latest_by_hash([]) == {}
    assert h.service.latest_by_hash([HASH])[HASH].id == "job-1"


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


@pytest.mark.parametrize(
    "cursor",
    [
        "!!!",
        "bm90LWEtY3Vyc29y",
        base64.urlsafe_b64encode(b"0001-01-01T00:00:00+01:00|job").decode(),
    ],
    ids=["not-base64", "no-separator", "out-of-range-time"],
)
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


def test_cancel_records_who_cancelled() -> None:
    h = Harness(make_job(status=JobStatus.DOWNLOADING, name="Show.mkv"))
    h.service.cancel("job-1", PHONE)
    assert h.events.recorded == [
        Recorded(
            EventType.JOB_STATUS_CHANGED,
            "job-1",
            PHONE,
            {"status": JobStatus.CANCELLED, "previous": JobStatus.DOWNLOADING, "name": "Show.mkv"},
        )
    ]


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


def test_retry_records_who_retried() -> None:
    error = JobError(stage=ErrorStage.DOWNLOAD, code="backend_error", message="x")
    h = Harness(make_job(status=JobStatus.FAILED, error=error))
    h.service.retry("job-1", PHONE)
    [event] = h.events.recorded
    assert (event.actor, event.data["status"], event.data["previous"]) == (
        PHONE,
        JobStatus.QUEUED,
        JobStatus.FAILED,
    )


def test_retry_download_failure_replaces_backend_task() -> None:
    error = JobError(stage=ErrorStage.DOWNLOAD, code="backend_error", message="x")
    h = Harness(make_job(status=JobStatus.FAILED, error=error, backend_task_id="old"))
    job = h.service.retry("job-1")
    assert (job.status, job.error, job.backend_task_id) == (JobStatus.QUEUED, None, "task-1")
    assert (h.downloader.removed, h.downloader.added) == (["old"], [MAGNET])


def vanished(code: str = "task_missing", size: int | None = 1000, **overrides) -> Job:
    """A job whose download failed (by default: its task vanished) at 96%."""
    error = JobError(stage=ErrorStage.DOWNLOAD, code=code, message="x")
    progress = Progress(percent=96.0, size_bytes=size, downloaded_bytes=960)
    return make_job(
        status=JobStatus.FAILED,
        error=error,
        name="Show.mkv",
        progress=progress,
        backend_task_id="old",
        **overrides,
    )


def test_retry_files_a_vanished_tasks_download_that_is_all_there() -> None:
    h = Harness(vanished())
    h.files.paths.add(PurePosixPath("/downloads/Show.mkv"))
    h.files.sizes[PurePosixPath("/downloads/Show.mkv")] = 1000
    job = h.service.retry("job-1", PHONE)
    assert (job.status, job.error, job.backend_task_id) == (JobStatus.COMPLETED, None, "old")
    assert job.progress == Progress(percent=100.0, size_bytes=1000, downloaded_bytes=1000)
    assert job.completed_at == h.clock()
    # Nothing fetched again; post-processing removes the old task, if the backend still has it.
    assert (h.downloader.added, h.downloader.removed) == ([], [])
    [event] = h.events.recorded
    assert (event.actor, event.data["status"]) == (PHONE, JobStatus.COMPLETED)


@pytest.mark.parametrize(
    ("job", "size_on_disk"),
    [
        (vanished(), 999),  # only part of it arrived
        (vanished(), None),  # nothing there
        (vanished(size=None), 1000),  # the backend never said how big it is
        (vanished(code="backend_error"), 1000),  # the backend failed it: don't trust the files
    ],
    ids=["partial", "absent", "size-unknown", "backend-error"],
)
def test_retry_downloads_again_unless_the_whole_download_is_there(
    job: Job, size_on_disk: int | None
) -> None:
    h = Harness(job)
    if size_on_disk is not None:
        h.files.paths.add(PurePosixPath("/downloads/Show.mkv"))
        h.files.sizes[PurePosixPath("/downloads/Show.mkv")] = size_on_disk
    retried = h.service.retry("job-1")
    assert (retried.status, retried.backend_task_id) == (JobStatus.QUEUED, "task-1")
    assert (h.downloader.removed, h.downloader.added) == (["old"], [MAGNET])


@pytest.mark.parametrize("status", [JobStatus.QUEUED, JobStatus.DONE, JobStatus.CANCELLED])
def test_retry_rejects_non_failed_job(status: JobStatus) -> None:
    h = Harness(make_job(status=status))
    with pytest.raises(ConflictError):
        h.service.retry("job-1")

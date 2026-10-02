from pathlib import PurePosixPath

import pytest

from charon.adapters.local_fs import LocalFileOps
from charon.domain import rename
from charon.domain.destinations import DestinationPolicy
from charon.domain.models import ErrorStage, JobStatus
from charon.services.post_processor import PostProcessor
from charon.services.rule_service import RuleService
from tests.unit.fakes import (
    ALLOW_ALL,
    FakeClock,
    FakeDownloader,
    FakeFileOps,
    InMemoryJobStore,
    InMemoryRuleStore,
    make_job,
    make_rule,
)

NAME = "Show.XYZ.mkv"
SOURCE = f"/downloads/{NAME}"
TARGET = "/d/e/f/Show.ABC.mkv"
XYZ_RULE = make_rule(
    id="xyz",
    pattern="*XYZ*",
    destination="/d/e/f",
    steps=[{"op": "replace", "find": "XYZ", "replace": "ABC"}],
)


class Harness:
    def __init__(self, job, rules=(XYZ_RULE,), existing=(SOURCE,), policy=ALLOW_ALL) -> None:
        self.jobs = InMemoryJobStore([job])
        self.downloader = FakeDownloader()
        self.files = FakeFileOps(existing)
        self.processor = PostProcessor(
            self.jobs,
            RuleService(InMemoryRuleStore(rules), ALLOW_ALL),
            self.downloader,
            self.files,
            PurePosixPath("/downloads"),
            policy,
            clock=FakeClock(),
        )

    def run(self):
        return self.processor.process(self.jobs.jobs["job-1"])


def completed_job(**overrides):
    return make_job(**{"status": JobStatus.COMPLETED, "name": NAME, **overrides})


def test_moves_renamed_item_and_removes_backend_task() -> None:
    h = Harness(completed_job())
    job = h.run()
    assert (job.status, job.rule_id, job.final_path) == (JobStatus.DONE, "xyz", TARGET)
    assert h.files.moves == [(PurePosixPath(SOURCE), PurePosixPath(TARGET))]
    assert h.downloader.removed == ["task-1"]
    assert h.jobs.jobs["job-1"] == job


def test_no_matching_rule_leaves_item_in_place() -> None:
    h = Harness(completed_job(), rules=())
    job = h.run()
    assert (job.status, job.rule_id, job.final_path) == (JobStatus.DONE, None, SOURCE)
    assert h.files.moves == []
    assert h.downloader.removed == []


def test_forced_rule_overrides_matching() -> None:
    forced = make_rule(id="forced", pattern="no-match", destination="/other")
    h = Harness(completed_job(forced_rule_id="forced"), rules=(XYZ_RULE, forced))
    job = h.run()
    assert (job.rule_id, job.final_path) == ("forced", f"/other/{NAME}")


@pytest.mark.parametrize(
    ("job_overrides", "rules", "existing", "code", "rule_id"),
    [
        ({}, (XYZ_RULE,), (SOURCE, TARGET), "destination_exists", "xyz"),
        ({}, (XYZ_RULE,), (), "source_missing", "xyz"),
        ({"name": None}, (XYZ_RULE,), (SOURCE,), "invalid_name", None),
        ({"forced_rule_id": "gone"}, (XYZ_RULE,), (SOURCE,), "rule_not_found", None),
        (
            {},
            (make_rule(id="bad", steps=[{"op": "replace", "find": "XYZ", "replace": "/"}]),),
            (SOURCE,),
            "unsafe_name",
            "bad",
        ),
    ],
)
def test_failures_mark_job_failed_without_moving(
    job_overrides: dict, rules: tuple, existing: tuple, code: str, rule_id: str | None
) -> None:
    h = Harness(completed_job(**job_overrides), rules=rules, existing=existing)
    job = h.run()
    assert job.status is JobStatus.FAILED
    assert (job.error.stage, job.error.code, job.rule_id) == (ErrorStage.PROCESSING, code, rule_id)
    assert h.files.moves == []
    assert h.downloader.removed == []
    assert h.jobs.jobs["job-1"].status is JobStatus.FAILED


def test_move_os_error_marks_job_failed() -> None:
    h = Harness(completed_job())
    h.files.fail_with = PermissionError("denied")
    job = h.run()
    assert (job.status, job.error.code) == (JobStatus.FAILED, "move_failed")


@pytest.mark.parametrize(
    ("method", "error", "code"),
    [
        ("exists", PermissionError(13, "Permission denied"), "filesystem_error"),
        ("resolve", PermissionError(13, "Permission denied"), "filesystem_error"),
        ("exists", RuntimeError("unexpected"), "internal_error"),
    ],
)
def test_unexpected_errors_fail_job_instead_of_stranding_it(
    method: str, error: Exception, code: str
) -> None:
    h = Harness(completed_job())
    h.files.fail_on[method] = error
    job = h.run()
    assert (job.status, job.error.stage, job.error.code) == (
        JobStatus.FAILED,
        ErrorStage.PROCESSING,
        code,
    )
    assert h.jobs.jobs["job-1"].status is JobStatus.FAILED
    assert h.files.moves == []


@pytest.mark.parametrize(
    "rule",
    [
        make_rule(id="slow", match_type="regex", pattern=r"(a|aa)+$"),
        make_rule(id="slow", steps=[{"op": "regex_replace", "find": r"(a|aa)+$", "replace": "x"}]),
    ],
)
def test_runaway_regex_fails_job_with_rule_timeout(monkeypatch, rule) -> None:
    monkeypatch.setattr(rename, "REGEX_TIMEOUT_SECONDS", 0.05)
    name = "a" * 40 + "!"
    h = Harness(completed_job(name=name), rules=(rule,), existing=(f"/downloads/{name}",))
    job = h.run()
    assert (job.status, job.error.code) == (JobStatus.FAILED, "rule_timeout")
    assert h.files.moves == []


def test_skips_job_already_claimed() -> None:
    h = Harness(completed_job())
    stale = h.jobs.jobs["job-1"]
    h.jobs.jobs["job-1"] = stale.model_copy(update={"status": JobStatus.CANCELLED})
    assert h.processor.process(stale) is None
    assert h.files.moves == []


@pytest.mark.parametrize(
    ("symlinks", "allowed"),
    [
        ({}, True),
        ({"/d/e/f": "/media/library"}, True),
        ({"/d/e/f": "/data"}, False),
        ({"/d": "/etc"}, False),
    ],
)
def test_destination_is_checked_after_resolving_symlinks(symlinks: dict, allowed: bool) -> None:
    policy = DestinationPolicy.of(["/d/e/f", "/media"], ["/data"])
    h = Harness(completed_job(), policy=policy)
    h.files.symlinks = {PurePosixPath(k): PurePosixPath(v) for k, v in symlinks.items()}
    job = h.run()
    if allowed:
        assert job.status is JobStatus.DONE
    else:
        assert (job.status, job.error.code) == (JobStatus.FAILED, "destination_not_allowed")
        assert h.files.moves == []


@pytest.mark.parametrize("target", ["outside dir", "outside file", "missing outside file"])
def test_symlink_at_final_path_is_never_followed_out_of_the_roots(tmp_path, target: str) -> None:
    downloads, library, outside = tmp_path / "downloads", tmp_path / "library", tmp_path / "out"
    for directory in (downloads, library, outside):
        directory.mkdir()
    (downloads / NAME).write_text("download")
    if target == "outside dir":
        (library / NAME).symlink_to(outside)
    elif target == "outside file":
        (outside / "victim").write_text("precious")
        (library / NAME).symlink_to(outside / "victim")
    else:
        (library / NAME).symlink_to(outside / "created")
    victims_before = {p.name: p.read_text() for p in outside.iterdir()}
    policy = DestinationPolicy.of([str(library)])
    jobs = InMemoryJobStore([completed_job()])
    processor = PostProcessor(
        jobs,
        RuleService(InMemoryRuleStore([make_rule(destination=str(library))]), policy),
        FakeDownloader(),
        LocalFileOps(),
        PurePosixPath(downloads),
        policy,
    )
    job = processor.process(jobs.jobs["job-1"])
    assert (job.status, job.error.code) == (JobStatus.FAILED, "destination_exists")
    assert {p.name: p.read_text() for p in outside.iterdir()} == victims_before
    assert (downloads / NAME).read_text() == "download"


def test_rule_outside_current_roots_fails_at_move_time() -> None:
    h = Harness(completed_job(), policy=DestinationPolicy.of(["/media"], ["/data"]))
    job = h.run()
    assert (job.status, job.error.code) == (JobStatus.FAILED, "destination_not_allowed")
    assert h.files.moves == []

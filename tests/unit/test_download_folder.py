from pathlib import PurePosixPath

import pytest

from charon.domain.models import Progress
from charon.services.download_folder import DownloadFolder, complete_progress
from tests.unit.fakes import FakeFileOps, make_job

SHOW = PurePosixPath("/downloads/Show.mkv")


def folder_with(size_on_disk: int | None) -> tuple[DownloadFolder, FakeFileOps]:
    files = FakeFileOps([] if size_on_disk is None else [str(SHOW)])
    if size_on_disk is not None:
        files.sizes[SHOW] = size_on_disk
    return DownloadFolder(files, PurePosixPath("/downloads")), files


@pytest.mark.parametrize(
    ("name", "path"),
    [("Show.mkv", SHOW), ("Show S01", PurePosixPath("/downloads/Show S01")), (None, None)]
    + [(unsafe, None) for unsafe in ["", ".", "..", "a/b", "nul\0byte"]],
)
def test_path_of_is_the_jobs_name_in_the_folder_if_usable(name: str | None, path) -> None:
    folder, _ = folder_with(None)
    assert folder.path_of(make_job(name=name)) == path


@pytest.mark.parametrize(
    ("size_on_disk", "reported", "complete"),
    [
        (1000, 1000, True),
        (1200, 1000, True),  # e.g. a folder the backend added a small file to
        (999, 1000, False),  # still arriving, or cut short
        (None, 1000, False),  # nothing there
        (1000, None, False),  # the backend never said how big it is
        (0, 0, False),
    ],
    ids=["exact", "bigger", "smaller", "absent", "size-unknown", "empty"],
)
def test_has_complete_needs_every_byte_the_backend_reported(
    size_on_disk: int | None, reported: int | None, complete: bool
) -> None:
    folder, _ = folder_with(size_on_disk)
    job = make_job(name="Show.mkv", progress=Progress(size_bytes=reported))
    assert folder.has_complete(job) is complete


@pytest.mark.parametrize("name", [None, "../escape"])
def test_has_complete_is_false_for_an_unusable_name(name: str | None) -> None:
    folder, _ = folder_with(1000)
    assert folder.has_complete(make_job(name=name, progress=Progress(size_bytes=1000))) is False


def test_has_complete_is_false_when_the_download_cant_be_measured(caplog) -> None:
    folder, files = folder_with(1000)
    files.fail_on["size"] = PermissionError("no access")
    job = make_job(name="Show.mkv", progress=Progress(size_bytes=1000))
    assert folder.has_complete(job) is False
    assert "could not measure /downloads/Show.mkv" in caplog.text


@pytest.mark.parametrize(("size", "downloaded"), [(1000, 1000), (None, 0)])
def test_complete_progress_is_all_of_it(size: int | None, downloaded: int) -> None:
    job = make_job(progress=Progress(percent=42.0, size_bytes=size, download_speed_bps=5))
    assert complete_progress(job) == Progress(
        percent=100.0, size_bytes=size, downloaded_bytes=downloaded
    )

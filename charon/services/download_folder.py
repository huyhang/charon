"""The folder the download backend saves into, where each job's download lands."""

import logging
from pathlib import PurePosixPath

from charon.domain.models import Job, Progress
from charon.domain.rename import is_safe_name
from charon.ports.files import FileOps

log = logging.getLogger(__name__)


class DownloadFolder:
    def __init__(self, files: FileOps, root: PurePosixPath) -> None:
        self._files = files
        self._root = root

    def path_of(self, job: Job) -> PurePosixPath | None:
        """The job's file or folder in it; None if the backend gave it an unusable name."""
        if job.name is None or not is_safe_name(job.name):
            return None
        return self._root / job.name

    def has_complete(self, job: Job) -> bool:
        """Whether the job's whole download is there: as many bytes as the backend reported.

        Without a size from the backend nothing counts as complete, since nothing proves it.
        """
        path = self.path_of(job)
        expected = job.progress.size_bytes
        if path is None or not expected or not self._files.exists(path):
            return False
        try:
            return self._files.size(path) >= expected
        except OSError as exc:
            # Unmeasurable (e.g. a file Charon may not read) can't be shown to be complete.
            log.warning("could not measure %s for job %s: %s", path, job.id, exc)
            return False


def complete_progress(job: Job) -> Progress:
    """The job's progress once its whole download is known to be in the folder."""
    size = job.progress.size_bytes
    return Progress(percent=100.0, size_bytes=size, downloaded_bytes=size or 0)

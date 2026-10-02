import logging

from charon.errors import DownloaderError
from charon.ports.downloader import Downloader

log = logging.getLogger(__name__)


def remove_task_best_effort(downloader: Downloader, task_id: str | None) -> None:
    """Remove a backend task, logging instead of raising on failure."""
    if task_id is None:
        return
    try:
        downloader.remove(task_id)
    except DownloaderError as exc:
        log.warning("could not remove backend task %s: %s", task_id, exc)

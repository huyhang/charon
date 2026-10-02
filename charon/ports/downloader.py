"""Port for torrent download backends (Download Station, Transmission, ...)."""

from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel


class BackendStatus(StrEnum):
    WAITING = "waiting"
    DOWNLOADING = "downloading"
    FINISHED = "finished"
    ERROR = "error"


class BackendTask(BaseModel):
    """Backend-agnostic snapshot of a download task."""

    id: str
    name: str | None = None
    status: BackendStatus
    size_bytes: int | None = None
    downloaded_bytes: int = 0
    speed_bps: int | None = None
    error_message: str | None = None


class Downloader(Protocol):
    """Raises charon.errors.DownloaderError when the backend fails."""

    def add(self, magnet: str) -> str:
        """Start downloading a magnet link and return the backend task id."""
        ...

    def get(self, task_id: str) -> BackendTask | None:
        """Return the task, or None if the backend no longer knows it."""
        ...

    def remove(self, task_id: str) -> None: ...

    def is_available(self) -> bool: ...

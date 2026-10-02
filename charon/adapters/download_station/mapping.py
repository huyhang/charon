"""Translate Download Station task payloads into backend-agnostic tasks."""

from typing import Any

from charon.ports.downloader import BackendStatus, BackendTask

_STATUSES = {
    "waiting": BackendStatus.WAITING,
    "paused": BackendStatus.WAITING,
    "hash_checking": BackendStatus.WAITING,
    "filehosting_waiting": BackendStatus.WAITING,
    "downloading": BackendStatus.DOWNLOADING,
    "finishing": BackendStatus.DOWNLOADING,
    "extracting": BackendStatus.DOWNLOADING,
    "finished": BackendStatus.FINISHED,
    "seeding": BackendStatus.FINISHED,
    "error": BackendStatus.ERROR,
}


def to_backend_task(raw: dict[str, Any]) -> BackendTask:
    # Download Station sends optional objects as null (e.g. `"status_extra": null`), so
    # `or {}` rather than a `.get()` default.
    transfer = (raw.get("additional") or {}).get("transfer") or {}
    return BackendTask(
        id=raw["id"],
        name=raw.get("title") or None,
        status=_STATUSES.get(str(raw.get("status")), BackendStatus.WAITING),
        size_bytes=raw.get("size") or None,
        downloaded_bytes=transfer.get("size_downloaded") or 0,
        speed_bps=transfer.get("speed_download"),
        error_message=(raw.get("status_extra") or {}).get("error_detail"),
    )


def find_task(data: dict[str, Any], task_id: str) -> BackendTask | None:
    for raw in data.get("tasks", []):
        if raw.get("id") == task_id and "error" not in raw:
            return to_backend_task(raw)
    return None

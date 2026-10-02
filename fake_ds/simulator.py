"""In-memory Download Station task simulator with time-based progress."""

import itertools
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

MAGNET_PREFIX = "magnet:?"


@dataclass
class FakeTask:
    id: str
    uri: str
    name: str
    destination: str
    created_at: float
    forced_status: str | None = None
    error_detail: str | None = None


class Simulator:
    """Tasks progress linearly from 0 to 100% over `duration_seconds`.

    When a task first reports `finished`, a small placeholder file named after the
    task is written into `download_dir`, mimicking Download Station's output.
    """

    def __init__(
        self,
        download_dir: Path,
        duration_seconds: float = 5.0,
        size_bytes: int = 10 * 1024 * 1024,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._download_dir = download_dir
        self._duration = duration_seconds
        self._size = size_bytes
        self._clock = clock
        self._tasks: dict[str, FakeTask] = {}
        self._ids = itertools.count(1)

    def create(self, uri: str, destination: str) -> FakeTask:
        task_id = f"dbid_{next(self._ids)}"
        task = FakeTask(task_id, uri, name_from_uri(uri, task_id), destination, self._clock())
        self._tasks[task_id] = task
        return task

    def get(self, task_id: str) -> FakeTask | None:
        return self._tasks.get(task_id)

    def all(self) -> list[FakeTask]:
        return list(self._tasks.values())

    def remove(self, task_id: str) -> bool:
        return self._tasks.pop(task_id, None) is not None

    def complete(self, task_id: str) -> FakeTask | None:
        return self._force(task_id, "finished")

    def fail(self, task_id: str, detail: str = "broken_link") -> FakeTask | None:
        task = self._force(task_id, "error")
        if task is not None:
            task.error_detail = detail
        return task

    def reset(self) -> None:
        self._tasks.clear()

    def snapshot(self, task: FakeTask) -> dict[str, Any]:
        """Render a task the way SYNO.DownloadStation.Task getinfo does.

        Types follow Synology's Download Station Web API guide: sizes are strings, and
        `status_extra` is null unless the task is in error.
        """
        fraction = self._fraction(task)
        status = task.forced_status or ("finished" if fraction >= 1 else "downloading")
        if status == "finished":
            self._materialize(task)
            fraction = 1.0
        return {
            "id": task.id,
            "title": task.name,
            "size": str(self._size),
            "status": status,
            "status_extra": {"error_detail": task.error_detail} if task.error_detail else None,
            "type": "bt",
            "username": "charon",
            "additional": {
                "detail": {"destination": task.destination, "uri": task.uri},
                "transfer": {
                    "size_downloaded": str(int(self._size * fraction)),
                    "speed_download": self._speed() if status == "downloading" else 0,
                },
            },
        }

    def _force(self, task_id: str, status: str) -> FakeTask | None:
        task = self._tasks.get(task_id)
        if task is not None:
            task.forced_status = status
        return task

    def _fraction(self, task: FakeTask) -> float:
        if self._duration <= 0:
            return 1.0
        return min((self._clock() - task.created_at) / self._duration, 1.0)

    def _speed(self) -> int:
        return int(self._size / self._duration) if self._duration > 0 else 0

    def _materialize(self, task: FakeTask) -> None:
        path = self._download_dir / task.name
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"fake download of {task.uri}\n")


def name_from_uri(uri: str, fallback: str) -> str:
    """Use the magnet's display name (dn), else its info hash, made filesystem-safe."""
    params = parse_qs(uri.removeprefix(MAGNET_PREFIX))
    if "dn" in params:
        name = params["dn"][0]
    elif "xt" in params:
        name = params["xt"][0].rsplit(":", 1)[-1]
    else:
        name = fallback
    return name.replace("/", "_").strip(". ") or fallback

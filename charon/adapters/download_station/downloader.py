import json

from charon.adapters.download_station.client import SynologyApiError, SynologyClient
from charon.adapters.download_station.mapping import find_task
from charon.errors import DownloaderError
from charon.ports.downloader import BackendTask

TASK_API = "SYNO.DownloadStation.Task"
TASK2_API = "SYNO.DownloadStation2.Task"
INFO_API = "SYNO.DownloadStation.Info"
# Download Station's documented "Invalid task id" error.
INVALID_TASK_ID = 404


class DownloadStationDownloader:
    """Downloader backed by Synology Download Station.

    Task creation uses the DownloadStation2 API because it returns the new task id;
    everything else uses the long-standing v1 task API.
    """

    def __init__(self, client: SynologyClient, destination: str) -> None:
        self._client = client
        self._destination = destination

    def add(self, magnet: str) -> str:
        data = self._client.call(
            TASK2_API,
            2,
            "create",
            type=json.dumps("url"),
            url=json.dumps([magnet]),
            destination=json.dumps(self._destination),
            create_list="false",
        )
        task_ids = data.get("task_id") or []
        if not task_ids:
            raise DownloaderError("Download Station did not return a task id")
        return str(task_ids[0])

    def get(self, task_id: str) -> BackendTask | None:
        try:
            data = self._client.call(
                TASK_API, 1, "getinfo", id=task_id, additional="detail,transfer"
            )
        except SynologyApiError as exc:
            if exc.api_code == INVALID_TASK_ID:
                return None
            raise
        return find_task(data, task_id)

    def remove(self, task_id: str) -> None:
        self._client.call(TASK_API, 1, "delete", id=task_id, force_complete="false")

    def is_available(self) -> bool:
        try:
            self._client.call(INFO_API, 1, "getinfo")
        except DownloaderError:
            return False
        return True

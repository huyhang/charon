import json
from urllib.parse import parse_qs

import httpx
import pytest

from charon.adapters.download_station.client import SynologyApiError, SynologyClient
from charon.adapters.download_station.downloader import DownloadStationDownloader
from charon.adapters.download_station.mapping import to_backend_task
from charon.errors import DownloaderError
from charon.ports.downloader import BackendStatus

# Payloads follow the documented Download Station Web API response shapes.
LOGIN_OK = {"success": True, "data": {"sid": "sid-1"}}
CREATE_OK = {"success": True, "data": {"list_id": [], "task_id": ["dbid_42"]}}
GETINFO_OK = {
    "success": True,
    "data": {
        "tasks": [
            {
                "id": "dbid_42",
                "title": "Show.XYZ.mkv",
                "size": 2000,
                "status": "downloading",
                "type": "bt",
                "username": "charon",
                "additional": {
                    "detail": {"destination": "downloads"},
                    "transfer": {"size_downloaded": 500, "speed_download": 100},
                },
            }
        ]
    },
}
SESSION_EXPIRED = {"success": False, "error": {"code": 106}}
INVALID_TASK_ID = {"success": False, "error": {"code": 404}}

# Where a DSM 7 NAS says each API lives when asked through SYNO.API.Info.
API_INFO = {
    "SYNO.API.Auth": {"path": "entry.cgi", "minVersion": 1, "maxVersion": 7},
    "SYNO.DownloadStation.Info": {
        "path": "DownloadStation/info.cgi",
        "minVersion": 1,
        "maxVersion": 2,
    },
    "SYNO.DownloadStation.Task": {
        "path": "DownloadStation/task.cgi",
        "minVersion": 1,
        "maxVersion": 3,
    },
    "SYNO.DownloadStation2.Task": {"path": "entry.cgi", "minVersion": 1, "maxVersion": 2},
}


class FakeSynology:
    """Replays canned responses keyed by (api, method), served only at discovered paths."""

    def __init__(
        self, responses: dict[tuple[str, str], list[dict]], api_info: dict = API_INFO
    ) -> None:
        self.responses = responses
        self.api_info = api_info
        self.requests: list[dict[str, str]] = []
        self.paths: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
        self.requests.append(form)
        self.paths.append(request.url.path)
        if (form["api"], request.url.path) == ("SYNO.API.Info", "/webapi/query.cgi"):
            return httpx.Response(200, json={"success": True, "data": self.api_info})
        info = self.api_info.get(form["api"])
        if info is None or request.url.path != f"/webapi/{info['path']}":
            return httpx.Response(200, json={"success": False, "error": {"code": 102}})
        queue = self.responses[(form["api"], form["method"])]
        return httpx.Response(200, json=queue.pop(0) if len(queue) > 1 else queue[0])

    def calls(self, method: str) -> list[dict[str, str]]:
        return [r for r in self.requests if r["method"] == method]


def make_downloader(
    responses, api_info: dict = API_INFO
) -> tuple[DownloadStationDownloader, FakeSynology]:
    fake = FakeSynology({("SYNO.API.Auth", "login"): [LOGIN_OK], **responses}, api_info)
    http = httpx.Client(base_url="http://nas:5000", transport=httpx.MockTransport(fake))
    return DownloadStationDownloader(SynologyClient(http, "user", "pass"), "downloads"), fake


def test_add_creates_task_and_returns_id() -> None:
    downloader, fake = make_downloader({("SYNO.DownloadStation2.Task", "create"): [CREATE_OK]})
    assert downloader.add("magnet:?xt=1") == "dbid_42"
    create = fake.calls("create")[0]
    assert json.loads(create["url"]) == ["magnet:?xt=1"]
    assert json.loads(create["destination"]) == "downloads"
    assert create["_sid"] == "sid-1"


def test_add_without_task_id_raises() -> None:
    empty = {"success": True, "data": {"task_id": []}}
    downloader, _ = make_downloader({("SYNO.DownloadStation2.Task", "create"): [empty]})
    with pytest.raises(DownloaderError):
        downloader.add("magnet:?xt=1")


def test_get_maps_task() -> None:
    downloader, _ = make_downloader({("SYNO.DownloadStation.Task", "getinfo"): [GETINFO_OK]})
    task = downloader.get("dbid_42")
    assert (task.name, task.status, task.size_bytes, task.downloaded_bytes, task.speed_bps) == (
        "Show.XYZ.mkv",
        BackendStatus.DOWNLOADING,
        2000,
        500,
        100,
    )


@pytest.mark.parametrize(
    "response",
    [
        {"success": True, "data": {"tasks": []}},
        {"success": True, "data": {"tasks": [{"id": "dbid_42", "error": 404}]}},
        INVALID_TASK_ID,
    ],
)
def test_get_missing_task_returns_none(response: dict) -> None:
    downloader, _ = make_downloader({("SYNO.DownloadStation.Task", "getinfo"): [response]})
    assert downloader.get("dbid_42") is None


def test_requests_go_to_discovered_paths_and_discovery_is_cached() -> None:
    ok = {"success": True, "data": [{"error": 0, "id": "dbid_42"}]}
    downloader, fake = make_downloader(
        {
            ("SYNO.DownloadStation2.Task", "create"): [CREATE_OK],
            ("SYNO.DownloadStation.Task", "getinfo"): [GETINFO_OK],
            ("SYNO.DownloadStation.Task", "delete"): [ok],
            ("SYNO.DownloadStation.Info", "getinfo"): [{"success": True, "data": {}}],
        }
    )
    downloader.add("magnet:?xt=1")
    downloader.get("dbid_42")
    downloader.remove("dbid_42")
    assert downloader.is_available()
    assert fake.paths == [
        "/webapi/query.cgi",
        "/webapi/entry.cgi",
        "/webapi/entry.cgi",
        "/webapi/DownloadStation/task.cgi",
        "/webapi/DownloadStation/task.cgi",
        "/webapi/DownloadStation/info.cgi",
    ]


@pytest.mark.parametrize(
    "api_info",
    [
        {k: v for k, v in API_INFO.items() if k != "SYNO.DownloadStation2.Task"},
        {**API_INFO, "SYNO.API.Auth": {"path": "auth.cgi", "minVersion": 1, "maxVersion": 2}},
    ],
)
def test_missing_api_or_version_is_reported_as_unsupported(api_info: dict) -> None:
    downloader, _ = make_downloader({}, api_info)
    with pytest.raises(DownloaderError) as exc_info:
        downloader.add("magnet:?xt=1")
    assert exc_info.value.code == "downloader_unsupported"


def test_remove_deletes_task() -> None:
    ok = {"success": True, "data": [{"error": 0, "id": "dbid_42"}]}
    downloader, fake = make_downloader({("SYNO.DownloadStation.Task", "delete"): [ok]})
    downloader.remove("dbid_42")
    assert fake.calls("delete")[0]["id"] == "dbid_42"


def test_expired_session_triggers_single_relogin() -> None:
    downloader, fake = make_downloader(
        {("SYNO.DownloadStation.Task", "getinfo"): [SESSION_EXPIRED, GETINFO_OK]}
    )
    assert downloader.get("dbid_42") is not None
    assert len(fake.calls("login")) == 2


def test_non_session_error_is_raised() -> None:
    failure = {"success": False, "error": {"code": 400}}
    downloader, fake = make_downloader({("SYNO.DownloadStation.Task", "getinfo"): [failure]})
    with pytest.raises(SynologyApiError) as exc_info:
        downloader.get("dbid_42")
    assert exc_info.value.api_code == 400
    assert len(fake.calls("login")) == 1


@pytest.mark.parametrize(
    ("info_response", "expected"),
    [({"success": True, "data": {}}, True), ({"success": False, "error": {"code": 102}}, False)],
)
def test_is_available(info_response: dict, expected: bool) -> None:
    downloader, _ = make_downloader({("SYNO.DownloadStation.Info", "getinfo"): [info_response]})
    assert downloader.is_available() is expected


def test_unreachable_nas_raises_downloader_error() -> None:
    def refuse(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    http = httpx.Client(base_url="http://nas:5000", transport=httpx.MockTransport(refuse))
    downloader = DownloadStationDownloader(SynologyClient(http, "u", "p"), "downloads")
    with pytest.raises(DownloaderError) as exc_info:
        downloader.get("dbid_42")
    assert exc_info.value.code == "downloader_unreachable"


@pytest.mark.parametrize(
    ("ds_status", "expected"),
    [
        ("waiting", BackendStatus.WAITING),
        ("paused", BackendStatus.WAITING),
        ("hash_checking", BackendStatus.WAITING),
        ("downloading", BackendStatus.DOWNLOADING),
        ("finishing", BackendStatus.DOWNLOADING),
        ("finished", BackendStatus.FINISHED),
        ("seeding", BackendStatus.FINISHED),
        ("error", BackendStatus.ERROR),
        ("something_new", BackendStatus.WAITING),
    ],
)
def test_status_mapping(ds_status: str, expected: BackendStatus) -> None:
    assert to_backend_task({"id": "t", "status": ds_status}).status is expected


def test_error_detail_is_mapped() -> None:
    raw = {"id": "t", "status": "error", "status_extra": {"error_detail": "broken_link"}}
    assert to_backend_task(raw).error_message == "broken_link"


# Verbatim getinfo example from Synology's Download Station Web API guide (pp. 10-11).
DOCUMENTED_TASK = {
    "id": "dbid_001",
    "type": "bt",
    "username": "admin",
    "title": "File 1",
    "size": "123456",
    "status": "downloading",
    "status_extra": None,
    "additional": {
        "detail": {
            "connected_leechers": 0,
            "connected_seeders": 0,
            "create_time": "1341210005",
            "destination": "Download",
            "priority": "auto",
            "total_peers": 0,
            "uri": "http://mp3.com/mix.torrent",
        },
        "transfer": {
            "size_downloaded": "54642",
            "size_uploaded": "435",
            "speed_download": "2605",
            "speed_upload": "0",
        },
    },
}


def test_documented_example_is_mapped() -> None:
    task = to_backend_task(DOCUMENTED_TASK)
    assert (task.name, task.status, task.size_bytes, task.downloaded_bytes, task.speed_bps) == (
        "File 1",
        BackendStatus.DOWNLOADING,
        123456,
        54642,
        2605,
    )
    assert task.error_message is None


@pytest.mark.parametrize(
    "nulls",
    [
        {"status_extra": None},
        {"additional": None},
        {"additional": {"detail": None, "transfer": None}},
        {"size": None, "title": None},
    ],
)
def test_null_members_are_tolerated(nulls: dict) -> None:
    task = to_backend_task({"id": "t", "status": "downloading", **nulls})
    assert (task.status, task.downloaded_bytes, task.error_message) == (
        BackendStatus.DOWNLOADING,
        0,
        None,
    )

"""Tests for the fake Download Station, including a contract test with Charon's adapter."""

import pytest
from fastapi.testclient import TestClient

from charon.adapters.download_station.client import SynologyApiError, SynologyClient
from charon.adapters.download_station.downloader import DownloadStationDownloader
from charon.ports.downloader import BackendStatus
from fake_ds.app import create_app
from fake_ds.simulator import Simulator, name_from_uri
from fake_ds.station import FakeStation


class ManualClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> ManualClock:
    return ManualClock()


@pytest.fixture
def simulator(tmp_path, clock) -> Simulator:
    return Simulator(tmp_path, duration_seconds=10, size_bytes=1000, clock=clock)


@pytest.mark.parametrize(
    ("uri", "expected"),
    [
        ("magnet:?xt=urn:btih:ABC&dn=Show.XYZ.mkv", "Show.XYZ.mkv"),
        ("magnet:?xt=urn:btih:ABC&dn=My+Show%20S01", "My Show S01"),
        ("magnet:?xt=urn:btih:ABC", "ABC"),
        ("magnet:?dn=../../etc/passwd", "_.._etc_passwd"),
        ("magnet:?dn=..", "fallback"),
        ("magnet:?", "fallback"),
    ],
)
def test_name_from_uri(uri: str, expected: str) -> None:
    assert name_from_uri(uri, "fallback") == expected


@pytest.mark.parametrize(
    ("elapsed", "status", "downloaded"),
    [
        (0, "downloading", "0"),
        (2.5, "downloading", "250"),
        (10, "finished", "1000"),
        (99, "finished", "1000"),
    ],
)
def test_progress_over_time(simulator, clock, elapsed, status, downloaded) -> None:
    task = simulator.create("magnet:?dn=f.mkv", "downloads")
    clock.now = elapsed
    raw = simulator.snapshot(task)
    assert (raw["status"], raw["additional"]["transfer"]["size_downloaded"]) == (status, downloaded)


def test_snapshot_uses_documented_types(simulator) -> None:
    raw = simulator.snapshot(simulator.create("magnet:?dn=f.mkv", "downloads"))
    assert (raw["size"], raw["status_extra"]) == ("1000", None)


def test_finishing_writes_placeholder_file_as_big_as_reported(simulator, tmp_path) -> None:
    task = simulator.create("magnet:?dn=f.mkv", "downloads")
    assert not (tmp_path / "f.mkv").exists()
    simulator.complete(task.id)
    simulator.snapshot(task)
    assert (tmp_path / "f.mkv").read_text().startswith("fake download of")
    assert (tmp_path / "f.mkv").stat().st_size == 1000


def test_vanish_drops_the_task_and_leaves_its_whole_download(simulator, tmp_path) -> None:
    task = simulator.create("magnet:?dn=f.mkv", "downloads")
    assert simulator.vanish(task.id) is True
    assert simulator.get(task.id) is None
    assert (tmp_path / "f.mkv").stat().st_size == 1000
    assert simulator.vanish(task.id) is False


def test_hiccup_hides_the_task_from_the_next_lookups_only(simulator) -> None:
    task = simulator.create("magnet:?dn=f.mkv", "downloads")
    assert simulator.hiccup(task.id, lookups=2) is task
    assert [simulator.lookup(task.id) for _ in range(3)] == [None, None, task]
    assert simulator.get(task.id) is task  # the control endpoints still see it
    assert simulator.hiccup("dbid_404") is None


def test_fail_reports_error_detail(simulator) -> None:
    task = simulator.create("magnet:?dn=f.mkv", "downloads")
    simulator.fail(task.id, "tracker_down")
    raw = simulator.snapshot(task)
    assert (raw["status"], raw["status_extra"]["error_detail"]) == ("error", "tracker_down")


@pytest.fixture
def fake(simulator) -> TestClient:
    return TestClient(create_app(FakeStation(simulator, "admin", "secret")))


def make_downloader(http, password: str = "secret") -> DownloadStationDownloader:
    return DownloadStationDownloader(SynologyClient(http, "admin", password), "downloads")


def test_contract_charon_adapter_against_fake(fake, clock) -> None:
    downloader = make_downloader(fake)
    assert downloader.is_available()
    task_id = downloader.add("magnet:?xt=urn:btih:ABC&dn=Show.mkv")
    assert downloader.get(task_id).status is BackendStatus.DOWNLOADING
    clock.now = 10
    finished = downloader.get(task_id)
    assert (finished.status, finished.name, finished.size_bytes) == (
        BackendStatus.FINISHED,
        "Show.mkv",
        1000,
    )
    downloader.remove(task_id)
    assert downloader.get(task_id) is None


def test_contract_relogin_after_sessions_expire(fake) -> None:
    downloader = make_downloader(fake)
    task_id = downloader.add("magnet:?dn=a")
    assert fake.post("/_control/sessions/expire").status_code == 204
    assert downloader.get(task_id) is not None


def test_contract_bad_credentials(fake) -> None:
    with pytest.raises(SynologyApiError) as exc_info:
        make_downloader(fake, password="wrong").add("magnet:?dn=a")
    assert exc_info.value.api_code == 400


TASK_GETINFO = {"api": "SYNO.DownloadStation.Task", "version": "1", "method": "getinfo"}


@pytest.mark.parametrize(
    ("path", "params", "code"),
    [
        ("DownloadStation/task.cgi", TASK_GETINFO, 119),
        ("entry.cgi", TASK_GETINFO, 102),
        ("entry.cgi", {"api": "SYNO.Nope", "version": "1", "method": "x"}, 102),
        ("entry.cgi", {"api": "SYNO.DownloadStation2.Task", "version": "2", "method": "x"}, 103),
        ("DownloadStation/task.cgi", {**TASK_GETINFO, "version": "9"}, 104),
    ],
)
def test_web_api_errors(fake, path: str, params: dict, code: int) -> None:
    assert fake.post(f"/webapi/{path}", data=params).json() == {
        "success": False,
        "error": {"code": code},
    }


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("SYNO.DownloadStation.Task", {"SYNO.DownloadStation.Task"}),
        ("SYNO.API.Auth,SYNO.Nope", {"SYNO.API.Auth"}),
        (
            "ALL",
            {
                "SYNO.API.Info",
                "SYNO.API.Auth",
                "SYNO.DownloadStation.Info",
                "SYNO.DownloadStation.Task",
                "SYNO.DownloadStation2.Task",
            },
        ),
    ],
)
def test_api_info_query(fake, query: str, expected: set[str]) -> None:
    params = {"api": "SYNO.API.Info", "version": "1", "method": "query", "query": query}
    data = fake.get("/webapi/query.cgi", params=params).json()["data"]
    assert set(data) == expected
    if "SYNO.DownloadStation.Task" in data:
        assert data["SYNO.DownloadStation.Task"]["path"] == "DownloadStation/task.cgi"


def test_getinfo_unknown_task_is_invalid_task_id(fake) -> None:
    login = {
        "api": "SYNO.API.Auth",
        "version": "6",
        "method": "login",
        "account": "admin",
        "passwd": "secret",
    }
    sid = fake.post("/webapi/entry.cgi", data=login).json()["data"]["sid"]
    response = fake.post(
        "/webapi/DownloadStation/task.cgi", data={**TASK_GETINFO, "id": "dbid_99", "_sid": sid}
    )
    assert response.json() == {"success": False, "error": {"code": 404}}


@pytest.mark.parametrize("action", ["complete", "fail"])
def test_control_unknown_task_is_404(fake, action: str) -> None:
    assert fake.post(f"/_control/tasks/nope/{action}").status_code == 404


def test_control_reset_clears_tasks(fake, simulator) -> None:
    simulator.create("magnet:?dn=a", "downloads")
    fake.post("/_control/reset")
    assert fake.get("/_control/tasks").json() == []


def test_contract_hiccup_and_vanish_through_the_web_api(fake) -> None:
    downloader = make_downloader(fake)
    task_id = downloader.add("magnet:?dn=Show.mkv")
    hiccup = fake.post(f"/_control/tasks/{task_id}/hiccup", json={"lookups": 1})
    assert hiccup.json()["id"] == task_id
    assert downloader.get(task_id) is None  # Download Station's "invalid task id"
    assert downloader.get(task_id) is not None
    assert fake.post(f"/_control/tasks/{task_id}/vanish").status_code == 204
    assert downloader.get(task_id) is None


@pytest.mark.parametrize("action", ["vanish", "hiccup"])
def test_steering_an_unknown_task_is_404(fake, action: str) -> None:
    assert fake.post(f"/_control/tasks/dbid_404/{action}").status_code == 404


def test_a_hiccup_lasts_at_least_one_lookup(fake) -> None:
    task_id = make_downloader(fake).add("magnet:?dn=Show.mkv")
    assert fake.post(f"/_control/tasks/{task_id}/hiccup", json={"lookups": 0}).status_code == 422

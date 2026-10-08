"""Fake Download Station state and Synology Web API request dispatch."""

import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fake_ds.simulator import Simulator

ERR_NO_SUCH_API = 102
ERR_UNKNOWN_METHOD = 103
ERR_UNSUPPORTED_VERSION = 104
ERR_NO_SESSION = 119
ERR_BAD_LOGIN = 400
ERR_INVALID_TASK_ID = 404

Params = dict[str, str]
Handler = Callable[["FakeStation", Params], Any]


@dataclass(frozen=True)
class ApiSpec:
    path: str
    min_version: int
    max_version: int


# Where each API lives, as a DSM 7 NAS reports it through SYNO.API.Info. Calling an API
# at any other path fails, so clients must discover paths the way the real API requires.
APIS = {
    "SYNO.API.Info": ApiSpec("query.cgi", 1, 1),
    "SYNO.API.Auth": ApiSpec("entry.cgi", 1, 7),
    "SYNO.DownloadStation.Info": ApiSpec("DownloadStation/info.cgi", 1, 2),
    "SYNO.DownloadStation.Task": ApiSpec("DownloadStation/task.cgi", 1, 3),
    "SYNO.DownloadStation2.Task": ApiSpec("entry.cgi", 1, 2),
}


class ApiFailure(Exception):
    def __init__(self, code: int) -> None:
        self.code = code


class FakeStation:
    def __init__(self, simulator: Simulator, username: str, password: str) -> None:
        self.simulator = simulator
        self.sessions: set[str] = set()
        self._username = username
        self._password = password

    def query(self, params: Params) -> dict[str, Any]:
        wanted = params.get("query", "ALL")
        names = APIS if wanted.upper() == "ALL" else [n for n in wanted.split(",") if n in APIS]
        return {
            name: {
                "path": APIS[name].path,
                "minVersion": APIS[name].min_version,
                "maxVersion": APIS[name].max_version,
            }
            for name in names
        }

    def login(self, params: Params) -> dict[str, Any]:
        if (params.get("account"), params.get("passwd")) != (self._username, self._password):
            raise ApiFailure(ERR_BAD_LOGIN)
        sid = uuid.uuid4().hex
        self.sessions.add(sid)
        return {"sid": sid}

    def logout(self, params: Params) -> dict[str, Any]:
        self.sessions.discard(params.get("_sid", ""))
        return {}

    def info(self, _: Params) -> dict[str, Any]:
        return {"is_manager": True, "version": 4000, "version_string": "fake-ds"}

    def create(self, params: Params) -> dict[str, Any]:
        destination = json.loads(params.get("destination", '""'))
        uris = json.loads(params.get("url", "[]"))
        tasks = [self.simulator.create(uri, destination) for uri in uris]
        return {"list_id": [], "task_id": [t.id for t in tasks]}

    def getinfo(self, params: Params) -> dict[str, Any]:
        found = [self.simulator.lookup(i) for i in params.get("id", "").split(",")]
        tasks = [self.simulator.snapshot(t) for t in found if t is not None]
        if not tasks:
            raise ApiFailure(ERR_INVALID_TASK_ID)
        return {"tasks": tasks}

    def list_tasks(self, _: Params) -> dict[str, Any]:
        tasks = [self.simulator.snapshot(t) for t in self.simulator.all()]
        return {"offset": 0, "total": len(tasks), "tasks": tasks}

    def delete(self, params: Params) -> list[dict[str, Any]]:
        ids = params.get("id", "").split(",")
        return [
            {"id": i, "error": 0 if self.simulator.remove(i) else ERR_INVALID_TASK_ID} for i in ids
        ]


PUBLIC: dict[tuple[str, str], Handler] = {
    ("SYNO.API.Info", "query"): FakeStation.query,
    ("SYNO.API.Auth", "login"): FakeStation.login,
    ("SYNO.API.Auth", "logout"): FakeStation.logout,
}
AUTHENTICATED: dict[tuple[str, str], Handler] = {
    ("SYNO.DownloadStation.Info", "getinfo"): FakeStation.info,
    ("SYNO.DownloadStation2.Task", "create"): FakeStation.create,
    ("SYNO.DownloadStation.Task", "getinfo"): FakeStation.getinfo,
    ("SYNO.DownloadStation.Task", "list"): FakeStation.list_tasks,
    ("SYNO.DownloadStation.Task", "delete"): FakeStation.delete,
}


def dispatch(station: FakeStation, path: str, params: Params) -> dict[str, Any]:
    """Route a Web API call made at `/webapi/{path}` and wrap the result in Synology's
    response envelope."""
    api = params.get("api", "")
    key = (api, params.get("method", ""))
    try:
        _check_api(api, path, params.get("version", ""))
        if key in PUBLIC:
            return {"success": True, "data": PUBLIC[key](station, params)}
        if key not in AUTHENTICATED:
            raise ApiFailure(ERR_UNKNOWN_METHOD)
        if params.get("_sid") not in station.sessions:
            raise ApiFailure(ERR_NO_SESSION)
        return {"success": True, "data": AUTHENTICATED[key](station, params)}
    except ApiFailure as exc:
        return {"success": False, "error": {"code": exc.code}}


def _check_api(api: str, path: str, version: str) -> None:
    spec = APIS.get(api)
    if spec is None or spec.path != path:
        raise ApiFailure(ERR_NO_SUCH_API)
    if not (version.isdigit() and spec.min_version <= int(version) <= spec.max_version):
        raise ApiFailure(ERR_UNSUPPORTED_VERSION)

"""Minimal Synology Web API client with API discovery and automatic re-login."""

from dataclasses import dataclass
from typing import Any

import httpx

from charon.errors import DownloaderError

# The one fixed endpoint: SYNO.API.Info says where every other API lives.
INFO_PATH = "/webapi/query.cgi"
SESSION_ERROR_CODES = frozenset({105, 106, 107, 119})


class SynologyApiError(DownloaderError):
    def __init__(self, api: str, method: str, code: int) -> None:
        super().__init__(f"{api}.{method} failed with Synology error {code}", "synology_error")
        self.api_code = code


@dataclass(frozen=True)
class ApiInfo:
    path: str
    min_version: int
    max_version: int


class SynologyClient:
    def __init__(
        self,
        http: httpx.Client,
        username: str,
        password: str,
        session_name: str = "DownloadStation",
    ) -> None:
        self._http = http
        self._username = username
        self._password = password
        self._session_name = session_name
        self._sid: str | None = None
        self._apis: dict[str, ApiInfo] | None = None

    def call(self, api: str, version: int, method: str, **params: Any) -> dict[str, Any]:
        """Call an authenticated API, logging in again once if the session expired."""
        try:
            return self._call_with_session(api, version, method, params)
        except SynologyApiError as exc:
            if exc.api_code not in SESSION_ERROR_CODES:
                raise
            self._sid = None
            return self._call_with_session(api, version, method, params)

    def _call_with_session(
        self, api: str, version: int, method: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        if self._sid is None:
            self._sid = self._login()
        return self._request(api, version, method, {**params, "_sid": self._sid})

    def _login(self) -> str:
        data = self._request(
            "SYNO.API.Auth",
            6,
            "login",
            {
                "account": self._username,
                "passwd": self._password,
                "session": self._session_name,
                "format": "sid",
            },
        )
        return str(data["sid"])

    def _request(
        self, api: str, version: int, method: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        form = {"api": api, "version": str(version), "method": method, **params}
        return self._post(self._path(api, version), form)

    def _path(self, api: str, version: int) -> str:
        info = self._discover().get(api)
        if info is None:
            raise DownloaderError(
                f"the NAS does not offer {api}; is Download Station installed and up to date?",
                "downloader_unsupported",
            )
        if not info.min_version <= version <= info.max_version:
            raise DownloaderError(
                f"the NAS supports {api} versions {info.min_version}-{info.max_version}, "
                f"Charon needs version {version}",
                "downloader_unsupported",
            )
        return f"/webapi/{info.path}"

    def _discover(self) -> dict[str, ApiInfo]:
        """Ask SYNO.API.Info where each API lives, as Synology's API guide prescribes."""
        if self._apis is None:
            form = {"api": "SYNO.API.Info", "version": "1", "method": "query", "query": "ALL"}
            self._apis = {
                name: ApiInfo(entry["path"], int(entry["minVersion"]), int(entry["maxVersion"]))
                for name, entry in self._post(INFO_PATH, form).items()
            }
        return self._apis

    def _post(self, path: str, form: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self._http.post(path, data=form)
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise DownloaderError(
                f"Synology request failed: {exc}", "downloader_unreachable"
            ) from exc
        if not body.get("success"):
            code = int((body.get("error") or {}).get("code", 0))
            raise SynologyApiError(form["api"], form["method"], code)
        return body.get("data") or {}

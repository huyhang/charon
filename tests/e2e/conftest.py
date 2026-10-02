"""End-to-end fixtures.

If CHARON_E2E_URL is set, tests run against already-running services (e.g. `make dev`
or docker/docker-compose.dev.yml). Otherwise Charon and the fake Download Station are started
in-process on free ports with temporary directories.
"""

import os
import socket
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest
import uvicorn
from fastapi import FastAPI

from charon.bootstrap import build_app
from charon.config import Settings
from fake_ds.app import create_app as create_fake_app
from fake_ds.simulator import Simulator
from fake_ds.station import FakeStation

API_KEY = "e2e-key"
API_PREFIX = "/api/v1"


@dataclass(frozen=True)
class Stack:
    charon: httpx.Client
    fake: httpx.Client
    library_local: Path
    library_service: str


@pytest.fixture(scope="session")
def stack(tmp_path_factory) -> Iterator[Stack]:
    if os.environ.get("CHARON_E2E_URL"):
        yield from _external_stack()
    else:
        yield from _in_process_stack(tmp_path_factory.mktemp("e2e"))


def _external_stack() -> Iterator[Stack]:
    library = os.environ.get("E2E_LIBRARY_DIR", "var/library")
    headers = {"X-API-Key": os.environ.get("CHARON_E2E_API_KEY", "")}
    with (
        httpx.Client(base_url=os.environ["CHARON_E2E_URL"] + API_PREFIX, headers=headers) as charon,
        httpx.Client(base_url=os.environ.get("FAKE_DS_E2E_URL", "http://localhost:5000")) as fake,
    ):
        yield Stack(charon, fake, Path(library), os.environ.get("E2E_LIBRARY_DIR_SERVICE", library))


def _in_process_stack(root: Path) -> Iterator[Stack]:
    downloads, library = root / "downloads", root / "library"
    downloads.mkdir()
    fake_station = FakeStation(Simulator(downloads, duration_seconds=1.5), "admin", "admin")
    fake_url = _serve(create_fake_app(fake_station))
    settings = Settings(
        _env_file=None,
        admin_api_key=API_KEY,
        db_path=root / "data" / "charon.db",
        rule_roots=[library],
        download_dir=downloads,
        poll_interval_seconds=0.2,
        ds_url=fake_url,
        ds_username="admin",
        ds_password="admin",
    )
    charon_url = _serve(build_app(settings))
    with (
        httpx.Client(base_url=charon_url + API_PREFIX, headers={"X-API-Key": API_KEY}) as charon,
        httpx.Client(base_url=fake_url) as fake,
    ):
        yield Stack(charon, fake, library, str(library))


def _serve(app: FastAPI) -> str:
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("server did not start")
        time.sleep(0.05)
    return f"http://127.0.0.1:{port}"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]

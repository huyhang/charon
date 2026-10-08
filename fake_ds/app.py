"""A fake Synology Download Station exposing the Web API subset Charon uses.

It also serves fake RSS feeds and a fake TMDB, so one process stands in for everything
Charon talks to.
"""

import os
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

from fastapi import FastAPI, Request

from fake_ds.control import router as control_router
from fake_ds.feed_routes import router as feed_router
from fake_ds.feeds import FakeFeeds
from fake_ds.simulator import Simulator
from fake_ds.station import FakeStation, Params, dispatch
from fake_ds.tmdb import DEV_TOKEN, FakeTmdb
from fake_ds.tmdb_routes import router as tmdb_router


def create_app(
    station: FakeStation, feeds: FakeFeeds | None = None, tmdb: FakeTmdb | None = None
) -> FastAPI:
    app = FastAPI(title="Fake Download Station")
    app.state.station = station
    app.state.feeds = feeds or FakeFeeds()
    app.state.tmdb = tmdb or FakeTmdb()

    @app.api_route("/webapi/{path:path}", methods=["GET", "POST"])
    async def web_api(path: str, request: Request) -> dict[str, Any]:
        params: Params = dict(request.query_params)
        form = parse_qs((await request.body()).decode())
        params.update({key: values[0] for key, values in form.items()})
        return dispatch(station, path, params)

    app.include_router(control_router)
    app.include_router(feed_router)
    app.include_router(tmdb_router)
    return app


def create_app_from_env() -> FastAPI:
    """Factory for `uvicorn fake_ds.app:create_app_from_env --factory`."""
    simulator = Simulator(
        download_dir=Path(os.environ.get("FAKE_DS_DOWNLOAD_DIR", "/downloads")),
        duration_seconds=float(os.environ.get("FAKE_DS_DURATION_SECONDS", "5")),
        size_bytes=int(os.environ.get("FAKE_DS_SIZE_BYTES", str(10 * 1024 * 1024))),
    )
    station = FakeStation(
        simulator,
        os.environ.get("FAKE_DS_USERNAME", "admin"),
        os.environ.get("FAKE_DS_PASSWORD", "admin"),
    )
    tmdb = FakeTmdb(os.environ.get("FAKE_TMDB_TOKEN", DEV_TOKEN))
    return create_app(station, tmdb=tmdb)

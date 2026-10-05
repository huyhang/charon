import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute

from charon.api import api_keys, auth, destinations, downloads, health, rules
from charon.api.deps import authenticate
from charon.api.errors import register_error_handlers
from charon.api.ui import SpaStaticFiles
from charon.container import Container
from charon.services.watcher import run_periodically

log = logging.getLogger(__name__)

API_PREFIX = "/api/v1"
VERSION = "0.1.0"

Lifespan = Callable[[FastAPI], AbstractAsyncContextManager[None]]


def create_api(lifespan: Lifespan | None = None) -> FastAPI:
    """The routes and OpenAPI spec, independent of any wiring."""
    app = FastAPI(
        title="Charon",
        version=VERSION,
        lifespan=lifespan,
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=f"{API_PREFIX}/docs",
        redoc_url=None,
        generate_unique_id_function=operation_id,
    )
    authenticated = [Depends(authenticate)]
    app.include_router(health.router, prefix=API_PREFIX)
    app.include_router(auth.router, prefix=API_PREFIX)
    app.include_router(downloads.router, prefix=API_PREFIX, dependencies=authenticated)
    app.include_router(rules.router, prefix=API_PREFIX, dependencies=authenticated)
    app.include_router(destinations.router, prefix=API_PREFIX, dependencies=authenticated)
    app.include_router(api_keys.router, prefix=API_PREFIX)
    register_error_handlers(app)
    return app


def create_app(container: Container) -> FastAPI:
    app = create_api(lifespan=_lifespan(container))
    app.state.container = container
    _enable_cors(app, container.cors_origins)
    _mount_ui(app, container.ui_dir)
    return app


def operation_id(route: APIRoute) -> str:
    """camelCase operation ids (e.g. submitDownload) for friendly generated clients."""
    first, *rest = route.name.split("_")
    return first + "".join(word.capitalize() for word in rest)


def _enable_cors(app: FastAPI, origins: list[str]) -> None:
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_methods=["*"],
            allow_headers=["X-API-Key", "Content-Type"],
        )


def _mount_ui(app: FastAPI, ui_dir: Path | None) -> None:
    # Mounted last so every API route takes precedence over static files.
    if ui_dir is None:
        return
    if not (ui_dir / "index.html").is_file():
        log.warning("UI directory %s has no index.html; not serving a UI", ui_dir)
        return
    app.mount("/", SpaStaticFiles(directory=ui_dir, html=True), name="ui")


def _lifespan(container: Container) -> Lifespan:
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        stop = asyncio.Event()
        watcher_task = await _start_watcher(container, stop)
        yield
        stop.set()
        if watcher_task is not None:
            await watcher_task
        for close in container.closers:
            close()

    return lifespan


async def _start_watcher(container: Container, stop: asyncio.Event) -> asyncio.Task[None] | None:
    if not container.poll_interval_seconds:
        return None
    await asyncio.to_thread(container.watcher.recover)
    return asyncio.create_task(
        run_periodically(container.watcher.tick, container.poll_interval_seconds, stop)
    )

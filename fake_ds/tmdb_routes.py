"""Serves the fake TMDB under /tmdb, plus test-only endpoints for steering it."""

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from fake_ds.tmdb import FakeTmdb, TmdbMode, throttled_body, unauthorized_body

router = APIRouter(tags=["tmdb"])


def _tmdb(request: Request) -> FakeTmdb:
    return request.app.state.tmdb


@router.get("/tmdb/3/search/multi", response_model=None)
def search_multi(request: Request, query: str = "", page: int = 1) -> dict[str, Any] | JSONResponse:
    """TMDB's multi search. Every request counts towards the limit, refused or not."""
    tmdb = _tmdb(request)
    within_limit = tmdb.record()
    if not tmdb.authorized(request.headers.get("Authorization")):
        return JSONResponse(unauthorized_body(), status_code=401)
    if tmdb.mode is TmdbMode.DOWN:
        return JSONResponse({"status_message": "Service unavailable"}, status_code=503)
    if tmdb.mode is TmdbMode.THROTTLED or not within_limit:
        return JSONResponse(throttled_body(tmdb.limit), status_code=429)
    return tmdb.page(query, max(page, 1))


@router.get("/_control/tmdb")
def tmdb_state(request: Request) -> dict[str, Any]:
    """The mode, how many requests arrived, and the most in any window."""
    return _tmdb(request).snapshot()


@router.post("/_control/tmdb/throttle")
def throttle(request: Request) -> dict[str, Any]:
    return _set_mode(request, TmdbMode.THROTTLED)


@router.post("/_control/tmdb/down")
def take_down(request: Request) -> dict[str, Any]:
    return _set_mode(request, TmdbMode.DOWN)


@router.post("/_control/tmdb/heal")
def heal(request: Request) -> dict[str, Any]:
    return _set_mode(request, TmdbMode.OK)


def _set_mode(request: Request, mode: TmdbMode) -> dict[str, Any]:
    tmdb = _tmdb(request)
    tmdb.mode = mode
    return tmdb.snapshot()

"""Test-only endpoints for steering the fake from scripts."""

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from fake_ds.station import FakeStation

router = APIRouter(prefix="/_control", tags=["control"])


class FailRequest(BaseModel):
    detail: str = "broken_link"


class HiccupRequest(BaseModel):
    lookups: int = Field(default=1, ge=1)


def _station(request: Request) -> FakeStation:
    return request.app.state.station


@router.get("/tasks")
def list_tasks(request: Request) -> list[dict[str, Any]]:
    simulator = _station(request).simulator
    return [simulator.snapshot(t) for t in simulator.all()]


@router.post("/tasks/{task_id}/complete")
def complete(task_id: str, request: Request) -> dict[str, Any]:
    simulator = _station(request).simulator
    return simulator.snapshot(_require(simulator.complete(task_id)))


@router.post("/tasks/{task_id}/fail")
def fail(task_id: str, request: Request, body: FailRequest | None = None) -> dict[str, Any]:
    simulator = _station(request).simulator
    detail = (body or FailRequest()).detail
    return simulator.snapshot(_require(simulator.fail(task_id, detail)))


@router.post("/tasks/{task_id}/vanish", status_code=204)
def vanish(task_id: str, request: Request) -> None:
    """Drop the task as Download Station can once it finishes, leaving its download."""
    _require(_station(request).simulator.vanish(task_id) or None)


@router.post("/tasks/{task_id}/hiccup")
def hiccup(task_id: str, request: Request, body: HiccupRequest | None = None) -> dict[str, Any]:
    """Answer "invalid task id" for the task's next `lookups` lookups, then normally again."""
    simulator = _station(request).simulator
    lookups = (body or HiccupRequest()).lookups
    return simulator.snapshot(_require(simulator.hiccup(task_id, lookups)))


@router.post("/sessions/expire", status_code=204)
def expire_sessions(request: Request) -> None:
    _station(request).sessions.clear()


@router.post("/reset", status_code=204)
def reset(request: Request) -> None:
    """Clear every task and session, and put the fake feeds and TMDB back as they started."""
    station = _station(request)
    station.simulator.reset()
    station.sessions.clear()
    request.app.state.feeds.reset()
    request.app.state.tmdb.reset()


def _require(task: Any) -> Any:
    if task is None:
        raise HTTPException(404, "task not found")
    return task

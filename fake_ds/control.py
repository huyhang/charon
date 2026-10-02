"""Test-only endpoints for steering the fake from scripts."""

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from fake_ds.station import FakeStation

router = APIRouter(prefix="/_control", tags=["control"])


class FailRequest(BaseModel):
    detail: str = "broken_link"


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


@router.post("/sessions/expire", status_code=204)
def expire_sessions(request: Request) -> None:
    _station(request).sessions.clear()


@router.post("/reset", status_code=204)
def reset(request: Request) -> None:
    station = _station(request)
    station.simulator.reset()
    station.sessions.clear()


def _require(task: Any) -> Any:
    if task is None:
        raise HTTPException(404, "task not found")
    return task

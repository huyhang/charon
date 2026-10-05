import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from charon import main


@pytest.fixture
def env(monkeypatch, tmp_path):
    """Settings come from CHARON_* variables; keep them away from any local .env file."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CHARON_DB_PATH", str(tmp_path / "data" / "charon.db"))
    monkeypatch.setenv("CHARON_RULE_ROOTS", str(tmp_path / "library"))
    return monkeypatch


def test_create_app_builds_charon_from_the_environment(env) -> None:
    # Without a `with` block the client skips the lifespan, so no watcher or downloader runs.
    response = TestClient(main.create_app()).get("/api/v1/openapi.json")
    assert response.status_code == 200
    assert "/api/v1/downloads/summary" in response.json()["paths"]


@pytest.mark.parametrize(
    ("variables", "host", "port", "level"),
    [
        ({}, "0.0.0.0", 8080, "INFO"),
        (
            {"CHARON_HOST": "127.0.0.1", "CHARON_PORT": "18080", "CHARON_LOG_LEVEL": "DEBUG"},
            "127.0.0.1",
            18080,
            "DEBUG",
        ),
    ],
    ids=["defaults", "from-env"],
)
def test_run_serves_on_the_configured_address(env, variables, host, port, level) -> None:
    for name, value in variables.items():
        env.setenv(name, value)
    served, logging_levels = {}, []
    env.setattr(main.uvicorn, "run", lambda app, **kw: served.update(app=app, **kw))
    env.setattr(main.logging, "basicConfig", lambda level: logging_levels.append(level))
    main.run()
    assert isinstance(served.pop("app"), FastAPI)
    assert served == {"host": host, "port": port}
    assert logging_levels == [level]

import logging

import uvicorn
from fastapi import FastAPI

from charon.bootstrap import build_app
from charon.config import Settings


def create_app() -> FastAPI:
    """Factory for `uvicorn charon.main:create_app --factory`."""
    return build_app(Settings())


def run() -> None:
    settings = Settings()
    logging.basicConfig(level=settings.log_level)
    uvicorn.run(build_app(settings), host=settings.host, port=settings.port)


if __name__ == "__main__":
    run()

from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from charon.errors import (
    CharonError,
    ConflictError,
    DownloaderError,
    ForbiddenError,
    InvalidInputError,
    NotFoundError,
    UnauthorizedError,
)

_STATUS_CODES: list[tuple[type[CharonError], int]] = [
    (UnauthorizedError, 401),
    (ForbiddenError, 403),
    (NotFoundError, 404),
    (ConflictError, 409),
    (InvalidInputError, 422),
    (DownloaderError, 502),
]


def status_code_for(exc: CharonError) -> int:
    return next((code for cls, code in _STATUS_CODES if isinstance(exc, cls)), 500)


def error_body(code: str, message: str, **extra: object) -> dict[str, object]:
    return {"error": {"code": code, "message": message, **extra}}


async def _charon_error(_: Request, exc: CharonError) -> JSONResponse:
    return JSONResponse(error_body(exc.code, exc.message), status_code=status_code_for(exc))


async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    details = jsonable_encoder(exc.errors())
    body = error_body("invalid_request", "request validation failed", details=details)
    return JSONResponse(body, status_code=422)


async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Unknown routes, wrong methods, etc. use the same error body as everything else."""
    phrase = HTTPStatus(exc.status_code).phrase
    body = error_body(phrase.lower().replace(" ", "_"), str(exc.detail))
    return JSONResponse(body, status_code=exc.status_code, headers=exc.headers)


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(CharonError, _charon_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)

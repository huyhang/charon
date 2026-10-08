import logging
import math
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
    MetadataError,
    NotFoundError,
    RateLimitedError,
    UnauthorizedError,
)
from charon.hints import hint_for, is_retryable

log = logging.getLogger(__name__)

_STATUS_CODES: list[tuple[type[CharonError], int]] = [
    (UnauthorizedError, 401),
    (ForbiddenError, 403),
    (NotFoundError, 404),
    (ConflictError, 409),
    (InvalidInputError, 422),
    (RateLimitedError, 429),
    (DownloaderError, 502),
    (MetadataError, 502),
]


def status_code_for(exc: CharonError) -> int:
    return next((code for cls, code in _STATUS_CODES if isinstance(exc, cls)), 500)


def error_body(code: str, message: str, **extra: object) -> dict[str, object]:
    detail = {"code": code, "message": message, "hint": hint_for(code)}
    return {"error": {**detail, "retryable": is_retryable(code), **extra}}


async def _charon_error(_: Request, exc: CharonError) -> JSONResponse:
    extra = {"details": exc.details} if exc.details is not None else {}
    body = error_body(exc.code, exc.message, **extra)
    return JSONResponse(body, status_code=status_code_for(exc), headers=_retry_after(exc))


def _retry_after(exc: CharonError) -> dict[str, str] | None:
    """The standard Retry-After header, for clients that understand it."""
    if isinstance(exc, RateLimitedError) and exc.retry_after is not None:
        return {"Retry-After": str(max(1, math.ceil(exc.retry_after)))}
    return None


async def _unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    """A bug, not a client mistake: logged in full, answered with the usual error body."""
    log.error("unexpected error on %s %s", request.method, request.url.path, exc_info=exc)
    body = error_body("internal_error", "something unexpected went wrong")
    return JSONResponse(body, status_code=500)


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
    app.add_exception_handler(Exception, _unexpected_error)

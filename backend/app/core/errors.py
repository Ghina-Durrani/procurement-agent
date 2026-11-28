"""Domain errors and the one error body every endpoint returns (ENGINEERING_HANDBOOK §3).

Every error looks like {"code": "...", "message": "...", "field_errors": {...} | null}, so the
frontend needs one parser. Messages never contain stack traces, SQL, secrets, the submitted
text, or a hint that another organization's record exists.
"""
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    """An expected failure that the API reports with a stable code."""

    status_code = 400
    code = "BAD_REQUEST"

    def __init__(self, message: str, field_errors: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.field_errors = field_errors


class NotFound(AppError):
    # Also used for other organizations' rows, so their existence is never revealed.
    status_code = 404
    code = "NOT_FOUND"


class Conflict(AppError):
    # The record exists but is not in a state that allows this action (for example, a
    # clarification answer for a request that is not waiting for one).
    status_code = 409
    code = "CONFLICT"


class Unauthenticated(AppError):
    status_code = 401
    code = "UNAUTHENTICATED"


def error_body(code: str, message: str, field_errors: dict[str, str] | None = None) -> dict[str, Any]:
    return {"code": code, "message": message, "field_errors": field_errors}


_HTTP_CODES = {401: "UNAUTHENTICATED", 403: "FORBIDDEN", 404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED", 409: "CONFLICT"}


def _field_name(location: tuple[Any, ...]) -> str:
    # ("body", "message") -> "message"; ("query", "limit") -> "limit".
    parts = [str(part) for part in location if part not in ("body", "query", "path")]
    return ".".join(parts) or "request"


async def _app_error(_: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, AppError)
    return JSONResponse(
        status_code=error.status_code,
        content=error_body(error.code, error.message, error.field_errors),
    )


async def _validation_error(_: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, RequestValidationError)
    # Only Pydantic's message is used: its "input" part could echo the request text.
    fields: dict[str, str] = {}
    for item in error.errors():
        fields.setdefault(_field_name(tuple(item.get("loc", ()))), str(item.get("msg", "Invalid value.")))
    return JSONResponse(
        status_code=422,
        content=error_body("VALIDATION_ERROR", "Some fields are not valid.", fields),
    )


async def _http_error(_: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, StarletteHTTPException)
    code = _HTTP_CODES.get(error.status_code, f"HTTP_{error.status_code}")
    message = error.detail if isinstance(error.detail, str) else "The request failed."
    return JSONResponse(status_code=error.status_code, content=error_body(code, message))


async def _unexpected_error(_: Request, __: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500, content=error_body("INTERNAL_ERROR", "Something went wrong on the server.")
    )


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(Exception, _unexpected_error)

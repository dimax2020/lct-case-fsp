from collections.abc import Mapping, Sequence
from typing import Any, NoReturn

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[dict[str, Any]] | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


class AppError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details
        super().__init__(message)


def error_payload(code: str, message: str, details: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"code": code, "message": message}
    if details:
        body["details"] = details
    return {"error": body}


async def app_error_handler(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, AppError):
        raise exc
    response = JSONResponse(
        status_code=exc.status_code,
        content=error_payload(exc.code, exc.message, exc.details),
    )
    request_id = getattr(request.state, "request_id", None)
    if request_id:
        response.headers["X-Request-Id"] = request_id
    return response


def not_implemented() -> NoReturn:
    raise AppError("not_implemented", "Метод ещё не реализован", status_code=501)


def validation_message(errors: Sequence[Any]) -> str:
    parts: list[str] = []
    for item in errors:
        if not isinstance(item, Mapping):
            parts.append(str(item))
            continue
        loc = ".".join(str(part) for part in item.get("loc", []) if part != "body")
        msg = str(item.get("msg", "некорректное значение"))
        parts.append(f"{loc}: {msg}" if loc else msg)
    return "; ".join(parts) or "Некорректный запрос"


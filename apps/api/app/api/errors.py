"""ProblemDetails-style errors: `{title, status, errors?}` with `application/problem+json`.

Validation failures are 400 with `errors: {field: [message]}` (FastAPI's 422 is converted).
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

PROBLEM_JSON = "application/problem+json"
VALIDATION_TITLE = "Uno o más datos no son válidos."

_STATUS_TITLES = {
    400: "Solicitud inválida.",
    401: "No autorizado.",
    403: "Acceso denegado.",
    404: "Recurso no encontrado.",
    405: "Método no permitido.",
    409: "Conflicto.",
    413: "El archivo es demasiado grande.",
    415: "Tipo de contenido no soportado.",
    500: "Error inesperado en el servidor.",
}


class ApiError(Exception):
    def __init__(
        self,
        status: int,
        title: str | None = None,
        errors: dict[str, list[str]] | None = None,
        headers: dict[str, str] | None = None,
        **extra: Any,
    ) -> None:
        super().__init__(title or _STATUS_TITLES.get(status, "Error."))
        self.status = status
        self.title = title or _STATUS_TITLES.get(status, "Error.")
        self.errors = errors
        self.headers = headers
        self.extra = extra


def not_found() -> ApiError:
    return ApiError(404)


def validation_error(field: str, message: str) -> ApiError:
    return ApiError(400, VALIDATION_TITLE, {field: [message]})


def conflict(title: str) -> ApiError:
    return ApiError(409, title)


def problem_response(
    status: int,
    title: str,
    errors: dict[str, list[str]] | None = None,
    headers: dict[str, str] | None = None,
    **extra: Any,
) -> JSONResponse:
    body: dict[str, Any] = {"title": title, "status": status}
    if errors:
        body["errors"] = errors
    body.update(extra)
    return JSONResponse(body, status_code=status, media_type=PROBLEM_JSON, headers=headers)


def _unit(kind: str, ctx: dict[str, Any]) -> str:
    return "elementos" if kind.startswith("too_") and ctx.get("field_type") == "List" else "caracteres"


def _translate(error: dict[str, Any]) -> str:
    kind = error.get("type", "")
    ctx = error.get("ctx") or {}
    if kind == "missing":
        return "El campo es requerido."
    if kind in ("string_too_short", "too_short"):
        if ctx.get("min_length") == 1:
            return "El campo es requerido."
        return f"Debe tener al menos {ctx.get('min_length')} {_unit(kind, ctx)}."
    if kind in ("string_too_long", "too_long"):
        return f"Debe tener como máximo {ctx.get('max_length')} {_unit(kind, ctx)}."
    if kind in ("greater_than_equal", "greater_than"):
        return f"El valor debe ser mayor o igual a {ctx.get('ge', ctx.get('gt'))}."
    if kind in ("less_than_equal", "less_than"):
        return f"El valor debe ser menor o igual a {ctx.get('le', ctx.get('lt'))}."
    if kind == "string_pattern_mismatch":
        return "El formato no es válido."
    if kind.startswith("date"):
        return "Fecha inválida (use AAAA-MM-DD)."
    if kind.startswith("time"):
        return "Hora inválida (use HH:MM:SS)."
    if kind.startswith("int") or kind.startswith("float") or kind.startswith("decimal"):
        return "Debe ser un número válido."
    if kind.startswith("bool"):
        return "Debe ser verdadero o falso."
    if kind == "uuid_parsing" or kind == "uuid_type":
        return "Identificador inválido."
    if kind == "json_invalid":
        return "El cuerpo de la solicitud no es JSON válido."
    if kind == "value_error":
        message = str(error.get("msg", ""))
        return message.removeprefix("Value error, ") or "Valor inválido."
    if kind == "string_type":
        return "Debe ser texto."
    if kind in ("list_type", "model_type", "dict_type", "model_attributes_type"):
        return "Formato inválido."
    return "Valor inválido."


def _field_name(loc: tuple[Any, ...]) -> str:
    parts = [str(p) for p in loc[1:]] if len(loc) > 1 else [str(loc[0]) if loc else "body"]
    return ".".join(parts) or "body"


async def _validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    raw = exc.errors()
    # A malformed id in the URL is a route miss in the previous API (`{id:guid}` constraint).
    if raw and all(e.get("loc", ("",))[0] == "path" for e in raw):
        return problem_response(404, _STATUS_TITLES[404])

    errors: dict[str, list[str]] = {}
    for error in raw:
        field = _field_name(tuple(error.get("loc", ())))
        message = _translate(error)
        bucket = errors.setdefault(field, [])
        if message not in bucket:
            bucket.append(message)
    return problem_response(400, VALIDATION_TITLE, errors)


async def _api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    return problem_response(exc.status, exc.title, exc.errors, exc.headers, **exc.extra)


async def _http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    title = exc.detail if isinstance(exc.detail, str) and exc.status_code not in _STATUS_TITLES else None
    return problem_response(
        exc.status_code,
        title or _STATUS_TITLES.get(exc.status_code, str(exc.detail)),
        headers=getattr(exc, "headers", None),
    )


async def _unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Error no controlado en %s %s", request.method, request.url.path)
    return problem_response(500, _STATUS_TITLES[500])


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, _validation_handler)  # type: ignore[arg-type]
    app.add_exception_handler(ApiError, _api_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, _http_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _unhandled_handler)

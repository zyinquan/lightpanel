"""Uniform error responses."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from ..domain.errors import LightPanelError

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(LightPanelError)
    async def _handle_domain_error(request: Request, exc: LightPanelError) -> JSONResponse:
        payload = exc.to_dict()
        if exc.status_code >= 500:
            # 5xx 多为可预期的运行失败（引擎不可用、命令非零退出），只记摘要；
            # 需要堆栈时把日志级别调到 DEBUG。
            logger.error(
                "request failed (status=%s, code=%s): %s", exc.status_code, exc.code, exc
            )
            logger.debug("error details", exc_info=exc)
        else:
            logger.warning("request rejected: %s", exc)
        return JSONResponse(status_code=exc.status_code, content=payload)

    @app.exception_handler(RequestValidationError)
    async def _handle_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {"field": ".".join(str(p) for p in e.get("loc", ())[1:]), "message": e.get("msg", "")}
            for e in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={
                "code": "validation_error",
                "message": "Request validation failed",
                "details": {"errors": errors},
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": "http_error", "message": str(exc.detail), "details": {}},
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled error while serving %s", request.url.path)
        return JSONResponse(
            status_code=500,
            content={
                "code": "internal_error",
                "message": "Internal server error",
                "details": {},
            },
        )

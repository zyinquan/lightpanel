"""FastAPI application factory."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .. import __version__
from ..composition import AppContainer, build_container
from ..config import AppConfig
from . import errors, routers
from .schemas import HealthOut

logger = logging.getLogger(__name__)

STATIC_CANDIDATES = (
    Path(__file__).resolve().parents[4] / "frontend" / "dist",
    Path("frontend/dist"),
    Path("/app/frontend/dist"),
)


def create_app(
    container: AppContainer | None = None,
    *,
    config: AppConfig | None = None,
) -> FastAPI:
    """Build the ASGI application.

    ``container`` may be injected directly (tests, embedding) or built from
    ``config`` (CLI, uvicorn).
    """
    if container is None:
        container = build_container(config or AppConfig())
    config = container.config

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info(
            "lightpanel %s starting (env=%s, docker=%s)",
            __version__,
            config.env,
            type(container.container_engine).__name__,
        )
        yield
        await container.aclose()

    app = FastAPI(
        title="LightPanel",
        description=(
            "轻量级自托管服务器面板：系统状态、软件标签、Docker / Compose 控制与自定义命令。"
        ),
        version=__version__,
        docs_url="/docs" if config.server.docs else None,
        redoc_url="/redoc" if config.server.docs else None,
        openapi_url="/openapi.json" if config.server.docs else None,
        root_path=config.server.root_path,
        lifespan=lifespan,
    )
    app.state.container = container

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(config.server.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    errors.register_exception_handlers(app)

    prefix = config.server.api_prefix.rstrip("/")

    @app.get(f"{prefix}/health", response_model=HealthOut, tags=["meta"])
    async def health() -> HealthOut:
        return HealthOut(status="ok", version=__version__, env=config.env)

    protected: list = []
    if container.auth.enabled:
        protected.append(Depends(container.auth))

    app.include_router(routers.system, prefix=prefix, dependencies=protected)
    app.include_router(routers.catalog, prefix=prefix, dependencies=protected)
    app.include_router(routers.containers, prefix=prefix, dependencies=protected)
    app.include_router(routers.stacks, prefix=prefix, dependencies=protected)
    app.include_router(routers.commands, prefix=prefix, dependencies=protected)
    app.include_router(routers.auth, prefix=prefix)

    _mount_frontend(app)
    return app


def _mount_frontend(app: FastAPI) -> None:
    """Serve the built SPA when it exists; the API works without it."""
    for candidate in STATIC_CANDIDATES:
        if candidate.is_dir() and (candidate / "index.html").is_file():
            app.mount("/", StaticFiles(directory=str(candidate), html=True), name="frontend")
            logger.info("serving frontend from %s", candidate)
            return
    logger.info("frontend build not found; API-only mode")


__all__ = ["create_app"]

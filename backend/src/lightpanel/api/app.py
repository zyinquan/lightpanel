"""FastAPI application factory."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

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


class SPAStaticFiles(StaticFiles):
    """静态托管 + history 路由回退。

    前端用 ``createWebHistory``，直接刷新 ``/containers`` 时磁盘上并没有这个文件；
    这里把「无扩展名且不是 API 前缀」的 404 回退到 ``index.html``，交给路由处理。
    """

    def __init__(self, *, directory: str, api_prefix: str = "/api", **kwargs) -> None:
        super().__init__(directory=directory, html=True, **kwargs)
        self.api_prefix = api_prefix.rstrip("/") or "/api"

    async def get_response(self, path: str, scope):
        try:
            response = await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404 or not self._should_fallback(path):
                raise
            response = await super().get_response("index.html", scope)
        self._apply_cache_headers(path, response)
        return response

    def _apply_cache_headers(self, path: str, response) -> None:
        """入口 HTML 必须每次回源验证，带哈希的产物可以长期缓存。

        ``index.html`` 里引用的 js 文件名带内容哈希，升级后旧文件就不再存在。
        浏览器若拿缓存的旧 HTML，会去请求已被删掉的旧 js，页面直接白屏——
        所以这里对 HTML 强制 ``no-cache``，只让 ``assets/`` 走长缓存。
        """
        cleaned = "/" + path.replace("\\", "/").lstrip("/")
        if cleaned.startswith("/assets/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            response.headers["Cache-Control"] = "no-cache"

    def _should_fallback(self, path: str) -> bool:
        # Windows 下 StaticFiles 会把分隔符换成反斜杠，先归一化再判断
        cleaned = "/" + path.replace("\\", "/").lstrip("/")
        if cleaned == self.api_prefix or cleaned.startswith(self.api_prefix + "/"):
            return False
        # 缺失的静态资源仍然返回 404，避免把 HTML 当成 js/css 返回
        return not Path(cleaned).suffix


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

    _mount_frontend(app, config.server.api_prefix)
    return app


def _mount_frontend(app: FastAPI, api_prefix: str = "/api") -> None:
    """Serve the built SPA when it exists; the API works without it."""
    for candidate in STATIC_CANDIDATES:
        if candidate.is_dir() and (candidate / "index.html").is_file():
            app.mount(
                "/",
                SPAStaticFiles(directory=str(candidate), api_prefix=api_prefix),
                name="frontend",
            )
            logger.info("serving frontend from %s", candidate)
            return
    logger.info("frontend build not found; API-only mode")


__all__ = ["SPAStaticFiles", "create_app"]

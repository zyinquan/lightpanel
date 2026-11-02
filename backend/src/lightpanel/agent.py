"""宿主机代理（``lightpanel-agent``）。

面板以容器方式部署时有两件事在容器里做不对：

1. **指标** —— 容器里的 psutil 读不到宿主机（Windows / macOS 上更只能读到
   Docker Desktop 的 Linux 虚拟机），得到的是容器自身的数字；
2. **compose** —— ``docker compose`` 会在它自己所在的文件系统上解析相对挂载
   （``./src:/app``），容器里解析出来的路径交给宿主机 docker 守护进程后并不存在，
   守护进程会建一个空目录顶上，容器照常起来了、代码却没了，而且不报错。

让宿主机跑这个小进程，把同一份领域模型通过 HTTP 暴露出去，面板侧用
:class:`RemoteMetricsProvider` 与 :class:`AgentComposeBackend` 取用即可。

用法::

    python -m lightpanel.agent --port 9101                  # 仅本机可访问
    python -m lightpanel.agent --host 0.0.0.0               # 面板在容器里时用这个
    python -m lightpanel.agent --token s3cret               # 需要鉴权时
    python -m lightpanel.agent --host 0.0.0.0 \\
        --stacks-root E:/docker-test --stacks-root E:/work

面板侧配置::

    metrics:
      remote_url: http://host.docker.internal:9101/metrics
      remote_token: s3cret          # 与 --token 一致，可留空
    compose:
      runner: agent
      agent_url: http://host.docker.internal:9101
      agent_token: s3cret
"""

from __future__ import annotations

import argparse
import logging
import os
from collections.abc import Sequence

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .adapters.docker.compose_scan import scan_projects
from .adapters.executor.subprocess_executor import SubprocessCommandExecutor
from .adapters.metrics.psutil_provider import PsutilMetricsProvider
from .api.schemas import CommandResultOut, StackOut, SystemOut
from .domain.errors import LightPanelError
from .domain.ports import MetricsProvider
from .services.host_compose import HostComposeService

logger = logging.getLogger(__name__)


class _ComposeActionIn(BaseModel):
    """只有动作、项目名与路径 —— 不接受自由命令行。"""

    name: str
    action: str
    config_files: str = ""
    working_dir: str = ""
    extra_args: list[str] = Field(default_factory=list)


def create_agent_app(
    provider: MetricsProvider | None = None,
    token: str = "",
    compose: HostComposeService | None = None,
) -> FastAPI:
    """Build the agent's FastAPI app (collaborators are injectable for tests)."""
    metrics = provider or PsutilMetricsProvider()
    app = FastAPI(title="LightPanel Host Agent", version="0.2.0", docs_url=None, redoc_url=None)

    @app.exception_handler(LightPanelError)
    async def domain_error_handler(_request: Request, exc: LightPanelError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=exc.to_dict())

    async def authorize(authorization: str | None = Header(default=None)) -> None:
        if not token:
            return
        if authorization != f"Bearer {token}":
            raise HTTPException(status_code=401, detail="invalid agent token")

    @app.get("/health", summary="代理存活检查")
    async def health() -> dict[str, object]:
        return {
            "status": "ok",
            "provider": metrics.name,
            "compose": compose is not None,
        }

    @app.get(
        "/metrics",
        response_model=SystemOut,
        dependencies=[Depends(authorize)],
        summary="宿主机指标快照",
    )
    async def snapshot() -> SystemOut:
        return SystemOut.from_domain(await metrics.snapshot())

    # -- compose ----------------------------------------------------------- #
    def require_compose() -> HostComposeService:
        if compose is None:
            raise LightPanelError(
                "agent 未启用 compose（启动时未指定 --stacks-root）",
                hint="用 --stacks-root 指定宿主机上的栈目录后重启代理",
            )
        return compose

    @app.get(
        "/compose/stacks",
        response_model=list[StackOut],
        dependencies=[Depends(authorize)],
        summary="宿主机上的 compose 项目",
    )
    async def compose_stacks() -> list[StackOut]:
        service = require_compose()
        return [StackOut.from_domain(s) for s in service.list_projects()]

    @app.post(
        "/compose/action",
        response_model=CommandResultOut,
        dependencies=[Depends(authorize)],
        summary="在宿主机上执行 compose 动作",
    )
    async def compose_action(payload: _ComposeActionIn) -> CommandResultOut:
        service = require_compose()
        result = await service.act(
            payload.name,
            payload.action,
            config_files=payload.config_files,
            working_dir=payload.working_dir,
            extra_args=payload.extra_args,
        )
        return CommandResultOut.from_domain(result)

    return app


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="lightpanel-agent",
        description="把宿主机指标与 compose 操作以 HTTP 暴露给 LightPanel（面板在容器里时必需）",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="监听地址；面板跑在容器内时用 0.0.0.0（默认只监听本机）",
    )
    parser.add_argument("--port", type=int, default=9101, help="监听端口（默认 9101）")
    parser.add_argument(
        "--token",
        default=os.environ.get("LIGHTPANEL_AGENT_TOKEN", ""),
        help="可选共享令牌；设置后请求需带 Authorization: Bearer <token>",
    )
    parser.add_argument(
        "--stacks-root",
        action="append",
        default=[],
        metavar="PATH",
        help="允许 agent 管理的 compose 根目录，可重复指定；不传则不启用 compose",
    )
    parser.add_argument("--max-depth", type=int, default=3, help="栈目录扫描深度（默认 3）")
    parser.add_argument("--compose-timeout", type=float, default=600.0, help="compose 超时秒数")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    compose: HostComposeService | None = None
    if args.stacks_root:
        compose = HostComposeService(
            args.stacks_root,
            max_depth=args.max_depth,
            timeout=args.compose_timeout,
            executor=SubprocessCommandExecutor(allowed_binaries=("docker", "docker-compose")),
            scanner=scan_projects,
        )

    if args.host not in ("127.0.0.1", "localhost", "::1") and not args.token:
        logger.warning(
            "agent 正在 %s:%s 上无鉴权监听，同网段任何人都能读到本机指标、"
            "并对 --stacks-root 下的 compose 项目执行启停（down 会删除容器）；"
            "强烈建议加 --token 或在防火墙层限制来源。",
            args.host,
            args.port,
        )
    logger.info("lightpanel-agent 监听 http://%s:%s/metrics", args.host, args.port)
    if compose is not None:
        logger.info("compose 已启用，栈根目录：%s", ", ".join(compose.roots))

    uvicorn.run(create_agent_app(token=args.token, compose=compose), host=args.host, port=args.port)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

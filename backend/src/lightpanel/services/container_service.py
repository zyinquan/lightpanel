"""Container use-cases."""

from __future__ import annotations

import asyncio
from enum import StrEnum
from time import monotonic
from typing import Any

from ..domain.errors import EngineUnavailableError, NotFoundError, ValidationError
from ..domain.models import ContainerInfo, ContainerState, ContainerUsage
from ..domain.ports import ContainerEngine

# 一次 stats 采样要等 daemon 跑完一个周期（~1s），十几个容器叠起来很贵；
# 面板侧不必秒级刷新，缓存几秒就能把成本压到一次采样。
USAGE_CACHE_TTL = 5.0
USAGE_PER_CONTAINER_TIMEOUT = 6.0


class ContainerAction(StrEnum):
    START = "start"
    STOP = "stop"
    RESTART = "restart"
    REMOVE = "remove"


class ContainerService:
    """Listing and lifecycle operations for containers."""

    def __init__(self, engine: ContainerEngine) -> None:
        self.engine = engine
        self._usage_cache: dict[str, ContainerUsage] = {}
        self._usage_sampled_at = 0.0
        self._usage_lock = asyncio.Lock()
        self._refresh_task: asyncio.Task[None] | None = None

    async def list_containers(
        self,
        *,
        include_stopped: bool = True,
        search: str = "",
        project: str = "",
        state: str = "",
    ) -> list[ContainerInfo]:
        containers = await self.engine.list_containers(include_stopped=include_stopped)
        needle = search.strip().casefold()
        project_needle = project.strip().casefold()
        wanted_state = ContainerState.parse(state) if state else None
        filtered: list[ContainerInfo] = []
        for container in containers:
            if needle and needle not in f"{container.name} {container.image}".casefold():
                continue
            if project_needle and container.compose_project.casefold() != project_needle:
                continue
            if wanted_state and container.state != wanted_state:
                continue
            filtered.append(container)
        return filtered

    async def get(self, container_id: str) -> ContainerInfo:
        try:
            return await self.engine.get_container(container_id)
        except NotFoundError:
            raise

    async def act(
        self, container_id: str, action: ContainerAction | str, *, timeout: int | None = None
    ) -> ContainerInfo:
        try:
            normalized = ContainerAction(_action_value(action))
        except ValueError as exc:
            raise ValidationError(f"Unsupported container action: {action}") from exc

        before = await self.engine.get_container(container_id)
        try:
            if normalized is ContainerAction.START:
                await self.engine.start(container_id)
            elif normalized is ContainerAction.STOP:
                await self.engine.stop(container_id, timeout=timeout)
            elif normalized is ContainerAction.RESTART:
                await self.engine.restart(container_id, timeout=timeout)
            elif normalized is ContainerAction.REMOVE:
                await self.engine.remove(container_id, force=True)
        except NotFoundError:
            raise
        if normalized is ContainerAction.REMOVE:
            return before
        return await self.engine.get_container(container_id)

    async def logs(self, container_id: str, *, tail: int = 200) -> str:
        if tail < 1 or tail > 10_000:
            raise ValidationError("tail must be between 1 and 10000")
        return await self.engine.logs(container_id, tail=tail)

    async def usage_map(self, *, max_age: float = USAGE_CACHE_TTL) -> dict[str, ContainerUsage]:
        """运行中容器的 CPU / 内存快照，按容器 ID 索引。

        只采集 ``state.is_active`` 的容器（停掉的没有 stats）；单个容器失败
        （刚退出、权限、超时）不影响整体——那块就直接缺省，页面显示「—」。

        回包永远不阻塞：有旧快照就先给旧快照，过期了在后台补一轮。一次
        stats 采样要等 daemon 约 1~3 秒，十几个容器若同步等待，页面每次
        轮询都会被拖住；页面上的占用数字差几秒也无所谓。
        """
        if not hasattr(self.engine, "usage"):
            return {}
        if self._usage_cache:
            if monotonic() - self._usage_sampled_at >= max_age:
                self._refresh_in_background()
            return dict(self._usage_cache)
        await self._refresh()  # 首次必须先有数字，否则首屏一片「—」
        return dict(self._usage_cache)

    async def _refresh(self) -> None:
        async with self._usage_lock:
            running = [
                c
                for c in await self.engine.list_containers(include_stopped=False)
                if c.state.is_active
            ]
            sampled = await asyncio.gather(
                *(self._sample_usage(c.id) for c in running), return_exceptions=True
            )
            self._usage_cache = {
                item.container_id: item for item in sampled if isinstance(item, ContainerUsage)
            }
            self._usage_sampled_at = monotonic()

    def _refresh_in_background(self) -> None:
        if self._refresh_task is not None and not self._refresh_task.done():
            return  # 已有一轮在跑，别叠第二个
        self._refresh_task = asyncio.create_task(self._refresh())

    async def _sample_usage(self, container_id: str) -> ContainerUsage | None:
        try:
            return await asyncio.wait_for(
                self.engine.usage(container_id), timeout=USAGE_PER_CONTAINER_TIMEOUT
            )
        except (EngineUnavailableError, NotFoundError, TimeoutError, OSError):
            return None

    async def status(self) -> dict[str, Any]:
        available = await self.engine.is_available()
        total = running = 0
        if available:
            containers = await self.engine.list_containers(include_stopped=True)
            total = len(containers)
            running = sum(1 for c in containers if c.state.is_active)
        return {
            "provider": getattr(self.engine, "name", "unknown"),
            "available": available,
            "total": total,
            "running": running,
            "stopped": total - running,
        }

    @staticmethod
    def ensure_available(available: bool) -> None:
        if not available:
            raise EngineUnavailableError("Docker engine is unavailable")


def _action_value(action: ContainerAction | str) -> str:
    """``str(ContainerAction.STOP)`` is 'ContainerAction.STOP'; we want 'stop'."""
    raw = action.value if isinstance(action, ContainerAction) else str(action)
    return raw.lower()

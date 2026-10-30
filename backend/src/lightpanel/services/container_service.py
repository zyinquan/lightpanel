"""Container use-cases."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from ..domain.errors import EngineUnavailableError, NotFoundError, ValidationError
from ..domain.models import ContainerInfo, ContainerState
from ..domain.ports import ContainerEngine


class ContainerAction(StrEnum):
    START = "start"
    STOP = "stop"
    RESTART = "restart"
    REMOVE = "remove"


class ContainerService:
    """Listing and lifecycle operations for containers."""

    def __init__(self, engine: ContainerEngine) -> None:
        self.engine = engine

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

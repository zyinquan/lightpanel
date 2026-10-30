"""Container engine used when Docker support is disabled."""

from __future__ import annotations

from ...domain.errors import EngineUnavailableError
from ...domain.models import ContainerInfo


class NullContainerEngine:
    """Every operation fails with :class:`EngineUnavailableError`."""

    @property
    def name(self) -> str:
        return "disabled"

    async def is_available(self) -> bool:
        return False

    async def list_containers(self, *, include_stopped: bool = True) -> list[ContainerInfo]:
        raise EngineUnavailableError("Docker support is disabled")

    async def get_container(self, container_id: str) -> ContainerInfo:
        raise EngineUnavailableError("Docker support is disabled")

    async def start(self, container_id: str) -> None:
        raise EngineUnavailableError("Docker support is disabled")

    async def stop(self, container_id: str, *, timeout: int | None = None) -> None:
        raise EngineUnavailableError("Docker support is disabled")

    async def restart(self, container_id: str, *, timeout: int | None = None) -> None:
        raise EngineUnavailableError("Docker support is disabled")

    async def remove(self, container_id: str, *, force: bool = False) -> None:
        raise EngineUnavailableError("Docker support is disabled")

    async def logs(self, container_id: str, *, tail: int = 200) -> str:
        raise EngineUnavailableError("Docker support is disabled")

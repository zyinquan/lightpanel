"""Container engine used when there is no usable Docker endpoint.

Two very different situations end up here, and the message is what users see on
the containers page: "disabled" is a configuration choice, while "no endpoint" is
almost always a deployment mistake (socket not mounted, ``docker.host`` empty
inside a container). Keep them distinct so the fix is obvious.
"""

from __future__ import annotations

from ...domain.errors import EngineUnavailableError
from ...domain.models import ContainerInfo

DISABLED_REASON = "Docker support is disabled (docker.enabled = false)"
NO_ENDPOINT_REASON = (
    "No Docker endpoint is reachable from this process: mount /var/run/docker.sock, "
    "or set docker.mode = api with docker.host pointing at the engine"
)


class NullContainerEngine:
    """Every operation fails with :class:`EngineUnavailableError`."""

    def __init__(self, reason: str = DISABLED_REASON) -> None:
        self.reason = reason

    @property
    def name(self) -> str:
        return "disabled"

    async def is_available(self) -> bool:
        return False

    def _fail(self) -> None:
        raise EngineUnavailableError(self.reason)

    async def list_containers(self, *, include_stopped: bool = True) -> list[ContainerInfo]:
        self._fail()
        return []  # pragma: no cover - keeps the declared return type honest

    async def get_container(self, container_id: str) -> ContainerInfo:
        self._fail()
        raise AssertionError("unreachable")  # pragma: no cover

    async def start(self, container_id: str) -> None:
        self._fail()

    async def stop(self, container_id: str, *, timeout: int | None = None) -> None:
        self._fail()

    async def restart(self, container_id: str, *, timeout: int | None = None) -> None:
        self._fail()

    async def remove(self, container_id: str, *, force: bool = False) -> None:
        self._fail()

    async def logs(self, container_id: str, *, tail: int = 200) -> str:
        self._fail()
        return ""  # pragma: no cover

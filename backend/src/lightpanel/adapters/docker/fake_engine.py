"""In-memory container engine for tests and for running LightPanel without Docker."""

from __future__ import annotations

import copy
from collections.abc import Sequence

from ...domain.errors import NotFoundError
from ...domain.models import ContainerInfo, ContainerState, ContainerUsage


class FakeContainerEngine:
    """A container engine you can script. Used when ``docker.mode: fake``."""

    def __init__(
        self,
        containers: Sequence[ContainerInfo] | None = None,
        *,
        available: bool = True,
    ) -> None:
        self._containers: dict[str, ContainerInfo] = {}
        for container in containers or []:
            self._containers[container.id] = container
        self._available = available
        self.log_calls: list[tuple[str, int]] = []

    # -- scripting helpers ------------------------------------------------- #
    @classmethod
    def with_demo_data(cls) -> FakeContainerEngine:
        return cls(list(demo_containers()))

    def set_available(self, available: bool) -> None:
        self._available = available

    # -- port implementation ----------------------------------------------- #
    @property
    def name(self) -> str:
        return "fake"

    async def is_available(self) -> bool:
        return self._available

    async def list_containers(self, *, include_stopped: bool = True) -> list[ContainerInfo]:
        containers = [copy.deepcopy(c) for c in self._containers.values()]
        if not include_stopped:
            containers = [c for c in containers if c.state.is_active]
        return sorted(containers, key=lambda c: c.name)

    async def get_container(self, container_id: str) -> ContainerInfo:
        return copy.deepcopy(self._require(container_id))

    async def start(self, container_id: str) -> None:
        self._set_state(container_id, ContainerState.RUNNING)

    async def stop(self, container_id: str, *, timeout: int | None = None) -> None:
        self._set_state(container_id, ContainerState.EXITED)

    async def restart(self, container_id: str, *, timeout: int | None = None) -> None:
        self._set_state(container_id, ContainerState.RUNNING)

    async def remove(self, container_id: str, *, force: bool = False) -> None:
        container = self._require(container_id)
        del self._containers[container.id]

    async def logs(self, container_id: str, *, tail: int = 200) -> str:
        container = self._require(container_id)
        self.log_calls.append((container_id, tail))
        return f"fake logs for {container.name} (tail={tail})\nline 1\nline 2"

    async def usage(self, container_id: str) -> ContainerUsage:
        """Deterministic numbers so UI tests and ``docker.mode: fake`` are stable."""
        container = self._require(container_id)
        if not container.state.is_active:
            raise NotFoundError(f"Container {container_id} is not running")
        seed = sum(ord(ch) for ch in container.name)
        return ContainerUsage(
            container_id=container_id,
            cpu_percent=round((seed % 40) / 4, 2),  # 0.00 ~ 9.75
            memory_bytes=(seed % 200 + 16) * 1024 * 1024,
            memory_limit_bytes=2 * 1024 * 1024 * 1024,
        )

    # -- internals --------------------------------------------------------- #
    def _require(self, container_id: str) -> ContainerInfo:
        container = self._containers.get(container_id)
        if container is None:
            for candidate in self._containers.values():
                if candidate.name == container_id or candidate.id.startswith(container_id):
                    return candidate
            raise NotFoundError(f"Container not found: {container_id}")
        return container

    def _set_state(self, container_id: str, state: ContainerState) -> None:
        container = self._require(container_id)
        status = "Up 5 minutes" if state == ContainerState.RUNNING else "Exited (0) 2 seconds ago"
        self._containers[container.id] = ContainerInfo(
            id=container.id,
            name=container.name,
            image=container.image,
            state=state,
            status=status,
            created_at=container.created_at,
            ports=container.ports,
            labels=container.labels,
            command=container.command,
        )


def demo_containers() -> list[ContainerInfo]:
    """A small, realistic fixture used by the fake engine and by tests."""
    return [
        ContainerInfo(
            id="a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6",
            name="lightpanel-web",
            image="ghcr.io/example/lightpanel:0.1.0",
            state=ContainerState.RUNNING,
            status="Up 3 hours",
            ports=[],
            labels={
                "com.docker.compose.project": "lightpanel",
                "com.docker.compose.service": "web",
                "com.docker.compose.project.working_dir": "/opt/lightpanel",
                "com.docker.compose.project.config_files": "/opt/lightpanel/docker-compose.yml",
            },
        ),
        ContainerInfo(
            id="b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1",
            name="postgres",
            image="postgres:16-alpine",
            state=ContainerState.RUNNING,
            status="Up 3 hours (healthy)",
            labels={
                "com.docker.compose.project": "lightpanel",
                "com.docker.compose.service": "db",
                "com.docker.compose.project.working_dir": "/opt/lightpanel",
                "com.docker.compose.project.config_files": "/opt/lightpanel/docker-compose.yml",
            },
        ),
        ContainerInfo(
            id="c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
            name="redis",
            image="redis:7-alpine",
            state=ContainerState.EXITED,
            status="Exited (0) 10 minutes ago",
            labels={"com.docker.compose.project": "cache"},
        ),
        ContainerInfo(
            id="d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3",
            name="nginx",
            image="nginx:1.27-alpine",
            state=ContainerState.RUNNING,
            status="Up 2 days",
        ),
    ]

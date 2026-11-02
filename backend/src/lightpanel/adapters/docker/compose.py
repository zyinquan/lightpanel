"""Docker Compose stack engine.

Compose has no Engine API, so stacks are controlled by shelling out to
``docker compose``. Two things have to happen for that to work:

* **discovery** — where are the projects? two sources are merged so both running
  and stopped projects show up: compose labels on live containers
  (``com.docker.compose.project`` …) and a bounded filesystem scan;
* **execution** — *which* filesystem does ``docker compose`` see?

The second point is why there is a :class:`ComposeBackend` seam. When the panel
runs inside a container the compose subprocess runs *there*, so a relative bind
mount such as ``./src:/app`` is resolved against the container's filesystem and
handed to the host daemon as ``/data/probe/src`` — a path that does not exist on
the host, so Docker silently creates an empty directory and the container comes
up without the source code. :class:`AgentComposeBackend` avoids that by asking an
agent running on the host to execute compose instead.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Protocol, runtime_checkable

from ...compose_cli import build_argv
from ...config import ComposeConfig
from ...domain.errors import EngineUnavailableError, NotFoundError, ValidationError
from ...domain.models import (
    CommandResult,
    ContainerInfo,
    StackInfo,
    StackStatus,
)
from ...domain.ports import CommandExecutor, ContainerEngine
from .compose_scan import COMPOSE_FILENAMES, project_name, scan_projects

__all__ = [
    "COMPOSE_FILENAMES",
    "ComposeBackend",
    "ComposeStackEngine",
    "LocalComposeBackend",
    "project_name",
    "scan_projects",
    "stacks_from_containers",
]

logger = logging.getLogger(__name__)


@runtime_checkable
class ComposeBackend(Protocol):
    """Where compose projects are discovered and where the CLI is executed."""

    @property
    def name(self) -> str: ...

    async def is_available(self) -> bool: ...

    async def list_projects(self) -> list[StackInfo]: ...

    async def act(
        self,
        stack: StackInfo,
        action: str,
        *,
        extra_args: Sequence[str] = (),
    ) -> CommandResult: ...


class ComposeStackEngine:
    """Implements the :class:`StackEngine` port for Docker Compose."""

    def __init__(
        self,
        container_engine: ContainerEngine,
        backend: ComposeBackend,
        settings: ComposeConfig | None = None,
    ) -> None:
        self.containers = container_engine
        self.backend = backend
        self.settings = settings or ComposeConfig()

    @property
    def name(self) -> str:
        return self.backend.name

    async def is_available(self) -> bool:
        if not self.settings.enabled:
            return False
        return await self.backend.is_available()

    async def list_stacks(self) -> list[StackInfo]:
        containers = await self.containers.list_containers(include_stopped=True)
        stacks = stacks_from_containers(containers)
        for stack in await self.backend.list_projects():
            existing = stacks.get(stack.name)
            if existing is None:
                stacks[stack.name] = stack
            elif not existing.discovered_paths and stack.discovered_paths:
                stacks[stack.name] = StackInfo(
                    name=existing.name,
                    config_files=existing.config_files,
                    working_dir=existing.working_dir or stack.working_dir,
                    containers=existing.containers,
                    discovered_paths=stack.discovered_paths,
                    status=existing.status,
                )
        return sorted(stacks.values(), key=lambda s: s.name)

    async def get_stack(self, name: str) -> StackInfo:
        for stack in await self.list_stacks():
            if stack.name == name:
                return stack
        raise NotFoundError(f"Stack not found: {name}")

    async def up(self, stack: StackInfo, *, extra_args: Sequence[str] = ()) -> CommandResult:
        return await self.backend.act(stack, "up", extra_args=extra_args)

    async def down(self, stack: StackInfo, *, extra_args: Sequence[str] = ()) -> CommandResult:
        return await self.backend.act(stack, "down", extra_args=extra_args)

    async def restart(self, stack: StackInfo, *, extra_args: Sequence[str] = ()) -> CommandResult:
        return await self.backend.act(stack, "restart", extra_args=extra_args)

    async def pull(self, stack: StackInfo, *, extra_args: Sequence[str] = ()) -> CommandResult:
        return await self.backend.act(stack, "pull", extra_args=extra_args)


class LocalComposeBackend:
    """Runs ``docker compose`` in this process.

    Only correct when the project files are visible *here* — i.e. the panel runs
    directly on the host. In a container, use :class:`AgentComposeBackend`.
    """

    def __init__(self, executor: CommandExecutor, settings: ComposeConfig) -> None:
        self.executor = executor
        self.settings = settings

    @property
    def name(self) -> str:
        return "docker-compose"

    async def is_available(self) -> bool:
        if not self.settings.enabled:
            return False
        probe = self.executor.run(
            [*self.settings.base_argv(), "version"], timeout=min(15.0, self.settings.timeout)
        )
        try:
            result = await probe
        except Exception:  # pragma: no cover - defensive
            return False
        return result.ok

    async def list_projects(self) -> list[StackInfo]:
        if not self.settings.enabled:
            return []
        return scan_projects(self.settings.search_paths, self.settings.max_depth)

    def readable_config_files(self, stack: StackInfo) -> list[str]:
        """Config files that actually exist on *this* host.

        A stack discovered from container labels carries the paths recorded by
        whoever ran compose — a ``compose.yml`` under ``/opt/app`` on the host is
        invisible to a panel running in a container. Only files we can read may
        go to ``-f``; the project name alone is enough for ``down``/``restart``
        because compose looks those containers up by label.
        """
        return [f for f in stack.config_files.split(",") if f and Path(f).is_file()]

    def build_argv(
        self, stack: StackInfo, action: str, extra_args: Sequence[str] = ()
    ) -> list[str]:
        readable = self.readable_config_files(stack)
        if action in ("up", "pull") and not readable:
            raise ValidationError(
                f"Compose files for stack '{stack.name}' are not readable from this host",
                config_files=stack.config_files,
                hint=(
                    "put the project under one of compose.search_paths, or switch "
                    "compose.runner to 'agent' and run lightpanel-agent on the host"
                ),
            )
        argv = build_argv(
            self.settings.base_argv(),
            project=stack.name,
            action=action,
            config_files=readable,
            extra_args=extra_args,
        )
        return argv

    def resolve_cwd(self, stack: StackInfo) -> str | None:
        cwd = stack.working_dir or None
        if cwd and not Path(cwd).is_dir():
            # 宿主机上的工作目录在面板所在主机不存在：交给 compose 用 -f / 项目名解析
            return None
        return cwd

    async def act(
        self,
        stack: StackInfo,
        action: str,
        *,
        extra_args: Sequence[str] = (),
    ) -> CommandResult:
        if not self.settings.enabled:
            raise EngineUnavailableError("Docker Compose support is disabled")
        argv = self.build_argv(stack, action, extra_args)
        cwd = self.resolve_cwd(stack)
        logger.info("executing compose command", extra={"argv": argv, "cwd": cwd})
        return await self.executor.run(argv, cwd=cwd, timeout=self.settings.timeout)


def stacks_from_containers(containers: Iterable[ContainerInfo]) -> dict[str, StackInfo]:
    """Group containers into projects using their compose labels."""
    grouped: dict[str, list[ContainerInfo]] = {}
    for container in containers:
        project = container.compose_project
        if not project:
            continue
        grouped.setdefault(project, []).append(container)

    stacks: dict[str, StackInfo] = {}
    for project, members in grouped.items():
        members.sort(key=lambda c: c.compose_service or c.name)
        working_dir = next((c.compose_working_dir for c in members if c.compose_working_dir), "")
        config_files = next((c.compose_config_files for c in members if c.compose_config_files), "")
        stacks[project] = StackInfo(
            name=project,
            config_files=config_files,
            working_dir=working_dir,
            containers=members,
            status=_status_from_containers(members),
        )
    return stacks


def _status_from_containers(containers: Sequence[ContainerInfo]) -> StackStatus:
    if not containers:
        return StackStatus.UNKNOWN
    running = sum(1 for c in containers if c.state.is_active)
    if running == len(containers):
        return StackStatus.RUNNING
    if running == 0:
        return StackStatus.STOPPED
    return StackStatus.PARTIAL

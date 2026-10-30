"""Docker Compose stack engine.

Compose has no Engine API, so stacks are controlled by shelling out to
``docker compose`` through the :class:`CommandExecutor` port. Stack *discovery*
combines two sources so both running and stopped projects show up:

* compose labels on live containers (``com.docker.compose.project`` …),
* a bounded filesystem scan for ``compose.y[a]ml`` / ``docker-compose.y[a]ml``.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterable, Sequence
from pathlib import Path

from ...config import ComposeConfig
from ...domain.errors import EngineUnavailableError, NotFoundError
from ...domain.models import (
    CommandResult,
    ContainerInfo,
    StackInfo,
    StackStatus,
)
from ...domain.ports import CommandExecutor, ContainerEngine

logger = logging.getLogger(__name__)

COMPOSE_FILENAMES = (
    "compose.yaml",
    "compose.yml",
    "docker-compose.yaml",
    "docker-compose.yml",
)


class ComposeStackEngine:
    """Implements the :class:`StackEngine` port for Docker Compose."""

    def __init__(
        self,
        container_engine: ContainerEngine,
        executor: CommandExecutor,
        settings: ComposeConfig | None = None,
    ) -> None:
        self.containers = container_engine
        self.executor = executor
        self.settings = settings or ComposeConfig()

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

    async def list_stacks(self) -> list[StackInfo]:
        containers = await self.containers.list_containers(include_stopped=True)
        stacks = self._stacks_from_containers(containers)
        for stack in self._stacks_from_filesystem():
            if stack.name not in stacks:
                stacks[stack.name] = stack
            else:
                existing = stacks[stack.name]
                if not existing.discovered_paths and stack.discovered_paths:
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
        argv = [*self._prefix(stack), "up", "-d", *extra_args]
        return await self._run(argv, stack)

    async def down(self, stack: StackInfo, *, extra_args: Sequence[str] = ()) -> CommandResult:
        argv = [*self._prefix(stack), "down", *extra_args]
        return await self._run(argv, stack)

    async def restart(self, stack: StackInfo, *, extra_args: Sequence[str] = ()) -> CommandResult:
        argv = [*self._prefix(stack), "restart", *extra_args]
        return await self._run(argv, stack)

    async def pull(self, stack: StackInfo, *, extra_args: Sequence[str] = ()) -> CommandResult:
        argv = [*self._prefix(stack), "pull", *extra_args]
        return await self._run(argv, stack)

    # -- internals --------------------------------------------------------- #
    def _prefix(self, stack: StackInfo) -> list[str]:
        argv = list(self.settings.base_argv())
        files = [f for f in stack.config_files.split(",") if f]
        if files:
            for file in files:
                argv += ["-f", file]
            argv += ["-p", stack.name]
        elif stack.working_dir:
            argv += ["-p", stack.name]
        else:
            argv += ["-p", stack.name]
        return argv

    async def _run(self, argv: Sequence[str], stack: StackInfo) -> CommandResult:
        if not self.settings.enabled:
            raise EngineUnavailableError("Docker Compose support is disabled")
        cwd = stack.working_dir or None
        logger.info("executing compose command", extra={"argv": list(argv), "cwd": cwd})
        return await self.executor.run(argv, cwd=cwd, timeout=self.settings.timeout)

    def _stacks_from_containers(self, containers: Iterable[ContainerInfo]) -> dict[str, StackInfo]:
        grouped: dict[str, list[ContainerInfo]] = {}
        for container in containers:
            project = container.compose_project
            if not project:
                continue
            grouped.setdefault(project, []).append(container)

        stacks: dict[str, StackInfo] = {}
        for project, members in grouped.items():
            members.sort(key=lambda c: c.compose_service or c.name)
            working_dir = next(
                (c.compose_working_dir for c in members if c.compose_working_dir), ""
            )
            config_files = next(
                (c.compose_config_files for c in members if c.compose_config_files), ""
            )
            stacks[project] = StackInfo(
                name=project,
                config_files=config_files,
                working_dir=working_dir,
                containers=members,
                status=_status_from_containers(members),
            )
        return stacks

    def _stacks_from_filesystem(self) -> list[StackInfo]:
        if not self.settings.enabled:
            return []
        discovered: list[StackInfo] = []
        for raw_root in self.settings.search_paths:
            root = Path(raw_root)
            if not root.is_dir():
                continue
            for path in _walk_limited(root, self.settings.max_depth):
                for filename in COMPOSE_FILENAMES:
                    candidate = path / filename
                    if candidate.is_file():
                        discovered.append(
                            StackInfo(
                                name=_project_name(path, root),
                                config_files=str(candidate),
                                working_dir=str(path),
                                status=StackStatus.STOPPED,
                                discovered_paths=[str(candidate)],
                            )
                        )
                        break
        # de-duplicate by name, keeping the first hit
        seen: set[str] = set()
        unique: list[StackInfo] = []
        for stack in discovered:
            if stack.name in seen:
                continue
            seen.add(stack.name)
            unique.append(stack)
        return unique


def _status_from_containers(containers: Sequence[ContainerInfo]) -> StackStatus:
    if not containers:
        return StackStatus.UNKNOWN
    running = sum(1 for c in containers if c.state.is_active)
    if running == len(containers):
        return StackStatus.RUNNING
    if running == 0:
        return StackStatus.STOPPED
    return StackStatus.PARTIAL


def _project_name(directory: Path, root: Path) -> str:
    """Project name = directory name (Docker Compose v2 default)."""
    return directory.name or root.name or "default"


def _walk_limited(root: Path, max_depth: int):
    base_depth = len(root.parts)
    for current, dirs, _files in os.walk(root):
        depth = len(Path(current).parts) - base_depth
        if depth >= max_depth:
            dirs[:] = []
        yield Path(current)

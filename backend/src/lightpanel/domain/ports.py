"""Ports: the abstract contracts that services depend on.

Services never import adapters. Everything they need is expressed here as a
:class:`typing.Protocol`, so a new backend (Podman, LXC, a remote agent, ...)
can be added by writing one adapter and registering it in the composition root —
existing code stays untouched (open/closed principle).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol, runtime_checkable

from .models import (
    CommandResult,
    ContainerInfo,
    SoftwareEntry,
    StackInfo,
    SystemSnapshot,
)


@runtime_checkable
class MetricsProvider(Protocol):
    """Source of host metrics (psutil today, SNMP / remote agent tomorrow)."""

    @property
    def name(self) -> str:
        ...

    async def snapshot(self) -> SystemSnapshot:
        ...


@runtime_checkable
class CatalogRepository(Protocol):
    """Persistence for the software catalog."""

    async def list_entries(self) -> list[SoftwareEntry]:
        ...

    async def get(self, entry_id: str) -> SoftwareEntry | None:
        ...

    async def add(self, entry: SoftwareEntry) -> SoftwareEntry:
        ...

    async def update(self, entry: SoftwareEntry) -> SoftwareEntry:
        ...

    async def remove(self, entry_id: str) -> bool:
        ...

    async def replace_all(self, entries: Sequence[SoftwareEntry]) -> None:
        ...


@runtime_checkable
class ContainerEngine(Protocol):
    """Control plane for individual containers."""

    @property
    def name(self) -> str:
        ...

    async def is_available(self) -> bool:
        ...

    async def list_containers(self, *, include_stopped: bool = True) -> list[ContainerInfo]:
        ...

    async def get_container(self, container_id: str) -> ContainerInfo:
        ...

    async def start(self, container_id: str) -> None:
        ...

    async def stop(self, container_id: str, *, timeout: int | None = None) -> None:
        ...

    async def restart(self, container_id: str, *, timeout: int | None = None) -> None:
        ...

    async def remove(self, container_id: str, *, force: bool = False) -> None:
        ...

    async def logs(self, container_id: str, *, tail: int = 200) -> str:
        ...


@runtime_checkable
class StackEngine(Protocol):
    """Control plane for Docker Compose projects."""

    @property
    def name(self) -> str:
        ...

    async def is_available(self) -> bool:
        ...

    async def list_stacks(self) -> list[StackInfo]:
        ...

    async def get_stack(self, name: str) -> StackInfo:
        ...

    async def up(self, stack: StackInfo, *, extra_args: Sequence[str] = ()) -> CommandResult:
        ...

    async def down(self, stack: StackInfo, *, extra_args: Sequence[str] = ()) -> CommandResult:
        ...

    async def restart(self, stack: StackInfo, *, extra_args: Sequence[str] = ()) -> CommandResult:
        ...

    async def pull(self, stack: StackInfo, *, extra_args: Sequence[str] = ()) -> CommandResult:
        ...


@runtime_checkable
class CommandExecutor(Protocol):
    """Runs an explicit argv list on the host (never a shell string)."""

    async def run(
        self,
        argv: Sequence[str],
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> CommandResult:
        ...


@runtime_checkable
class Clock(Protocol):
    """Abstract time source, so services stay deterministic under test."""

    def now(self) -> float:
        ...

    def monotonic(self) -> float:
        ...


@runtime_checkable
class EventSink(Protocol):
    """Optional observability hook; implementations may be no-ops."""

    def emit(self, event: str, **payload: Any) -> None:
        ...

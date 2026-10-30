"""Pure domain entities.

These dataclasses are intentionally free of any framework, I/O or transport
concern: they are the vocabulary shared by every adapter and service.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


# --------------------------------------------------------------------------- #
# System status
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class HostInfo:
    hostname: str
    os_name: str
    os_version: str
    arch: str
    boot_time: float
    uptime_seconds: float


@dataclass(frozen=True, slots=True)
class CpuMetrics:
    percent: float
    logical_count: int
    physical_count: int | None
    per_cpu: list[float] = field(default_factory=list)
    load_average: tuple[float, float, float] | None = None
    frequency_mhz: float | None = None


@dataclass(frozen=True, slots=True)
class MemoryMetrics:
    total: int
    used: int
    available: int
    percent: float
    swap_total: int = 0
    swap_used: int = 0
    swap_percent: float = 0.0


@dataclass(frozen=True, slots=True)
class DiskMetrics:
    device: str
    mountpoint: str
    fstype: str
    total: int
    used: int
    free: int
    percent: float


@dataclass(frozen=True, slots=True)
class NetworkMetrics:
    bytes_sent: int
    bytes_recv: int
    packets_sent: int = 0
    packets_recv: int = 0
    interfaces: dict[str, dict[str, int]] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SystemSnapshot:
    host: HostInfo
    cpu: CpuMetrics
    memory: MemoryMetrics
    disks: list[DiskMetrics] = field(default_factory=list)
    network: NetworkMetrics | None = None
    collected_at: datetime | None = None


# --------------------------------------------------------------------------- #
# Software catalog (软件标签)
# --------------------------------------------------------------------------- #
@dataclass(slots=True)
class SoftwareEntry:
    """A single software / service shortcut shown on the panel."""

    id: str
    name: str
    url: str
    description: str = ""
    icon: str = ""
    color: str = ""
    category: str = ""
    tags: list[str] = field(default_factory=list)
    enabled: bool = True
    order: int = 0

    def normalized_tags(self) -> list[str]:
        seen: dict[str, str] = {}
        for raw in self.tags:
            tag = raw.strip()
            if not tag:
                continue
            seen[tag.casefold()] = tag
        return sorted(seen.values(), key=str.casefold)


@dataclass(frozen=True, slots=True)
class TagSummary:
    name: str
    count: int


# --------------------------------------------------------------------------- #
# Docker
# --------------------------------------------------------------------------- #
class ContainerState(StrEnum):
    RUNNING = "running"
    CREATED = "created"
    PAUSED = "paused"
    RESTARTING = "restarting"
    EXITED = "exited"
    DEAD = "dead"
    UNKNOWN = "unknown"

    @classmethod
    def parse(cls, raw: str | None) -> ContainerState:
        if not raw:
            return cls.UNKNOWN
        try:
            return cls(raw.lower())
        except ValueError:
            return cls.UNKNOWN

    @property
    def is_active(self) -> bool:
        return self in {
            ContainerState.RUNNING,
            ContainerState.PAUSED,
            ContainerState.RESTARTING,
        }


@dataclass(frozen=True, slots=True)
class PortBinding:
    host_ip: str = "0.0.0.0"
    host_port: str = ""
    container_port: str = ""
    protocol: str = "tcp"

    def display(self) -> str:
        if not self.host_port:
            return ""
        prefix = f"{self.host_ip}:" if self.host_ip and self.host_ip != "0.0.0.0" else ""
        suffix = f"/{self.protocol}" if self.protocol and self.protocol != "tcp" else ""
        return f"{prefix}{self.host_port}->{self.container_port}{suffix}"


@dataclass(frozen=True, slots=True)
class ContainerInfo:
    id: str
    name: str
    image: str
    state: ContainerState
    status: str = ""
    created_at: datetime | None = None
    ports: list[PortBinding] = field(default_factory=list)
    labels: dict[str, str] = field(default_factory=dict)
    command: str = ""

    @property
    def short_id(self) -> str:
        return self.id[:12]

    def label(self, key: str, default: str = "") -> str:
        return self.labels.get(key, default)

    @property
    def compose_project(self) -> str:
        return self.label("com.docker.compose.project")

    @property
    def compose_service(self) -> str:
        return self.label("com.docker.compose.service")

    @property
    def compose_config_files(self) -> str:
        return self.label("com.docker.compose.project.config_files")

    @property
    def compose_working_dir(self) -> str:
        return self.label("com.docker.compose.project.working_dir")


class StackStatus(StrEnum):
    RUNNING = "running"
    PARTIAL = "partial"
    STOPPED = "stopped"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class StackInfo:
    """A Docker Compose project, derived from compose labels on containers."""

    name: str
    config_files: str = ""
    working_dir: str = ""
    containers: list[ContainerInfo] = field(default_factory=list)
    discovered_paths: list[str] = field(default_factory=list)
    status: StackStatus = StackStatus.UNKNOWN

    @property
    def status_text(self) -> str:
        return self.status.value


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
class CommandTarget(StrEnum):
    CONTAINER = "container"
    STACK = "stack"
    SYSTEM = "system"


class CommandKind(StrEnum):
    """Whether a command talks to Docker directly or through the shell."""

    DOCKER_API = "docker_api"
    SHELL = "shell"


@dataclass(frozen=True, slots=True)
class CommandResult:
    argv: tuple[str, ...]
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    ok: bool = True

    @classmethod
    def success(
        cls, argv: tuple[str, ...], stdout: str = "", duration_ms: int = 0
    ) -> CommandResult:
        return cls(
            argv=argv,
            exit_code=0,
            stdout=stdout,
            stderr="",
            duration_ms=duration_ms,
            ok=True,
        )

    @classmethod
    def failure(
        cls,
        argv: tuple[str, ...],
        exit_code: int,
        stdout: str = "",
        stderr: str = "",
        duration_ms: int = 0,
    ) -> CommandResult:
        return cls(
            argv=argv,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            duration_ms=duration_ms,
            ok=False,
        )


@dataclass(frozen=True, slots=True)
class CommandDefinition:
    """A user-visible, re-usable command.

    ``argv`` is a template list. Placeholders ``{id}``, ``{name}``,
    ``{project}``, ``{config_file}``, ``{working_dir}`` and ``{image}`` are
    substituted at execution time from the command context.
    """

    id: str
    name: str
    target: CommandTarget
    argv: tuple[str, ...] = ()
    kind: CommandKind = CommandKind.SHELL
    action: str = ""
    description: str = ""
    confirm: bool = False
    danger: bool = False
    timeout: float = 120.0
    working_dir: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    builtin: bool = False

    def with_argv(self, argv: list[str]) -> CommandDefinition:
        return CommandDefinition(
            id=self.id,
            name=self.name,
            target=self.target,
            argv=tuple(argv),
            kind=self.kind,
            action=self.action,
            description=self.description,
            confirm=self.confirm,
            danger=self.danger,
            timeout=self.timeout,
            working_dir=self.working_dir,
            env=dict(self.env),
            builtin=self.builtin,
        )


@dataclass(frozen=True, slots=True)
class CommandContext:
    """Values available to argv templates."""

    values: dict[str, str] = field(default_factory=dict)

    @classmethod
    def of(cls, **values: Any) -> CommandContext:
        return cls(values={k: str(v) for k, v in values.items() if v is not None})

    def get(self, key: str, default: str = "") -> str:
        return self.values.get(key, default)

    def render(self, token: str) -> str:
        try:
            return token.format(**self.values)
        except (KeyError, IndexError):
            return token

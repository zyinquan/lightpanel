"""Pydantic DTOs.

The transport layer is the only place that knows about JSON. Keeping the
conversion here (``XxxOut.from_domain``) means domain objects stay free of
serialization concerns and the API can evolve independently.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..domain.models import (
    CommandDefinition,
    CommandResult,
    ContainerInfo,
    CpuMetrics,
    DiskMetrics,
    HostInfo,
    MemoryMetrics,
    NetworkMetrics,
    SoftwareEntry,
    StackInfo,
    SystemSnapshot,
)
from ..services.catalog_service import CatalogQuery
from ..services.system_service import MetricSample


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --------------------------------------------------------------------------- #
# System
# --------------------------------------------------------------------------- #
class HostOut(_Out):
    hostname: str
    os_name: str
    os_version: str
    arch: str
    boot_time: float
    uptime_seconds: float
    uptime_human: str

    @classmethod
    def from_domain(cls, host: HostInfo) -> HostOut:
        return cls(
            hostname=host.hostname,
            os_name=host.os_name,
            os_version=host.os_version,
            arch=host.arch,
            boot_time=host.boot_time,
            uptime_seconds=round(host.uptime_seconds, 1),
            uptime_human=human_duration(host.uptime_seconds),
        )


class CpuOut(_Out):
    percent: float
    logical_count: int
    physical_count: int | None
    per_cpu: list[float] = Field(default_factory=list)
    load_average: list[float] | None = None
    frequency_mhz: float | None = None

    @classmethod
    def from_domain(cls, cpu: CpuMetrics) -> CpuOut:
        return cls(
            percent=round(cpu.percent, 2),
            logical_count=cpu.logical_count,
            physical_count=cpu.physical_count,
            per_cpu=[round(v, 2) for v in cpu.per_cpu],
            load_average=list(cpu.load_average) if cpu.load_average else None,
            frequency_mhz=cpu.frequency_mhz,
        )


class MemoryOut(_Out):
    total: int
    used: int
    available: int
    percent: float
    total_human: str
    used_human: str
    swap_total: int = 0
    swap_used: int = 0
    swap_percent: float = 0.0

    @classmethod
    def from_domain(cls, memory: MemoryMetrics) -> MemoryOut:
        return cls(
            total=memory.total,
            used=memory.used,
            available=memory.available,
            percent=round(memory.percent, 2),
            total_human=human_bytes(memory.total),
            used_human=human_bytes(memory.used),
            swap_total=memory.swap_total,
            swap_used=memory.swap_used,
            swap_percent=round(memory.swap_percent, 2),
        )


class DiskOut(_Out):
    device: str
    mountpoint: str
    fstype: str
    total: int
    used: int
    free: int
    percent: float
    total_human: str
    used_human: str

    @classmethod
    def from_domain(cls, disk: DiskMetrics) -> DiskOut:
        return cls(
            device=disk.device,
            mountpoint=disk.mountpoint,
            fstype=disk.fstype,
            total=disk.total,
            used=disk.used,
            free=disk.free,
            percent=round(disk.percent, 2),
            total_human=human_bytes(disk.total),
            used_human=human_bytes(disk.used),
        )


class NetworkOut(_Out):
    bytes_sent: int
    bytes_recv: int
    packets_sent: int = 0
    packets_recv: int = 0
    interfaces: dict[str, dict[str, int]] = Field(default_factory=dict)

    @classmethod
    def from_domain(cls, network: NetworkMetrics | None) -> NetworkOut | None:
        if network is None:
            return None
        return cls(
            bytes_sent=network.bytes_sent,
            bytes_recv=network.bytes_recv,
            packets_sent=network.packets_sent,
            packets_recv=network.packets_recv,
            interfaces=network.interfaces,
        )


class SystemOut(_Out):
    host: HostOut
    cpu: CpuOut
    memory: MemoryOut
    disks: list[DiskOut] = Field(default_factory=list)
    network: NetworkOut | None = None
    collected_at: datetime | None = None

    @classmethod
    def from_domain(cls, snapshot: SystemSnapshot) -> SystemOut:
        return cls(
            host=HostOut.from_domain(snapshot.host),
            cpu=CpuOut.from_domain(snapshot.cpu),
            memory=MemoryOut.from_domain(snapshot.memory),
            disks=[DiskOut.from_domain(d) for d in snapshot.disks],
            network=NetworkOut.from_domain(snapshot.network),
            collected_at=snapshot.collected_at,
        )


class SampleOut(_Out):
    timestamp: datetime
    cpu_percent: float
    memory_percent: float

    @classmethod
    def from_domain(cls, sample: MetricSample) -> SampleOut:
        return cls(
            timestamp=sample.timestamp,
            cpu_percent=sample.cpu_percent,
            memory_percent=sample.memory_percent,
        )


class EngineStatusOut(_Out):
    provider: str
    available: bool
    total: int = 0
    running: int = 0
    stopped: int = 0


# --------------------------------------------------------------------------- #
# Catalog
# --------------------------------------------------------------------------- #
class SoftwareEntryIn(BaseModel):
    id: str = Field(default="", max_length=64)
    name: str = Field(min_length=1, max_length=80)
    url: str = ""
    description: str = ""
    icon: str = ""
    color: str = ""
    category: str = ""
    tags: list[str] = Field(default_factory=list)
    enabled: bool = True
    order: int = 0

    def to_domain(self) -> SoftwareEntry:
        from ..services.catalog_service import slugify

        return SoftwareEntry(
            id=self.id.strip() or slugify(self.name),
            name=self.name.strip(),
            url=self.url.strip(),
            description=self.description.strip(),
            icon=self.icon.strip(),
            color=self.color.strip(),
            category=self.category.strip(),
            tags=[t.strip() for t in self.tags],
            enabled=self.enabled,
            order=self.order,
        )


class SoftwareEntryOut(_Out):
    id: str
    name: str
    url: str
    description: str = ""
    icon: str = ""
    color: str = ""
    category: str = ""
    tags: list[str] = Field(default_factory=list)
    enabled: bool = True
    order: int = 0

    @classmethod
    def from_domain(cls, entry: SoftwareEntry) -> SoftwareEntryOut:
        return cls(
            id=entry.id,
            name=entry.name,
            url=entry.url,
            description=entry.description,
            icon=entry.icon,
            color=entry.color,
            category=entry.category,
            tags=entry.normalized_tags(),
            enabled=entry.enabled,
            order=entry.order,
        )


class TagOut(_Out):
    name: str
    count: int


class CatalogPageOut(_Out):
    entries: list[SoftwareEntryOut]
    tags: list[TagOut]
    total: int


class TagsUpdateIn(BaseModel):
    tags: list[str] = Field(default_factory=list)


class ReorderIn(BaseModel):
    ids: list[str] = Field(default_factory=list)


def catalog_query_from_params(
    tags: str = "",
    match_all: bool = False,
    category: str = "",
    search: str = "",
    enabled_only: bool = False,
    sort: Literal["order", "name", "recent"] = "order",
) -> CatalogQuery:
    return CatalogQuery(
        tags=tuple(t.strip() for t in tags.split(",") if t.strip()),
        match_all_tags=match_all,
        category=category,
        search=search,
        enabled_only=enabled_only,
        sort=sort,
    )


# --------------------------------------------------------------------------- #
# Docker
# --------------------------------------------------------------------------- #
class ContainerOut(_Out):
    id: str
    short_id: str
    name: str
    image: str
    state: str
    status: str = ""
    created_at: datetime | None = None
    ports: list[str] = Field(default_factory=list)
    labels: dict[str, str] = Field(default_factory=dict)
    compose_project: str = ""
    compose_service: str = ""

    @classmethod
    def from_domain(cls, container: ContainerInfo) -> ContainerOut:
        return cls(
            id=container.id,
            short_id=container.short_id,
            name=container.name,
            image=container.image,
            state=container.state.value,
            status=container.status,
            created_at=container.created_at,
            ports=[p.display() for p in container.ports if p.display()],
            labels=container.labels,
            compose_project=container.compose_project,
            compose_service=container.compose_service,
        )


class ContainerActionIn(BaseModel):
    timeout: int | None = Field(default=None, ge=0, le=600)


class LogsOut(_Out):
    container: str
    tail: int
    content: str


class ContainerActionOut(_Out):
    """Result of a lifecycle action plus the refreshed container."""

    container: ContainerOut
    result: CommandResultOut


class StackOut(_Out):
    name: str
    config_files: str = ""
    working_dir: str = ""
    status: str = "unknown"
    discovered_paths: list[str] = Field(default_factory=list)
    containers: list[ContainerOut] = Field(default_factory=list)
    running: int = 0
    total: int = 0

    @classmethod
    def from_domain(cls, stack: StackInfo) -> StackOut:
        return cls(
            name=stack.name,
            config_files=stack.config_files,
            working_dir=stack.working_dir,
            status=stack.status.value,
            discovered_paths=list(stack.discovered_paths),
            containers=[ContainerOut.from_domain(c) for c in stack.containers],
            running=sum(1 for c in stack.containers if c.state.is_active),
            total=len(stack.containers),
        )


class StackActionIn(BaseModel):
    extra_args: list[str] = Field(default_factory=list)


class StackActionOut(_Out):
    stack: StackOut
    result: CommandResultOut


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
class CommandOut(_Out):
    id: str
    name: str
    target: str
    kind: str
    action: str = ""
    argv: list[str] = Field(default_factory=list)
    description: str = ""
    confirm: bool = False
    danger: bool = False
    timeout: float = 120.0
    working_dir: str | None = None
    builtin: bool = False

    @classmethod
    def from_domain(cls, definition: CommandDefinition) -> CommandOut:
        return cls(
            id=definition.id,
            name=definition.name,
            target=definition.target.value,
            kind=definition.kind.value,
            action=definition.action,
            argv=list(definition.argv),
            description=definition.description,
            confirm=definition.confirm,
            danger=definition.danger,
            timeout=definition.timeout,
            working_dir=definition.working_dir,
            builtin=definition.builtin,
        )


class CommandRunIn(BaseModel):
    target_id: str | None = None
    extra_args: list[str] = Field(default_factory=list)
    timeout: float | None = None


class AdHocCommandIn(BaseModel):
    argv: list[str] = Field(min_length=1)
    cwd: str | None = None
    timeout: float | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class CommandResultOut(_Out):
    ok: bool
    exit_code: int
    argv: list[str]
    stdout: str = ""
    stderr: str = ""
    duration_ms: int = 0

    @classmethod
    def from_domain(cls, result: CommandResult) -> CommandResultOut:
        return cls(
            ok=result.ok,
            exit_code=result.exit_code,
            argv=list(result.argv),
            stdout=result.stdout,
            stderr=result.stderr,
            duration_ms=result.duration_ms,
        )


class CommandPreviewOut(_Out):
    id: str
    argv: list[str]


# --------------------------------------------------------------------------- #
# Misc
# --------------------------------------------------------------------------- #
class HealthOut(_Out):
    status: str
    version: str
    env: str


class AuthStatusOut(_Out):
    enabled: bool
    authenticated: bool


class LoginIn(BaseModel):
    token: str = Field(min_length=1)


class ErrorOut(_Out):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


# --------------------------------------------------------------------------- #
# formatting helpers
# --------------------------------------------------------------------------- #
def human_bytes(size: float) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if value < 1024 or unit == "PB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} PB"


def human_duration(seconds: float) -> str:
    total = int(max(0, seconds))
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    if days:
        return f"{days}d {hours}h {minutes}m"
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


__all__ = [
    "AdHocCommandIn",
    "AuthStatusOut",
    "CatalogPageOut",
    "catalog_query_from_params",
    "CommandOut",
    "CommandPreviewOut",
    "CommandResultOut",
    "CommandRunIn",
    "ContainerActionIn",
    "ContainerActionOut",
    "ContainerOut",
    "EngineStatusOut",
    "ErrorOut",
    "HealthOut",
    "HostOut",
    "LogsOut",
    "LoginIn",
    "ReorderIn",
    "SampleOut",
    "SoftwareEntryIn",
    "SoftwareEntryOut",
    "StackActionIn",
    "StackActionOut",
    "StackOut",
    "SystemOut",
    "TagOut",
    "TagsUpdateIn",
    "human_bytes",
    "human_duration",
]

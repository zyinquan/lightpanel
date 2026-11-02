"""Host metrics backed by :mod:`psutil`."""

from __future__ import annotations

import asyncio
import os
import platform
import socket
from datetime import UTC, datetime

import psutil

from ...config import MetricsConfig
from ...domain.clock import SystemClock
from ...domain.models import (
    CpuMetrics,
    DiskMetrics,
    HostInfo,
    MemoryMetrics,
    NetworkMetrics,
    SystemSnapshot,
)
from ...domain.ports import Clock, MetricsProvider
from .environment import runtime_scope

CONTAINER_HINT = (
    "面板运行在容器内：CPU / 内存 / 负载取所在内核（Linux 宿主机上即整机，"
    "Docker Desktop 上是其 Linux 虚拟机），网络与磁盘只覆盖本容器。"
    "需要完整宿主机口径请在宿主机启动 lightpanel-agent，并指向 metrics.remote_url。"
)


class PsutilMetricsProvider:
    """Metrics provider implemented on top of psutil (Linux / macOS / Windows)."""

    def __init__(self, settings: MetricsConfig | None = None, clock: Clock | None = None) -> None:
        self.settings = settings or MetricsConfig()
        self._clock = clock or SystemClock()
        self._primed = False
        # 进程所在环境固定，探测一次即可。
        self._scope = runtime_scope()

    @property
    def name(self) -> str:
        return "psutil"

    async def snapshot(self) -> SystemSnapshot:
        return await asyncio.to_thread(self._collect)

    # -- internals --------------------------------------------------------- #
    def _collect(self) -> SystemSnapshot:
        # The very first cpu_percent() call is meaningless (it has no previous
        # sample), so prime it once and discard the result.
        if not self._primed:
            psutil.cpu_percent(interval=None)
            self._primed = True

        host = self._host_info()
        cpu = self._cpu_metrics()
        memory = self._memory_metrics()
        disks = self._disk_metrics()
        network = self._network_metrics()
        return SystemSnapshot(
            host=host,
            cpu=cpu,
            memory=memory,
            disks=disks,
            network=network,
            collected_at=datetime.now(UTC),
            scope=self._scope,
            source="psutil",
            hint=CONTAINER_HINT if self._scope == "container" else None,
        )

    def _host_info(self) -> HostInfo:
        boot_time = psutil.boot_time()
        return HostInfo(
            hostname=socket.gethostname(),
            os_name=platform.system(),
            os_version=platform.release(),
            arch=platform.machine(),
            boot_time=boot_time,
            uptime_seconds=max(0.0, self._clock.now() - boot_time),
        )

    def _cpu_metrics(self) -> CpuMetrics:
        percent = psutil.cpu_percent(interval=None)
        per_cpu = psutil.cpu_percent(interval=None, percpu=True)
        logical = psutil.cpu_count(logical=True) or 1
        physical = psutil.cpu_count(logical=False)
        load_average = None
        if hasattr(psutil, "getloadavg"):
            try:
                load_average = tuple(psutil.getloadavg())
            except OSError:  # pragma: no cover - platform dependent
                load_average = None
        frequency = None
        try:
            freq = psutil.cpu_freq()
            if freq is not None:
                frequency = round(freq.current, 2)
        except Exception:  # pragma: no cover - platform dependent
            frequency = None
        return CpuMetrics(
            percent=percent,
            logical_count=logical,
            physical_count=physical,
            per_cpu=list(per_cpu),
            load_average=load_average,
            frequency_mhz=frequency,
        )

    def _memory_metrics(self) -> MemoryMetrics:
        vm = psutil.virtual_memory()
        swap = psutil.swap_memory()
        return MemoryMetrics(
            total=vm.total,
            used=vm.used,
            available=getattr(vm, "available", vm.free),
            percent=vm.percent,
            swap_total=swap.total,
            swap_used=swap.used,
            swap_percent=swap.percent,
        )

    def _disk_metrics(self) -> list[DiskMetrics]:
        settings = self.settings
        wanted = set(settings.disk_mounts)
        excluded = {fs.lower() for fs in settings.disk_exclude_fs}
        results: list[DiskMetrics] = []
        seen: set[str] = set()
        for partition in psutil.disk_partitions(all=False):
            if partition.fstype.lower() in excluded:
                continue
            if wanted and partition.mountpoint not in wanted:
                continue
            if partition.mountpoint in seen:
                continue
            # 容器里 /etc/hostname、/etc/hosts、/etc/resolv.conf 是单文件挂载，
            # psutil 会把它们列成"分区"，但当成磁盘展示毫无意义
            if not os.path.isdir(partition.mountpoint):
                continue
            try:
                usage = psutil.disk_usage(partition.mountpoint)
            except (PermissionError, OSError):  # pragma: no cover - platform dependent
                continue
            seen.add(partition.mountpoint)
            results.append(
                DiskMetrics(
                    device=partition.device,
                    mountpoint=partition.mountpoint,
                    fstype=partition.fstype,
                    total=usage.total,
                    used=usage.used,
                    free=usage.free,
                    percent=usage.percent,
                )
            )
        results.sort(key=lambda d: d.mountpoint)
        return results

    def _network_metrics(self) -> NetworkMetrics | None:
        try:
            per_nic = psutil.net_io_counters(pernic=True)
            total = psutil.net_io_counters()
        except Exception:  # pragma: no cover - platform dependent
            return None
        wanted = set(self.settings.network_interfaces)
        interfaces: dict[str, dict[str, int]] = {}
        for nic, counters in per_nic.items():
            if wanted and nic not in wanted:
                continue
            interfaces[nic] = {
                "bytes_sent": counters.bytes_sent,
                "bytes_recv": counters.bytes_recv,
                "packets_sent": getattr(counters, "packets_sent", 0),
                "packets_recv": getattr(counters, "packets_recv", 0),
            }
        return NetworkMetrics(
            bytes_sent=total.bytes_sent,
            bytes_recv=total.bytes_recv,
            packets_sent=getattr(total, "packets_sent", 0),
            packets_recv=getattr(total, "packets_recv", 0),
            interfaces=interfaces,
        )


# Explicit check: keep the Protocol honest at import time.
def _assert_protocol() -> None:  # pragma: no cover
    provider: MetricsProvider = PsutilMetricsProvider()
    assert provider.name == "psutil"

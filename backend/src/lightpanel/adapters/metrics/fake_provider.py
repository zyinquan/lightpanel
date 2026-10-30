"""Deterministic metrics provider used by tests and by ``metrics.provider: fake``."""

from __future__ import annotations

import math
from datetime import UTC, datetime

from ...config import MetricsConfig
from ...domain.models import (
    CpuMetrics,
    DiskMetrics,
    HostInfo,
    MemoryMetrics,
    NetworkMetrics,
    SystemSnapshot,
)


class FakeMetricsProvider:
    """Synthesizes plausible metrics without touching the host.

    Values evolve smoothly over time so charts look alive in demo mode.
    """

    def __init__(
        self,
        settings: MetricsConfig | None = None,
        *,
        cpu_percent: float = 23.5,
        memory_percent: float = 46.0,
        hostname: str = "lightpanel-demo",
        tick: float = 0.0,
    ) -> None:
        self.settings = settings or MetricsConfig()
        self._cpu = cpu_percent
        self._memory = memory_percent
        self._hostname = hostname
        self._tick = tick
        self.calls = 0

    @property
    def name(self) -> str:
        return "fake"

    async def snapshot(self) -> SystemSnapshot:
        self.calls += 1
        self._tick += 1.0
        wave = math.sin(self._tick / 6.0)
        cpu = max(1.0, min(99.0, self._cpu + wave * 6.0))
        memory = max(1.0, min(99.0, self._memory + math.cos(self._tick / 9.0) * 3.0))
        total_mem = 16 * 1024**3
        used_mem = int(total_mem * memory / 100)
        return SystemSnapshot(
            host=HostInfo(
                hostname=self._hostname,
                os_name="FakeOS",
                os_version="1.0",
                arch="x86_64",
                boot_time=1_700_000_000.0,
                uptime_seconds=86_400.0 + self._tick,
            ),
            cpu=CpuMetrics(
                percent=round(cpu, 2),
                logical_count=8,
                physical_count=4,
                per_cpu=[round(cpu + i, 2) for i in range(8)],
                load_average=(round(cpu / 25, 2), round(cpu / 30, 2), round(cpu / 40, 2)),
                frequency_mhz=3200.0,
            ),
            memory=MemoryMetrics(
                total=total_mem,
                used=used_mem,
                available=total_mem - used_mem,
                percent=round(memory, 2),
                swap_total=2 * 1024**3,
                swap_used=0,
                swap_percent=0.0,
            ),
            disks=[
                DiskMetrics(
                    device="/dev/sda1",
                    mountpoint="/",
                    fstype="ext4",
                    total=512 * 1024**3,
                    used=180 * 1024**3,
                    free=332 * 1024**3,
                    percent=35.2,
                ),
                DiskMetrics(
                    device="/dev/sdb1",
                    mountpoint="/data",
                    fstype="ext4",
                    total=2 * 1024**4,
                    used=900 * 1024**3,
                    free=1148 * 1024**3,
                    percent=43.9,
                ),
            ],
            network=NetworkMetrics(
                bytes_sent=int(1.2 * 1024**3 + self._tick * 1024),
                bytes_recv=int(4.8 * 1024**3 + self._tick * 4096),
                packets_sent=1_200_000,
                packets_recv=3_400_000,
                interfaces={
                    "eth0": {
                        "bytes_sent": int(1.2 * 1024**3),
                        "bytes_recv": int(4.8 * 1024**3),
                        "packets_sent": 1_200_000,
                        "packets_recv": 3_400_000,
                    }
                },
            ),
            collected_at=datetime.now(UTC),
        )

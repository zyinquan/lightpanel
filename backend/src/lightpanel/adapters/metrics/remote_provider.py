"""Metrics provider backed by a remote agent running **on the host**.

容器里的 psutil 只能看到容器（Windows / macOS 上是 Docker Desktop 的 Linux
虚拟机）。想要真实的宿主机数字，就让宿主机自己跑一个 ``lightpanel-agent``，
面板按 HTTP 去取 —— 端口不变，只是多了一个可替换的适配器。
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import datetime
from typing import Any

import httpx

from ...domain.errors import RemoteMetricsError
from ...domain.models import (
    CpuMetrics,
    DiskMetrics,
    HostInfo,
    MemoryMetrics,
    NetworkMetrics,
    SystemSnapshot,
)
from ...domain.ports import MetricsProvider

logger = logging.getLogger(__name__)


class RemoteMetricsProvider:
    """Fetches a snapshot from ``lightpanel-agent`` (JSON, same shape as ``/api/system``)."""

    def __init__(
        self,
        url: str,
        *,
        timeout: float = 2.0,
        token: str = "",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.url = url
        self._timeout = timeout
        self._token = token
        self._transport = transport

    @property
    def name(self) -> str:
        return "agent"

    async def snapshot(self) -> SystemSnapshot:
        headers = {"Authorization": f"Bearer {self._token}"} if self._token else {}
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, transport=self._transport
            ) as client:
                response = await client.get(self.url, headers=headers)
                response.raise_for_status()
                payload: Any = response.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 401:
                raise RemoteMetricsError(
                    "宿主机代理要求鉴权，请检查 metrics.remote_token", url=self.url
                ) from exc
            raise RemoteMetricsError(
                f"宿主机代理返回 {exc.response.status_code}", url=self.url
            ) from exc
        except httpx.HTTPError as exc:
            raise RemoteMetricsError(f"连不上宿主机代理：{exc}", url=self.url) from exc
        except ValueError as exc:
            raise RemoteMetricsError("宿主机代理返回的不是合法 JSON", url=self.url) from exc

        if not isinstance(payload, Mapping):
            raise RemoteMetricsError("宿主机代理返回了非预期的数据格式", url=self.url)
        return snapshot_from_payload(payload)


def snapshot_from_payload(payload: Mapping[str, Any]) -> SystemSnapshot:
    """把代理返回的 JSON 还原成领域对象（对缺字段宽容，缺了就落到默认值）。"""
    host = _section(payload, "host")
    cpu = _section(payload, "cpu")
    memory = _section(payload, "memory")
    network = payload.get("network")

    disks = [
        DiskMetrics(
            device=str(item.get("device") or ""),
            mountpoint=str(item.get("mountpoint") or ""),
            fstype=str(item.get("fstype") or ""),
            total=int(item.get("total") or 0),
            used=int(item.get("used") or 0),
            free=int(item.get("free") or 0),
            percent=float(item.get("percent") or 0.0),
        )
        for item in payload.get("disks") or []
        if isinstance(item, Mapping)
    ]

    return SystemSnapshot(
        host=HostInfo(
            hostname=str(host.get("hostname") or ""),
            os_name=str(host.get("os_name") or ""),
            os_version=str(host.get("os_version") or ""),
            arch=str(host.get("arch") or ""),
            boot_time=float(host.get("boot_time") or 0.0),
            uptime_seconds=float(host.get("uptime_seconds") or 0.0),
        ),
        cpu=CpuMetrics(
            percent=float(cpu.get("percent") or 0.0),
            logical_count=int(cpu.get("logical_count") or 1),
            physical_count=cpu.get("physical_count"),
            per_cpu=[float(v) for v in cpu.get("per_cpu") or []],
            load_average=_load_average(cpu.get("load_average")),
            frequency_mhz=cpu.get("frequency_mhz"),
        ),
        memory=MemoryMetrics(
            total=int(memory.get("total") or 0),
            used=int(memory.get("used") or 0),
            available=int(memory.get("available") or 0),
            percent=float(memory.get("percent") or 0.0),
            swap_total=int(memory.get("swap_total") or 0),
            swap_used=int(memory.get("swap_used") or 0),
            swap_percent=float(memory.get("swap_percent") or 0.0),
        ),
        disks=disks,
        network=NetworkMetrics(
            bytes_sent=int(network.get("bytes_sent") or 0),
            bytes_recv=int(network.get("bytes_recv") or 0),
            packets_sent=int(network.get("packets_sent") or 0),
            packets_recv=int(network.get("packets_recv") or 0),
            interfaces={
                str(name): {str(k): int(v) for k, v in counters.items()}
                for name, counters in (network.get("interfaces") or {}).items()
                if isinstance(counters, Mapping)
            },
        )
        if isinstance(network, Mapping)
        else None,
        collected_at=_parse_time(payload.get("collected_at")),
        # 代理默认就跑在宿主机上；它自己若在容器里，会如实回报 container。
        scope=str(payload.get("scope") or "host"),
        source="agent",
        hint=payload.get("hint"),
    )


def _section(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, Mapping) else {}


def _load_average(value: Any) -> tuple[float, float, float] | None:
    """领域模型固定三元组；代理给的数组不足三位就当没有。"""
    if not isinstance(value, (list, tuple)) or len(value) < 3:
        return None
    return (float(value[0]), float(value[1]), float(value[2]))


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


# Explicit check: keep the Protocol honest at import time.
def _assert_protocol() -> None:  # pragma: no cover
    provider: MetricsProvider = RemoteMetricsProvider("http://127.0.0.1:9101/metrics")
    assert provider.name == "agent"

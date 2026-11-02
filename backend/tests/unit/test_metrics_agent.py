"""宿主机指标代理：远端适配器、回落组合、agent 应用。"""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from lightpanel.adapters.metrics.environment import is_running_in_container, runtime_scope
from lightpanel.adapters.metrics.fake_provider import FakeMetricsProvider
from lightpanel.adapters.metrics.fallback_provider import FallbackMetricsProvider
from lightpanel.adapters.metrics.psutil_provider import CONTAINER_HINT, PsutilMetricsProvider
from lightpanel.adapters.metrics.remote_provider import RemoteMetricsProvider, snapshot_from_payload
from lightpanel.agent import create_agent_app
from lightpanel.domain.errors import RemoteMetricsError

PAYLOAD = {
    "host": {
        "hostname": "DESKTOP-ABC",
        "os_name": "Windows",
        "os_version": "11",
        "arch": "AMD64",
        "boot_time": 1_700_000_000.0,
        "uptime_seconds": 3600.0,
        "uptime_human": "1小时 0分",
    },
    "cpu": {
        "percent": 12.5,
        "logical_count": 16,
        "physical_count": 8,
        "per_cpu": [10.0, 15.0],
        "load_average": [1.5, 1.2, 0.9],
        "frequency_mhz": 3600.0,
    },
    "memory": {
        "total": 34_359_738_368,
        "used": 17_179_869_184,
        "available": 17_179_869_184,
        "percent": 50.0,
        "swap_total": 0,
        "swap_used": 0,
        "swap_percent": 0.0,
    },
    "disks": [
        {
            "device": "C:\\",
            "mountpoint": "C:\\",
            "fstype": "NTFS",
            "total": 1_000_000_000_000,
            "used": 400_000_000_000,
            "free": 600_000_000_000,
            "percent": 40.0,
        }
    ],
    "network": {
        "bytes_sent": 1,
        "bytes_recv": 2,
        "packets_sent": 3,
        "packets_recv": 4,
        "interfaces": {"eth0": {"bytes_sent": 1, "bytes_recv": 2}},
    },
    "collected_at": "2026-11-01T12:00:00+00:00",
    "scope": "host",
    "source": "psutil",
    "hint": None,
}


def _provider(handler, **kwargs) -> RemoteMetricsProvider:
    return RemoteMetricsProvider(
        "http://host.docker.internal:9101/metrics",
        transport=httpx.MockTransport(handler),
        **kwargs,
    )


async def test_remote_provider_maps_host_payload():
    provider = _provider(lambda request: httpx.Response(200, json=PAYLOAD))
    snapshot = await provider.snapshot()

    assert provider.name == "agent"
    assert snapshot.host.hostname == "DESKTOP-ABC"
    assert snapshot.cpu.logical_count == 16
    assert snapshot.cpu.load_average == (1.5, 1.2, 0.9)
    assert snapshot.memory.total == 34_359_738_368
    assert snapshot.disks[0].mountpoint == "C:\\"
    assert snapshot.network is not None and snapshot.network.packets_recv == 4
    assert snapshot.scope == "host"
    assert snapshot.source == "agent"


async def test_remote_provider_sends_token():
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization", "")
        return httpx.Response(200, json=PAYLOAD)

    await _provider(handler, token="s3cret").snapshot()
    assert seen["auth"] == "Bearer s3cret"


async def test_remote_provider_reports_connection_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(RemoteMetricsError) as excinfo:
        await _provider(handler).snapshot()
    assert "连不上" in excinfo.value.message


async def test_remote_provider_reports_token_rejection():
    provider = _provider(lambda request: httpx.Response(401))
    with pytest.raises(RemoteMetricsError) as excinfo:
        await provider.snapshot()
    assert "remote_token" in excinfo.value.message


async def test_remote_provider_rejects_garbage():
    with pytest.raises(RemoteMetricsError):
        await _provider(lambda request: httpx.Response(200, json=["not", "a", "map"])).snapshot()
    with pytest.raises(RemoteMetricsError):
        await _provider(lambda request: httpx.Response(200, text="<html>")).snapshot()


def test_snapshot_from_payload_tolerates_missing_fields():
    snapshot = snapshot_from_payload({"cpu": {"percent": 3.0}})
    assert snapshot.cpu.logical_count == 1
    assert snapshot.memory.total == 0
    assert snapshot.disks == []
    assert snapshot.network is None
    assert snapshot.scope == "host"


async def test_fallback_uses_primary_when_healthy():
    remote = _provider(lambda request: httpx.Response(200, json=PAYLOAD))
    provider = FallbackMetricsProvider(remote, FakeMetricsProvider())
    snapshot = await provider.snapshot()
    assert snapshot.host.hostname == "DESKTOP-ABC"
    assert provider.target.endswith("/metrics")


async def test_fallback_degrades_and_explains_why():
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    provider = FallbackMetricsProvider(_provider(boom), FakeMetricsProvider())
    snapshot = await provider.snapshot()
    assert snapshot.host.hostname == "lightpanel-demo"
    assert snapshot.hint and "宿主机代理不可用" in snapshot.hint


def test_environment_detection_is_boolean():
    assert isinstance(is_running_in_container(), bool)
    assert runtime_scope() in {"host", "container"}


def test_psutil_provider_labels_container_scope(monkeypatch):
    monkeypatch.setattr(
        "lightpanel.adapters.metrics.psutil_provider.runtime_scope", lambda: "container"
    )
    snapshot = PsutilMetricsProvider()._collect()
    assert snapshot.scope == "container"
    assert snapshot.hint == CONTAINER_HINT


async def test_system_out_exposes_scope_fields():
    from dataclasses import replace

    from lightpanel.api.schemas import SystemOut

    base = await FakeMetricsProvider().snapshot()
    payload = SystemOut.from_domain(replace(base, scope="container", hint="容器内"))
    assert payload.scope == "container"
    assert payload.hint == "容器内"


# --------------------------------------------------------------------------- #
# agent
# --------------------------------------------------------------------------- #
def test_agent_serves_metrics():
    client = TestClient(create_agent_app(provider=FakeMetricsProvider()))
    assert client.get("/health").json()["status"] == "ok"

    response = client.get("/metrics")
    assert response.status_code == 200
    body = response.json()
    assert body["host"]["hostname"] == "lightpanel-demo"
    assert body["scope"] in {"host", "container"}


def test_agent_enforces_token():
    client = TestClient(create_agent_app(provider=FakeMetricsProvider(), token="s3cret"))
    assert client.get("/metrics").status_code == 401
    ok = client.get("/metrics", headers={"Authorization": "Bearer s3cret"})
    assert ok.status_code == 200


async def test_agent_roundtrip_through_remote_provider():
    """agent 的输出必须能被面板的远端适配器原样吃下（协议自洽）。"""
    client = TestClient(create_agent_app(provider=FakeMetricsProvider()))
    payload = client.get("/metrics").json()

    provider = _provider(lambda request: httpx.Response(200, json=payload))
    snapshot = await provider.snapshot()
    assert snapshot.host.hostname == "lightpanel-demo"
    assert snapshot.memory.total > 0

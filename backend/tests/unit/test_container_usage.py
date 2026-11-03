"""Container usage sampling: stats parsing, aggregation and API surface."""

from __future__ import annotations

import httpx
import pytest

from lightpanel.adapters.docker.engine import DockerApiContainerEngine, _parse_usage
from lightpanel.config import DockerConfig


def _stats_payload(*, cpu_total: int, pre_total: int, system: int, pre_system: int) -> dict:
    return {
        "cpu_stats": {
            "cpu_usage": {"total_usage": cpu_total, "percpu_usage": [1, 2, 3, 4]},
            "system_cpu_usage": system,
            "online_cpus": 4,
        },
        "precpu_stats": {
            "cpu_usage": {"total_usage": pre_total},
            "system_cpu_usage": pre_system,
        },
        "memory_stats": {
            "usage": 300 * 1024 * 1024,
            "limit": 1024 * 1024 * 1024,
            "stats": {"inactive_file": 80 * 1024 * 1024},
        },
    }


def test_parse_usage_normalises_cpu_to_whole_machine():
    # 一个采样周期内用了 0.5 个核（4 核机器上 system delta 的 1/8）
    payload = _stats_payload(
        cpu_total=6_000_000, pre_total=5_000_000, system=80_000_000, pre_system=72_000_000
    )
    usage = _parse_usage("abc", payload)
    assert usage.cpu_percent == pytest.approx(50.0)


def test_parse_usage_subtracts_page_cache():
    usage = _parse_usage("abc", _stats_payload(
        cpu_total=0, pre_total=0, system=0, pre_system=0
    ))
    # 300MB 里 80MB 是可回收的 page cache
    assert usage.memory_bytes == 220 * 1024 * 1024
    assert usage.memory_limit_bytes == 1024 * 1024 * 1024
    assert usage.memory_percent == pytest.approx(21.48, abs=0.01)


def test_parse_usage_falls_back_on_cgroup_v1_cache_key():
    payload = _stats_payload(
        cpu_total=0, pre_total=0, system=0, pre_system=0
    )
    payload["memory_stats"]["stats"] = {"cache": 100 * 1024 * 1024}
    usage = _parse_usage("abc", payload)
    assert usage.memory_bytes == 200 * 1024 * 1024


def test_parse_usage_without_previous_sample_reports_zero_cpu():
    """首次采样 precpu 为 0 时不能算出天文数字。"""
    payload = _stats_payload(cpu_total=6_000_000, pre_total=0, system=0, pre_system=0)
    assert _parse_usage("abc", payload).cpu_percent == 0.0


async def test_engine_requests_stream_false():
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1.44/containers/abc/stats"
        seen.update(dict(request.url.params))
        return httpx.Response(200, json=_stats_payload(
            cpu_total=6_000_000, pre_total=5_000_000, system=80_000_000, pre_system=72_000_000
        ))

    engine = DockerApiContainerEngine(
        DockerConfig(api_version="v1.44"), transport=httpx.MockTransport(handler)
    )
    usage = await engine.usage("abc")
    assert seen.get("stream") == "false"
    assert usage.cpu_percent == pytest.approx(50.0)


def test_usage_endpoint_lists_running_containers_only(client):
    body = client.get("/api/containers/usage").json()
    ids = {item["container_id"] for item in body["items"]}
    assert ids  # fake 引擎有 3 个运行中的容器
    assert body["sampled_at"]
    item = body["items"][0]
    assert item["memory_percent"] >= 0
    assert item["cpu_percent"] >= 0

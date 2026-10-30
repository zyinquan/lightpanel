"""System service: caching and history."""

from __future__ import annotations

from lightpanel.adapters.metrics.fake_provider import FakeMetricsProvider
from lightpanel.config import MetricsConfig
from lightpanel.domain.clock import FixedClock
from lightpanel.services.system_service import SystemService


def build(provider, *, cache_ttl=2.0, history_size=5):
    clock = FixedClock()
    service = SystemService(
        provider, MetricsConfig(cache_ttl=cache_ttl, history_size=history_size), clock=clock
    )
    return service, clock


async def test_snapshot_is_cached():
    provider = FakeMetricsProvider()
    service, clock = build(provider)
    first = await service.snapshot()
    second = await service.snapshot()
    assert first is second
    assert provider.calls == 1

    clock.advance(10)
    await service.snapshot()
    assert provider.calls == 2


async def test_force_bypasses_cache():
    provider = FakeMetricsProvider()
    service, _ = build(provider)
    await service.snapshot()
    await service.snapshot(force=True)
    assert provider.calls == 2


async def test_invalidate_clears_cache():
    provider = FakeMetricsProvider()
    service, _ = build(provider)
    await service.snapshot()
    service.invalidate()
    await service.snapshot()
    assert provider.calls == 2


async def test_history_is_bounded_and_populated():
    provider = FakeMetricsProvider()
    service, clock = build(provider, cache_ttl=0, history_size=3)
    for _ in range(6):
        clock.advance(5)
        await service.snapshot()
    history = service.history()
    assert len(history) == 3
    assert all(0 <= sample.cpu_percent <= 100 for sample in history)
    assert [s.timestamp for s in history] == sorted(s.timestamp for s in history)


async def test_history_disabled():
    provider = FakeMetricsProvider()
    service, _ = build(provider, cache_ttl=0, history_size=0)
    await service.snapshot()
    assert service.history() == []


async def test_any_provider_implementation_can_be_used():
    """The service only depends on the MetricsProvider port."""

    class Constant:
        name = "constant"

        async def snapshot(self):
            return await FakeMetricsProvider().snapshot()

    service = SystemService(Constant(), MetricsConfig(cache_ttl=0))
    snapshot = await service.snapshot()
    assert snapshot.host.hostname

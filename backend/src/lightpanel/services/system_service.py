"""System status use-cases: cached snapshots + a short rolling history."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime

from ..config import MetricsConfig
from ..domain.clock import SystemClock
from ..domain.models import SystemSnapshot
from ..domain.ports import Clock, MetricsProvider


@dataclass(frozen=True, slots=True)
class MetricSample:
    timestamp: datetime
    cpu_percent: float
    memory_percent: float


class SystemService:
    """Serves host metrics.

    * snapshots are cached for ``cache_ttl`` seconds so a browser polling every
      second cannot hammer psutil,
    * every *fresh* sample is appended to a bounded ring buffer that the UI
      renders as sparklines.
    """

    def __init__(
        self,
        provider: MetricsProvider,
        settings: MetricsConfig | None = None,
        clock: Clock | None = None,
    ) -> None:
        self.provider = provider
        self.settings = settings or MetricsConfig()
        self._clock = clock or SystemClock()
        self._cache: SystemSnapshot | None = None
        self._cache_at = 0.0
        self._history: deque[MetricSample] = deque(maxlen=self.settings.history_size or 1)

    async def snapshot(self, *, force: bool = False) -> SystemSnapshot:
        now = self._clock.monotonic()
        if (
            not force
            and self._cache is not None
            and (now - self._cache_at) < self.settings.cache_ttl
        ):
            return self._cache

        snapshot = await self.provider.snapshot()
        self._cache = snapshot
        self._cache_at = now
        if self.settings.history_size > 0:
            self._history.append(
                MetricSample(
                    timestamp=datetime.now(UTC),
                    cpu_percent=round(snapshot.cpu.percent, 2),
                    memory_percent=round(snapshot.memory.percent, 2),
                )
            )
        return snapshot

    def history(self) -> list[MetricSample]:
        return list(self._history)

    def invalidate(self) -> None:
        self._cache = None
        self._cache_at = 0.0

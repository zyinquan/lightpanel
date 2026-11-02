"""组合指标源：优先用宿主机代理，取不到就回落到本机 psutil。

回落是**有意的**：面板本身的可用性比指标口径更重要。回落时在快照上留一条
hint，UI 会明确写出"现在看到的是容器指标，不是宿主机"。
"""

from __future__ import annotations

import logging
from dataclasses import replace

from ...domain.models import SystemSnapshot
from ...domain.ports import MetricsProvider

logger = logging.getLogger(__name__)

FALLBACK_NOTE = "宿主机代理不可用（{reason}），当前显示的是面板所在环境的指标。"


class FallbackMetricsProvider:
    """Tries ``primary`` first, degrades to ``fallback`` on any failure."""

    def __init__(self, primary: MetricsProvider, fallback: MetricsProvider) -> None:
        self.primary = primary
        self.fallback = fallback
        self._warned = False

    @property
    def name(self) -> str:
        return self.primary.name

    @property
    def target(self) -> str:
        """The configured primary source, shown in diagnostics."""
        return getattr(self.primary, "url", self.primary.name)

    async def snapshot(self) -> SystemSnapshot:
        try:
            return await self.primary.snapshot()
        except Exception as exc:  # noqa: BLE001 - 任何失败都回落，面板不能因此白屏
            if not self._warned:
                # 只在第一次失败时告警，避免 3 秒一次的轮询把日志刷满。
                logger.warning(
                    "metrics: %s 不可用，回落到 %s（%s）",
                    self.primary.name,
                    self.fallback.name,
                    exc,
                )
                self._warned = True
            snapshot = await self.fallback.snapshot()
            note = FALLBACK_NOTE.format(reason=exc)
            return replace(snapshot, hint=_merge_hint(snapshot.hint, note))


def _merge_hint(current: str | None, extra: str) -> str:
    return f"{current} {extra}" if current else extra

"""Time source implementations."""

from __future__ import annotations

import time


class SystemClock:
    """Wall-clock implementation of :class:`Clock`."""

    name = "system"

    def now(self) -> float:
        return time.time()

    def monotonic(self) -> float:
        return time.monotonic()


class FixedClock:
    """Deterministic clock for tests."""

    name = "fixed"

    def __init__(self, now: float = 0.0) -> None:
        self._now = now
        self._monotonic = now

    def now(self) -> float:
        return self._now

    def monotonic(self) -> float:
        return self._monotonic

    def advance(self, seconds: float) -> None:
        self._now += seconds
        self._monotonic += seconds

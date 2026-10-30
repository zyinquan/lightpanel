"""Real-host adapters: psutil metrics and logging setup."""

from __future__ import annotations

import logging

import pytest

from lightpanel.adapters.metrics.psutil_provider import PsutilMetricsProvider
from lightpanel.config import LoggingConfig, MetricsConfig
from lightpanel.logging_conf import JsonFormatter, setup_logging


@pytest.mark.slow
async def test_psutil_provider_returns_real_metrics():
    provider = PsutilMetricsProvider(MetricsConfig())
    snapshot = await provider.snapshot()

    assert snapshot.host.hostname
    assert snapshot.cpu.logical_count >= 1
    assert 0 <= snapshot.cpu.percent <= 100
    assert snapshot.memory.total > 0
    assert 0 <= snapshot.memory.percent <= 100
    assert snapshot.collected_at is not None


@pytest.mark.slow
async def test_psutil_provider_respects_disk_filters():
    provider = PsutilMetricsProvider(MetricsConfig(disk_mounts=["/__definitely_missing__"]))
    snapshot = await provider.snapshot()
    assert snapshot.disks == []


@pytest.mark.slow
async def test_psutil_provider_excludes_filesystem_types():
    provider = PsutilMetricsProvider(MetricsConfig(disk_exclude_fs=["NTFS", "FAT32"]))
    snapshot = await provider.snapshot()
    assert all(d.fstype.upper() not in {"NTFS", "FAT32"} for d in snapshot.disks)


def test_setup_logging_plain(caplog):
    setup_logging(LoggingConfig(level="WARNING", format="plain"))
    assert logging.getLogger().level == logging.WARNING
    logging.getLogger("test.plain").warning("hello")
    setup_logging(LoggingConfig(level="INFO"))


def test_json_formatter_emits_json():
    formatter = JsonFormatter()
    record = logging.LogRecord("n", logging.INFO, "p", 1, "message", None, None)
    payload = formatter.format(record)
    assert '"level": "INFO"' in payload
    assert '"message": "message"' in payload


def test_json_formatter_includes_extra():
    formatter = JsonFormatter()
    record = logging.LogRecord("n", logging.INFO, "p", 1, "run", None, None)
    record.argv = ["docker", "ps"]  # type: ignore[attr-defined]
    assert '"argv"' in formatter.format(record)


def test_setup_logging_json():
    setup_logging(LoggingConfig(level="DEBUG", format="json"))
    assert logging.getLogger().level == logging.DEBUG
    setup_logging(LoggingConfig(level="INFO"))

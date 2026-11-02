"""Real-host adapters: psutil metrics and logging setup."""

from __future__ import annotations

import logging
from collections import namedtuple

import psutil
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


def test_disk_metrics_ignore_single_file_mounts(monkeypatch, tmp_path):
    """容器里 /etc/hostname 这类单文件挂载不是磁盘，不能出现在面板上。"""
    mount_dir = tmp_path / "data"
    mount_dir.mkdir()
    mount_file = tmp_path / "hostname"
    mount_file.write_text("container", encoding="utf-8")

    class _Partition:
        def __init__(self, mountpoint: str, device: str = "/dev/sda1") -> None:
            self.mountpoint = mountpoint
            self.device = device
            self.fstype = "ext4"

    usage = namedtuple("usage", "total used free percent")
    monkeypatch.setattr(
        psutil,
        "disk_partitions",
        lambda all=False: [_Partition(str(mount_dir)), _Partition(str(mount_file))],
    )
    monkeypatch.setattr(
        psutil,
        "disk_usage",
        lambda path: usage(total=100, used=40, free=60, percent=40.0),
    )

    provider = PsutilMetricsProvider(MetricsConfig())
    disks = provider._disk_metrics()

    assert [d.mountpoint for d in disks] == [str(mount_dir)]

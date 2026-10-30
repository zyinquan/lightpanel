"""Schema / formatting helpers and domain model invariants."""

from __future__ import annotations

from datetime import UTC, datetime

from lightpanel.api.schemas import (
    ContainerOut,
    SoftwareEntryOut,
    SystemOut,
    human_bytes,
    human_duration,
)
from lightpanel.domain.models import (
    ContainerInfo,
    ContainerState,
    CpuMetrics,
    HostInfo,
    MemoryMetrics,
    SoftwareEntry,
)


def test_human_bytes():
    assert human_bytes(0).endswith("B")
    assert human_bytes(1024) == "1.0 KB"
    assert human_bytes(1536) == "1.5 KB"
    assert human_bytes(5 * 1024**3) == "5.0 GB"


def test_human_duration():
    assert human_duration(0) == "0s"
    assert human_duration(65) == "1m 5s"
    assert human_duration(3725) == "1h 2m"
    assert human_duration(90000) == "1d 1h 0m"


def test_system_out_from_domain():
    from lightpanel.domain.models import DiskMetrics, SystemSnapshot

    snapshot = SystemSnapshot(
        host=HostInfo(
            hostname="h", os_name="Linux", os_version="6.1", arch="x86_64", boot_time=0, uptime_seconds=61
        ),
        cpu=CpuMetrics(percent=12.345, logical_count=4, physical_count=2, load_average=(1.0, 2.0, 3.0)),
        memory=MemoryMetrics(total=1024**3, used=512 * 1024**2, available=512 * 1024**2, percent=50),
        disks=[
            DiskMetrics(
                device="/dev/sda", mountpoint="/", fstype="ext4", total=100, used=40, free=60, percent=40
            )
        ],
        collected_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    out = SystemOut.from_domain(snapshot)
    assert out.cpu.percent == 12.35
    assert out.memory.used_human == "512.0 MB"
    assert out.disks[0].percent == 40.0
    assert out.host.uptime_human == "1m 1s"


def test_container_out_ports():
    from lightpanel.domain.models import PortBinding

    container = ContainerInfo(
        id="a" * 64,
        name="web",
        image="nginx",
        state=ContainerState.RUNNING,
        ports=[PortBinding(host_ip="0.0.0.0", host_port="8080", container_port="80", protocol="tcp")],
        labels={"com.docker.compose.project": "demo"},
    )
    out = ContainerOut.from_domain(container)
    assert out.ports == ["8080->80"]
    assert out.compose_project == "demo"
    assert out.short_id == "a" * 12


def test_software_entry_out_normalizes_tags():
    entry = SoftwareEntry(id="x", name="X", url="https://x", tags=["Ops", "ops", " ops "])
    assert SoftwareEntryOut.from_domain(entry).tags == ["ops"]


def test_entry_roundtrip_through_pydantic():
    from lightpanel.api.schemas import SoftwareEntryIn

    payload = {"name": "中文面板", "url": "https://x.local", "tags": ["a", "b"]}
    entry = SoftwareEntryIn(**payload).to_domain()
    assert entry.id.startswith("e-")
    assert entry.tags == ["a", "b"]


def test_container_state_helpers():
    assert ContainerState.parse("running").is_active
    assert ContainerState.parse("exited").is_active is False
    assert ContainerState.parse("weird") is ContainerState.UNKNOWN
    assert ContainerState.parse(None) is ContainerState.UNKNOWN

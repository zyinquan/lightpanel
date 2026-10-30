"""Adapter-level tests: YAML repository, Docker API parsing, subprocess executor."""

from __future__ import annotations

import pytest

from lightpanel.adapters.catalog.yaml_repository import YamlCatalogRepository
from lightpanel.adapters.docker.engine import DockerApiContainerEngine
from lightpanel.adapters.executor.subprocess_executor import SubprocessCommandExecutor
from lightpanel.config import DockerConfig
from lightpanel.domain.errors import StorageError
from lightpanel.domain.models import CommandResult, ContainerState, SoftwareEntry


# --------------------------------------------------------------------------- #
# YAML catalog repository
# --------------------------------------------------------------------------- #
async def test_yaml_repository_roundtrip(tmp_path):
    repo = YamlCatalogRepository(tmp_path / "catalog.yaml")
    await repo.add(SoftwareEntry(id="a", name="A", url="https://a.local", tags=["x"]))
    reloaded = YamlCatalogRepository(tmp_path / "catalog.yaml")
    entries = await reloaded.list_entries()
    assert [e.id for e in entries] == ["a"]
    assert entries[0].tags == ["x"]


async def test_yaml_repository_update_and_remove(tmp_path):
    repo = YamlCatalogRepository(tmp_path / "catalog.yaml")
    await repo.add(SoftwareEntry(id="a", name="A", url=""))
    await repo.update(SoftwareEntry(id="a", name="A2", url="https://a.local"))
    assert (await repo.get("a")).name == "A2"
    assert await repo.remove("a") is True
    assert await repo.remove("a") is False


async def test_yaml_repository_invalid_document(tmp_path):
    path = tmp_path / "catalog.yaml"
    path.write_text("- not a mapping\n", encoding="utf-8")
    repo = YamlCatalogRepository(path)
    with pytest.raises(StorageError):
        await repo.list_entries()


async def test_yaml_repository_seed(tmp_path):
    repo = YamlCatalogRepository(tmp_path / "catalog.yaml")
    example = tmp_path / "example.yaml"
    example.write_text("entries:\n  - id: seed\n    name: Seed\n    url: ''\n", encoding="utf-8")
    assert repo.seed_if_missing(example) is True
    assert repo.seed_if_missing(example) is False
    assert [e.id for e in await repo.list_entries()] == ["seed"]


async def test_yaml_repository_replace_all(tmp_path):
    repo = YamlCatalogRepository(tmp_path / "catalog.yaml")
    await repo.replace_all([SoftwareEntry(id="x", name="X", url="")])
    assert [e.id for e in await repo.list_entries()] == ["x"]


# --------------------------------------------------------------------------- #
# Docker API engine parsing
# --------------------------------------------------------------------------- #
def test_parse_container_row():
    row = {
        "Id": "a" * 64,
        "Names": ["/web"],
        "Image": "nginx:latest",
        "State": "running",
        "Status": "Up 2 hours",
        "Created": 1700000000,
        "Ports": [{"IP": "0.0.0.0", "PrivatePort": 80, "PublicPort": 8080, "Type": "tcp"}],
        "Labels": {"com.docker.compose.project": "demo"},
        "Command": "nginx -g daemon off;",
    }
    container = DockerApiContainerEngine._parse_container(row)
    assert container.name == "web"
    assert container.state is ContainerState.RUNNING
    assert container.ports[0].display() == "8080->80"
    assert container.compose_project == "demo"
    assert container.created_at is not None


def test_parse_unknown_state():
    container = DockerApiContainerEngine._parse_container({"Id": "b" * 64, "State": "weird"})
    assert container.state is ContainerState.UNKNOWN
    assert container.state.is_active is False


def test_parse_timestamp_variants():
    from lightpanel.adapters.docker.engine import _parse_timestamp

    assert _parse_timestamp(1700000000) is not None
    assert _parse_timestamp("2026-01-01T10:00:00.123456789Z") is not None
    assert _parse_timestamp("not-a-date") is None
    assert _parse_timestamp("") is None


def test_engine_url_building():
    engine = DockerApiContainerEngine(DockerConfig(api_version="v1.44"))
    assert engine._api_url() == "http://localhost/v1.44"
    engine = DockerApiContainerEngine(DockerConfig(host="tcp://1.2.3.4:2375"))
    assert engine._api_url() == "tcp://1.2.3.4:2375/v1.44"


# --------------------------------------------------------------------------- #
# Subprocess executor
# --------------------------------------------------------------------------- #
async def test_executor_rejects_disallowed_binary():
    executor = SubprocessCommandExecutor(allowed_binaries=("docker",))
    result = await executor.run(["echo", "hi"])
    assert result.exit_code == 126
    assert "not allowed" in result.stderr


async def test_executor_reports_missing_binary():
    executor = SubprocessCommandExecutor()
    result = await executor.run(["definitely-not-a-binary-xyz", "--help"])
    assert result.exit_code == 127
    assert result.ok is False


async def test_executor_empty_argv():
    executor = SubprocessCommandExecutor()
    result = await executor.run([])
    assert result.exit_code == 2


async def test_executor_runs_real_command():
    import sys

    executor = SubprocessCommandExecutor()
    result = await executor.run([sys.executable, "-c", "print('hello')"])
    assert result.ok is True
    assert "hello" in result.stdout


async def test_executor_captures_failure():
    import sys

    executor = SubprocessCommandExecutor()
    result = await executor.run([sys.executable, "-c", "import sys; sys.stderr.write('bad'); sys.exit(3)"])
    assert result.exit_code == 3
    assert "bad" in result.stderr


async def test_fake_executor_scripting():
    from lightpanel.adapters.executor.fake_executor import FakeCommandExecutor

    executor = FakeCommandExecutor()
    executor.script(CommandResult.success(("a",), stdout="one"))
    executor.for_argv(["docker", "ps"], CommandResult.success(("docker", "ps"), stdout="two"))
    assert (await executor.run(["a"])).stdout == "one"
    assert (await executor.run(["docker", "ps"])).stdout == "two"
    assert (await executor.run(["docker", "ps"])).stdout == "two"
    assert executor.argv_containing("ps") == [("docker", "ps"), ("docker", "ps")]

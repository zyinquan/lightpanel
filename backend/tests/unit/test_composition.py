"""Composition root tests: wiring switches and first-run seeding."""

from __future__ import annotations

import pytest

from lightpanel import composition
from lightpanel.adapters.catalog.memory_repository import InMemoryCatalogRepository
from lightpanel.adapters.catalog.yaml_repository import YamlCatalogRepository
from lightpanel.adapters.docker.fake_engine import FakeContainerEngine
from lightpanel.adapters.docker.null_engine import NullContainerEngine
from lightpanel.config import load_config


def _config(tmp_path, **overrides):
    base = {
        "docker": {"mode": "fake"},
        "catalog": {"provider": "memory"},
        "metrics": {"provider": "fake", "cache_ttl": 0},
        "commands": {"extra_file": str(tmp_path / "commands.yaml")},
    }
    base.update(overrides)
    return load_config(overrides=base)


def test_build_container_wires_fake_adapters(tmp_path):
    container = composition.build_container(_config(tmp_path))
    assert isinstance(container.container_engine, FakeContainerEngine)
    assert isinstance(container.catalog_repository, InMemoryCatalogRepository)
    assert container.system is not None
    assert container.commands.list_definitions()


def test_docker_disabled_uses_null_engine(tmp_path):
    container = composition.build_container(_config(tmp_path, docker={"enabled": False}))
    assert isinstance(container.container_engine, NullContainerEngine)


def test_yaml_catalog_is_seeded_from_example(tmp_path):
    target = tmp_path / "data" / "catalog.yaml"
    container = composition.build_container(
        _config(tmp_path, catalog={"provider": "yaml", "path": str(target)})
    )
    assert isinstance(container.catalog_repository, YamlCatalogRepository)
    assert target.is_file()
    assert "entries" in target.read_text(encoding="utf-8")


def test_seeding_skips_when_catalog_exists(tmp_path):
    target = tmp_path / "catalog.yaml"
    target.write_text("entries: []\n", encoding="utf-8")
    composition.build_container(
        _config(tmp_path, catalog={"provider": "yaml", "path": str(target)})
    )
    assert target.read_text(encoding="utf-8") == "entries: []\n"


def test_catalog_seeded_from_configured_example(tmp_path):
    example = tmp_path / "examples" / "catalog.example.yaml"
    example.parent.mkdir()
    example.write_text(
        "entries:\n  - id: demo\n    name: Demo\n    url: 'http://demo'\n", encoding="utf-8"
    )
    target = tmp_path / "data" / "catalog.yaml"
    composition.build_container(
        _config(
            tmp_path,
            catalog={
                "provider": "yaml",
                "path": str(target),
                "example_file": str(example),
            },
        )
    )
    assert target.is_file()
    assert "demo" in target.read_text(encoding="utf-8")


def test_no_example_file_means_no_seeding(tmp_path):
    target = tmp_path / "commands.yaml"
    composition._seed_commands_file(str(target), None)
    assert not target.exists()


def test_commands_file_seeded_from_configured_example(tmp_path):
    example = tmp_path / "commands.example.yaml"
    example.write_text(
        "commands:\n  - id: demo.echo\n    target: system\n    argv: ['docker', 'ps']\n",
        encoding="utf-8",
    )
    target = tmp_path / "nested" / "commands.yaml"
    composition._seed_commands_file(str(target), str(example))
    assert "demo.echo" in target.read_text(encoding="utf-8")


def test_commands_seeding_never_overwrites(tmp_path):
    example = tmp_path / "commands.example.yaml"
    example.write_text("commands: []\n", encoding="utf-8")
    target = tmp_path / "commands.yaml"
    target.write_text("keep: me\n", encoding="utf-8")
    composition._seed_commands_file(str(target), str(example))
    assert target.read_text(encoding="utf-8") == "keep: me\n"


def test_commands_seeding_tolerates_missing_example(tmp_path):
    target = tmp_path / "commands.yaml"
    composition._seed_commands_file(str(target), str(tmp_path / "nope.yml"))
    assert not target.exists()


def test_commands_seeding_does_not_copy_target_onto_itself(tmp_path):
    target = tmp_path / "commands.yaml"
    composition._seed_commands_file(str(target), str(target))
    assert not target.exists()


def test_commands_seeding_reports_write_failure(tmp_path, caplog):
    example = tmp_path / "commands.example.yaml"
    example.write_text("commands: []\n", encoding="utf-8")
    blocker = tmp_path / "blocked"
    blocker.write_text("i am a file, not a directory", encoding="utf-8")
    with caplog.at_level("WARNING"):
        composition._seed_commands_file(str(blocker / "commands.yaml"), str(example))
    assert "unable to seed command file" in caplog.text


def test_build_container_seeds_commands_when_configured(tmp_path):
    example = tmp_path / "commands.example.yaml"
    example.write_text(
        "commands:\n  - id: demo.echo\n    name: Echo\n    target: system\n"
        "    argv: ['docker', 'ps']\n",
        encoding="utf-8",
    )
    target = tmp_path / "commands.yaml"
    container = composition.build_container(
        _config(
            tmp_path,
            commands={"extra_file": str(target), "example_file": str(example)},
        )
    )
    assert target.is_file()
    assert "demo.echo" in {d.id for d in container.commands.list_definitions()}


@pytest.mark.parametrize("mode", ["api", "auto"])
def test_docker_api_modes(tmp_path, mode):
    container = composition.build_container(
        _config(tmp_path, docker={"mode": mode, "host": "unix:///nonexistent.sock"})
    )
    assert type(container.container_engine).__name__ == "DockerApiContainerEngine"

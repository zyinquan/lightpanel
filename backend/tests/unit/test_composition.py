"""Composition root tests: wiring switches and first-run seeding."""

from __future__ import annotations

import pytest

from lightpanel import composition
from lightpanel.adapters.catalog.memory_repository import InMemoryCatalogRepository
from lightpanel.adapters.catalog.yaml_repository import YamlCatalogRepository
from lightpanel.adapters.docker.agent_compose import AgentComposeBackend
from lightpanel.adapters.docker.compose import LocalComposeBackend
from lightpanel.adapters.docker.fake_engine import FakeContainerEngine
from lightpanel.adapters.docker.null_engine import NullContainerEngine
from lightpanel.adapters.metrics.fallback_provider import FallbackMetricsProvider
from lightpanel.adapters.metrics.psutil_provider import PsutilMetricsProvider
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


def test_missing_endpoint_explains_how_to_fix_it(tmp_path):
    """auto 模式但看不到 socket：降级原因要说清怎么修，不能只说"已禁用"。"""
    container = composition.build_container(
        _config(
            tmp_path,
            docker={"mode": "auto", "socket": str(tmp_path / "no-socket-here.sock"), "host": ""},
        )
    )
    assert isinstance(container.container_engine, NullContainerEngine)
    assert "docker.sock" in container.container_engine.reason
    assert "docker.mode = api" in container.container_engine.reason


def test_disabled_engine_reason_points_at_config(tmp_path):
    container = composition.build_container(_config(tmp_path, docker={"enabled": False}))
    assert "docker.enabled" in container.container_engine.reason


def test_metrics_remote_url_builds_fallback_chain(tmp_path):
    container = composition.build_container(
        _config(
            tmp_path,
            metrics={
                "provider": "psutil",
                "remote_url": "http://host.docker.internal:9101/metrics",
                "remote_token": "s3cret",
                "cache_ttl": 0,
            },
        )
    )
    provider = container.system.provider
    assert isinstance(provider, FallbackMetricsProvider)
    assert provider.primary.name == "agent"
    assert provider.target.endswith("/metrics")
    assert provider.primary._token == "s3cret"
    assert isinstance(provider.fallback, PsutilMetricsProvider)


def test_metrics_without_remote_url_stays_local(tmp_path):
    container = composition.build_container(
        _config(tmp_path, metrics={"provider": "psutil", "cache_ttl": 0})
    )
    assert isinstance(container.system.provider, PsutilMetricsProvider)


def test_compose_runner_agent_uses_host_agent(tmp_path):
    container = composition.build_container(
        _config(
            tmp_path,
            compose={
                "runner": "agent",
                "agent_url": "http://host.docker.internal:9101",
                "agent_token": "s3cret",
            },
        )
    )
    engine = container.stacks.engine
    assert isinstance(engine.backend, AgentComposeBackend)
    assert engine.name == "docker-compose@agent"
    assert engine.backend.base_url == "http://host.docker.internal:9101"


def test_compose_runner_agent_without_url_falls_back_to_local(tmp_path, caplog):
    container = composition.build_container(
        _config(tmp_path, compose={"runner": "agent", "agent_url": ""})
    )
    assert isinstance(container.stacks.engine.backend, LocalComposeBackend)
    assert "compose.agent_url" in caplog.text


def test_compose_runner_defaults_to_local(tmp_path):
    container = composition.build_container(_config(tmp_path))
    assert isinstance(container.stacks.engine.backend, LocalComposeBackend)


def test_agent_runner_warns_about_inert_panel_side_settings(tmp_path, caplog):
    """agent 模式下 search_paths / max_depth 由宿主机决定，配了要明说。"""
    with caplog.at_level("WARNING"):
        composition.build_container(
            _config(
                tmp_path,
                compose={
                    "runner": "agent",
                    "agent_url": "http://host.docker.internal:9101",
                    "search_paths": ["/data", "/opt/stacks"],
                    "max_depth": 6,
                },
            )
        )
    assert "compose.search_paths" in caplog.text
    assert "compose.max_depth" in caplog.text
    assert "--stacks-root" in caplog.text


def test_agent_runner_stays_quiet_with_default_scan_settings(tmp_path, caplog):
    with caplog.at_level("WARNING"):
        composition.build_container(
            _config(
                tmp_path,
                compose={"runner": "agent", "agent_url": "http://host.docker.internal:9101"},
            )
        )
    assert "不生效" not in caplog.text


def test_local_runner_does_not_warn_about_scan_settings(tmp_path, caplog):
    with caplog.at_level("WARNING"):
        composition.build_container(
            _config(
                tmp_path, compose={"runner": "local", "search_paths": ["/data"], "max_depth": 5}
            )
        )
    assert "不生效" not in caplog.text

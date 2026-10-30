"""Command definition loading + composition root behaviour."""

from __future__ import annotations

import textwrap

import pytest

from lightpanel.adapters.commands.yaml_definitions import load_definitions
from lightpanel.adapters.docker.engine import DockerApiContainerEngine
from lightpanel.adapters.docker.fake_engine import FakeContainerEngine
from lightpanel.adapters.docker.null_engine import NullContainerEngine
from lightpanel.composition import build_container
from lightpanel.config import AppConfig
from lightpanel.domain.errors import EngineUnavailableError, StorageError, ValidationError
from lightpanel.domain.models import CommandKind, CommandTarget


def test_load_definitions(tmp_path):
    path = tmp_path / "commands.yaml"
    path.write_text(
        textwrap.dedent(
            """
            commands:
              - id: container.echo
                name: 回显
                target: container
                argv: ["docker", "inspect", "{name}"]
                confirm: true
                timeout: 15
            """
        ),
        encoding="utf-8",
    )
    definitions = load_definitions(str(path))
    assert len(definitions) == 1
    assert definitions[0].id == "container.echo"
    assert definitions[0].kind is CommandKind.SHELL
    assert definitions[0].target is CommandTarget.CONTAINER
    assert definitions[0].confirm is True
    assert definitions[0].timeout == 15.0


def test_missing_file_yields_nothing(tmp_path):
    assert load_definitions(str(tmp_path / "nope.yaml")) == []


def test_invalid_target_is_rejected(tmp_path):
    path = tmp_path / "commands.yaml"
    path.write_text("commands:\n  - id: x\n    target: planet\n    argv: ['docker']\n", encoding="utf-8")
    with pytest.raises(ValidationError):
        load_definitions(str(path))


def test_shell_command_without_argv_is_rejected(tmp_path):
    path = tmp_path / "commands.yaml"
    path.write_text("commands:\n  - id: x\n    target: system\n", encoding="utf-8")
    with pytest.raises(ValidationError):
        load_definitions(str(path))


def test_docker_api_command_requires_action(tmp_path):
    path = tmp_path / "commands.yaml"
    path.write_text(
        "commands:\n  - id: x\n    target: container\n    kind: docker_api\n", encoding="utf-8"
    )
    with pytest.raises(ValidationError):
        load_definitions(str(path))


def test_malformed_yaml(tmp_path):
    path = tmp_path / "commands.yaml"
    path.write_text("commands: 3\n", encoding="utf-8")
    with pytest.raises(StorageError):
        load_definitions(str(path))


def test_composition_selects_fake_engine():
    container = build_container(
        AppConfig.model_validate(
            {
                "docker": {"mode": "fake"},
                "catalog": {"provider": "memory"},
                "commands": {"extra_file": "__missing__.yaml"},
            }
        )
    )
    assert isinstance(container.container_engine, FakeContainerEngine)


def test_composition_disables_docker_when_requested():
    container = build_container(
        AppConfig.model_validate(
            {
                "docker": {"enabled": False},
                "catalog": {"provider": "memory"},
                "commands": {"extra_file": "__missing__.yaml"},
            }
        )
    )
    assert isinstance(container.container_engine, NullContainerEngine)


def test_composition_uses_api_engine_when_mode_is_api():
    container = build_container(
        AppConfig.model_validate(
            {
                "docker": {"mode": "api"},
                "catalog": {"provider": "memory"},
                "commands": {"extra_file": "__missing__.yaml"},
            }
        )
    )
    assert isinstance(container.container_engine, DockerApiContainerEngine)


async def test_null_engine_always_fails():
    engine = NullContainerEngine()
    assert await engine.is_available() is False
    with pytest.raises(EngineUnavailableError):
        await engine.list_containers()
    with pytest.raises(EngineUnavailableError):
        await engine.start("x")


def test_composition_registers_extra_commands(tmp_path):
    path = tmp_path / "commands.yaml"
    path.write_text(
        "commands:\n  - id: custom.hello\n    name: Hello\n    target: system\n"
        "    argv: ['docker', 'version']\n",
        encoding="utf-8",
    )
    container = build_container(
        AppConfig.model_validate(
            {
                "docker": {"mode": "fake"},
                "catalog": {"provider": "memory"},
                "commands": {"extra_file": str(path)},
            }
        )
    )
    assert "custom.hello" in {d.id for d in container.commands.list_definitions()}


def test_composition_can_skip_builtins(tmp_path):
    container = build_container(
        AppConfig.model_validate(
            {
                "docker": {"mode": "fake"},
                "catalog": {"provider": "memory"},
                "commands": {
                    "include_builtin": False,
                    "extra_file": str(tmp_path / "missing.yaml"),
                },
            }
        )
    )
    assert container.commands.list_definitions() == []

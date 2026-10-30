"""Configuration loading: defaults, YAML, environment overrides."""

from __future__ import annotations

import textwrap

import pytest

from lightpanel.config import AppConfig, load_config


def test_defaults_are_sane():
    config = AppConfig()
    assert config.server.port == 9000
    assert config.server.api_prefix == "/api"
    assert config.docker.mode == "auto"
    assert config.metrics.provider == "psutil"
    assert config.security.enabled is False


def test_yaml_file_is_loaded(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        textwrap.dedent(
            """
            env: prod
            server:
              port: 8080
            docker:
              mode: api
              socket: /run/docker.sock
            """
        ),
        encoding="utf-8",
    )
    config = load_config(path)
    assert config.env == "prod"
    assert config.server.port == 8080
    assert config.docker.mode == "api"
    assert config.docker.socket == "/run/docker.sock"


def test_env_overrides_yaml(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("server:\n  port: 8080\n", encoding="utf-8")
    config = load_config(
        path,
        env={"LIGHTPANEL_SERVER__PORT": "9999", "LIGHTPANEL_SECURITY__ENABLED": "true"},
    )
    assert config.server.port == 9999
    assert config.security.enabled is True


def test_env_lists_are_parsed_as_json():
    config = load_config(env={"LIGHTPANEL_COMMANDS__ALLOWED_BINARIES": '["docker","podman"]'})
    assert config.commands.allowed_binaries == ["docker", "podman"]


def test_programmatic_overrides_win():
    config = load_config(
        env={"LIGHTPANEL_SERVER__PORT": "9999"}, overrides={"server": {"port": 1234}}
    )
    assert config.server.port == 1234


def test_unknown_field_is_rejected(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("server:\n  nope: 1\n", encoding="utf-8")
    with pytest.raises(ValueError):  # pydantic ValidationError 是其子类
        load_config(path)


def test_missing_explicit_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "nope.yaml")


def test_token_file_is_read(tmp_path):
    token = tmp_path / "token"
    token.write_text("s3cret\n", encoding="utf-8")
    config = load_config(overrides={"security": {"token_file": str(token)}})
    assert config.security.resolved_token() == "s3cret"


def test_compose_base_argv():
    config = AppConfig()
    assert config.compose.base_argv() == ["docker", "compose"]
    config.compose.subcommand = ""
    config.compose.binary = "docker-compose"
    assert config.compose.base_argv() == ["docker-compose"]

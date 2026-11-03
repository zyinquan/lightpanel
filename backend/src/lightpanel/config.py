"""Application configuration.

Configuration is layered, from lowest to highest precedence:

1. built-in defaults (the pydantic models below)
2. a YAML file (``config.yaml``, path overridable with ``--config``)
3. environment variables prefixed with ``LIGHTPANEL_``
4. explicit programmatic overrides (used by tests)

Nesting is expressed with a double underscore, e.g. ``LIGHTPANEL_SERVER__PORT=8080``
maps to ``server.port``. Values that look like JSON (arrays / objects / numbers)
are parsed as JSON, everything else is passed through as a string and coerced by
pydantic.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

ENV_PREFIX = "LIGHTPANEL_"
ENV_SEPARATOR = "__"


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class ServerConfig(_Base):
    host: str = "0.0.0.0"
    port: int = Field(default=9000, ge=1, le=65535)
    root_path: str = ""
    api_prefix: str = "/api"
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])
    docs: bool = True


class SecurityConfig(_Base):
    """Optional single-token protection.

    LightPanel can start/stop containers, so exposing it without any protection
    is dangerous. Set ``enabled: true`` and provide ``api_token`` (or
    ``token_file``) for any non-loopback deployment.
    """

    enabled: bool = False
    api_token: str = ""
    token_file: str = ""
    header_name: str = "X-LightPanel-Token"
    cookie_name: str = "lightpanel_token"
    query_param: str = "token"

    def resolved_token(self) -> str:
        if self.api_token:
            return self.api_token
        if self.token_file and Path(self.token_file).is_file():
            return Path(self.token_file).read_text(encoding="utf-8").strip()
        return ""


class MetricsConfig(_Base):
    provider: Literal["psutil", "fake"] = "psutil"
    cache_ttl: float = Field(default=2.0, ge=0.0)
    history_size: int = Field(default=60, ge=0, le=1000)
    disk_mounts: list[str] = Field(default_factory=list)
    disk_exclude_fs: list[str] = Field(
        default_factory=lambda: ["squashfs", "tmpfs", "devtmpfs", "overlay", "iso9660"]
    )
    network_interfaces: list[str] = Field(default_factory=list)
    # 宿主机指标代理：面板跑在容器里时，本地 psutil 只能看到容器（Windows / macOS
    # 上是 Docker Desktop 的 Linux 虚拟机）。填上 lightpanel-agent 的地址，就能显示
    # 真实宿主机指标；取不到时自动回落到本地，并在快照 hint 里说明。
    remote_url: str = ""
    remote_timeout: float = Field(default=2.0, gt=0)
    remote_token: str = ""


class DockerConfig(_Base):
    enabled: bool = True
    mode: Literal["auto", "api", "fake"] = "auto"
    socket: str = "/var/run/docker.sock"
    host: str = ""
    api_version: str = "v1.44"
    timeout: float = Field(default=10.0, gt=0)
    include_stopped: bool = True


class ComposeConfig(_Base):
    enabled: bool = True
    binary: str = "docker"
    subcommand: str = "compose"
    search_paths: list[str] = Field(default_factory=lambda: ["/opt", "/srv", "/home", "/data"])
    max_depth: int = Field(default=3, ge=1, le=8)
    timeout: float = Field(default=600.0, gt=0)
    # local: 在本进程里跑 docker compose（要求面板与项目文件在同一文件系统）
    # agent: 交给宿主机上的 lightpanel-agent 跑（面板在容器里时用这个，
    #        否则 compose 文件里的相对 bind mount 会被解析成容器内路径）
    runner: Literal["local", "agent"] = "local"
    agent_url: str = ""
    agent_token: str = ""
    agent_timeout: float = Field(default=600.0, gt=0)

    def base_argv(self) -> list[str]:
        argv = [self.binary]
        if self.subcommand:
            argv.append(self.subcommand)
        return argv


class CatalogConfig(_Base):
    provider: Literal["yaml", "memory"] = "yaml"
    path: str = "data/catalog.yaml"
    # 上传的图标图片存放目录
    icons_dir: str = "data/icons"
    # 首次启动若 path 不存在，从该文件复制一份
    example_file: str | None = None


class CommandsConfig(_Base):
    extra_file: str = "data/commands.yaml"
    # 首次启动若 extra_file 不存在，从该文件复制一份（Docker 镜像用它在空 /data 卷上写出厂示例）
    example_file: str | None = None
    allowed_binaries: list[str] = Field(default_factory=lambda: ["docker", "docker-compose"])
    default_timeout: float = Field(default=120.0, gt=0)
    max_timeout: float = Field(default=1800.0, gt=0)
    allow_ad_hoc_argv: bool = True
    include_builtin: bool = True
    executor: Literal["subprocess", "fake"] = "subprocess"


class LoggingConfig(_Base):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    format: Literal["plain", "json"] = "plain"


class AppConfig(_Base):
    env: Literal["dev", "prod"] = "dev"
    config_path: str = ""
    server: ServerConfig = Field(default_factory=ServerConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    metrics: MetricsConfig = Field(default_factory=MetricsConfig)
    docker: DockerConfig = Field(default_factory=DockerConfig)
    compose: ComposeConfig = Field(default_factory=ComposeConfig)
    catalog: CatalogConfig = Field(default_factory=CatalogConfig)
    commands: CommandsConfig = Field(default_factory=CommandsConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)


DEFAULT_CONFIG_FILENAMES = ("config.yaml", "config.yml", "/etc/lightpanel/config.yaml")


def _deep_set(target: dict[str, Any], path: list[str], value: Any) -> None:
    cursor: dict[str, Any] = target
    for key in path[:-1]:
        nxt = cursor.get(key)
        if not isinstance(nxt, dict):
            nxt = {}
            cursor[key] = nxt
        cursor = nxt
    cursor[path[-1]] = value


def _coerce(raw: str) -> Any:
    stripped = raw.strip()
    if not stripped:
        return raw
    if stripped[0] in "[{" or stripped in {"true", "false", "null"}:
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            return raw
    try:
        return int(stripped)
    except ValueError:
        pass
    try:
        return float(stripped)
    except ValueError:
        pass
    return raw


def env_overrides(env: dict[str, str] | None = None, prefix: str = ENV_PREFIX) -> dict[str, Any]:
    """Turn ``LIGHTPANEL_SERVER__PORT=8080`` into ``{"server": {"port": 8080}}``."""
    source = os.environ if env is None else env
    result: dict[str, Any] = {}
    for raw_key, raw_value in source.items():
        if not raw_key.startswith(prefix):
            continue
        key = raw_key[len(prefix) :]
        if not key:
            continue
        parts = [p.lower() for p in key.split(ENV_SEPARATOR) if p]
        if not parts:
            continue
        _deep_set(result, parts, _coerce(raw_value))
    return result


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = _deep_merge(current, value)
        else:
            merged[key] = value
    return merged


def find_default_config(start: Path | None = None) -> Path | None:
    for name in DEFAULT_CONFIG_FILENAMES:
        candidate = Path(name)
        if candidate.is_file():
            return candidate
    return None


def load_config(
    path: str | os.PathLike[str] | None = None,
    *,
    env: dict[str, str] | None = None,
    overrides: dict[str, Any] | None = None,
) -> AppConfig:
    """Load configuration from YAML + environment variables + explicit overrides."""
    data: dict[str, Any] = {}
    chosen: Path | None = None

    candidates: list[Path] = []
    if path is not None:
        candidates.append(Path(path))
    else:
        found = find_default_config()
        if found is not None:
            candidates.append(found)

    for candidate in candidates:
        if candidate.is_file():
            loaded = yaml.safe_load(candidate.read_text(encoding="utf-8")) or {}
            if not isinstance(loaded, dict):
                raise ValueError(f"config file {candidate} must contain a mapping at the top level")
            data = _deep_merge(data, loaded)
            chosen = candidate
            break
        if path is not None:
            raise FileNotFoundError(f"config file not found: {candidate}")

    data = _deep_merge(data, env_overrides(env=env))
    if overrides:
        data = _deep_merge(data, overrides)

    config = AppConfig.model_validate(data)
    config.config_path = str(chosen) if chosen else ""
    return config


def persist_security_token(config_path: str | os.PathLike[str], token: str) -> None:
    """把新的 ``security.api_token`` 写回 YAML 配置文件。

    只改动这一个键，其余键保持原值；先写临时文件再原子替换，避免写一半
    被读到残缺配置。注释会丢失——用 yaml 往返无法保留，属可接受代价。
    """
    path = Path(config_path)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"config file {path} must contain a mapping at the top level")
    security = data.get("security")
    if not isinstance(security, dict):
        security = {}
    security["api_token"] = token
    data["security"] = security
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    tmp.replace(path)

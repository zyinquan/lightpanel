"""Loads user-defined commands from a YAML file.

Example::

    commands:
      - id: backup.postgres
        name: 备份数据库
        target: container          # container | stack | system
        argv: ["docker", "exec", "{name}", "pg_dump", "-U", "postgres"]
        description: 对指定容器执行 pg_dump
        confirm: true
        danger: false
        timeout: 300
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from ...domain.errors import StorageError, ValidationError
from ...domain.models import CommandDefinition, CommandKind, CommandTarget

logger = logging.getLogger(__name__)


def load_definitions(path: str) -> list[CommandDefinition]:
    file = Path(path)
    if not file.is_file():
        return []
    try:
        document = yaml.safe_load(file.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise StorageError(
            f"Unable to read command definitions at {file}", reason=str(exc)
        ) from exc
    if document is None:
        return []
    rows: list[Any]
    if isinstance(document, dict):
        rows = document.get("commands") or []
    elif isinstance(document, list):
        rows = document
    else:
        raise StorageError("Command definition file must be a mapping or a list")
    if not isinstance(rows, list):
        raise StorageError("'commands' must be a list of definitions")

    definitions: list[CommandDefinition] = []
    for row in rows:
        if not isinstance(row, dict):
            raise StorageError("Each command definition must be a mapping")
        definitions.append(_parse(row))
    return definitions


def _parse(row: dict[str, Any]) -> CommandDefinition:
    command_id = str(row.get("id", "")).strip()
    if not command_id:
        raise ValidationError("Command definition requires an 'id'", field="id")

    try:
        target = CommandTarget(str(row.get("target", "system")).lower())
    except ValueError as exc:
        raise ValidationError(
            f"Invalid target for command {command_id}: {row.get('target')}", field="target"
        ) from exc

    try:
        kind = CommandKind(str(row.get("kind", "shell")).lower())
    except ValueError as exc:
        raise ValidationError(
            f"Invalid kind for command {command_id}: {row.get('kind')}", field="kind"
        ) from exc

    argv = tuple(str(a) for a in row.get("argv", []) or [])
    if kind is CommandKind.SHELL and not argv:
        raise ValidationError(f"Shell command {command_id} requires 'argv'", field="argv")
    if kind is CommandKind.DOCKER_API and not str(row.get("action", "")).strip():
        raise ValidationError(
            f"docker_api command {command_id} requires 'action'", field="action"
        )

    return CommandDefinition(
        id=command_id,
        name=str(row.get("name", command_id)),
        target=target,
        argv=argv,
        kind=kind,
        action=str(row.get("action", "")).strip(),
        description=str(row.get("description", "")),
        confirm=bool(row.get("confirm", False)),
        danger=bool(row.get("danger", False)),
        timeout=float(row.get("timeout", 120.0)),
        working_dir=(str(row["working_dir"]) if row.get("working_dir") else None),
        env={str(k): str(v) for k, v in (row.get("env") or {}).items()},
        builtin=False,
    )

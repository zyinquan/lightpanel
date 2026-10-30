"""Built-in command definitions.

Built-ins are ordinary :class:`CommandDefinition` objects, registered exactly
like user-defined ones — the only difference is ``builtin=True``, which lets the
UI render them in a dedicated section and lets configuration hide them.
"""

from __future__ import annotations

from ..domain.models import CommandDefinition, CommandKind, CommandTarget

BUILTIN_CONTAINER_ACTIONS: tuple[tuple[str, str, str, bool, bool], ...] = (
    # (id suffix, action, label, confirm, danger)
    ("start", "start", "启动", False, False),
    ("stop", "stop", "停止", True, True),
    ("restart", "restart", "重启", True, True),
    ("remove", "remove", "删除", True, True),
)

BUILTIN_STACK_ACTIONS: tuple[tuple[str, str, str, bool, bool], ...] = (
    ("up", "up", "启动 (up -d)", False, False),
    ("down", "down", "停止并移除 (down)", True, True),
    ("restart", "restart", "重启", True, True),
    ("pull", "pull", "拉取镜像", False, False),
)


def builtin_container_commands() -> list[CommandDefinition]:
    return [
        CommandDefinition(
            id=f"container.{suffix}",
            name=label,
            target=CommandTarget.CONTAINER,
            kind=CommandKind.DOCKER_API,
            action=action,
            description=f"通过 Docker API 对容器执行 {action}",
            confirm=confirm,
            danger=danger,
            builtin=True,
        )
        for suffix, action, label, confirm, danger in BUILTIN_CONTAINER_ACTIONS
    ]


def builtin_stack_commands() -> list[CommandDefinition]:
    return [
        CommandDefinition(
            id=f"stack.{suffix}",
            name=label,
            target=CommandTarget.STACK,
            kind=CommandKind.DOCKER_API,
            action=action,
            description=f"对 Compose 项目执行 {action}",
            confirm=confirm,
            danger=danger,
            builtin=True,
        )
        for suffix, action, label, confirm, danger in BUILTIN_STACK_ACTIONS
    ]


def all_builtin_commands() -> list[CommandDefinition]:
    return [*builtin_container_commands(), *builtin_stack_commands()]

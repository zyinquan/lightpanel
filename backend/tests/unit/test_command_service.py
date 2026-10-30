"""Command service: registry, rendering, execution."""

from __future__ import annotations

import pytest

from lightpanel.domain.errors import (
    CommandFailedError,
    CommandRejectedError,
    NotFoundError,
    ValidationError,
)
from lightpanel.domain.models import (
    CommandDefinition,
    CommandKind,
    CommandResult,
    CommandTarget,
)
from lightpanel.services.command_policy import CommandPolicy
from lightpanel.services.command_service import CommandService

from ..conftest import echo_command


def test_builtin_commands_are_registered_by_default():
    from lightpanel.composition import build_container
    from lightpanel.config import AppConfig

    container = build_container(
        AppConfig.model_validate(
            {
                "docker": {"mode": "fake"},
                "catalog": {"provider": "memory"},
                "commands": {"extra_file": "__missing__.yaml"},
            }
        )
    )
    ids = {d.id for d in container.commands.list_definitions()}
    assert {"container.start", "container.stop", "stack.up", "stack.down"} <= ids


async def test_register_and_list_by_target(command_service):
    command_service.register(echo_command())
    container_commands = command_service.list_definitions(CommandTarget.CONTAINER)
    assert "container.echo" in {c.id for c in container_commands}


async def test_unregister(command_service):
    command_service.register(echo_command())
    assert command_service.unregister("container.echo") is True
    assert command_service.unregister("container.echo") is False
    with pytest.raises(NotFoundError):
        command_service.get("container.echo")


async def test_registration_rejects_unsafe_template(command_service):
    with pytest.raises(CommandRejectedError):
        command_service.register(
            CommandDefinition(
                id="bad",
                name="bad",
                target=CommandTarget.CONTAINER,
                kind=CommandKind.SHELL,
                argv=("docker", "{name}; rm -rf /"),
            )
        )


async def test_shell_command_renders_context(command_service, executor):
    command_service.register(echo_command())
    executor.script(CommandResult.success(("docker", "inspect", "nginx"), stdout="[]"))
    result = await command_service.run("container.echo", target_id="nginx")
    assert result.argv == ("docker", "inspect", "nginx")
    assert executor.last_argv == ("docker", "inspect", "nginx")


async def test_shell_command_failure_raises(command_service, executor):
    command_service.register(echo_command())
    executor.always(CommandResult.failure(("docker", "inspect", "nginx"), 1, stderr="boom"))
    with pytest.raises(CommandFailedError) as exc:
        await command_service.run("container.echo", target_id="nginx")
    assert exc.value.details["exit_code"] == 1
    assert "boom" in exc.value.details["stderr"]


async def test_preview_does_not_execute(command_service, executor):
    command_service.register(echo_command())
    argv = await command_service.preview("container.echo", target_id="postgres")
    assert argv == ["docker", "inspect", "postgres"]
    assert executor.calls == []


async def test_container_command_requires_target(command_service):
    command_service.register(echo_command())
    with pytest.raises(ValidationError):
        await command_service.run("container.echo")


async def test_engine_action_start_and_stop(command_service, container_engine):
    command_service.register(
        CommandDefinition(
            id="container.start",
            name="启动",
            target=CommandTarget.CONTAINER,
            kind=CommandKind.DOCKER_API,
            action="start",
        )
    )
    await command_service.run("container.start", target_id="redis")
    assert (await container_engine.get_container("redis")).state.value == "running"


async def test_stack_engine_action(command_service, executor):
    command_service.register(
        CommandDefinition(
            id="stack.up",
            name="启动",
            target=CommandTarget.STACK,
            kind=CommandKind.DOCKER_API,
            action="up",
        )
    )
    executor.always(CommandResult.success(("docker", "compose", "up"), stdout="done"))
    result = await command_service.run("stack.up", target_id="lightpanel")
    assert result.argv[:2] == ("docker", "compose")
    assert "up" in result.argv


async def test_unknown_engine_action_is_rejected(command_service):
    command_service.register(
        CommandDefinition(
            id="stack.teleport",
            name="x",
            target=CommandTarget.STACK,
            kind=CommandKind.DOCKER_API,
            action="teleport",
        )
    )
    with pytest.raises(CommandRejectedError):
        await command_service.run("stack.teleport", target_id="lightpanel")


async def test_ad_hoc_command(command_service, executor):
    result = await command_service.run_argv(["docker", "ps"])
    assert result.ok
    assert executor.last_argv == ("docker", "ps")


async def test_ad_hoc_can_be_blocked_by_policy(container_engine, stack_engine, executor):
    service = CommandService(
        container_engine,
        stack_engine,
        executor,
        CommandPolicy(allowed_binaries=("docker",), allow_ad_hoc_argv=False),
    )
    with pytest.raises(CommandRejectedError):
        await service.run_argv(["docker", "ps"])


async def test_extra_args_are_appended(command_service, executor):
    command_service.register(echo_command())
    await command_service.run("container.echo", target_id="nginx", extra_args=["--format", "json"])
    assert executor.last_argv == ("docker", "inspect", "nginx", "--format", "json")


async def test_timeout_is_forwarded(command_service, executor):
    command_service.register(echo_command())
    await command_service.run("container.echo", target_id="nginx", timeout=5)
    assert executor.calls[-1][2] == 5.0

"""Command registry + execution engine (the "自定义命令" feature).

Two kinds of commands exist:

``DOCKER_API``
    Talk to the container / stack engine directly. Fast, no shell involved.
    Used by the built-in start/stop/restart actions.

``SHELL``
    Run an explicit argv list through :class:`CommandExecutor`. The argv is a
    template rendered against the target's context
    (``{id}``, ``{name}``, ``{project}``, ``{config_file}``, ``{working_dir}``…).

Adding a new command never requires touching this file: build a
:class:`CommandDefinition` and call :meth:`CommandService.register`.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence

from ..domain.errors import CommandFailedError, CommandRejectedError, NotFoundError, ValidationError
from ..domain.models import (
    CommandContext,
    CommandDefinition,
    CommandKind,
    CommandResult,
    CommandTarget,
)
from ..domain.ports import CommandExecutor, ContainerEngine, StackEngine
from .command_policy import CommandPolicy

logger = logging.getLogger(__name__)


class CommandService:
    def __init__(
        self,
        containers: ContainerEngine,
        stacks: StackEngine,
        executor: CommandExecutor,
        policy: CommandPolicy,
        definitions: Iterable[CommandDefinition] = (),
    ) -> None:
        self.containers = containers
        self.stacks = stacks
        self.executor = executor
        self.policy = policy
        self._definitions: dict[str, CommandDefinition] = {}
        for definition in definitions:
            self.register(definition)

    # -- registry ---------------------------------------------------------- #
    def register(self, definition: CommandDefinition) -> CommandDefinition:
        if not definition.id:
            raise ValidationError("Command id must not be empty", field="id")
        if definition.kind is CommandKind.SHELL and definition.argv:
            # Validate the *template* shape; concrete values are checked later.
            self.policy.validate_argv(_neutralize_placeholders(definition.argv))
        self._definitions[definition.id] = definition
        return definition

    def unregister(self, command_id: str) -> bool:
        return self._definitions.pop(command_id, None) is not None

    def list_definitions(
        self, target: CommandTarget | str | None = None
    ) -> list[CommandDefinition]:
        values = list(self._definitions.values())
        if target is None:
            return sorted(values, key=lambda d: (d.target.value, d.id))
        wanted = target if isinstance(target, CommandTarget) else CommandTarget(str(target).lower())
        return sorted(
            (d for d in values if d.target is wanted), key=lambda d: (not d.builtin, d.id)
        )

    def get(self, command_id: str) -> CommandDefinition:
        try:
            return self._definitions[command_id]
        except KeyError as exc:
            raise NotFoundError(f"Command not found: {command_id}") from exc

    # -- execution --------------------------------------------------------- #
    async def run(
        self,
        command_id: str,
        *,
        target_id: str | None = None,
        extra_args: Sequence[str] = (),
        timeout: float | None = None,
    ) -> CommandResult:
        definition = self.get(command_id)
        context = await self._context_for(definition, target_id)

        if definition.kind is CommandKind.DOCKER_API:
            return await self._run_engine_action(definition, target_id, timeout, extra_args)

        argv = [context.render(token) for token in definition.argv]
        argv.extend(str(a) for a in extra_args)
        argv = list(self.policy.validate_argv(argv))

        cwd = self.policy.validate_cwd(
            definition.working_dir or context.get("working_dir") or None
        )
        effective_timeout = self.policy.resolve_timeout(timeout or definition.timeout)
        logger.info(
            "running custom command",
            extra={"command": definition.id, "argv": argv, "cwd": cwd},
        )
        result = await self.executor.run(
            argv, cwd=cwd, env=dict(definition.env) or None, timeout=effective_timeout
        )
        if not result.ok:
            raise CommandFailedError(
                f"Command '{definition.id}' failed (exit {result.exit_code})",
                exit_code=result.exit_code,
                stdout=result.stdout,
                stderr=result.stderr,
            )
        return result

    async def run_argv(
        self,
        argv: Sequence[str],
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: float | None = None,
        context: CommandContext | None = None,
    ) -> CommandResult:
        """Run a one-off argv list (used by the "自定义命令" box in the UI)."""
        self.policy.ensure_ad_hoc_allowed()
        context = context or CommandContext()
        rendered = [context.render(str(token)) for token in argv]
        safe_argv = self.policy.validate_argv(rendered)
        safe_cwd = self.policy.validate_cwd(cwd)
        effective_timeout = self.policy.resolve_timeout(timeout)
        result = await self.executor.run(
            safe_argv, cwd=safe_cwd, env=env, timeout=effective_timeout
        )
        if not result.ok:
            raise CommandFailedError(
                f"Ad-hoc command failed (exit {result.exit_code})",
                exit_code=result.exit_code,
                stdout=result.stdout,
                stderr=result.stderr,
            )
        return result

    async def preview(
        self, command_id: str, *, target_id: str | None = None
    ) -> list[str]:
        """Render a command without running it — handy for UI confirmation."""
        definition = self.get(command_id)
        context = await self._context_for(definition, target_id)
        return [context.render(token) for token in definition.argv]

    # -- internals --------------------------------------------------------- #
    async def _context_for(
        self, definition: CommandDefinition, target_id: str | None
    ) -> CommandContext:
        if definition.target is CommandTarget.CONTAINER:
            if not target_id:
                raise ValidationError("Container commands require a target_id")
            container = await self.containers.get_container(target_id)
            return CommandContext.of(
                id=container.id,
                short_id=container.short_id,
                name=container.name,
                image=container.image,
                project=container.compose_project,
                service=container.compose_service,
                working_dir=container.compose_working_dir,
                config_file=container.compose_config_files,
            )
        if definition.target is CommandTarget.STACK:
            if not target_id:
                raise ValidationError("Stack commands require a target_id")
            stack = await self.stacks.get_stack(target_id)
            files = [f for f in stack.config_files.split(",") if f]
            return CommandContext.of(
                name=stack.name,
                project=stack.name,
                working_dir=stack.working_dir,
                config_file=files[0] if files else "",
            )
        return CommandContext.of(name=target_id or "")

    async def _run_engine_action(
        self,
        definition: CommandDefinition,
        target_id: str | None,
        timeout: float | None,
        extra_args: Sequence[str],
    ) -> CommandResult:
        action = definition.action
        argv = (definition.id, action, target_id or "")
        if definition.target is CommandTarget.CONTAINER:
            if not target_id:
                raise ValidationError("Container commands require a target_id")
            if action == "start":
                await self.containers.start(target_id)
            elif action == "stop":
                await self.containers.stop(target_id, timeout=int(timeout) if timeout else None)
            elif action == "restart":
                await self.containers.restart(target_id, timeout=int(timeout) if timeout else None)
            elif action == "remove":
                await self.containers.remove(target_id, force=True)
            else:
                raise CommandRejectedError(f"Unknown container action: {action}")
            return CommandResult.success(argv, stdout=f"container {action} ok")

        if definition.target is CommandTarget.STACK:
            if not target_id:
                raise ValidationError("Stack commands require a target_id")
            stack = await self.stacks.get_stack(target_id)
            if action == "up":
                result = await self.stacks.up(stack, extra_args=extra_args)
            elif action == "down":
                result = await self.stacks.down(stack, extra_args=extra_args)
            elif action == "restart":
                result = await self.stacks.restart(stack, extra_args=extra_args)
            elif action == "pull":
                result = await self.stacks.pull(stack, extra_args=extra_args)
            else:
                raise CommandRejectedError(f"Unknown stack action: {action}")
            if not result.ok:
                raise CommandFailedError(
                    f"Stack '{target_id}' {action} failed (exit {result.exit_code})",
                    exit_code=result.exit_code,
                    stdout=result.stdout,
                    stderr=result.stderr,
                )
            return result

        raise CommandRejectedError(f"Commands for {definition.target} cannot use the engine API")


def _neutralize_placeholders(argv: Sequence[str]) -> list[str]:
    """Replace ``{...}`` placeholders with a placeholder-safe token for validation."""
    import re

    return [re.sub(r"\{[^}]*\}", "value", token) for token in argv]

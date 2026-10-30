"""Docker Compose stack use-cases."""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum
from typing import Any

from ..domain.errors import CommandFailedError, ValidationError
from ..domain.models import CommandResult, StackInfo
from ..domain.ports import StackEngine


class StackAction(StrEnum):
    UP = "up"
    DOWN = "down"
    RESTART = "restart"
    PULL = "pull"


class StackService:
    """Listing and lifecycle operations for Compose projects."""

    def __init__(self, engine: StackEngine) -> None:
        self.engine = engine

    async def list_stacks(self, *, search: str = "") -> list[StackInfo]:
        stacks = await self.engine.list_stacks()
        needle = search.strip().casefold()
        if not needle:
            return stacks
        return [s for s in stacks if needle in s.name.casefold()]

    async def get(self, name: str) -> StackInfo:
        return await self.engine.get_stack(name)

    async def act(
        self,
        name: str,
        action: StackAction | str,
        *,
        extra_args: Sequence[str] = (),
    ) -> tuple[CommandResult, StackInfo]:
        try:
            raw = action.value if isinstance(action, StackAction) else str(action)
            normalized = StackAction(raw.lower())
        except ValueError as exc:
            raise ValidationError(f"Unsupported stack action: {action}") from exc

        stack = await self.engine.get_stack(name)
        if normalized is StackAction.UP:
            result = await self.engine.up(stack, extra_args=extra_args)
        elif normalized is StackAction.DOWN:
            result = await self.engine.down(stack, extra_args=extra_args)
        elif normalized is StackAction.RESTART:
            result = await self.engine.restart(stack, extra_args=extra_args)
        else:
            result = await self.engine.pull(stack, extra_args=extra_args)

        if not result.ok:
            raise CommandFailedError(
                f"{normalized.value} failed for stack {name} (exit {result.exit_code})",
                exit_code=result.exit_code,
                stdout=result.stdout,
                stderr=result.stderr,
            )
        try:
            refreshed = await self.engine.get_stack(name)
        except Exception:  # pragma: no cover - stack may have vanished
            refreshed = stack
        return result, refreshed

    async def status(self) -> dict[str, Any]:
        available = await self.engine.is_available()
        stacks = await self.engine.list_stacks() if available else []
        return {
            "provider": getattr(self.engine, "name", "unknown"),
            "available": available,
            "total": len(stacks),
            "running": sum(1 for s in stacks if s.status.value == "running"),
        }

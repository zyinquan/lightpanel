"""Scriptable command executor used by tests and ``docker.mode: fake``."""

from __future__ import annotations

from collections.abc import Sequence

from ...domain.models import CommandResult


class FakeCommandExecutor:
    """Records every invocation and replays scripted results.

    Usage::

        executor = FakeCommandExecutor()
        executor.script(CommandResult.success(("docker", "start", "web")))
        result = await executor.run(["docker", "start", "web"])
    """

    def __init__(self, *, default_result: CommandResult | None = None) -> None:
        self.calls: list[tuple[tuple[str, ...], str | None, float | None]] = []
        self.envs: list[dict[str, str] | None] = []
        self._scripted: list[CommandResult] = []
        self._by_argv: dict[tuple[str, ...], CommandResult] = {}
        self._default = default_result

    # -- scripting helpers ------------------------------------------------- #
    def script(self, *results: CommandResult) -> FakeCommandExecutor:
        self._scripted.extend(results)
        return self

    def for_argv(self, argv: Sequence[str], result: CommandResult) -> FakeCommandExecutor:
        self._by_argv[tuple(argv)] = result
        return self

    def always(self, result: CommandResult) -> FakeCommandExecutor:
        self._default = result
        return self

    # -- port implementation ----------------------------------------------- #
    async def run(
        self,
        argv: Sequence[str],
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> CommandResult:
        args = tuple(str(a) for a in argv)
        self.calls.append((args, cwd, timeout))
        self.envs.append(env)

        if args in self._by_argv:
            return self._by_argv[args]
        if self._scripted:
            return self._scripted.pop(0)
        if self._default is not None:
            return self._default
        return CommandResult.success(args, stdout=f"ok: {' '.join(args)}", duration_ms=1)

    # -- assertions helpers ------------------------------------------------ #
    @property
    def last_argv(self) -> tuple[str, ...] | None:
        return self.calls[-1][0] if self.calls else None

    def argv_containing(self, token: str) -> list[tuple[str, ...]]:
        return [argv for argv, _, _ in self.calls if token in argv]

    def reset(self) -> None:
        self.calls.clear()
        self.envs.clear()
        self._scripted.clear()
        self._by_argv.clear()

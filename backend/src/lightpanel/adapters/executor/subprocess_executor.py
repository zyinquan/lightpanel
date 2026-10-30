"""Runs commands as an explicit argv list — never through a shell string."""

from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
import time
from collections.abc import Sequence

from ...domain.models import CommandResult


class SubprocessCommandExecutor:
    """Default :class:`CommandExecutor`: ``asyncio.create_subprocess_exec``.

    Security notes:

    * No ``shell=True`` anywhere, so shell metacharacters are inert.
    * ``allowed_binaries`` (when non-empty) is a second line of defence applied
      *after* the service-level policy check.
    * Output is capped so a runaway container cannot exhaust memory.
    """

    def __init__(
        self,
        *,
        allowed_binaries: Sequence[str] | None = None,
        default_timeout: float = 120.0,
        max_output_bytes: int = 256 * 1024,
        base_env: dict[str, str] | None = None,
    ) -> None:
        self.allowed_binaries = tuple(allowed_binaries or ())
        self.default_timeout = default_timeout
        self.max_output_bytes = max_output_bytes

    async def run(
        self,
        argv: Sequence[str],
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> CommandResult:
        args = tuple(str(a) for a in argv)
        started = time.monotonic()
        if not args:
            return CommandResult.failure(args, exit_code=2, stderr="empty argv")

        if self.allowed_binaries and os.path.basename(args[0]) not in self.allowed_binaries:
            return CommandResult.failure(
                args, exit_code=126, stderr=f"binary not allowed: {args[0]}"
            )

        merged_env: dict[str, str] | None = None
        if env:
            merged_env = {**os.environ, **{str(k): str(v) for k, v in env.items()}}

        effective_timeout = timeout if timeout is not None else self.default_timeout

        try:
            process = await asyncio.create_subprocess_exec(
                *args,
                cwd=cwd or None,
                env=merged_env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except (FileNotFoundError, PermissionError, OSError) as exc:
            return CommandResult.failure(
                args,
                exit_code=127,
                stderr=f"unable to execute {args[0]}: {exc}",
                duration_ms=_elapsed(started),
            )

        try:
            stdout_raw, stderr_raw = await asyncio.wait_for(
                process.communicate(), timeout=effective_timeout
            )
        except TimeoutError:
            _kill(process)
            return CommandResult.failure(
                args,
                exit_code=124,
                stderr=f"command timed out after {effective_timeout}s",
                duration_ms=_elapsed(started),
            )

        exit_code = process.returncode or 0
        stdout = _decode(stdout_raw, self.max_output_bytes)
        stderr = _decode(stderr_raw, self.max_output_bytes)
        result = CommandResult(
            argv=args,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            duration_ms=_elapsed(started),
            ok=exit_code == 0,
        )
        return result

    @staticmethod
    def which(binary: str) -> str | None:
        return shutil.which(binary)


def _elapsed(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def _decode(raw: bytes | None, limit: int) -> str:
    if not raw:
        return ""
    text = raw[:limit].decode("utf-8", errors="replace")
    if len(raw) > limit:
        text += "…(truncated)"
    return text


def _kill(process: asyncio.subprocess.Process) -> None:  # pragma: no cover - timing dependent
    with contextlib.suppress(ProcessLookupError):
        process.kill()

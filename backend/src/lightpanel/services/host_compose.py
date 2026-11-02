"""Agent-side Compose operations (runs **on the host**).

The panel already talks to a ``lightpanel-agent`` for host metrics; the same
agent can also execute compose. That matters because compose resolves relative
bind mounts (``./src:/app``) against the filesystem it runs on. Inside a panel
container those paths point into the container, so Docker ends up creating empty
directories on the host and the service starts without its code — no error, just
silently wrong. Running the CLI on the host keeps every path meaningful.

Security posture: this service never accepts a free-form command line. It only
takes an action from a fixed set, a project name, and paths that must live under
one of the configured stack roots.
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Callable, Sequence
from pathlib import Path

from ..compose_cli import build_argv
from ..domain.errors import CommandRejectedError, ValidationError
from ..domain.models import CommandResult, StackInfo
from ..domain.ports import CommandExecutor

logger = logging.getLogger(__name__)

ACTIONS = ("up", "down", "restart", "pull")
_PROJECT_NAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$")
# 这些选项会让调用方绕开路径限制（换项目目录 / 换 compose 文件）
_OVERRIDING_FLAGS = {"-f", "--file", "-p", "--project-name", "--project-directory", "--env-file"}


class HostComposeService:
    """Discover and control compose projects rooted at ``roots`` on this host."""

    def __init__(
        self,
        roots: Sequence[str],
        *,
        executor: CommandExecutor,
        scanner: Callable[[Sequence[str], int], list[StackInfo]],
        max_depth: int = 3,
        binary: str = "docker",
        subcommand: str = "compose",
        timeout: float = 600.0,
    ) -> None:
        self.roots = [str(r) for r in roots]
        self.max_depth = max_depth
        self.binary = binary
        self.subcommand = subcommand
        self.timeout = timeout
        self.executor = executor
        self._scanner = scanner

    # -- discovery --------------------------------------------------------- #
    def list_projects(self) -> list[StackInfo]:
        return self._scanner(self.roots, self.max_depth)

    # -- actions ----------------------------------------------------------- #
    async def act(
        self,
        name: str,
        action: str,
        *,
        config_files: str = "",
        working_dir: str = "",
        extra_args: Sequence[str] = (),
    ) -> CommandResult:
        normalized = action.lower()
        if normalized not in ACTIONS:
            raise ValidationError(f"Unsupported stack action: {action}")
        if not _PROJECT_NAME.match(name):
            raise ValidationError(f"Invalid stack name: {name}", name=name)

        readable = self._readable_config_files(config_files)
        if normalized in ("up", "pull") and not readable:
            raise ValidationError(
                f"Compose files for stack '{name}' are not reachable from the agent",
                config_files=config_files,
                roots=self.roots,
            )

        base = [self.binary, *([self.subcommand] if self.subcommand else [])]
        argv = build_argv(
            base,
            project=name,
            action=normalized,
            config_files=readable,
            extra_args=self._sanitize_extra(extra_args),
        )

        cwd = working_dir if working_dir and Path(working_dir).is_dir() else None
        if cwd and not self.is_within_roots(cwd):
            # 相对 bind mount 由 compose 文件所在目录决定，cwd 只是附加保险
            logger.warning("working_dir %s 不在允许的栈根目录内，已忽略", cwd)
            cwd = None

        logger.info("agent executing compose", extra={"argv": argv, "cwd": cwd})
        return await self.executor.run(argv, cwd=cwd, timeout=self.timeout)

    # -- validation -------------------------------------------------------- #
    def _readable_config_files(self, config_files: str) -> list[str]:
        files: list[str] = []
        for raw in (config_files or "").split(","):
            candidate = raw.strip()
            if not candidate:
                continue
            if not self.is_within_roots(candidate):
                raise ValidationError(
                    f"Compose file is outside the allowed stack roots: {candidate}",
                    roots=self.roots,
                )
            if Path(candidate).is_file():
                files.append(candidate)
        return files

    def is_within_roots(self, path: str) -> bool:
        target = _resolve(path)
        for root in self.roots:
            base = _resolve(root)
            try:
                common = os.path.commonpath([target, base])
            except ValueError:  # 不同盘符（Windows）
                continue
            if os.path.normcase(common) == os.path.normcase(base):
                return True
        return False

    @staticmethod
    def _sanitize_extra(extra_args: Sequence[str]) -> list[str]:
        cleaned: list[str] = []
        for token in extra_args:
            text = str(token)
            if text.split("=")[0] in _OVERRIDING_FLAGS:
                raise CommandRejectedError(f"compose 参数不允许覆盖项目路径：{text}")
            cleaned.append(text)
        return cleaned


def _resolve(path: str) -> str:
    return os.path.realpath(os.path.expanduser(str(path)))

"""Safety policy applied to every shell command before execution.

LightPanel runs commands on the host, so this is the single choke point that
decides what may run. It is intentionally conservative:

* only binaries on the allow-list may be executed,
* no shell metacharacters (the command is never passed to a shell anyway,
  but a stray ``;`` would silently break the intent),
* timeouts are clamped,
* working directories must be absolute and must exist.
"""

from __future__ import annotations

import os
from collections.abc import Sequence

from ..domain.errors import CommandRejectedError

FORBIDDEN_TOKENS = (";", "&&", "||", "|", "`", "$(", ">", "<", "\n", "\r", "\0")
INTERPRETERS = {"sh", "bash", "zsh", "cmd", "powershell", "python", "python3", "perl"}


class CommandPolicy:
    def __init__(
        self,
        *,
        allowed_binaries: Sequence[str] = (),
        default_timeout: float = 120.0,
        max_timeout: float = 1800.0,
        allow_ad_hoc_argv: bool = True,
    ) -> None:
        self.allowed_binaries = tuple(allowed_binaries)
        self.default_timeout = default_timeout
        self.max_timeout = max_timeout
        self.allow_ad_hoc_argv = allow_ad_hoc_argv

    def validate_argv(self, argv: Sequence[str]) -> tuple[str, ...]:
        tokens = [str(token) for token in argv]
        if not tokens:
            raise CommandRejectedError("Command must not be empty")

        binary = os.path.basename(tokens[0])
        if binary.lower() in INTERPRETERS:
            raise CommandRejectedError(
                f"Interpreter '{binary}' is not allowed; call the target binary directly",
                binary=binary,
            )
        if self.allowed_binaries and binary not in self.allowed_binaries:
            raise CommandRejectedError(
                f"Binary '{binary}' is not on the allow-list",
                binary=binary,
                allowed=list(self.allowed_binaries),
            )
        for token in tokens:
            if token.strip() == "":
                raise CommandRejectedError("Command contains an empty argument")
            for forbidden in FORBIDDEN_TOKENS:
                if forbidden in token:
                    raise CommandRejectedError(
                        f"Argument contains forbidden sequence {forbidden!r}",
                        argument=token,
                    )
        return tuple(tokens)

    def resolve_timeout(self, timeout: float | None) -> float:
        if timeout is None:
            return self.default_timeout
        if timeout <= 0:
            raise CommandRejectedError("Timeout must be positive", timeout=timeout)
        return min(timeout, self.max_timeout)

    def validate_cwd(self, cwd: str | None) -> str | None:
        if cwd is None or cwd == "":
            return None
        if not os.path.isabs(cwd):
            raise CommandRejectedError("Working directory must be an absolute path", cwd=cwd)
        if not os.path.isdir(cwd):
            raise CommandRejectedError("Working directory does not exist", cwd=cwd)
        return cwd

    def ensure_ad_hoc_allowed(self) -> None:
        if not self.allow_ad_hoc_argv:
            raise CommandRejectedError(
                "Ad-hoc commands are disabled; use a registered command id"
            )

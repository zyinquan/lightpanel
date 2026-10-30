"""Domain error hierarchy.

Every error raised inside the domain / service layer derives from
:class:`LightPanelError` and carries a stable ``code`` plus an HTTP
``status_code``, so the API layer can map failures to responses without
``if isinstance(...)`` chains.
"""

from __future__ import annotations

from typing import Any


class LightPanelError(Exception):
    """Base class for all expected, user-facing errors."""

    status_code: int = 500
    code: str = "internal_error"
    default_message: str = "Unexpected error"

    def __init__(self, message: str | None = None, **details: Any) -> None:
        self.message = message or self.default_message
        self.details = details
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details:
            payload["details"] = self.details
        return payload

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"{type(self).__name__}({self.message!r}, details={self.details!r})"


class ValidationError(LightPanelError):
    status_code = 400
    code = "validation_error"
    default_message = "Invalid input"


class NotFoundError(LightPanelError):
    status_code = 404
    code = "not_found"
    default_message = "Resource not found"


class ConflictError(LightPanelError):
    status_code = 409
    code = "conflict"
    default_message = "Resource already exists"


class AuthenticationError(LightPanelError):
    status_code = 401
    code = "unauthenticated"
    default_message = "Authentication required"


class PermissionDeniedError(LightPanelError):
    status_code = 403
    code = "forbidden"
    default_message = "Permission denied"


class EngineUnavailableError(LightPanelError):
    status_code = 503
    code = "engine_unavailable"
    default_message = "Backend engine is unavailable"


class CommandRejectedError(LightPanelError):
    """A command was refused *before* execution (guard / allow-list violation)."""

    status_code = 400
    code = "command_rejected"
    default_message = "Command rejected by policy"


class CommandFailedError(LightPanelError):
    """A command was accepted but exited with a non-zero status."""

    status_code = 502
    code = "command_failed"
    default_message = "Command execution failed"

    def __init__(
        self,
        message: str | None = None,
        *,
        exit_code: int = -1,
        stdout: str = "",
        stderr: str = "",
        **details: Any,
    ) -> None:
        super().__init__(
            message,
            exit_code=exit_code,
            stdout=_truncate(stdout),
            stderr=_truncate(stderr),
            **details,
        )


class StorageError(LightPanelError):
    status_code = 500
    code = "storage_error"
    default_message = "Persistence layer failure"


def _truncate(text: str, limit: int = 4000) -> str:
    if text is None:
        return ""
    return text if len(text) <= limit else text[:limit] + "…(truncated)"

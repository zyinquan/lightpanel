"""Logging setup."""

from __future__ import annotations

import json
import logging
import logging.config
from datetime import UTC, datetime
from typing import Any

from .config import LoggingConfig

PLAIN_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"


class JsonFormatter(logging.Formatter):
    """Minimal JSON log formatter (no extra dependency)."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        extra = getattr(record, "__dict__", {})
        for key in ("argv", "command", "cwd"):
            if key in extra:
                payload[key] = extra[key]
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(settings: LoggingConfig | None = None) -> None:
    settings = settings or LoggingConfig()
    handlers: dict[str, Any] = {
        "default": {
            "class": "logging.StreamHandler",
            "formatter": "json" if settings.format == "json" else "plain",
            "stream": "ext://sys.stdout",
        }
    }
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "plain": {"format": PLAIN_FORMAT},
                "json": {"()": JsonFormatter},
            },
            "handlers": handlers,
            "root": {"level": settings.level, "handlers": ["default"]},
            "loggers": {
                "uvicorn": {"level": settings.level, "handlers": ["default"], "propagate": False},
                "uvicorn.access": {
                    "level": settings.level,
                    "handlers": ["default"],
                    "propagate": False,
                },
            },
        }
    )

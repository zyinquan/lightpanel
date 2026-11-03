"""Filesystem-backed store for uploaded catalog icons.

Files live in a dedicated directory (``data/icons`` by default) and are served
through ``GET /catalog/icons/{name}``. Names are random hex, so user input never
touches the filesystem path and a replaced icon simply gets a new URL — browsers
can cache aggressively without stale-image risk.
"""

from __future__ import annotations

import asyncio
import contextlib
import re
import secrets
from pathlib import Path

from ...domain.errors import ValidationError

MAX_ICON_BYTES = 2 * 1024 * 1024

# 只收位图格式；SVG 可以内嵌脚本，作为上传目标一律拒绝。
_MAGIC = (
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"\xff\xd8\xff", ".jpg"),
    (b"GIF87a", ".gif"),
    (b"GIF89a", ".gif"),
)

NAME_PATTERN = re.compile(r"^[0-9a-f]{16}\.[a-z]{3,4}$")
EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


class IconStore:
    """Stores uploaded icon images and maps them to stable URLs."""

    def __init__(self, root: str | Path, *, max_bytes: int = MAX_ICON_BYTES) -> None:
        self.root = Path(root)
        self.max_bytes = max_bytes

    async def save(self, data: bytes) -> str:
        """Persist image bytes, return the URL path of the stored file."""
        if not data:
            raise ValidationError("Icon file is empty", field="icon_image")
        if len(data) > self.max_bytes:
            raise ValidationError(
                f"Icon file is too large (max {self.max_bytes // (1024 * 1024)} MB)",
                field="icon_image",
            )
        extension = self._sniff(data)
        name = f"{secrets.token_hex(8)}{extension}"
        await asyncio.to_thread(self._write, name, data)
        return self.url_for(name)

    async def delete(self, reference: str) -> None:
        """Remove the file behind a stored icon reference. Missing files are fine."""
        path = self.resolve(reference)
        if path is None:
            return
        await asyncio.to_thread(_unlink_quiet, path)

    def resolve(self, reference: str) -> Path | None:
        """Map a stored URL (or bare filename) to a path inside the store."""
        name = reference.rstrip("/").rsplit("/", 1)[-1]
        if not NAME_PATTERN.match(name):
            return None
        path = self.root / name
        if path.suffix not in EXTENSIONS or not path.is_file():
            return None
        return path

    def url_for(self, name: str) -> str:
        return f"/api/catalog/icons/{name}"

    def is_managed(self, reference: str) -> bool:
        """True when the reference points into this store (vs. an external URL)."""
        return reference.startswith(self.url_for("").rstrip("/"))

    def _write(self, name: str, data: bytes) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / name).write_bytes(data)

    @staticmethod
    def _sniff(data: bytes) -> str:
        for magic, extension in _MAGIC:
            if data.startswith(magic):
                return extension
        if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            return ".webp"
        raise ValidationError(
            "Unsupported icon format: use PNG, JPEG, WebP or GIF",
            field="icon_image",
        )


def _unlink_quiet(path: Path) -> None:
    with contextlib.suppress(FileNotFoundError):
        path.unlink()

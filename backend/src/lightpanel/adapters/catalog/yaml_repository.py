"""YAML-backed software catalog repository.

The file is the single source of truth and is rewritten atomically, so a crash
mid-write can never leave a half-written catalog behind.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml

from ...domain.errors import StorageError
from ...domain.models import SoftwareEntry


class YamlCatalogRepository:
    """Persists :class:`SoftwareEntry` objects in a YAML document."""

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path)
        self._lock = asyncio.Lock()

    # -- public API -------------------------------------------------------- #
    async def list_entries(self) -> list[SoftwareEntry]:
        return list(await self._read())

    async def get(self, entry_id: str) -> SoftwareEntry | None:
        for entry in await self._read():
            if entry.id == entry_id:
                return entry
        return None

    async def add(self, entry: SoftwareEntry) -> SoftwareEntry:
        async with self._lock:
            entries = list(await self._read_unlocked())
            if any(e.id == entry.id for e in entries):
                raise KeyError(entry.id)
            entries.append(entry)
            await self._write_unlocked(entries)
        return entry

    async def update(self, entry: SoftwareEntry) -> SoftwareEntry:
        async with self._lock:
            entries = await self._read_unlocked()
            for index, existing in enumerate(entries):
                if existing.id == entry.id:
                    entries[index] = entry
                    await self._write_unlocked(entries)
                    return entry
        raise KeyError(entry.id)

    async def remove(self, entry_id: str) -> bool:
        async with self._lock:
            entries = await self._read_unlocked()
            remaining = [e for e in entries if e.id != entry_id]
            if len(remaining) == len(entries):
                return False
            await self._write_unlocked(remaining)
            return True

    async def replace_all(self, entries: Sequence[SoftwareEntry]) -> None:
        async with self._lock:
            await self._write_unlocked(list(entries))

    def seed_if_missing(self, example_path: str | os.PathLike[str]) -> bool:
        """Copy ``example_path`` to the catalog path when no catalog exists yet.

        Deliberately synchronous: it runs once at startup, before the event loop
        serves requests, and a blocking copy keeps the factory free of awaiting.
        """
        if self.path.exists():
            return False
        source = Path(example_path)
        if not source.is_file():
            return False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_bytes(source.read_bytes())
        return True

    # -- internals --------------------------------------------------------- #
    async def _read(self) -> list[SoftwareEntry]:
        async with self._lock:
            return await self._read_unlocked()

    async def _read_unlocked(self) -> list[SoftwareEntry]:
        if not self.path.exists():
            return []
        try:
            raw = await asyncio.to_thread(self.path.read_text, encoding="utf-8")
            document = yaml.safe_load(raw)
        except (OSError, yaml.YAMLError) as exc:
            raise StorageError(
                f"Unable to read catalog at {self.path}", reason=str(exc)
            ) from exc
        return self._deserialize(document)

    @staticmethod
    def _deserialize(document: Any) -> list[SoftwareEntry]:
        if document is None:
            return []
        if isinstance(document, list):
            rows = document
        elif isinstance(document, dict):
            rows = document.get("entries", [])
        else:
            raise StorageError("Catalog document must be a mapping or a list")

        entries: list[SoftwareEntry] = []
        for row in rows:
            if not isinstance(row, dict):
                raise StorageError("Catalog entries must be mappings")
            try:
                entries.append(
                    SoftwareEntry(
                        id=str(row["id"]),
                        name=str(row.get("name", row["id"])),
                        url=str(row.get("url", "")),
                        description=str(row.get("description", "")),
                        icon=str(row.get("icon", "")),
                        color=str(row.get("color", "")),
                        category=str(row.get("category", "")),
                        tags=[str(t) for t in row.get("tags", []) or []],
                        enabled=bool(row.get("enabled", True)),
                        order=int(row.get("order", 0)),
                    )
                )
            except KeyError as exc:  # pragma: no cover - defensive
                raise StorageError(f"Catalog entry missing field: {exc}") from exc
        return entries

    async def _write_unlocked(self, entries: Sequence[SoftwareEntry]) -> None:
        payload = {"entries": [asdict(e) for e in entries]}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        text = yaml.safe_dump(
            payload, allow_unicode=True, sort_keys=False, default_flow_style=False
        )
        try:
            await asyncio.to_thread(self._atomic_write, text)
        except OSError as exc:
            raise StorageError(
                f"Unable to write catalog at {self.path}", reason=str(exc)
            ) from exc

    def _atomic_write(self, text: str) -> None:
        directory = str(self.path.parent)
        handle = tempfile.NamedTemporaryFile(  # noqa: SIM115 - delete=False needs manual cleanup
            "w", encoding="utf-8", dir=directory, prefix=".catalog-", suffix=".yaml", delete=False
        )
        try:
            with handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(handle.name, self.path)
        finally:
            if os.path.exists(handle.name):  # pragma: no cover - only on failure
                os.unlink(handle.name)

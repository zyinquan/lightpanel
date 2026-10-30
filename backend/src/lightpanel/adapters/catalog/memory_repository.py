"""In-memory catalog repository (tests, ephemeral deployments)."""

from __future__ import annotations

import copy
from collections.abc import Sequence

from ...domain.models import SoftwareEntry


class InMemoryCatalogRepository:
    """Dictionary-backed repository; no durability, useful for tests."""

    def __init__(self, entries: Sequence[SoftwareEntry] | None = None) -> None:
        self._entries: dict[str, SoftwareEntry] = {}
        for entry in entries or []:
            self._entries[entry.id] = entry

    async def list_entries(self) -> list[SoftwareEntry]:
        return [copy.deepcopy(e) for e in self._entries.values()]

    async def get(self, entry_id: str) -> SoftwareEntry | None:
        found = self._entries.get(entry_id)
        return copy.deepcopy(found) if found else None

    async def add(self, entry: SoftwareEntry) -> SoftwareEntry:
        if entry.id in self._entries:
            raise KeyError(entry.id)
        self._entries[entry.id] = copy.deepcopy(entry)
        return copy.deepcopy(entry)

    async def update(self, entry: SoftwareEntry) -> SoftwareEntry:
        if entry.id not in self._entries:
            raise KeyError(entry.id)
        self._entries[entry.id] = copy.deepcopy(entry)
        return copy.deepcopy(entry)

    async def remove(self, entry_id: str) -> bool:
        return self._entries.pop(entry_id, None) is not None

    async def replace_all(self, entries: Sequence[SoftwareEntry]) -> None:
        self._entries = {e.id: copy.deepcopy(e) for e in entries}

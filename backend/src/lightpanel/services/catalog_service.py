"""Software catalog use-cases (entries + tags)."""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Literal

from ..domain.errors import ConflictError, NotFoundError, ValidationError
from ..domain.models import SoftwareEntry, TagSummary
from ..domain.ports import CatalogRepository

ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
COLOR_PATTERN = re.compile(r"^(#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}))?$")
MAX_TAGS = 24
MAX_TAG_LENGTH = 32


@dataclass(frozen=True, slots=True)
class CatalogQuery:
    tags: tuple[str, ...] = ()
    match_all_tags: bool = False
    category: str = ""
    search: str = ""
    enabled_only: bool = False
    sort: Literal["order", "name", "recent"] = "order"


@dataclass(slots=True)
class CatalogPage:
    entries: list[SoftwareEntry] = field(default_factory=list)
    tags: list[TagSummary] = field(default_factory=list)
    total: int = 0


class CatalogService:
    """CRUD + tag aggregation for the software catalog.

    The service knows nothing about YAML, SQL or HTTP — it only speaks the
    :class:`CatalogRepository` port.
    """

    def __init__(self, repository: CatalogRepository) -> None:
        self.repository = repository

    async def list_entries(self, query: CatalogQuery | None = None) -> list[SoftwareEntry]:
        query = query or CatalogQuery()
        entries = await self.repository.list_entries()
        return self._apply(entries, query)

    async def page(self, query: CatalogQuery | None = None) -> CatalogPage:
        query = query or CatalogQuery()
        all_entries = await self.repository.list_entries()
        filtered = self._apply(all_entries, query)
        counter: Counter[str] = Counter()
        for entry in all_entries:
            if query.enabled_only and not entry.enabled:
                continue
            for tag in entry.normalized_tags():
                counter[tag] += 1
        tags = [TagSummary(name=name, count=count) for name, count in counter.items()]
        tags.sort(key=lambda t: (-t.count, t.name.casefold()))
        return CatalogPage(entries=filtered, tags=tags, total=len(filtered))

    async def get(self, entry_id: str) -> SoftwareEntry:
        entry = await self.repository.get(entry_id)
        if entry is None:
            raise NotFoundError(f"Software entry not found: {entry_id}")
        return entry

    async def create(self, entry: SoftwareEntry) -> SoftwareEntry:
        validate_entry(entry)
        if await self.repository.get(entry.id) is not None:
            raise ConflictError(f"Software entry already exists: {entry.id}")
        return await self.repository.add(entry)

    async def update(self, entry: SoftwareEntry) -> SoftwareEntry:
        validate_entry(entry)
        if await self.repository.get(entry.id) is None:
            raise NotFoundError(f"Software entry not found: {entry.id}")
        return await self.repository.update(entry)

    async def delete(self, entry_id: str) -> None:
        if not await self.repository.remove(entry_id):
            raise NotFoundError(f"Software entry not found: {entry_id}")

    async def tags(self) -> list[TagSummary]:
        counter: Counter[str] = Counter()
        for entry in await self.repository.list_entries():
            for tag in entry.normalized_tags():
                counter[tag] += 1
        return sorted(
            (TagSummary(name=n, count=c) for n, c in counter.items()),
            key=lambda t: (-t.count, t.name.casefold()),
        )

    async def set_tags(self, entry_id: str, tags: list[str]) -> SoftwareEntry:
        entry = await self.get(entry_id)
        entry.tags = list(tags)
        validate_entry(entry)
        return await self.repository.update(entry)

    async def reorder(self, ordered_ids: list[str]) -> list[SoftwareEntry]:
        entries = {e.id: e for e in await self.repository.list_entries()}
        for index, entry_id in enumerate(ordered_ids):
            entry = entries.get(entry_id)
            if entry is None:
                raise NotFoundError(f"Software entry not found: {entry_id}")
            entry.order = index
        await self.repository.replace_all(list(entries.values()))
        return sorted(entries.values(), key=lambda e: e.order)

    # -- internals --------------------------------------------------------- #
    @staticmethod
    def _apply(entries: list[SoftwareEntry], query: CatalogQuery) -> list[SoftwareEntry]:
        wanted_tags = {t.casefold() for t in query.tags if t.strip()}
        search = query.search.strip().casefold()
        result: list[SoftwareEntry] = []
        for entry in entries:
            if query.enabled_only and not entry.enabled:
                continue
            if query.category and entry.category.casefold() != query.category.casefold():
                continue
            tag_names = {t.casefold() for t in entry.normalized_tags()}
            if wanted_tags:
                if query.match_all_tags:
                    if not wanted_tags.issubset(tag_names):
                        continue
                elif not wanted_tags & tag_names:
                    continue
            if search and search not in _searchable(entry):
                continue
            result.append(entry)
        return _sort(result, query.sort)


def _searchable(entry: SoftwareEntry) -> str:
    return " ".join([entry.name, entry.description, entry.category, *entry.tags]).casefold()


def _sort(entries: list[SoftwareEntry], sort: str) -> list[SoftwareEntry]:
    if sort == "name":
        return sorted(entries, key=lambda e: (e.name.casefold(), e.id))
    if sort == "recent":
        return sorted(entries, key=lambda e: (-e.order, e.name.casefold()))
    return sorted(entries, key=lambda e: (e.order, e.name.casefold(), e.id))


def slugify(name: str) -> str:
    """Build an id from a name.

    Non-ASCII names (e.g. Chinese) reduce to an empty slug, so fall back to a
    short deterministic hash to keep ids unique and stable.
    """
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", name.strip()).strip("-._").lower()
    slug = slug[:64]
    if slug:
        return slug
    digest = hashlib.sha1(name.strip().encode("utf-8")).hexdigest()[:10]
    return f"e-{digest}"


def validate_entry(entry: SoftwareEntry) -> None:
    """Raise :class:`ValidationError` when an entry is not acceptable."""
    if not entry.id or not ID_PATTERN.match(entry.id):
        raise ValidationError(
            "Invalid entry id: use letters, digits, '.', '_' or '-' (max 64 chars)",
            field="id",
        )
    if not entry.name.strip():
        raise ValidationError("Entry name must not be empty", field="name")
    if len(entry.name) > 80:
        raise ValidationError("Entry name is too long (max 80 chars)", field="name")
    if entry.url and not entry.url.startswith(("http://", "https://")):
        raise ValidationError("Entry url must start with http:// or https://", field="url")
    if entry.color and not COLOR_PATTERN.match(entry.color):
        raise ValidationError("Entry color must be a #rgb or #rrggbb value", field="color")
    if len(entry.tags) > MAX_TAGS:
        raise ValidationError(f"Too many tags (max {MAX_TAGS})", field="tags")
    for tag in entry.tags:
        if not tag.strip():
            raise ValidationError("Tags must not be empty", field="tags")
        if len(tag) > MAX_TAG_LENGTH:
            raise ValidationError(f"Tag is too long (max {MAX_TAG_LENGTH})", field="tags")

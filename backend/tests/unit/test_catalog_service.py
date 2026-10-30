"""Software catalog service: filtering, tags, validation."""

from __future__ import annotations

import pytest

from lightpanel.domain.errors import ConflictError, NotFoundError, ValidationError
from lightpanel.domain.models import SoftwareEntry
from lightpanel.services.catalog_service import (
    CatalogQuery,
    CatalogService,
    slugify,
    validate_entry,
)


async def test_list_returns_all_entries(catalog_service):
    entries = await catalog_service.list_entries()
    assert [e.id for e in entries] == ["alpha", "beta", "gamma"]


async def test_filter_by_single_tag(catalog_service):
    entries = await catalog_service.list_entries(CatalogQuery(tags=("ops",)))
    assert {e.id for e in entries} == {"alpha", "beta"}


async def test_filter_by_all_tags(catalog_service):
    entries = await catalog_service.list_entries(CatalogQuery(tags=("ops", "media"), match_all_tags=True))
    assert {e.id for e in entries} == {"beta"}


async def test_filter_by_category_and_search(catalog_service):
    entries = await catalog_service.list_entries(CatalogQuery(search="second"))
    assert [e.id for e in entries] == ["beta"]


async def test_enabled_only_hides_disabled(catalog_service):
    entries = await catalog_service.list_entries(CatalogQuery(enabled_only=True))
    assert "gamma" not in {e.id for e in entries}


async def test_sort_by_name(catalog_service):
    entries = await catalog_service.list_entries(CatalogQuery(sort="name"))
    assert [e.name for e in entries] == ["Alpha", "Beta", "Gamma"]


async def test_tag_summary_is_sorted_by_count_then_name(catalog_service):
    page = await catalog_service.page()
    assert [(t.name, t.count) for t in page.tags] == [("media", 2), ("ops", 2), ("监控", 1)]


async def test_create_and_get(catalog_service):
    entry = await catalog_service.create(
        SoftwareEntry(id="delta", name="Delta", url="https://delta.local", tags=["new"])
    )
    assert (await catalog_service.get("delta")).name == "Delta"
    assert entry.id == "delta"


async def test_create_duplicate_conflicts(catalog_service):
    with pytest.raises(ConflictError):
        await catalog_service.create(SoftwareEntry(id="alpha", name="dup", url=""))


async def test_update_missing_raises_not_found(catalog_service):
    with pytest.raises(NotFoundError):
        await catalog_service.update(SoftwareEntry(id="ghost", name="Ghost", url=""))


async def test_delete(catalog_service):
    await catalog_service.delete("beta")
    with pytest.raises(NotFoundError):
        await catalog_service.get("beta")
    with pytest.raises(NotFoundError):
        await catalog_service.delete("beta")


async def test_set_tags(catalog_service):
    entry = await catalog_service.set_tags("alpha", ["x", "y"])
    assert entry.tags == ["x", "y"]
    with pytest.raises(ValidationError):
        await catalog_service.set_tags("alpha", ["  "])


async def test_reorder(catalog_service):
    entries = await catalog_service.reorder(["gamma", "beta", "alpha"])
    assert [e.id for e in entries] == ["gamma", "beta", "alpha"]
    with pytest.raises(NotFoundError):
        await catalog_service.reorder(["ghost"])


async def test_tags_are_normalized_and_deduplicated(catalog_service):
    entry = await catalog_service.set_tags("alpha", ["Ops", "ops", " ops "])
    assert entry.normalized_tags() == ["ops"]


def test_validate_entry_rejects_bad_id():
    with pytest.raises(ValidationError):
        validate_entry(SoftwareEntry(id="bad id!", name="x", url=""))


def test_validate_entry_rejects_bad_url():
    with pytest.raises(ValidationError):
        validate_entry(SoftwareEntry(id="ok", name="x", url="ftp://x"))


def test_validate_entry_rejects_bad_color():
    with pytest.raises(ValidationError):
        validate_entry(SoftwareEntry(id="ok", name="x", url="", color="blue"))


def test_validate_entry_rejects_too_many_tags():
    with pytest.raises(ValidationError):
        validate_entry(SoftwareEntry(id="ok", name="x", url="", tags=[f"t{i}" for i in range(30)]))


def test_slugify_ascii():
    assert slugify("Hello World!") == "hello-world"


def test_slugify_non_ascii_falls_back_to_hash():
    slug = slugify("中文面板")
    assert slug.startswith("e-")
    validate_entry(SoftwareEntry(id=slug, name="中文面板", url=""))


async def test_service_works_with_any_repository():
    """Swapping the repository implementation needs no service change."""
    from lightpanel.adapters.catalog.memory_repository import InMemoryCatalogRepository

    service = CatalogService(InMemoryCatalogRepository())
    assert await service.list_entries() == []

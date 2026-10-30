"""Software catalog (软件标签) endpoints."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query, status

from ..dependencies import CatalogDep
from ..schemas import (
    CatalogPageOut,
    ReorderIn,
    SoftwareEntryIn,
    SoftwareEntryOut,
    TagOut,
    TagsUpdateIn,
    catalog_query_from_params,
)

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("", response_model=CatalogPageOut, summary="软件目录 + 标签统计")
async def list_entries(
    service: CatalogDep,
    tags: str = Query("", description="逗号分隔的标签列表"),
    match_all: bool = Query(False, description="true 表示需同时命中所有标签"),
    category: str = "",
    search: str = "",
    enabled_only: bool = False,
    sort: Literal["order", "name", "recent"] = "order",
):
    query = catalog_query_from_params(
        tags=tags,
        match_all=match_all,
        category=category,
        search=search,
        enabled_only=enabled_only,
        sort=sort,
    )
    page = await service.page(query)
    return CatalogPageOut(
        entries=[SoftwareEntryOut.from_domain(e) for e in page.entries],
        tags=[TagOut(name=t.name, count=t.count) for t in page.tags],
        total=page.total,
    )


@router.get("/tags", response_model=list[TagOut], summary="全部标签及数量")
async def list_tags(service: CatalogDep):
    return [TagOut(name=t.name, count=t.count) for t in await service.tags()]


@router.get("/entries/{entry_id}", response_model=SoftwareEntryOut, summary="查询单个软件条目")
async def get_entry(entry_id: str, service: CatalogDep):
    return SoftwareEntryOut.from_domain(await service.get(entry_id))


@router.post(
    "/entries",
    response_model=SoftwareEntryOut,
    status_code=status.HTTP_201_CREATED,
    summary="新增软件条目",
)
async def create_entry(payload: SoftwareEntryIn, service: CatalogDep):
    entry = await service.create(payload.to_domain())
    return SoftwareEntryOut.from_domain(entry)


@router.put("/entries/{entry_id}", response_model=SoftwareEntryOut, summary="更新软件条目")
async def update_entry(entry_id: str, payload: SoftwareEntryIn, service: CatalogDep):
    entry = payload.to_domain()
    entry.id = entry_id
    return SoftwareEntryOut.from_domain(await service.update(entry))


@router.delete(
    "/entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除软件条目"
)
async def delete_entry(entry_id: str, service: CatalogDep):
    await service.delete(entry_id)
    return None


@router.put("/entries/{entry_id}/tags", response_model=SoftwareEntryOut, summary="覆盖条目标签")
async def set_tags(entry_id: str, payload: TagsUpdateIn, service: CatalogDep):
    entry = await service.set_tags(entry_id, payload.tags)
    return SoftwareEntryOut.from_domain(entry)


@router.post("/reorder", response_model=list[SoftwareEntryOut], summary="按给定顺序重排条目")
async def reorder(payload: ReorderIn, service: CatalogDep):
    entries = await service.reorder(payload.ids)
    return [SoftwareEntryOut.from_domain(e) for e in entries]

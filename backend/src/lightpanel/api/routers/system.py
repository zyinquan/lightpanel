"""System status endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Query

from ..dependencies import SystemDep
from ..schemas import SampleOut, SystemOut

router = APIRouter(prefix="/system", tags=["system"])


@router.get("", response_model=SystemOut, summary="当前服务器状态快照")
async def snapshot(service: SystemDep, force: bool = Query(False, description="跳过缓存重新采集")):
    return SystemOut.from_domain(await service.snapshot(force=force))


@router.get("/history", response_model=list[SampleOut], summary="最近的 CPU / 内存采样")
async def history(service: SystemDep):
    return [SampleOut.from_domain(sample) for sample in service.history()]


@router.post("/invalidate", summary="丢弃缓存快照")
async def invalidate(service: SystemDep):
    service.invalidate()
    return {"ok": True}

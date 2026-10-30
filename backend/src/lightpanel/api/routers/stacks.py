"""Docker Compose stack endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from ...domain.errors import ValidationError
from ...services.stack_service import StackAction
from ..dependencies import StacksDep
from ..schemas import (
    CommandResultOut,
    EngineStatusOut,
    StackActionIn,
    StackActionOut,
    StackOut,
)

router = APIRouter(prefix="/stacks", tags=["stacks"])

ACTIONS = "|".join(a.value for a in StackAction)


@router.get("/status", response_model=EngineStatusOut, summary="Compose 引擎可用性")
async def status_endpoint(service: StacksDep):
    return EngineStatusOut(**await service.status())


@router.get("", response_model=list[StackOut], summary="Compose 项目列表")
async def list_stacks(service: StacksDep, search: str = ""):
    stacks = await service.list_stacks(search=search)
    return [StackOut.from_domain(s) for s in stacks]


@router.get("/{name}", response_model=StackOut, summary="Compose 项目详情")
async def get_stack(name: str, service: StacksDep):
    return StackOut.from_domain(await service.get(name))


@router.post("/{name}/{action}", response_model=StackActionOut, summary=f"Compose 操作 ({ACTIONS})")
async def stack_action(
    name: str, action: str, service: StacksDep, payload: StackActionIn | None = None
):
    try:
        normalized = StackAction(action.lower())
    except ValueError as exc:
        raise ValidationError(f"Unsupported stack action: {action}") from exc
    extra_args = payload.extra_args if payload else []
    result, stack = await service.act(name, normalized, extra_args=extra_args)
    return StackActionOut(
        stack=StackOut.from_domain(stack), result=CommandResultOut.from_domain(result)
    )

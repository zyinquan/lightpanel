"""Container endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Query

from ...domain.errors import ValidationError
from ...domain.models import CommandResult
from ...services.container_service import ContainerAction
from ..dependencies import ContainersDep
from ..schemas import (
    ContainerActionIn,
    ContainerActionOut,
    ContainerOut,
    EngineStatusOut,
    LogsOut,
)

router = APIRouter(prefix="/containers", tags=["containers"])

ACTIONS = "|".join(a.value for a in ContainerAction)


@router.get("/status", response_model=EngineStatusOut, summary="Docker 引擎可用性与容器数量")
async def status_endpoint(service: ContainersDep):
    return EngineStatusOut(**await service.status())


@router.get("", response_model=list[ContainerOut], summary="容器列表")
async def list_containers(
    service: ContainersDep,
    include_stopped: bool = True,
    search: str = "",
    project: str = "",
    state: str = "",
):
    containers = await service.list_containers(
        include_stopped=include_stopped, search=search, project=project, state=state
    )
    return [ContainerOut.from_domain(c) for c in containers]


@router.get("/{container_id}", response_model=ContainerOut, summary="容器详情")
async def get_container(container_id: str, service: ContainersDep):
    return ContainerOut.from_domain(await service.get(container_id))


@router.post(
    "/{container_id}/{action}",
    response_model=ContainerActionOut,
    summary=f"容器生命周期操作 ({ACTIONS})",
)
async def container_action(
    container_id: str,
    action: str,
    service: ContainersDep,
    payload: ContainerActionIn | None = None,
):
    timeout = payload.timeout if payload else None
    try:
        normalized = ContainerAction(action.lower())
    except ValueError as exc:
        raise ValidationError(f"Unsupported container action: {action}") from exc
    container = await service.act(container_id, normalized, timeout=timeout)
    result = CommandResult.success(
        ("container", action.lower(), container_id), stdout=f"{action} ok"
    )
    return ContainerActionOut(
        container=ContainerOut.from_domain(container), result=_out(result)
    )


@router.get("/{container_id}/logs", response_model=LogsOut, summary="容器日志")
async def container_logs(
    container_id: str,
    service: ContainersDep,
    tail: int = Query(200, ge=1, le=10000),
):
    content = await service.logs(container_id, tail=tail)
    return LogsOut(container=container_id, tail=tail, content=content)


def _out(result: CommandResult):
    from ..schemas import CommandResultOut

    return CommandResultOut.from_domain(result)

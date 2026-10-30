"""Command registry + custom command execution."""

from __future__ import annotations

from fastapi import APIRouter

from ...domain.models import CommandContext
from ..dependencies import CommandsDep
from ..schemas import (
    AdHocCommandIn,
    CommandOut,
    CommandPreviewOut,
    CommandResultOut,
    CommandRunIn,
)

router = APIRouter(prefix="/commands", tags=["commands"])


@router.get("", response_model=list[CommandOut], summary="已注册命令列表")
async def list_commands(service: CommandsDep, target: str | None = None):
    return [CommandOut.from_domain(d) for d in service.list_definitions(target)]


@router.get("/{command_id}", response_model=CommandOut, summary="命令定义详情")
async def get_command(command_id: str, service: CommandsDep):
    return CommandOut.from_domain(service.get(command_id))


@router.post("/{command_id}/preview", response_model=CommandPreviewOut, summary="渲染但不执行")
async def preview(command_id: str, payload: CommandRunIn, service: CommandsDep):
    argv = await service.preview(command_id, target_id=payload.target_id)
    return CommandPreviewOut(id=command_id, argv=argv)


@router.post("/{command_id}/run", response_model=CommandResultOut, summary="执行已注册命令")
async def run(command_id: str, payload: CommandRunIn, service: CommandsDep):
    result = await service.run(
        command_id,
        target_id=payload.target_id,
        extra_args=payload.extra_args,
        timeout=payload.timeout,
    )
    return CommandResultOut.from_domain(result)


@router.post("/run-adhoc", response_model=CommandResultOut, summary="执行一次性自定义命令")
async def run_ad_hoc(payload: AdHocCommandIn, service: CommandsDep):
    result = await service.run_argv(
        payload.argv,
        cwd=payload.cwd,
        timeout=payload.timeout,
        context=CommandContext.of(**payload.context),
    )
    return CommandResultOut.from_domain(result)

"""Authentication endpoints (public)."""

from __future__ import annotations

from fastapi import APIRouter, Response

from ...domain.errors import AuthenticationError
from ..dependencies import ContainerDep
from ..schemas import AuthStatusOut, LoginIn

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/status", response_model=AuthStatusOut, summary="鉴权开关与当前状态")
async def status(container: ContainerDep):
    auth = container.auth
    return AuthStatusOut(enabled=auth.enabled, authenticated=not auth.enabled)


@router.post("/login", summary="校验 token 并写入 Cookie")
async def login(payload: LoginIn, response: Response, container: ContainerDep):
    auth = container.auth
    if not auth.enabled:
        return {"ok": True, "enabled": False}
    if not auth.verify(payload.token):
        raise AuthenticationError("Invalid token")
    response.set_cookie(
        key=auth.settings.cookie_name,
        value=payload.token,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 7,
    )
    return {"ok": True, "enabled": True}


@router.post("/logout", summary="清除 Cookie")
async def logout(response: Response, container: ContainerDep):
    response.delete_cookie(container.auth.settings.cookie_name)
    return {"ok": True}

"""Authentication endpoints (public)."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

from ...domain.errors import AuthenticationError
from ..dependencies import ContainerDep
from ..schemas import AuthStatusOut, LoginIn, LoginOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/status", response_model=AuthStatusOut, summary="鉴权开关与当前状态")
async def status(request: Request, container: ContainerDep):
    auth = container.auth
    if not auth.enabled:
        return AuthStatusOut(enabled=False, authenticated=True)
    # 带上 Cookie / Header 时也要回答「这一次请求是否已通过」，
    # 否则前端每次刷新都会退回登录页（token 存着却没被承认）。
    return AuthStatusOut(enabled=True, authenticated=auth.verify(auth.extract(request)))


@router.post("/login", response_model=LoginOut, summary="校验 token 并写入 Cookie")
async def login(payload: LoginIn, response: Response, container: ContainerDep):
    auth = container.auth
    if not auth.enabled:
        return LoginOut(enabled=False, authenticated=True)
    if not auth.verify(payload.token):
        raise AuthenticationError("Invalid token")
    response.set_cookie(
        key=auth.settings.cookie_name,
        value=payload.token,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 7,
    )
    return LoginOut(enabled=True, authenticated=True)


@router.post("/logout", response_model=AuthStatusOut, summary="清除 Cookie")
async def logout(response: Response, container: ContainerDep):
    auth = container.auth
    response.delete_cookie(auth.settings.cookie_name)
    return AuthStatusOut(enabled=auth.enabled, authenticated=not auth.enabled)

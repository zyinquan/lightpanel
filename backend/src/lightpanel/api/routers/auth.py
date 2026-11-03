"""Authentication endpoints (public)."""

from __future__ import annotations

import os

from fastapi import APIRouter, Request, Response

from ...config import persist_security_token
from ...domain.errors import AuthenticationError, ValidationError
from ..dependencies import ContainerDep
from ..schemas import AuthStatusOut, LoginIn, LoginOut, PasswordChangeIn

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


@router.post("/password", response_model=LoginOut, summary="修改登录密码（即 API Token）")
async def change_password(
    payload: PasswordChangeIn,
    response: Response,
    container: ContainerDep,
) -> LoginOut:
    """验证当前密码后更换令牌：内存即时生效，并写回配置文件持久化。"""
    auth = container.auth
    if not auth.enabled:
        raise ValidationError(
            "面板未启用鉴权，请先在配置中设置 security.enabled: true 并提供 api_token"
        )
    if os.environ.get("LIGHTPANEL_SECURITY__API_TOKEN"):
        raise ValidationError(
            "api_token 由环境变量 LIGHTPANEL_SECURITY__API_TOKEN 提供，"
            "优先级高于配置文件，无法在面板中修改"
        )
    if not auth.verify(payload.current):
        raise AuthenticationError("当前密码不正确")

    new_token = payload.new.strip()
    if len(new_token) < len(payload.new) or new_token != payload.new:
        raise ValidationError("新密码不能包含首尾空白字符")
    if new_token == payload.current:
        raise ValidationError("新密码不能与当前密码相同")

    auth.update_token(new_token)
    container.config.security.api_token = new_token

    config_path = container.config.config_path
    if config_path:
        persist_security_token(config_path, new_token)
    # token_file 模式下 api_token 现在已写入/将写入配置并优先生效；
    # 没有配置文件（纯环境/token_file 启动）则只改内存，重启后回到原值。

    response.set_cookie(
        key=auth.settings.cookie_name,
        value=new_token,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 7,
    )
    return LoginOut(enabled=True, authenticated=True)

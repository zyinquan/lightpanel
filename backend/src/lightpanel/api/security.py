"""Optional single-token authentication.

LightPanel can start and stop containers, so exposing it unauthenticated on a
routable network is a bad idea. When ``security.enabled`` is true, every
protected route requires a token supplied via header, cookie or query string.
"""

from __future__ import annotations

import hmac

from fastapi import Request

from ..config import SecurityConfig
from ..domain.errors import AuthenticationError

PUBLIC_PATH_SUFFIXES = ("/api/health", "/api/auth/status", "/api/auth/login")


class TokenAuth:
    def __init__(self, settings: SecurityConfig) -> None:
        self.settings = settings
        self.token = settings.resolved_token()

    @property
    def enabled(self) -> bool:
        return self.settings.enabled and bool(self.token)

    def extract(self, request: Request) -> str:
        header = request.headers.get(self.settings.header_name)
        if header:
            return header.strip()
        cookie = request.cookies.get(self.settings.cookie_name)
        if cookie:
            return cookie.strip()
        query = request.query_params.get(self.settings.query_param)
        if query:
            return query.strip()
        return ""

    def is_public(self, request: Request) -> bool:
        path = request.url.path.rstrip("/")
        if request.method == "OPTIONS":
            return True
        if path.endswith(PUBLIC_PATH_SUFFIXES):
            return True
        return path in {"/docs", "/redoc", "/openapi.json", "/"}

    async def __call__(self, request: Request) -> None:
        if not self.enabled:
            request.state.authenticated = False
            return
        if self.is_public(request):
            request.state.authenticated = self.verify(self.extract(request))
            return
        if not self.verify(self.extract(request)):
            raise AuthenticationError("Invalid or missing API token")

    def verify(self, candidate: str) -> bool:
        if not self.enabled:
            return True
        if not candidate:
            return False
        return hmac.compare_digest(candidate, self.token)

    def update_token(self, token: str) -> None:
        """运行中替换令牌；下一次请求即刻生效，无需重启。"""
        self.token = token

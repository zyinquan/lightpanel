"""Compose backend that executes on the host agent.

Why this exists
---------------
``docker compose`` resolves a relative bind mount (``./src:/app``) against the
filesystem the CLI runs on. When the panel itself runs in a container, that
filesystem is the *container's*, and the path it derives gets handed to the host
daemon — which happily creates an empty directory instead of using the user's
code. The failure is silent: the stack reports ``up``, the container runs, and
the source code is simply missing.

Delegating to ``lightpanel-agent`` on the host removes the mismatch entirely:
same filesystem as the daemon, so paths mean what the user wrote.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from typing import Any

import httpx

from ...domain.errors import EngineUnavailableError, ValidationError
from ...domain.models import CommandResult, StackInfo, StackStatus

logger = logging.getLogger(__name__)


class AgentComposeBackend:
    """Runs compose through ``lightpanel-agent``'s ``/compose/*`` endpoints."""

    def __init__(
        self,
        base_url: str,
        *,
        token: str = "",
        timeout: float = 600.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._token = token
        self._timeout = timeout
        self._transport = transport

    @property
    def name(self) -> str:
        return "docker-compose@agent"

    # -- backend protocol -------------------------------------------------- #
    async def is_available(self) -> bool:
        try:
            async with self._client(min(5.0, self._timeout)) as client:
                response = await client.get(self._url("/health"), headers=self._headers())
                response.raise_for_status()
                payload: Any = response.json()
        except httpx.HTTPError as exc:
            logger.debug("compose agent 不可用：%s", exc)
            return False
        except ValueError:
            return False
        return bool(payload.get("compose")) if isinstance(payload, Mapping) else False

    async def list_projects(self) -> list[StackInfo]:
        try:
            async with self._client(self._timeout) as client:
                response = await client.get(self._url("/compose/stacks"), headers=self._headers())
                response.raise_for_status()
                payload: Any = response.json()
        except httpx.HTTPStatusError as exc:
            raise self._status_error(exc) from exc
        except httpx.HTTPError as exc:
            raise self._unreachable(exc) from exc
        except ValueError as exc:
            raise EngineUnavailableError(
                f"宿主机代理返回的不是合法 JSON：{exc}", url=self.base_url
            ) from exc

        if not isinstance(payload, list):
            raise EngineUnavailableError("宿主机代理的栈列表格式不正确", url=self.base_url)
        return [self._to_stack(item) for item in payload if isinstance(item, Mapping)]

    async def act(
        self,
        stack: StackInfo,
        action: str,
        *,
        extra_args: Sequence[str] = (),
    ) -> CommandResult:
        body = {
            "name": stack.name,
            "action": action,
            "config_files": stack.config_files,
            "working_dir": stack.working_dir,
            "extra_args": list(extra_args),
        }
        try:
            async with self._client(self._timeout) as client:
                response = await client.post(
                    self._url("/compose/action"), json=body, headers=self._headers()
                )
                response.raise_for_status()
                payload: Any = response.json()
        except httpx.HTTPStatusError as exc:
            raise self._status_error(exc) from exc
        except httpx.HTTPError as exc:
            raise self._unreachable(exc) from exc
        except ValueError as exc:
            raise EngineUnavailableError(
                f"宿主机代理返回的不是合法 JSON：{exc}", url=self.base_url
            ) from exc

        if not isinstance(payload, Mapping):
            raise EngineUnavailableError("宿主机代理的返回格式不正确", url=self.base_url)
        return _to_result(payload)

    # -- internals --------------------------------------------------------- #
    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"} if self._token else {}

    def _client(self, timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=timeout, transport=self._transport)

    def _unreachable(self, exc: Exception) -> EngineUnavailableError:
        return EngineUnavailableError(
            f"连不上宿主机代理（{exc}），请确认已启动 lightpanel-agent 且 compose.agent_url 指向它",
            url=self.base_url,
        )

    def _status_error(self, exc: httpx.HTTPStatusError) -> Exception:
        detail = _detail(exc.response)
        if exc.response.status_code == 401:
            return EngineUnavailableError(
                "宿主机代理要求鉴权，请检查 compose.agent_token", url=self.base_url
            )
        if exc.response.status_code in (400, 422):
            return ValidationError(detail or "宿主机代理拒绝了该操作", url=self.base_url)
        if exc.response.status_code == 404:
            return EngineUnavailableError(
                "宿主机代理没有 compose 端点，请升级 lightpanel-agent", url=self.base_url
            )
        return EngineUnavailableError(
            f"宿主机代理返回 {exc.response.status_code}：{detail}", url=self.base_url
        )

    @staticmethod
    def _to_stack(item: Mapping[str, Any]) -> StackInfo:
        raw_status = str(item.get("status") or "unknown")
        try:
            status = StackStatus(raw_status)
        except ValueError:
            status = StackStatus.UNKNOWN
        discovered = item.get("discovered_paths") or []
        return StackInfo(
            name=str(item.get("name") or ""),
            config_files=str(item.get("config_files") or ""),
            working_dir=str(item.get("working_dir") or ""),
            status=status,
            discovered_paths=[str(p) for p in discovered if p],
        )


def _to_result(payload: Mapping[str, Any]) -> CommandResult:
    argv = payload.get("argv") or []
    return CommandResult(
        argv=tuple(str(a) for a in argv),
        exit_code=int(payload.get("exit_code") or 0),
        stdout=str(payload.get("stdout") or ""),
        stderr=str(payload.get("stderr") or ""),
        duration_ms=int(payload.get("duration_ms") or 0),
        ok=bool(payload.get("ok")),
    )


def _detail(response: httpx.Response) -> str:
    try:
        payload: Any = response.json()
    except ValueError:
        return response.text[:200]
    if isinstance(payload, Mapping):
        detail = payload.get("message") or payload.get("detail")
        return str(detail) if detail else ""
    return ""

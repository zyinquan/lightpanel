"""Container engine backed by the Docker Engine HTTP API.

Talks to ``/var/run/docker.sock`` (or a TCP endpoint) directly, so LightPanel
does not need the ``docker`` CLI installed for container-level operations.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

import httpx

from ...config import DockerConfig
from ...domain.errors import EngineUnavailableError, NotFoundError
from ...domain.models import ContainerInfo, ContainerState, ContainerUsage, PortBinding

# 容器名/ID 只允许 Docker 认可的字符；其它输入一律拒绝，避免拼进 URL 后打到
# 别的 Docker API 端点（例如 "../../version" 之类）。
_SAFE_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")

_SOCKET_PERMISSION_HINT = (
    "面板进程读不到 docker.sock：容器内用户与宿主机 docker 组的 GID 不一致。"
    "用 DOCKER_GID=$(stat -c '%g' /var/run/docker.sock) docker compose up -d 重启面板，"
    '或以 user: "0:0" 运行。'
)


def _is_permission_denied(exc: BaseException) -> bool:
    """沿 ``__cause__`` / ``__context__`` 找 ``PermissionError``。

    httpx 会把 socket 的 EACCES 包成 ``ConnectError``，只看最外层类型会漏掉，
    于是 "socket 不可读" 被误报成 "daemon 没启动" —— 两者修法完全不同。
    """
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, PermissionError):
            return True
        current = current.__cause__ or current.__context__
    return False


def _unreachable(exc: Exception) -> EngineUnavailableError:
    """把连接失败翻译成带修复提示的错误。"""
    if _is_permission_denied(exc):
        return EngineUnavailableError(
            "读不到 Docker socket（权限不足）",
            reason=str(exc),
            hint=_SOCKET_PERMISSION_HINT,
        )
    return EngineUnavailableError("Docker daemon unreachable", reason=str(exc))


def _safe_reference(value: str) -> str:
    reference = str(value or "").strip()
    if not _SAFE_REFERENCE.match(reference):
        raise NotFoundError(f"Invalid container reference: {value!r}")
    return reference


class DockerApiContainerEngine:
    """Implements the :class:`ContainerEngine` port against the Docker API."""

    def __init__(
        self, settings: DockerConfig | None = None, *, transport: Any | None = None
    ) -> None:
        self.settings = settings or DockerConfig()
        self._client: httpx.AsyncClient | None = None
        self._injected_transport = transport

    # -- lifecycle --------------------------------------------------------- #
    @property
    def name(self) -> str:
        return "docker-api"

    @property
    def base_url(self) -> str:
        if self.settings.host:
            return self.settings.host.rstrip("/")
        return "http://localhost"

    def _api_url(self) -> str:
        return f"{self.base_url}/{self.settings.api_version.strip('/')}"

    def _build_client(self) -> httpx.AsyncClient:
        if self._injected_transport is not None:
            return httpx.AsyncClient(transport=self._injected_transport, base_url=self._api_url())
        if self.settings.host:
            return httpx.AsyncClient(base_url=self._api_url(), timeout=self.settings.timeout)
        return httpx.AsyncClient(
            transport=httpx.AsyncHTTPTransport(uds=self.settings.socket),
            base_url=self._api_url(),
            timeout=self.settings.timeout,
        )

    async def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = self._build_client()
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # -- port implementation ----------------------------------------------- #
    async def is_available(self) -> bool:
        try:
            response = await (await self.client()).get("/version")
        except (httpx.HTTPError, OSError):
            return False
        return response.status_code < 500

    async def list_containers(self, *, include_stopped: bool = True) -> list[ContainerInfo]:
        all_flag = "1" if include_stopped else "0"
        payload = await self._get("/containers/json", params={"all": all_flag})
        containers = [self._parse_container(row) for row in payload or []]
        if not include_stopped:
            containers = [c for c in containers if c.state.is_active]
        return sorted(containers, key=lambda c: c.name.lstrip("/"))

    async def get_container(self, container_id: str) -> ContainerInfo:
        reference = _safe_reference(container_id)
        payload = await self._get(f"/containers/{reference}/json")
        if not isinstance(payload, dict):
            raise NotFoundError(f"Container not found: {container_id}")
        return self._parse_container(
            {
                "Id": payload.get("Id", container_id),
                "Names": [payload.get("Name", container_id)],
                "Image": (payload.get("Config") or {}).get("Image", ""),
                "Command": " ".join((payload.get("Config") or {}).get("Cmd") or []),
                "Created": payload.get("Created", ""),
                "State": (payload.get("State") or {}).get("Status", ""),
                "Status": (payload.get("State") or {}).get("Status", ""),
                "Ports": self._ports_from_inspect(payload),
                "Labels": (payload.get("Config") or {}).get("Labels") or {},
            }
        )

    async def start(self, container_id: str) -> None:
        await self._post(f"/containers/{_safe_reference(container_id)}/start")

    async def stop(self, container_id: str, *, timeout: int | None = None) -> None:
        params = {"t": str(timeout)} if timeout is not None else None
        await self._post(f"/containers/{_safe_reference(container_id)}/stop", params=params)

    async def restart(self, container_id: str, *, timeout: int | None = None) -> None:
        params = {"t": str(timeout)} if timeout is not None else None
        await self._post(
            f"/containers/{_safe_reference(container_id)}/restart", params=params
        )

    async def remove(self, container_id: str, *, force: bool = False) -> None:
        await self._delete(
            f"/containers/{_safe_reference(container_id)}",
            params={"force": "1" if force else "0"},
        )

    async def logs(self, container_id: str, *, tail: int = 200) -> str:
        reference = _safe_reference(container_id)
        client = await self.client()
        try:
            response = await client.get(
                f"/containers/{reference}/logs",
                params={"stdout": "1", "stderr": "1", "tail": str(tail)},
            )
        except (httpx.HTTPError, OSError) as exc:
            raise _unreachable(exc) from exc
        if response.status_code == 404:
            raise NotFoundError(f"Container not found: {container_id}")
        if response.status_code >= 400:
            raise EngineUnavailableError(
                "Docker API error", status=response.status_code, body=response.text[:500]
            )
        return _decode_log_stream(response.content)

    async def usage(self, container_id: str) -> ContainerUsage:
        """单次采样容器 CPU / 内存。

        ``stream=false`` 会让 daemon 等一个采样周期再返回，这样
        ``precpu_stats`` 才有效；改用 ``one-shot=true`` 虽然快，但
        ``system_cpu_usage`` 差值会退化成整机累计值，算出的百分比恒接近 0。
        """
        reference = _safe_reference(container_id)
        payload = await self._get(
            f"/containers/{reference}/stats", params={"stream": "false"}
        )
        if not isinstance(payload, dict):
            raise EngineUnavailableError(f"No stats payload for container {container_id}")
        return _parse_usage(container_id, payload)

    # -- helpers ----------------------------------------------------------- #
    async def _get(self, path: str, params: dict[str, str] | None = None) -> Any:
        client = await self.client()
        try:
            response = await client.get(path, params=params)
        except (httpx.HTTPError, OSError) as exc:
            raise _unreachable(exc) from exc
        return self._unwrap(response, path)

    async def _post(self, path: str, params: dict[str, str] | None = None) -> None:
        client = await self.client()
        try:
            response = await client.post(path, params=params)
        except (httpx.HTTPError, OSError) as exc:
            raise _unreachable(exc) from exc
        self._unwrap(response, path)

    async def _delete(self, path: str, params: dict[str, str] | None = None) -> None:
        client = await self.client()
        try:
            response = await client.delete(path, params=params)
        except (httpx.HTTPError, OSError) as exc:
            raise _unreachable(exc) from exc
        self._unwrap(response, path)

    @staticmethod
    def _unwrap(response: httpx.Response, path: str) -> Any:
        if response.status_code == 404:
            raise NotFoundError(f"Docker resource not found: {path}")
        if response.status_code >= 400:
            raise EngineUnavailableError(
                "Docker API error", status=response.status_code, body=response.text[:500]
            )
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            return None

    @staticmethod
    def _parse_container(row: dict[str, Any]) -> ContainerInfo:
        names = row.get("Names") or []
        name = str(names[0]).lstrip("/") if names else str(row.get("Id", ""))[:12]
        ports = [
            PortBinding(
                host_ip=str(p.get("IP") or "0.0.0.0"),
                host_port=str(p.get("PublicPort") or ""),
                container_port=str(p.get("PrivatePort") or ""),
                protocol=str(p.get("Type") or "tcp"),
            )
            for p in row.get("Ports") or []
        ]
        return ContainerInfo(
            id=str(row.get("Id", "")),
            name=name,
            image=str(row.get("Image", "")),
            state=ContainerState.parse(row.get("State")),
            status=str(row.get("Status", "")),
            created_at=_parse_timestamp(row.get("Created")),
            ports=ports,
            labels={str(k): str(v) for k, v in (row.get("Labels") or {}).items()},
            command=str(row.get("Command", "")),
        )

    @staticmethod
    def _ports_from_inspect(payload: dict[str, Any]) -> list[dict[str, Any]]:
        ports: list[dict[str, Any]] = []
        exposed = ((payload.get("Config") or {}).get("ExposedPorts") or {}).keys()
        bindings = ((payload.get("HostConfig") or {}).get("PortBindings") or {})
        for port in exposed:
            host_bindings = bindings.get(port) or []
            if host_bindings:
                for binding in host_bindings:
                    ports.append(
                        {
                            "IP": binding.get("HostIp") or "0.0.0.0",
                            "PublicPort": binding.get("HostPort") or "",
                            "PrivatePort": port.split("/")[0],
                            "Type": port.split("/")[-1],
                        }
                    )
            else:
                ports.append(
                    {
                        "IP": "0.0.0.0",
                        "PublicPort": "",
                        "PrivatePort": port.split("/")[0],
                        "Type": port.split("/")[-1],
                    }
                )
        return ports


def _parse_usage(container_id: str, payload: dict[str, Any]) -> ContainerUsage:
    """把 ``/containers/{id}/stats`` 的原始返回折算成百分比。

    - CPU：按 ``docker stats`` 的口径归一化到整机（除以 system delta 再乘
      在线核数），单核跑满 = 100%。
    - 内存：cgroup v1 要减掉 page cache（``stats.cache``），v2 是
      ``stats.inactive_file``；否则「刚拷完大文件」会显示占用暴涨。
    """
    cpu = payload.get("cpu_stats") or {}
    pre = payload.get("precpu_stats") or {}
    cpu_total = int((cpu.get("cpu_usage") or {}).get("total_usage") or 0)
    pre_total = int((pre.get("cpu_usage") or {}).get("total_usage") or 0)
    system_total = int(cpu.get("system_cpu_usage") or 0)
    pre_system = int(pre.get("system_cpu_usage") or 0)

    online = int(cpu.get("online_cpus") or 0)
    if online <= 0:
        online = len((cpu.get("cpu_usage") or {}).get("percpu_usage") or []) or 1

    cpu_percent = 0.0
    cpu_delta = cpu_total - pre_total
    system_delta = system_total - pre_system
    if cpu_delta > 0 and system_delta > 0:
        cpu_percent = round(cpu_delta / system_delta * online * 100, 2)

    memory = payload.get("memory_stats") or {}
    stats = memory.get("stats") or {}
    usage = int(memory.get("usage") or 0)
    reclaimable = int(stats.get("total_inactive_file") or stats.get("inactive_file") or 0)
    if not reclaimable:
        reclaimable = int(stats.get("cache") or 0)
    memory_bytes = max(usage - reclaimable, 0)

    return ContainerUsage(
        container_id=container_id,
        cpu_percent=cpu_percent,
        memory_bytes=memory_bytes,
        memory_limit_bytes=int(memory.get("limit") or 0),
    )


def _decode_log_stream(payload: bytes) -> str:
    """Decode the Docker logs payload.

    Without a TTY the daemon answers with a multiplexed stream where every frame
    starts with an 8-byte header (stream type + 3 pad bytes + big-endian length).
    Containers created with ``tty: true`` return plain text instead, so we fall
    back to the raw bytes whenever the framing does not line up.
    """
    if not payload:
        return ""
    # Containers created with ``tty: true`` return plain text: no valid stream
    # type byte can lead such a stream, so bail out immediately.
    if payload[0] not in (0, 1, 2):
        return payload.decode("utf-8", errors="replace")
    chunks: list[bytes] = []
    offset = 0
    total = len(payload)
    while offset < total:
        frame_type = payload[offset]
        if frame_type not in (0, 1, 2) or offset + 8 > total:
            chunks.append(payload[offset:])
            break
        size = int.from_bytes(payload[offset + 4 : offset + 8], "big")
        start = offset + 8
        end = start + size
        if end > total:
            # Truncated tail: keep what we can instead of dropping every frame.
            chunks.append(payload[offset:])
            break
        chunks.append(payload[start:end])
        offset = end
    return b"".join(chunks).decode("utf-8", errors="replace")


def _parse_timestamp(value: Any) -> datetime | None:
    """Docker returns either an epoch int or an RFC3339 nano-second string."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=UTC)
    text = str(value)
    try:
        # Trim nanoseconds to microseconds (Python only accepts 6 digits).
        if "." in text:
            head, _, tail = text.partition(".")
            digits = "".join(ch for ch in tail if ch.isdigit())[:6]
            text = f"{head}.{digits}" if digits else head
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    # /containers/{id}/json omits the offset; the daemon always means UTC.
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)

"""Docker Engine API adapter, exercised through an httpx MockTransport."""

from __future__ import annotations

import httpx
import pytest

from lightpanel.adapters.docker.engine import (
    DockerApiContainerEngine,
    _decode_log_stream,
    _is_permission_denied,
)
from lightpanel.config import DockerConfig
from lightpanel.domain.errors import EngineUnavailableError, NotFoundError
from lightpanel.domain.models import ContainerState

CONTAINER_ROW = {
    "Id": "a" * 64,
    "Names": ["/web"],
    "Image": "nginx:latest",
    "State": "running",
    "Status": "Up 2 hours",
    "Created": 1700000000,
    "Ports": [{"IP": "0.0.0.0", "PrivatePort": 80, "PublicPort": 8080, "Type": "tcp"}],
    "Labels": {"com.docker.compose.project": "demo"},
    "Command": "nginx -g 'daemon off;'",
}


def engine_for(handler) -> DockerApiContainerEngine:
    return DockerApiContainerEngine(
        DockerConfig(api_version="v1.44"), transport=httpx.MockTransport(handler)
    )


async def test_list_containers():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1.44/containers/json"
        return httpx.Response(200, json=[CONTAINER_ROW])

    engine = engine_for(handler)
    containers = await engine.list_containers()
    assert [c.name for c in containers] == ["web"]
    assert containers[0].state is ContainerState.RUNNING
    assert containers[0].ports[0].display() == "8080->80"
    await engine.aclose()


async def test_list_containers_hides_stopped():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["all"] == "0"
        return httpx.Response(200, json=[CONTAINER_ROW, {**CONTAINER_ROW, "State": "exited"}])

    engine = engine_for(handler)
    containers = await engine.list_containers(include_stopped=False)
    assert [c.name for c in containers] == ["web"]


async def test_lifecycle_actions_hit_the_right_endpoints():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(f"{request.method} {request.url}")
        return httpx.Response(204)

    engine = engine_for(handler)
    await engine.start("web")
    await engine.stop("web", timeout=5)
    await engine.restart("web")
    await engine.remove("web", force=True)
    assert seen == [
        "POST http://localhost/v1.44/containers/web/start",
        "POST http://localhost/v1.44/containers/web/stop?t=5",
        "POST http://localhost/v1.44/containers/web/restart",
        "DELETE http://localhost/v1.44/containers/web?force=1",
    ]


async def test_not_found_is_mapped():
    engine = engine_for(lambda request: httpx.Response(404, json={"message": "nope"}))
    with pytest.raises(NotFoundError):
        await engine.get_container("ghost")


async def test_api_error_is_mapped():
    engine = engine_for(lambda request: httpx.Response(500, text="boom"))
    with pytest.raises(EngineUnavailableError):
        await engine.list_containers()


async def test_transport_failure_is_mapped():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no daemon", request=request)

    engine = engine_for(handler)
    with pytest.raises(EngineUnavailableError):
        await engine.list_containers()
    assert await engine.is_available() is False


async def test_is_available_true():
    engine = engine_for(lambda request: httpx.Response(200, json={"Version": "27.0.1"}))
    assert await engine.is_available() is True


async def test_logs_and_inspect():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/logs"):
            return httpx.Response(200, text="hello logs")
        return httpx.Response(
            200,
            json={
                "Id": "b" * 64,
                "Name": "/db",
                "Created": "2026-01-01T10:00:00.123456789Z",
                "Config": {
                    "Image": "postgres:16",
                    "Cmd": ["postgres"],
                    "Labels": {"x": "y"},
                    "ExposedPorts": {"5432/tcp": {}},
                },
                "State": {"Status": "running"},
                "HostConfig": {"PortBindings": {"5432/tcp": [{"HostIp": "0.0.0.0", "HostPort": "5432"}]}},
            },
        )

    engine = engine_for(handler)
    assert await engine.logs("db", tail=10) == "hello logs"
    container = await engine.get_container("db")
    assert container.name == "db"
    assert container.image == "postgres:16"
    assert container.labels == {"x": "y"}
    assert container.ports[0].display() == "5432->5432"


async def test_empty_body_is_tolerated():
    engine = engine_for(lambda request: httpx.Response(204))
    assert await engine.list_containers() == []


def _frame(stream: int, payload: bytes) -> bytes:
    return bytes([stream, 0, 0, 0]) + len(payload).to_bytes(4, "big") + payload


def test_decode_log_stream_strips_frame_headers():
    body = _frame(1, b"line one\n") + _frame(2, b"oops\n") + _frame(1, b"line two\n")
    assert _decode_log_stream(body) == "line one\noops\nline two\n"


def test_decode_log_stream_passes_plain_text_through():
    # Containers with tty: true answer with an unframed byte stream.
    assert _decode_log_stream(b"raw tty output\n") == "raw tty output\n"
    assert _decode_log_stream(b"") == ""


def test_decode_log_stream_falls_back_on_truncated_frame():
    body = _frame(1, b"complete\n") + _frame(1, b"cut")[:-2]
    assert _decode_log_stream(body).startswith("complete\n")


async def test_logs_decodes_multiplexed_stream():
    body = _frame(1, b"server started\n") + _frame(2, b"warning: low disk\n")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/logs"):
            return httpx.Response(200, content=body)
        return httpx.Response(200, json=CONTAINER_ROW)

    engine = engine_for(handler)
    assert await engine.logs("web") == "server started\nwarning: low disk\n"


def test_parse_timestamp_assumes_utc_for_naive_values():
    from lightpanel.adapters.docker.engine import _parse_timestamp

    assert _parse_timestamp("2026-01-01T10:00:00.123456789Z") is not None
    naive = _parse_timestamp("2026-01-01T10:00:00.123456")
    assert naive is not None and naive.tzinfo is not None
    assert naive.utcoffset().total_seconds() == 0
    epoch = _parse_timestamp(1767225600)
    assert epoch is not None and epoch.utcoffset().total_seconds() == 0
    assert _parse_timestamp(None) is None
    assert _parse_timestamp("") is None


@pytest.mark.parametrize("bad", ["lpdemo; rm -rf /", "../version", "a b", "", "x/y/json"])
async def test_container_reference_is_validated(bad):
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        return httpx.Response(200, json=CONTAINER_ROW)

    engine = engine_for(handler)
    with pytest.raises(NotFoundError):
        await engine.get_container(bad)
    with pytest.raises(NotFoundError):
        await engine.start(bad)
    with pytest.raises(NotFoundError):
        await engine.logs(bad)


async def test_get_container_tolerates_non_object_body():
    # 空的 / 非 JSON 响应不应该以 AttributeError 冒成 500
    engine = engine_for(lambda request: httpx.Response(200, content=b""))
    with pytest.raises(NotFoundError):
        await engine.get_container("web")


async def test_socket_permission_denied_is_not_reported_as_unreachable():
    """socket 不可读与 daemon 没起来是两回事，修法完全不同。"""

    def handler(request: httpx.Request) -> httpx.Response:
        raise PermissionError(13, "Permission denied")

    engine = engine_for(handler)
    with pytest.raises(EngineUnavailableError) as caught:
        await engine.list_containers()
    error = caught.value
    assert "socket" in error.message
    assert "GID" in error.details.get("hint", "")


def test_permission_denied_is_found_behind_httpx_wrapper():
    # httpx 会把 EACCES 包进 ConnectError，只看最外层类型会漏掉
    try:
        try:
            raise PermissionError(13, "Permission denied")
        except PermissionError as exc:
            raise httpx.ConnectError("All connection attempts failed") from exc
    except httpx.ConnectError as wrapped:
        assert _is_permission_denied(wrapped) is True


async def test_generic_connection_failure_stays_unreachable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise ConnectionRefusedError(111, "Connection refused")

    engine = engine_for(handler)
    with pytest.raises(EngineUnavailableError) as caught:
        await engine.list_containers()
    assert caught.value.message == "Docker daemon unreachable"

"""宿主机 compose 链路：agent 侧服务、面板侧适配器、agent 应用端点。

背景见 ``adapters/docker/agent_compose.py``：面板跑在容器里时，本地执行
``docker compose`` 会把 ``./src:/app`` 解析成容器内路径，宿主机 docker 只能
建一个空目录顶上，容器照常起来但代码没挂上。这条链路就是为它准备的。
"""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from lightpanel.adapters.docker.agent_compose import AgentComposeBackend
from lightpanel.adapters.docker.compose_scan import scan_projects
from lightpanel.adapters.executor.fake_executor import FakeCommandExecutor
from lightpanel.agent import create_agent_app
from lightpanel.domain.errors import CommandRejectedError, EngineUnavailableError, ValidationError
from lightpanel.domain.models import StackInfo, StackStatus
from lightpanel.services.host_compose import HostComposeService


# --------------------------------------------------------------------------- #
# agent 侧：HostComposeService
# --------------------------------------------------------------------------- #
def _service(tmp_path, executor=None, **kwargs) -> HostComposeService:
    return HostComposeService(
        [str(tmp_path)],
        executor=executor or FakeCommandExecutor(),
        scanner=scan_projects,
        **kwargs,
    )


async def test_agent_up_builds_argv_and_works_in_project_dir(tmp_path):
    project = tmp_path / "web"
    project.mkdir()
    compose_file = project / "docker-compose.yml"
    compose_file.write_text("services: {}\n", encoding="utf-8")
    executor = FakeCommandExecutor()
    service = _service(tmp_path, executor)

    result = await service.act(
        "web", "up", config_files=str(compose_file), working_dir=str(project)
    )

    assert result.ok
    argv, cwd, _ = executor.calls[-1]
    # -d 必须有：compose up 默认前台，面板会一直挂着
    assert argv == ("docker", "compose", "-f", str(compose_file), "-p", "web", "up", "-d")
    assert cwd == str(project)


async def test_agent_rejects_compose_file_outside_roots(tmp_path):
    outside = tmp_path.parent / "elsewhere.yml"
    outside.write_text("services: {}\n", encoding="utf-8")
    executor = FakeCommandExecutor()
    service = _service(tmp_path / "stacks", executor)

    with pytest.raises(ValidationError) as excinfo:
        await service.act("web", "up", config_files=str(outside))

    assert "outside" in excinfo.value.message
    assert executor.calls == []


async def test_agent_rejects_sibling_prefix_path(tmp_path):
    """``/data/stacks-evil`` 不能因为字符串前缀而算作 ``/data/stacks`` 的子目录。"""
    root = tmp_path / "stacks"
    root.mkdir()
    evil = tmp_path / "stacks-evil"
    evil.mkdir()
    service = _service(root)

    assert service.is_within_roots(str(root / "a" / "compose.yml")) is True
    assert service.is_within_roots(str(evil / "compose.yml")) is False


async def test_agent_rejects_bad_action_and_project_name(tmp_path):
    service = _service(tmp_path)

    with pytest.raises(ValidationError):
        await service.act("web", "rm -rf")
    with pytest.raises(ValidationError):
        await service.act("web; rm -rf /", "up", config_files="")


async def test_agent_refuses_extra_args_that_override_paths(tmp_path):
    project = tmp_path / "web"
    project.mkdir()
    compose_file = project / "docker-compose.yml"
    compose_file.write_text("services: {}\n", encoding="utf-8")
    service = _service(tmp_path)

    for flag in ("-f", "--file", "--project-directory"):
        with pytest.raises(CommandRejectedError):
            await service.act(
                "web", "up", config_files=str(compose_file), extra_args=[flag, "/etc"]
            )


async def test_agent_down_does_not_need_compose_file(tmp_path):
    executor = FakeCommandExecutor()
    service = _service(tmp_path, executor)

    await service.act("web", "down")

    assert executor.last_argv == ("docker", "compose", "-p", "web", "down")


async def test_agent_lists_projects_under_roots(tmp_path):
    for name in ("alpha", "beta"):
        project = tmp_path / name
        project.mkdir()
        (project / "compose.yaml").write_text("services: {}\n", encoding="utf-8")

    stacks = _service(tmp_path).list_projects()

    assert {s.name for s in stacks} == {"alpha", "beta"}


# --------------------------------------------------------------------------- #
# 面板侧：AgentComposeBackend
# --------------------------------------------------------------------------- #
def _backend(handler, **kwargs) -> AgentComposeBackend:
    return AgentComposeBackend(
        "http://host:9101",
        transport=httpx.MockTransport(handler),
        **kwargs,
    )


async def test_backend_lists_stacks_from_agent():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/compose/stacks"
        return httpx.Response(
            200,
            json=[
                {
                    "name": "web",
                    "config_files": "E:/dev/web/docker-compose.yml",
                    "working_dir": "E:/dev/web",
                    "status": "running",
                    "discovered_paths": ["E:/dev/web/docker-compose.yml"],
                }
            ],
        )

    stacks = await _backend(handler).list_projects()

    assert len(stacks) == 1
    assert stacks[0].name == "web"
    assert stacks[0].status is StackStatus.RUNNING
    assert stacks[0].working_dir == "E:/dev/web"


async def test_backend_sends_paths_and_parses_result():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = request.read().decode()
        return httpx.Response(
            200,
            json={
                "ok": True,
                "exit_code": 0,
                "argv": ["docker", "compose", "up", "-d"],
                "stdout": "started",
                "stderr": "",
                "duration_ms": 12,
            },
        )

    stack = StackInfo(
        name="web",
        config_files="E:/dev/web/docker-compose.yml",
        working_dir="E:/dev/web",
    )
    result = await _backend(handler).act(stack, "up")

    assert seen["path"] == "/compose/action"
    assert '"config_files":"E:/dev/web/docker-compose.yml"' in seen["body"]
    assert result.ok and result.exit_code == 0 and result.stdout == "started"


async def test_backend_sends_token():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json=[])

    await _backend(handler, token="s3cret").list_projects()
    assert seen["auth"] == "Bearer s3cret"


async def test_backend_maps_401_to_actionable_error():
    backend = _backend(lambda request: httpx.Response(401, json={"message": "invalid token"}))

    with pytest.raises(EngineUnavailableError) as excinfo:
        await backend.list_projects()
    assert "compose.agent_token" in excinfo.value.message


async def test_backend_maps_400_to_validation_error():
    backend = _backend(lambda request: httpx.Response(400, json={"message": "路径越界"}))

    with pytest.raises(ValidationError) as excinfo:
        await backend.list_projects()
    assert "路径越界" in excinfo.value.message


async def test_backend_reports_unreachable_agent():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    backend = _backend(handler)
    with pytest.raises(EngineUnavailableError) as excinfo:
        await backend.list_projects()
    assert "lightpanel-agent" in excinfo.value.message

    # 可用性探测失败只返回 False，不能把面板带崩
    assert await backend.is_available() is False


async def test_backend_health_requires_compose_support():
    assert await _backend(lambda r: httpx.Response(200, json={"compose": True})).is_available()
    assert not await _backend(lambda r: httpx.Response(200, json={"status": "ok"})).is_available()


# --------------------------------------------------------------------------- #
# agent 应用端点
# --------------------------------------------------------------------------- #
def _app_client(tmp_path, token: str = "") -> TestClient:
    project = tmp_path / "web"
    project.mkdir()
    (project / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    service = HostComposeService(
        [str(tmp_path)],
        executor=FakeCommandExecutor(),
        scanner=scan_projects,
    )
    return TestClient(create_agent_app(token=token, compose=service))


def test_agent_exposes_compose_stacks(tmp_path):
    client = _app_client(tmp_path)

    response = client.get("/compose/stacks")

    assert response.status_code == 200
    assert [s["name"] for s in response.json()] == ["web"]
    assert client.get("/health").json()["compose"] is True


def test_agent_compose_requires_token(tmp_path):
    client = _app_client(tmp_path, token="s3cret")
    assert client.get("/compose/stacks").status_code == 401


def test_agent_compose_action_returns_command_result(tmp_path):
    client = _app_client(tmp_path)
    body = {
        "name": "web",
        "action": "down",
        "config_files": "",
        "working_dir": "",
        "extra_args": [],
    }

    response = client.post("/compose/action", json=body)

    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_agent_compose_action_maps_domain_error_to_400(tmp_path):
    client = _app_client(tmp_path)
    body = {"name": "web", "action": "up", "config_files": "/etc/passwd"}

    response = client.post("/compose/action", json=body)

    assert response.status_code == 400
    assert response.json()["code"] == "validation_error"


def test_agent_without_stacks_root_reports_unsupported():
    client = TestClient(create_agent_app())

    assert client.get("/health").json()["compose"] is False
    response = client.get("/compose/stacks")
    assert response.status_code == 500
    assert "--stacks-root" in response.json()["message"]

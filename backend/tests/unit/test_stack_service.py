"""Compose stack discovery & actions."""

from __future__ import annotations

import pytest

from lightpanel.adapters.docker.compose import ComposeStackEngine, LocalComposeBackend
from lightpanel.adapters.docker.fake_engine import FakeContainerEngine
from lightpanel.adapters.executor.fake_executor import FakeCommandExecutor
from lightpanel.config import ComposeConfig
from lightpanel.domain.errors import CommandFailedError, NotFoundError, ValidationError
from lightpanel.domain.models import CommandResult, StackStatus
from lightpanel.services.stack_service import StackAction, StackService


def _engine(container_engine, executor, settings: ComposeConfig | None = None):
    cfg = settings or ComposeConfig()
    return ComposeStackEngine(container_engine, LocalComposeBackend(executor, cfg), cfg)


@pytest.fixture
def file_backed_service(tmp_path, executor):
    """栈的 compose 文件真实存在于本机，用于验证动作 argv。"""
    project = tmp_path / "lightpanel"
    project.mkdir()
    (project / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    engine = _engine(
        FakeContainerEngine([]),
        executor,
        ComposeConfig(search_paths=[str(tmp_path)], max_depth=2),
    )
    return StackService(engine)


async def test_stacks_are_grouped_by_compose_project(stack_service):
    stacks = {s.name: s for s in await stack_service.list_stacks()}
    assert set(stacks) == {"lightpanel", "cache"}
    assert stacks["lightpanel"].status is StackStatus.RUNNING
    assert stacks["cache"].status is StackStatus.STOPPED


async def test_stack_metadata_comes_from_labels(stack_service):
    stack = await stack_service.get("lightpanel")
    assert stack.working_dir == "/opt/lightpanel"
    assert stack.config_files.endswith("docker-compose.yml")
    # containers are ordered by their compose service name: db -> web
    assert [c.name for c in stack.containers] == ["postgres", "lightpanel-web"]


async def test_unknown_stack(stack_service):
    with pytest.raises(NotFoundError):
        await stack_service.get("ghost")


async def test_up_down_restart_pull(file_backed_service, executor):
    executor.always(CommandResult.success(("docker", "compose", "up"), stdout="ok"))
    for action in ("up", "down", "restart", "pull"):
        result, stack = await file_backed_service.act("lightpanel", action)
        assert result.ok
        assert stack.name == "lightpanel"
    verbs = [
        next(t for t in argv if t in {"up", "down", "restart", "pull"})
        for argv, _, _ in executor.calls
    ]
    assert verbs == ["up", "down", "restart", "pull"]


async def test_up_uses_daemon_flag(file_backed_service, executor):
    executor.always(CommandResult.success(("docker", "compose"), stdout="ok"))
    await file_backed_service.act("lightpanel", StackAction.UP)
    assert executor.last_argv[-2:] == ("up", "-d")


async def test_extra_args_are_passed_through(file_backed_service, executor):
    executor.always(CommandResult.success(("docker", "compose"), stdout="ok"))
    await file_backed_service.act("lightpanel", "up", extra_args=["--force-recreate"])
    assert executor.last_argv[-1] == "--force-recreate"


async def test_failure_is_reported(file_backed_service, executor):
    executor.always(CommandResult.failure(("docker", "compose", "up"), 1, stderr="nope"))
    with pytest.raises(CommandFailedError):
        await file_backed_service.act("lightpanel", "up")


async def test_invalid_action(stack_service):
    with pytest.raises(ValidationError):
        await stack_service.act("lightpanel", "nuke")


async def test_filesystem_discovery(tmp_path, container_engine, executor):
    project = tmp_path / "demo"
    project.mkdir()
    (project / "docker-compose.yml").write_text("services: {}", encoding="utf-8")
    engine = _engine(
        container_engine, executor, ComposeConfig(search_paths=[str(tmp_path)], max_depth=2)
    )
    service = StackService(engine)
    names = {s.name for s in await service.list_stacks()}
    assert "demo" in names


async def test_disabled_engine_reports_unavailable(container_engine, executor):
    engine = _engine(container_engine, executor, ComposeConfig(enabled=False))
    service = StackService(engine)
    assert (await service.status())["available"] is False


async def test_search_filter(stack_service):
    assert [s.name for s in await stack_service.list_stacks(search="cache")] == ["cache"]


async def test_partial_status(tmp_path):
    from lightpanel.adapters.docker.fake_engine import FakeContainerEngine
    from lightpanel.domain.models import ContainerInfo, ContainerState

    engine = FakeContainerEngine(
        [
            ContainerInfo(
                id="1" * 64,
                name="a",
                image="x",
                state=ContainerState.RUNNING,
                labels={"com.docker.compose.project": "mix"},
            ),
            ContainerInfo(
                id="2" * 64,
                name="b",
                image="x",
                state=ContainerState.EXITED,
                labels={"com.docker.compose.project": "mix"},
            ),
        ]
    )
    service = StackService(_engine(engine, FakeCommandExecutor()))
    stack = await service.get("mix")
    assert stack.status is StackStatus.PARTIAL

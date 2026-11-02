"""Compose adapter: what happens when the project files are not on this host.

背景：面板跑在容器里、通过 TCP 控制宿主机引擎时，compose 标签里记录的配置
路径是宿主机的绝对路径，容器内根本不存在。以前的实现把该路径直接塞给
``-f`` 并作为 ``cwd``，结果是 ``exit 127 / No such file or directory``，用户
看不出问题在哪。这里锁定修复后的行为。
"""

from __future__ import annotations

import pytest

from lightpanel.adapters.docker.compose import ComposeStackEngine, LocalComposeBackend
from lightpanel.adapters.executor.fake_executor import FakeCommandExecutor
from lightpanel.config import ComposeConfig
from lightpanel.domain.errors import ValidationError
from lightpanel.domain.models import StackInfo, StackStatus


class _NullContainers:
    """Compose 引擎只需要容器引擎来发现栈，这里测动作不需要真实数据。"""

    async def list_containers(self, include_stopped: bool = True):  # noqa: ARG002
        return []


def _engine(
    executor: FakeCommandExecutor, settings: ComposeConfig | None = None
) -> ComposeStackEngine:
    settings = settings or ComposeConfig(search_paths=[])
    return ComposeStackEngine(_NullContainers(), LocalComposeBackend(executor, settings), settings)


def _stack(*, config_files: str = "", working_dir: str = "") -> StackInfo:
    return StackInfo(name="demo", config_files=config_files, working_dir=working_dir)


async def test_prefix_uses_project_name_when_files_are_unreachable():
    executor = FakeCommandExecutor()
    engine = _engine(executor)

    await engine.restart(_stack(config_files="/host/only/compose.yml", working_dir="/host/only"))

    argv, cwd, _ = executor.calls[-1]
    assert argv == ("docker", "compose", "-p", "demo", "restart")
    # 宿主机路径不能作为子进程 cwd，否则 create_subprocess_exec 直接 127
    assert cwd is None


async def test_prefix_keeps_reachable_config_files(tmp_path):
    compose_file = tmp_path / "compose.yml"
    compose_file.write_text("services: {}\n", encoding="utf-8")
    executor = FakeCommandExecutor()
    engine = _engine(executor)

    await engine.restart(_stack(config_files=str(compose_file), working_dir=str(tmp_path)))

    argv, cwd, _ = executor.calls[-1]
    assert argv == ("docker", "compose", "-f", str(compose_file), "-p", "demo", "restart")
    assert cwd == str(tmp_path)


async def test_prefix_skips_only_the_missing_files_of_a_multi_file_project(tmp_path):
    present = tmp_path / "compose.yml"
    present.write_text("services: {}\n", encoding="utf-8")
    executor = FakeCommandExecutor()
    engine = _engine(executor)

    await engine.restart(_stack(config_files=f"{present},/host/only/override.yml"))

    argv, _, _ = executor.calls[-1]
    assert argv == ("docker", "compose", "-f", str(present), "-p", "demo", "restart")


async def test_up_requires_readable_compose_files():
    executor = FakeCommandExecutor()
    engine = _engine(executor)

    with pytest.raises(ValidationError) as excinfo:
        await engine.up(_stack(config_files="/host/only/compose.yml"))

    assert excinfo.value.status_code == 400
    assert "demo" in excinfo.value.message
    assert excinfo.value.details["config_files"] == "/host/only/compose.yml"
    # 拒绝之前不能真的去跑 compose
    assert executor.calls == []


async def test_pull_requires_readable_compose_files():
    executor = FakeCommandExecutor()
    engine = _engine(executor)

    with pytest.raises(ValidationError):
        await engine.pull(_stack(config_files="/host/only/compose.yml"))
    assert executor.calls == []


async def test_down_still_works_without_files(tmp_path):
    """down / restart 依靠容器标签即可，不需要 compose 文件。"""
    executor = FakeCommandExecutor()
    engine = _engine(executor)

    await engine.down(_stack(config_files="/host/only/compose.yml"))

    assert executor.last_argv == ("docker", "compose", "-p", "demo", "down")


async def test_up_runs_with_readable_files(tmp_path):
    compose_file = tmp_path / "compose.yml"
    compose_file.write_text("services: {}\n", encoding="utf-8")
    executor = FakeCommandExecutor()
    engine = _engine(executor)

    await engine.up(_stack(config_files=str(compose_file)))

    assert executor.last_argv == (
        "docker",
        "compose",
        "-f",
        str(compose_file),
        "-p",
        "demo",
        "up",
        "-d",
    )


async def test_snapshot_stack_defaults_are_unknown():
    """没有容器成员的栈状态是 unknown，与文件是否可见无关。"""
    engine = _engine(FakeCommandExecutor())
    stack = _stack(config_files="/host/only/compose.yml")
    assert stack.status is StackStatus.UNKNOWN
    assert engine.name == "docker-compose"

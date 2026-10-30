"""Container service behaviour (fake engine)."""

from __future__ import annotations

import pytest

from lightpanel.domain.errors import NotFoundError, ValidationError
from lightpanel.domain.models import ContainerState
from lightpanel.services.container_service import ContainerAction, ContainerService


async def test_list_returns_all(container_service):
    containers = await container_service.list_containers()
    assert len(containers) == 4


async def test_list_can_hide_stopped(container_service):
    containers = await container_service.list_containers(include_stopped=False)
    assert {c.name for c in containers} == {"lightpanel-web", "postgres", "nginx"}


async def test_list_filter_by_project_and_search(container_service):
    assert {c.name for c in await container_service.list_containers(project="lightpanel")} == {
        "lightpanel-web",
        "postgres",
    }
    assert [c.name for c in await container_service.list_containers(search="nginx")] == ["nginx"]


async def test_list_filter_by_state(container_service):
    containers = await container_service.list_containers(state="exited")
    assert [c.name for c in containers] == ["redis"]


async def test_start_stop_restart(container_service):
    await container_service.act("redis", ContainerAction.START)
    assert (await container_service.get("redis")).state is ContainerState.RUNNING
    await container_service.act("redis", "stop")
    assert (await container_service.get("redis")).state is ContainerState.EXITED
    await container_service.act("redis", "RESTART")
    assert (await container_service.get("redis")).state is ContainerState.RUNNING


async def test_remove(container_service):
    await container_service.act("nginx", ContainerAction.REMOVE)
    with pytest.raises(NotFoundError):
        await container_service.get("nginx")


async def test_invalid_action(container_service):
    with pytest.raises(ValidationError):
        await container_service.act("nginx", "explode")


async def test_unknown_container(container_service):
    with pytest.raises(NotFoundError):
        await container_service.get("nope")


async def test_logs_validate_tail(container_service):
    assert "nginx" in await container_service.logs("nginx", tail=10)
    with pytest.raises(ValidationError):
        await container_service.logs("nginx", tail=0)


async def test_status_counts(container_service):
    status = await container_service.status()
    assert status["available"] is True
    assert status["total"] == 4
    assert status["running"] == 3


async def test_status_when_unavailable():
    from lightpanel.adapters.docker.fake_engine import FakeContainerEngine

    engine = FakeContainerEngine.with_demo_data()
    engine.set_available(False)
    status = await ContainerService(engine).status()
    assert status["available"] is False
    assert status["total"] == 0

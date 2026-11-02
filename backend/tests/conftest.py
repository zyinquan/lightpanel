"""Shared pytest fixtures.

Every fixture is built from in-memory / fake adapters, so the suite runs
offline and without Docker.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from lightpanel.adapters.catalog.memory_repository import InMemoryCatalogRepository
from lightpanel.adapters.catalog.yaml_repository import YamlCatalogRepository
from lightpanel.adapters.docker.compose import ComposeStackEngine, LocalComposeBackend
from lightpanel.adapters.docker.fake_engine import FakeContainerEngine
from lightpanel.adapters.executor.fake_executor import FakeCommandExecutor
from lightpanel.adapters.metrics.fake_provider import FakeMetricsProvider
from lightpanel.api.app import create_app
from lightpanel.config import AppConfig, ComposeConfig, load_config
from lightpanel.domain.clock import FixedClock
from lightpanel.domain.models import CommandDefinition, CommandKind, CommandTarget, SoftwareEntry
from lightpanel.services.catalog_service import CatalogService
from lightpanel.services.command_policy import CommandPolicy
from lightpanel.services.command_service import CommandService
from lightpanel.services.container_service import ContainerService
from lightpanel.services.stack_service import StackService


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock()


@pytest.fixture
def metrics_provider() -> FakeMetricsProvider:
    return FakeMetricsProvider()


@pytest.fixture
def catalog_repository() -> InMemoryCatalogRepository:
    return InMemoryCatalogRepository(sample_entries())


@pytest.fixture
def container_engine() -> FakeContainerEngine:
    return FakeContainerEngine.with_demo_data()


@pytest.fixture
def executor() -> FakeCommandExecutor:
    return FakeCommandExecutor()


@pytest.fixture
def stack_engine(container_engine, executor) -> ComposeStackEngine:
    settings = ComposeConfig()
    return ComposeStackEngine(container_engine, LocalComposeBackend(executor, settings), settings)


@pytest.fixture
def policy() -> CommandPolicy:
    return CommandPolicy(allowed_binaries=("docker",), default_timeout=30.0, max_timeout=600.0)


@pytest.fixture
def command_service(container_engine, stack_engine, executor, policy) -> CommandService:
    return CommandService(container_engine, stack_engine, executor, policy)


@pytest.fixture
def catalog_service(catalog_repository) -> CatalogService:
    return CatalogService(catalog_repository)


@pytest.fixture
def container_service(container_engine) -> ContainerService:
    return ContainerService(container_engine)


@pytest.fixture
def stack_service(stack_engine) -> StackService:
    return StackService(stack_engine)


@pytest.fixture
def test_config(tmp_path) -> AppConfig:
    """A config that never touches the real host."""
    return load_config(
        overrides={
            "env": "dev",
            "metrics": {"provider": "fake", "cache_ttl": 0, "history_size": 10},
            "docker": {"mode": "fake"},
            "catalog": {"provider": "memory"},
            "commands": {
                "extra_file": str(tmp_path / "missing-commands.yaml"),
                "executor": "fake",
            },
        }
    )


@pytest.fixture
def app(test_config):
    return create_app(config=test_config)


@pytest.fixture
def client(app) -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def sample_entries() -> list[SoftwareEntry]:
    return [
        SoftwareEntry(
            id="alpha",
            name="Alpha",
            url="https://alpha.local",
            description="first",
            icon="🅰️",
            tags=["监控", "ops"],
            order=0,
        ),
        SoftwareEntry(
            id="beta",
            name="Beta",
            url="https://beta.local",
            description="second",
            tags=["ops", "media"],
            order=1,
        ),
        SoftwareEntry(
            id="gamma",
            name="Gamma",
            url="https://gamma.local",
            description="third",
            tags=["media"],
            enabled=False,
            order=2,
        ),
    ]


def echo_command() -> CommandDefinition:
    return CommandDefinition(
        id="container.echo",
        name="回显容器名",
        target=CommandTarget.CONTAINER,
        kind=CommandKind.SHELL,
        argv=("docker", "inspect", "{name}"),
        description="echo the container name",
        timeout=15.0,
    )


def yaml_catalog_path(tmp_path):
    return YamlCatalogRepository(tmp_path / "catalog.yaml")

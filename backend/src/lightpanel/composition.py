"""Composition root.

This is the *only* module that knows about every concrete adapter. Everything
else depends on abstractions, so swapping an implementation (or adding a new
one) is a change confined to this file.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from .adapters.catalog.memory_repository import InMemoryCatalogRepository
from .adapters.catalog.yaml_repository import YamlCatalogRepository
from .adapters.docker.compose import ComposeStackEngine
from .adapters.docker.engine import DockerApiContainerEngine
from .adapters.docker.fake_engine import FakeContainerEngine
from .adapters.docker.null_engine import NullContainerEngine
from .adapters.executor.fake_executor import FakeCommandExecutor
from .adapters.executor.subprocess_executor import SubprocessCommandExecutor
from .adapters.metrics.fake_provider import FakeMetricsProvider
from .adapters.metrics.psutil_provider import PsutilMetricsProvider
from .api.security import TokenAuth
from .config import AppConfig
from .domain.ports import CatalogRepository, CommandExecutor, ContainerEngine, MetricsProvider
from .services.builtin_commands import all_builtin_commands
from .services.catalog_service import CatalogService
from .services.command_policy import CommandPolicy
from .services.command_service import CommandService
from .services.container_service import ContainerService
from .services.stack_service import StackService
from .services.system_service import SystemService

logger = logging.getLogger(__name__)

EXAMPLE_CATALOG_CANDIDATES = (
    "data/catalog.example.yaml",
    "../data/catalog.example.yaml",
    "backend/data/catalog.example.yaml",
    # 容器镜像把示例放在 /app/data-examples（见 deploy/Dockerfile）
    "/app/data-examples/catalog.example.yaml",
)



@dataclass
class AppContainer:
    config: AppConfig
    system: SystemService
    catalog: CatalogService
    containers: ContainerService
    stacks: StackService
    commands: CommandService
    auth: TokenAuth
    metrics_provider: MetricsProvider
    container_engine: ContainerEngine
    command_executor: CommandExecutor
    catalog_repository: CatalogRepository
    extra_closables: list = field(default_factory=list)

    async def aclose(self) -> None:
        for closable in self.extra_closables:
            close = getattr(closable, "aclose", None) or getattr(closable, "close", None)
            if close is None:
                continue
            try:
                result = close()
                if hasattr(result, "__await__"):
                    await result
            except Exception:  # pragma: no cover - shutdown best effort
                logger.warning("failed to close %s", closable, exc_info=True)


def build_container(config: AppConfig) -> AppContainer:
    """Assemble the object graph from configuration."""
    metrics_provider = _build_metrics_provider(config)
    catalog_repository = _build_catalog_repository(config)
    container_engine = _build_container_engine(config)
    executor = _build_executor(config)
    stack_engine = ComposeStackEngine(container_engine, executor, config.compose)

    policy = CommandPolicy(
        allowed_binaries=config.commands.allowed_binaries,
        default_timeout=config.commands.default_timeout,
        max_timeout=config.commands.max_timeout,
        allow_ad_hoc_argv=config.commands.allow_ad_hoc_argv,
    )

    definitions = list(all_builtin_commands()) if config.commands.include_builtin else []
    _seed_commands_file(config.commands.extra_file, config.commands.example_file)
    definitions.extend(load_extra_command_definitions(config.commands.extra_file))

    closables: list = []
    if hasattr(container_engine, "aclose"):
        closables.append(container_engine)

    return AppContainer(
        config=config,
        system=SystemService(metrics_provider, config.metrics),
        catalog=CatalogService(catalog_repository),
        containers=ContainerService(container_engine),
        stacks=StackService(stack_engine),
        commands=CommandService(container_engine, stack_engine, executor, policy, definitions),
        auth=TokenAuth(config.security),
        metrics_provider=metrics_provider,
        container_engine=container_engine,
        command_executor=executor,
        catalog_repository=catalog_repository,
        extra_closables=closables,
    )


# --------------------------------------------------------------------------- #
# factories
# --------------------------------------------------------------------------- #
def _build_metrics_provider(config: AppConfig) -> MetricsProvider:
    if config.metrics.provider == "fake":
        return FakeMetricsProvider(config.metrics)
    return PsutilMetricsProvider(config.metrics)


def _build_catalog_repository(config: AppConfig) -> CatalogRepository:
    if config.catalog.provider == "memory":
        return InMemoryCatalogRepository()
    repository = YamlCatalogRepository(config.catalog.path)
    candidates = (
        (config.catalog.example_file, *EXAMPLE_CATALOG_CANDIDATES)
        if config.catalog.example_file
        else EXAMPLE_CATALOG_CANDIDATES
    )
    for candidate in candidates:
        if repository.seed_if_missing(candidate):
            logger.info("seeded catalog from %s -> %s", candidate, config.catalog.path)
            break
    return repository


def _build_container_engine(config: AppConfig) -> ContainerEngine:
    if not config.docker.enabled:
        return NullContainerEngine()
    if config.docker.mode == "fake":
        return FakeContainerEngine.with_demo_data()
    if config.docker.mode == "api":
        return DockerApiContainerEngine(config.docker)
    # auto: prefer the real daemon when we can see an endpoint
    if config.docker.host or Path(config.docker.socket).exists():
        return DockerApiContainerEngine(config.docker)
    logger.warning(
        "docker mode is 'auto' but no endpoint is reachable (%s); "
        "Docker features will report as unavailable",
        config.docker.socket,
    )
    return NullContainerEngine()


def _build_executor(config: AppConfig) -> CommandExecutor:
    if config.commands.executor == "fake":
        return FakeCommandExecutor()
    return SubprocessCommandExecutor(
        allowed_binaries=config.commands.allowed_binaries,
        default_timeout=config.commands.default_timeout,
    )


def load_extra_command_definitions(path: str) -> list:
    """Read user-defined commands from YAML (missing file = no extra commands)."""
    from .adapters.commands.yaml_definitions import load_definitions

    return load_definitions(path)


def _seed_commands_file(target_path: str, example_path: str | None = None) -> None:
    """Create the user command file from ``example_path`` when it is missing.

    Opt-in via ``commands.example_file`` so the app never copies files based on
    the working directory. The Docker image points this at the bundled examples,
    which gives a fresh ``/data`` volume its factory custom commands.
    Existing files are never overwritten.
    """
    if not example_path:
        return
    target = Path(target_path)
    if target.exists():
        return
    source = Path(example_path)
    if not source.is_file() or source.resolve() == target.resolve():
        return
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    except OSError as exc:
        logger.warning("unable to seed command file %s: %s", target, exc)
        return
    logger.info("seeded command definitions from %s -> %s", source, target)

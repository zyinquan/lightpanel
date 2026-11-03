"""FastAPI dependency wiring.

Routers ask for *services*, never for adapters, so the transport layer stays
decoupled from implementations.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from ..adapters.catalog.icon_store import IconStore
from ..composition import AppContainer
from ..services.catalog_service import CatalogService
from ..services.command_service import CommandService
from ..services.container_service import ContainerService
from ..services.stack_service import StackService
from ..services.system_service import SystemService


def get_container(request: Request) -> AppContainer:
    container: AppContainer = request.app.state.container
    return container


def get_icon_store(container: Annotated[AppContainer, Depends(get_container)]) -> IconStore:
    return container.icon_store


def get_system(container: Annotated[AppContainer, Depends(get_container)]) -> SystemService:
    return container.system


def get_catalog(container: Annotated[AppContainer, Depends(get_container)]) -> CatalogService:
    return container.catalog


def get_containers(container: Annotated[AppContainer, Depends(get_container)]) -> ContainerService:
    return container.containers


def get_stacks(container: Annotated[AppContainer, Depends(get_container)]) -> StackService:
    return container.stacks


def get_commands(container: Annotated[AppContainer, Depends(get_container)]) -> CommandService:
    return container.commands


ContainerDep = Annotated[AppContainer, Depends(get_container)]
SystemDep = Annotated[SystemService, Depends(get_system)]
CatalogDep = Annotated[CatalogService, Depends(get_catalog)]
IconDep = Annotated[IconStore, Depends(get_icon_store)]
ContainersDep = Annotated[ContainerService, Depends(get_containers)]
StacksDep = Annotated[StackService, Depends(get_stacks)]
CommandsDep = Annotated[CommandService, Depends(get_commands)]

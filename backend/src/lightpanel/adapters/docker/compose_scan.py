"""Filesystem discovery of Docker Compose projects.

Kept separate from :mod:`.compose` because two very different callers need it:
the panel (when it runs on the host) and the host agent (when the panel runs in
a container). Neither of them should own the other's scanning code.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Sequence
from pathlib import Path

from ...domain.models import StackInfo, StackStatus

logger = logging.getLogger(__name__)

COMPOSE_FILENAMES = (
    "compose.yaml",
    "compose.yml",
    "docker-compose.yaml",
    "docker-compose.yml",
)


def scan_projects(search_paths: Sequence[str], max_depth: int) -> list[StackInfo]:
    """Find compose projects under ``search_paths`` (missing roots are skipped)."""
    discovered: list[StackInfo] = []
    for raw_root in search_paths:
        root = Path(raw_root)
        if not root.is_dir():
            continue
        for path in _walk_limited(root, max_depth):
            for filename in COMPOSE_FILENAMES:
                candidate = path / filename
                if candidate.is_file():
                    discovered.append(
                        StackInfo(
                            name=project_name(path, root),
                            config_files=str(candidate),
                            working_dir=str(path),
                            status=StackStatus.STOPPED,
                            discovered_paths=[str(candidate)],
                        )
                    )
                    break

    # Docker derives the project name from the directory, so two projects called
    # ``app`` are the *same* project as far as compose is concerned: keep the
    # first hit, but say so instead of dropping the other one silently.
    unique: list[StackInfo] = []
    seen: dict[str, str] = {}
    for stack in discovered:
        previous = seen.get(stack.name)
        if previous is not None:
            logger.warning(
                "compose 项目重名，已忽略 %s（%s 已在 %s）",
                stack.name,
                stack.config_files,
                previous,
            )
            continue
        seen[stack.name] = stack.config_files
        unique.append(stack)
    return unique


def project_name(directory: Path, root: Path) -> str:
    """Project name = directory name (Docker Compose v2 default)."""
    return directory.name or root.name or "default"


def _walk_limited(root: Path, max_depth: int):
    base_depth = len(root.parts)
    for current, dirs, _files in os.walk(root):
        depth = len(Path(current).parts) - base_depth
        if depth >= max_depth:
            dirs[:] = []
        yield Path(current)

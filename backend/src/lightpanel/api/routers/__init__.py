"""HTTP routers, one module per resource."""

from .auth import router as auth
from .catalog import router as catalog
from .commands import router as commands
from .containers import router as containers
from .stacks import router as stacks
from .system import router as system

__all__ = ["auth", "catalog", "commands", "containers", "stacks", "system"]

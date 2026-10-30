"""CLI entry point: ``python -m lightpanel`` / ``lightpanel``."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from . import __version__
from .api.app import create_app
from .config import load_config
from .logging_conf import setup_logging


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lightpanel", description="LightPanel — lightweight self-hosted server panel"
    )
    parser.add_argument("-c", "--config", help="配置文件路径 (YAML)")
    parser.add_argument("--host", help="覆盖 server.host")
    parser.add_argument("--port", type=int, help="覆盖 server.port")
    parser.add_argument("--env", choices=["dev", "prod"], help="覆盖运行环境")
    parser.add_argument(
        "--reload", action="store_true", help="开启热重载（仅开发环境）"
    )
    parser.add_argument("--version", action="version", version=f"lightpanel {__version__}")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    overrides: dict = {}
    if args.host:
        overrides["server"] = {"host": args.host}
    if args.port:
        overrides.setdefault("server", {})["port"] = args.port
    if args.env:
        overrides["env"] = args.env

    config = load_config(args.config, overrides=overrides or None)
    setup_logging(config.logging)

    import uvicorn

    if args.reload:
        uvicorn.run(
            "lightpanel.api.app:create_app",
            factory=True,
            host=config.server.host,
            port=config.server.port,
            reload=True,
        )
    else:
        app = create_app(config=config)
        uvicorn.run(app, host=config.server.host, port=config.server.port)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

"""``docker compose`` 命令行约定，面板侧与宿主机代理侧共用。

两边各有一套 argv 组装（一处在本进程执行，一处经 HTTP 交给宿主机执行），
但「哪个动作要带什么默认参数」必须只有一份，否则很容易改了一边忘了另一边。
"""

from __future__ import annotations

from collections.abc import Sequence

# ``compose up`` 默认前台运行，面板要的是后台
DEFAULT_ACTION_ARGS: dict[str, tuple[str, ...]] = {"up": ("-d",)}


def build_argv(
    base: Sequence[str],
    *,
    project: str,
    action: str,
    config_files: Sequence[str] = (),
    extra_args: Sequence[str] = (),
) -> list[str]:
    """``docker compose [-f …] -p <project> <action> [defaults] [extra]``."""
    argv = list(base)
    for file in config_files:
        argv += ["-f", file]
    argv += ["-p", project, action, *DEFAULT_ACTION_ARGS.get(action, ()), *extra_args]
    return argv

"""运行环境探测：面板自己是跑在宿主机上，还是跑在容器里。

psutil 读到的永远是**当前进程所在的环境**。容器里的 psutil 看到的是容器
（Linux 上）或 Docker Desktop 的 Linux 虚拟机（Windows / macOS 上），
跟用户心里的"宿主机"完全不是一回事。把这个区别显式暴露出来，UI 才不会撒谎。
"""

from __future__ import annotations

from pathlib import Path

CONTAINER_MARKERS = (
    Path("/.dockerenv"),
    Path("/run/.containerenv"),  # podman
)
CGROUP_HINTS = ("docker", "kubepods", "containerd", "lxc", "podman")


def is_running_in_container() -> bool:
    """判断当前进程是否在容器内运行（Windows 上恒为 False）。"""
    if any(marker.exists() for marker in CONTAINER_MARKERS):
        return True
    # 老版本 cgroup v1 会把容器运行时写进 /proc/1/cgroup；v2 下常常为空，
    # 所以这只是补充判断，不能作为唯一依据。
    try:
        content = Path("/proc/1/cgroup").read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    return any(hint in content for hint in CGROUP_HINTS)


def runtime_scope() -> str:
    """返回 ``host`` 或 ``container``。"""
    return "container" if is_running_in_container() else "host"

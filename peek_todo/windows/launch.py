"""固定 Windows 启动入口，协调后台进程和单实例。"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from ..storage.paths import package_dir, user_data_dir


def launch_arguments(*args: str) -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, *args]

    executable = Path(sys.executable)
    pythonw = executable.with_name("pythonw.exe")
    # 显式固定模块查找位置，登录启动时也能找到当前这一份源码。
    root = package_dir().parent
    code = (
        "import pathlib, runpy, sys; "
        f"sys.path.insert(0, {str(root)!r}); "
        "entry = pathlib.Path(sys.path[0]) / 'peek_todo' / '__main__.py'; "
        "sys.exit('PeekTodo has moved. Recreate its startup shortcut.') if not entry.is_file() else None; "
        "runpy.run_module('peek_todo', run_name='__main__', alter_sys=True)"
    )
    return [str(pythonw if pythonw.exists() else executable), "-c", code, *args]


def _lock_path() -> Path:
    """锁文件优先放临时目录；拿不到（权限/环境异常）就退回程序目录。

    PEEK_LOCK_PATH 可覆盖，用于调试时开第二个实例。
    """
    override = os.environ.get("PEEK_LOCK_PATH")
    if override:
        return Path(override)
    try:
        import tempfile

        return Path(tempfile.gettempdir()) / "peektodo.lock"
    except Exception:  # noqa: BLE001 - 任何异常都不该让程序起不来
        return user_data_dir() / "peektodo.lock"


def single_instance_lock():
    """先锁住第 4096 字节，再写入 PID，供其他实例读取。"""
    try:
        import msvcrt
    except ImportError:
        return True

    try:
        fd = os.open(_lock_path(), os.O_RDWR | os.O_CREAT | os.O_BINARY)
        handle = os.fdopen(fd, "r+b")
    except OSError:
        return True
    try:
        handle.seek(4096)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        handle.close()
        return None
    try:
        handle.seek(0)
        handle.write(f"{os.getpid():<24}".encode("ascii"))
        handle.truncate()
        handle.flush()
    except OSError:
        pass
    return handle


def running_instance_pid() -> int | None:
    """读锁文件里记录的 PID，用来提示用户是哪个进程占着。"""
    try:
        text = _lock_path().read_text(encoding="ascii", errors="ignore").strip()
        return int(text) if text.isdigit() else None
    except OSError:
        return None


def acquire_lock(retry: bool):
    """后台启动时给刚退出的实例一点时间释放锁。"""
    lock = single_instance_lock()
    if lock is None and retry:
        for _ in range(10):
            time.sleep(0.2)
            lock = single_instance_lock()
            if lock is not None:
                break
    return lock


def detach_to_background(argv: list[str]) -> bool:
    """从终端启动时，改为无控制台的后台进程，然后让终端立刻返回。

    这样关掉命令行窗口不会顺带把面板杀掉。带 --doctor/--setup 的不转，
    因为这些要在当前终端里看输出。
    """
    if getattr(sys, "frozen", False) or sys.platform != "win32":
        return False
    if "--detached-child" in argv or "--no-detach" in argv or "--doctor" in argv or "--setup" in argv:
        return False
    forced = "--detach" in argv
    if not forced and not (
        sys.stdout is not None and getattr(sys.stdout, "isatty", lambda: False)()
    ):
        return False

    pythonw = Path(sys.executable).with_name("pythonw.exe")
    if not pythonw.exists() or sys.executable.lower().endswith("pythonw.exe"):
        return False

    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
        subprocess, "CREATE_NEW_PROCESS_GROUP", 0
    )
    try:
        subprocess.Popen(
            launch_arguments("--detached-child", *(a for a in argv if a != "--detach")),
            creationflags=flags,
            close_fds=True,
        )
    except OSError:
        return False

    print("已请求启动 PeekTodo。启动后可在系统托盘找到它。")
    return True

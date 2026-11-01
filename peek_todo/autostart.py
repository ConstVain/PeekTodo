"""开机自启：写 HKCU 的 Run 项，不需要管理员权限，删掉即卸载。"""

from __future__ import annotations

import sys
from pathlib import Path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_ID = "PeekTodo"


def _pythonw() -> Path:
    exe = Path(sys.executable)
    candidate = exe.with_name("pythonw.exe")
    return candidate if candidate.exists() else exe


def launch_command() -> str:
    """打包成 exe 后直接指向 exe；源码运行时用 pythonw -m peek_todo。"""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    return f'"{_pythonw()}" -m peek_todo'


def is_enabled() -> bool:
    try:
        import winreg
    except ImportError:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, APP_ID)
            return bool(value)
    except OSError:
        return False


def enable() -> None:
    import winreg

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        winreg.SetValueEx(key, APP_ID, 0, winreg.REG_SZ, launch_command())


def disable() -> None:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, APP_ID)
    except OSError:
        pass


def toggle(enabled: bool) -> bool:
    if enabled:
        enable()
    else:
        disable()
    return is_enabled()

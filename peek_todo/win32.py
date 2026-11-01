"""pywin32 的加载兜底。

Anaconda 环境里经常有两份 pywin32：conda 放在 `Library\\bin` 的旧 DLL
和 pip 装到 `site-packages\\pywin32_system32` 的新 DLL。PATH 顺序会让
`import win32api` 加载到旧的那份，报 WinError 127（找不到指定的程序）。

这里按完整路径先把正确的那份 DLL 载入进程，之后 import 就会复用它。
"""

from __future__ import annotations

import ctypes
import sysconfig
from pathlib import Path


def _dll_dir() -> Path:
    return Path(sysconfig.get_paths()["purelib"]) / "pywin32_system32"


def preload() -> None:
    """预加载 pywintypes / pythoncom 的 DLL。失败就静默跳过。"""
    folder = _dll_dir()
    if not folder.is_dir():
        return
    for name in ("pywintypes312.dll", "pythoncom312.dll"):
        path = folder / name
        if not path.exists():
            continue
        try:
            ctypes.WinDLL(str(path))
        except OSError:
            pass


def import_gui():
    """返回 (win32gui, win32con)，不可用则抛 ImportError。"""
    preload()
    import win32con  # noqa: F401
    import win32gui

    return win32gui, win32con

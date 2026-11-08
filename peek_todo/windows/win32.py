"""pywin32 的加载兜底。

Anaconda 环境里经常有两份 pywin32：conda 放在 `Library\\bin` 的旧 DLL
和 pip 装到 `site-packages\\pywin32_system32` 的新 DLL。PATH 顺序会让
`import win32api` 加载到旧的那份，报 WinError 127（找不到指定的程序）。

这里按完整路径先把正确的那份 DLL 载入进程，之后 import 就会复用它。
"""

from __future__ import annotations

import ctypes
import sys
import sysconfig
from pathlib import Path


def _dll_dir() -> Path:
    return Path(sysconfig.get_paths()["purelib"]) / "pywin32_system32"


def preload() -> None:
    """预加载 pywintypes / pythoncom 的 DLL。失败就静默跳过。"""
    folder = _dll_dir()
    if not folder.is_dir():
        return
    version = f"{sys.version_info.major}{sys.version_info.minor}"
    for name in (f"pywintypes{version}.dll", f"pythoncom{version}.dll"):
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


def set_no_activate(window, enabled: bool) -> None:
    """开关 WS_EX_NOACTIVATE：关掉之后窗口才能被点成前台、拿到键盘焦点。"""
    try:
        win32gui, win32con = import_gui()
        hwnd = int(window.winId())
        style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
        if enabled:
            style |= win32con.WS_EX_NOACTIVATE
        else:
            style &= ~win32con.WS_EX_NOACTIVATE
        win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, style | win32con.WS_EX_TOOLWINDOW)
    except Exception:  # noqa: BLE001 - 拿不到样式也不能崩
        pass


def left_button_down() -> bool:
    """左键此刻是否按着（用异步按键状态，不依赖窗口焦点）。"""
    try:
        return bool(ctypes.windll.user32.GetAsyncKeyState(0x01) & 0x8000)
    except Exception:  # noqa: BLE001
        return False


def raise_foreground(window) -> None:
    """把窗口提到前台。Qt 的 activateWindow 在被系统限制时不管用，补一刀。"""
    try:
        ctypes.windll.user32.SetForegroundWindow(int(window.winId()))
    except Exception:  # noqa: BLE001
        pass

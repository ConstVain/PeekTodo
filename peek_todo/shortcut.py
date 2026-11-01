"""桌面快捷方式：把图标放好，再建 .lnk。

两个坑写在这里，免得再踩：
  1. .lnk 里存的是绝对路径，所以目标必须是"每台机器都有的路径"
     （pythonw.exe + -m peek_todo，或者打包后的 exe）。
  2. 图标要先复制到 C: 盘用户目录——有些机器上资源管理器不渲染其它盘上的 .ico。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

SHORTCUT_NAME = "PeekTodo.lnk"


def icon_path() -> Path:
    """把包里的 app.ico 复制到 %LOCALAPPDATA%\\PeekTodo\\app.ico 并返回。"""
    target_dir = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "PeekTodo"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "app.ico"
    source = Path(__file__).resolve().parent / "assets" / "app.ico"
    if source.exists():
        try:
            target.write_bytes(source.read_bytes())
        except OSError:
            return source
    return target


def desktop_path() -> Path:
    """真实的桌面目录（可能被重定向到别的盘，比如 D:\\desktop）。"""
    try:
        from .win32 import preload

        preload()
        from win32com.client import Dispatch

        folder = Dispatch("WScript.Shell").SpecialFolders("Desktop")
        if folder:
            return Path(folder) / SHORTCUT_NAME
    except Exception:  # noqa: BLE001
        pass
    return Path(os.environ.get("USERPROFILE", Path.home())) / "Desktop" / SHORTCUT_NAME


def _launch_command() -> tuple[str, str]:
    """返回 (target, arguments)。"""
    if getattr(sys, "frozen", False):
        return sys.executable, ""

    pythonw = Path(sys.executable).with_name("pythonw.exe")
    exe = pythonw if pythonw.exists() else Path(sys.executable)
    return str(exe), "-m peek_todo"


def create(overwrite: bool = True) -> Path | None:
    """在桌面创建快捷方式；失败返回 None（不影响主程序）。"""
    link = desktop_path()
    if link.exists() and not overwrite:
        return link

    target, args = _launch_command()
    icon = icon_path()

    try:
        from .win32 import preload

        preload()
        from win32com.client import Dispatch

        shell = Dispatch("WScript.Shell")
        shortcut = shell.CreateShortcut(str(link))
        shortcut.TargetPath = target
        shortcut.Arguments = args
        shortcut.WorkingDirectory = str(Path(__file__).resolve().parent.parent)
        shortcut.IconLocation = f"{icon},0"
        shortcut.Description = "PeekTodo - 贴右边缘滑出的待办面板"
        shortcut.WindowStyle = 1
        shortcut.Save()
        return link
    except Exception:  # noqa: BLE001 - 建不出来也不能影响启动
        return None


def remove() -> bool:
    link = desktop_path()
    try:
        link.unlink()
        return True
    except OSError:
        return False

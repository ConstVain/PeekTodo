"""Create a desktop shortcut pinned to this PeekTodo installation."""

from __future__ import annotations

import os
from hashlib import sha256
from subprocess import list2cmdline
from pathlib import Path

from ..storage.paths import assets_dir, package_dir
from .launch import launch_arguments

SHORTCUT_NAME = "PeekTodo.lnk"


def icon_path() -> Path:
    """给每版图标一个稳定的新路径，避免资源管理器沿用旧图标缓存。"""
    target_dir = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "PeekTodo"
    source = assets_dir() / "app.ico"
    if not source.is_file():
        return target_dir / "app.ico"
    try:
        data = source.read_bytes()
        digest = sha256(data).hexdigest()[:16]
        target = target_dir / f"app-{digest}.ico"
        target_dir.mkdir(parents=True, exist_ok=True)
        if not target.is_file() or target.read_bytes() != data:
            target.write_bytes(data)
        return target
    except OSError:
        return source


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


def working_directory() -> Path | None:
    """Find the old portable state directory before replacing a shortcut."""
    link = desktop_path()
    if not link.exists():
        return None
    try:
        from .win32 import preload

        preload()
        from win32com.client import Dispatch

        directory = Dispatch("WScript.Shell").CreateShortcut(str(link)).WorkingDirectory
        return Path(directory) if directory else None
    except Exception:
        return None


def create(overwrite: bool = True) -> Path | None:
    """在桌面创建快捷方式；失败返回 None（不影响主程序）。"""
    link = desktop_path()
    if link.exists() and not overwrite:
        return link

    target, *args = launch_arguments()
    icon = icon_path()

    try:
        from .win32 import preload

        preload()
        from win32com.client import Dispatch

        shell = Dispatch("WScript.Shell")
        shortcut = shell.CreateShortcut(str(link))
        shortcut.TargetPath = target
        shortcut.Arguments = list2cmdline(args)
        shortcut.WorkingDirectory = str(package_dir().parent)
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

"""Resolve program files, portable configuration, and shared user state."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def package_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def assets_dir() -> Path:
    return package_dir() / "assets"


def user_data_dir() -> Path:
    return Path(os.environ.get("APPDATA") or Path.home()) / "PeekTodo"


def portable_dir() -> Path | None:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    root = package_dir().parent
    if (root / "pyproject.toml").is_file() or (root / ".git").exists():
        return root
    return None


def config_path() -> Path:
    shared = user_data_dir() / "config.json"
    portable = portable_dir()
    if portable is not None:
        local = portable / "config.json"
        if local.exists() or not shared.exists():
            return local
    return shared


def state_path() -> Path:
    return user_data_dir() / ".state.json"

"""配置的读写与默认值。

配置文件放在程序目录（便携），首次运行时由向导生成。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .json_file import write_json

DEFAULT_PERIODS = [
    {"name": "上午", "start": "06:00"},
    {"name": "下午", "start": "12:00"},
    {"name": "晚上", "start": "18:00"},
]

DEFAULT_PANEL = {
    "width": 360,
    "theme": "cream",
    "heightRatio": 0.62,
    "maxHeight": 720,
    "hotZone": 3,
    "hotZonePad": 0,
    "hideDelayMs": 120,
    "animateMs": 90,
    "pollMs": 40,
}

DEFAULT_BEHAVIOR = {"refreshMs": 5000, "autostart": False, "desktopShortcut": True}


@dataclass
class Config:
    path: Path
    raw: dict[str, Any] = field(default_factory=dict)

    # ---- 读取 ----

    @classmethod
    def load(cls, path: str | Path) -> "Config":
        p = Path(path).expanduser()
        if not p.exists():
            raise FileNotFoundError(f"配置文件不存在：{p}")
        # utf-8-sig：记事本另存会带 BOM，不能让它把配置读废
        raw = json.loads(p.read_text(encoding="utf-8-sig"))
        if not isinstance(raw, dict):
            raise ValueError("config.json must contain a JSON object")
        return cls(path=p, raw=raw)

    def save(self) -> None:
        write_json(self.path, self.raw)

    # ---- 取值（都带默认，缺字段不会炸） ----

    @property
    def source(self) -> dict[str, Any]:
        return self.raw.get("source") or {}

    @property
    def mapping(self) -> dict[str, Any]:
        return self.raw.get("mapping") or {}

    @property
    def vocabulary(self) -> dict[str, Any]:
        return self.raw.get("vocabulary") or {}

    @property
    def periods(self) -> list[dict[str, str]]:
        return self.raw.get("periods") or DEFAULT_PERIODS

    @property
    def panel(self) -> dict[str, Any]:
        return {**DEFAULT_PANEL, **(self.raw.get("panel") or {})}

    @property
    def behavior(self) -> dict[str, Any]:
        return {**DEFAULT_BEHAVIOR, **(self.raw.get("behavior") or {})}

    def source_path(self) -> Path | None:
        """Markdown 源的路径，相对路径按配置文件所在目录解析。"""
        raw_path = self.source.get("path")
        if not raw_path:
            return None
        p = Path(raw_path).expanduser()
        if not p.is_absolute():
            p = (self.path.parent / p).resolve()
        return p


    def resolved_source(self) -> dict[str, Any]:
        path = self.source_path() if self.source.get("type") == "markdown" else None
        return {**self.source, "path": str(path)} if path is not None else self.source

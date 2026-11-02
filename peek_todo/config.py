"""配置的读写与默认值。

配置文件放在程序目录（便携），首次运行时由向导生成。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_PERIODS = [
    {"name": "上午", "start": "06:00"},
    {"name": "下午", "start": "12:00"},
    {"name": "晚上", "start": "18:00"},
]

DEFAULT_PANEL = {
    "width": 360,
    "theme": "dark",
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
        return cls(path=p, raw=json.loads(p.read_text(encoding="utf-8-sig")))

    def save(self) -> None:
        self.path.write_text(
            json.dumps(self.raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

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


def build_source(cfg: Config):
    """按配置造数据源。类型不认识就抛错，由调用方显示成提示。"""
    from .sources.base import SourceError
    from .sources.markdown import MarkdownSource
    from .sources.mubu import MubuSource

    kind = (cfg.source.get("type") or "").lower()
    if kind == "markdown":
        path = cfg.source_path()
        if path is None:
            raise SourceError("配置里没有填 markdown 路径")
        return MarkdownSource(path, recursive=bool(cfg.source.get("recursive", True)))
    if kind == "mubu":
        doc_id = cfg.source.get("docId")
        if not doc_id:
            raise SourceError("配置里没有填幕布文档 id")
        return MubuSource(doc_id)
    raise SourceError(f"不认识的数据源类型：{kind or '(空)'}")


def build_mapping(cfg: Config):
    from .structure import MappingConfig
    from .vocabulary import Vocabulary

    raw = cfg.mapping
    return MappingConfig(
        root_path=raw.get("root_path"),
        mode=(raw.get("mode") or "A").upper(),
        aliases=raw.get("aliases") or {},
        vocabulary=Vocabulary.from_config(cfg.vocabulary),
    )

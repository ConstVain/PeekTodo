"""幕布数据源：读桌面端写的本地备份。

注意这是**非公开的内部格式**，幕布升级可能改结构。读不到时抛 SourceError，
由上层显示"数据是旧的/没打开过"，而不是空面板。
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path

from ..domain.model import Node
from .base import FetchResult, Source, SourceError

DATA_ROOT = (
    Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    / "Mubu"
    / "mubu_app_data"
    / "mubu_data"
)

_TAG_RE = re.compile(r"<[^>]+>")
_BR_RE = re.compile(r"<br\s*/?>", re.I)
_ENTITIES = {"&nbsp;": " ", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&#39;": "'", "&amp;": "&"}


def strip_html(html: str | None) -> str:
    if not html:
        return ""
    text = _BR_RE.sub(" ", html)
    text = _TAG_RE.sub("", text)
    for entity, char in _ENTITIES.items():
        text = text.replace(entity, char)
    return re.sub(r"\s+", " ", text).strip()


def normalize_doc_id(raw: str) -> str:
    raw = (raw or "").strip()
    return raw[len("shortcut-") :] if raw.startswith("shortcut-") else raw


def _to_node(raw: dict) -> Node:
    status = raw.get("taskStatus")
    return Node(
        id=str(raw.get("id", "")),
        text=strip_html(raw.get("text")),
        done=None if status is None else int(status) == 1,
        children=[_to_node(child) for child in raw.get("children") or []],
    )


def list_documents() -> list[tuple[str, str]]:
    """扫本地备份目录，返回 [(doc_id, 最近保存时间)]，给首次运行向导用。"""
    folder = DATA_ROOT / "backup"
    if not folder.is_dir():
        return []
    result: list[tuple[str, str]] = []
    for doc_dir in sorted(folder.iterdir()):
        if not doc_dir.is_dir():
            continue
        files = [p for p in doc_dir.glob("*.json") if not p.name.startswith("Exit-")]
        if not files:
            continue
        latest = max(files, key=lambda p: p.stat().st_mtime)
        stamp = datetime.fromtimestamp(latest.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        result.append((doc_dir.name, stamp))
    return result


class MubuSource(Source):
    name = "mubu"

    def __init__(self, doc_id: str):
        self.doc_id = normalize_doc_id(doc_id)

    def fetch(self) -> FetchResult:
        folder = DATA_ROOT / "backup" / self.doc_id
        if not folder.is_dir():
            raise SourceError(f"找不到幕布文档 {self.doc_id} 的本地备份：{folder}")

        files = [p for p in folder.glob("*.json") if not p.name.startswith("Exit-")]
        if not files:
            raise SourceError(f"文档 {self.doc_id} 还没有任何备份文件")

        latest = max(files, key=lambda p: p.stat().st_mtime)
        try:
            doc = json.loads(latest.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise SourceError(f"解析备份文件失败（{latest.name}）：{exc}") from exc

        if not isinstance(doc.get("nodes"), list):
            raise SourceError(f"备份文件结构异常（{latest.name}）：缺少 nodes 数组")

        root = Node(id=f"mubu:{self.doc_id}", text="", children=[_to_node(n) for n in doc["nodes"]])
        saved_at = datetime.fromtimestamp(latest.stat().st_mtime)
        warnings = []
        if (datetime.now() - saved_at).total_seconds() > 24 * 3600:
            warnings.append(f"幕布数据是 {saved_at:%m-%d %H:%M} 的，桌面端可能很久没打开了")

        return FetchResult(
            tree=root,
            source_name=self.name,
            display=f"幕布 / {self.doc_id}",
            fetched_at=saved_at,
            warnings=warnings,
        )

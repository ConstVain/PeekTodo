"""幕布数据源：读桌面端写的本地备份。

注意这是**非公开的内部格式**，幕布升级可能改结构。读不到时抛 SourceError，
由上层显示"数据是旧的/没打开过"，而不是空面板。
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path

from ..domain.model import ColorSpan, Node
from .base import FetchResult, Source, SourceError

DATA_ROOT = (
    Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    / "Mubu"
    / "mubu_app_data"
    / "mubu_data"
)

_TEXT_COLORS = {
    "red": "#c33340",
    "orange": "#995016",
    "yellow": "#856200",
    "green": "#267248",
    "blue": "#215fbc",
    "purple": "#7244a4",
    "pink": "#ae3970",
    "gray": "#646c76",
}
_TEXT_COLOR_NAMES = {value: name for name, color in _TEXT_COLORS.items() for value in (name, color)}
_HIGHLIGHTS = {
    "red": "#ffccd0",
    "orange": "#ffdbab",
    "yellow": "#ffe782",
    "green": "#cef0a6",
    "blue": "#c4e2ff",
    "purple": "#e5d3ff",
    "pink": "#ffd7eb",
    "gray": "#e2e4e8",
}
_VOID_TAGS = frozenset("area base br col embed hr img input link meta param source track wbr".split())
_TEXT_PARTS = re.compile(r"\s+|\S+")


def _css_color(value: str | None) -> str | None:
    value = (value or "").strip().lower()
    if re.fullmatch(r"#[0-9a-f]{3}(?:[0-9a-f]{3})?", value):
        return value
    if value not in {"transparent", "inherit", "initial", "unset", "currentcolor"}:
        if re.fullmatch(r"[a-z]{1,24}", value):
            return value
    match = re.fullmatch(r"rgb\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)", value)
    if match:
        channels = [int(channel) for channel in match.groups()]
        if max(channels) <= 255:
            return "#{:02x}{:02x}{:02x}".format(*channels)
    return None


class _NodeText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.chunks: list[str] = []
        self.colors: list[ColorSpan] = []
        self._length = 0
        self._stack: list[tuple[str, str | None, str | None]] = [("", None, None)]
        self._pending_space: tuple[str | None, str | None] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "br":
            self.handle_data(" ")
        if tag in _VOID_TAGS:
            return

        _, foreground, background = self._stack[-1]
        if tag == "mark":
            background = _HIGHLIGHTS["yellow"]
        attrs = dict(attrs)
        for name in (attrs.get("class") or "").lower().split():
            if name.startswith("text-color-"):
                foreground = _TEXT_COLORS.get(name.removeprefix("text-color-"), foreground)
            elif name.startswith("highlight-"):
                background = _HIGHLIGHTS.get(name.removeprefix("highlight-"), background)
        foreground = _css_color(attrs.get("color")) or foreground
        background = _css_color(attrs.get("bgcolor")) or background
        for declaration in (attrs.get("style") or "").split(";"):
            name, _, value = declaration.partition(":")
            name = name.strip().lower()
            if name == "color":
                foreground = _css_color(value) or foreground
            elif name in {"background-color", "background"}:
                background = _css_color(value) or background
        self._stack.append((tag, foreground, background))

    def handle_endtag(self, tag):
        for index in range(len(self._stack) - 1, 0, -1):
            if self._stack[index][0] == tag:
                del self._stack[index:]
                break

    def handle_data(self, data):
        _, foreground, background = self._stack[-1]
        for part in _TEXT_PARTS.findall(data):
            if part.isspace():
                if self._length and self._pending_space is None:
                    self._pending_space = (foreground, background)
                continue
            if self._pending_space is not None:
                self._append(" ", *self._pending_space)
                self._pending_space = None
            self._append(part, foreground, background)

    def _append(self, text: str, foreground: str | None, background: str | None) -> None:
        start = self._length
        self._length += len(text)
        self.chunks.append(text)
        if foreground is None and background is None:
            return
        if self.colors:
            last = self.colors[-1]
            if (last.end, last.foreground, last.background) == (start, foreground, background):
                self.colors[-1] = ColorSpan(last.start, self._length, foreground, background, last.foreground_name)
                return
        self.colors.append(ColorSpan(start, self._length, foreground, background, _TEXT_COLOR_NAMES.get(foreground)))


def _parse_html(html: str | None) -> tuple[str, tuple[ColorSpan, ...]]:
    if not html:
        return "", ()
    parser = _NodeText()
    parser.feed(html)
    parser.close()
    return "".join(parser.chunks), tuple(parser.colors)


def strip_html(html: str | None) -> str:
    return _parse_html(html)[0]


def normalize_doc_id(raw: str) -> str:
    raw = (raw or "").strip()
    return raw[len("shortcut-") :] if raw.startswith("shortcut-") else raw


def _to_node(raw: dict) -> Node:
    status = raw.get("taskStatus")
    text, colors = _parse_html(raw.get("text"))
    return Node(
        id=str(raw.get("id", "")),
        text=text,
        done=None if status is None else int(status) == 1,
        children=[_to_node(child) for child in raw.get("children") or []],
        colors=colors,
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

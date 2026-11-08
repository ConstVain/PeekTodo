"""Markdown 数据源：把标题和列表项解析成 Node 树。

约定（都由结构映射决定怎么用，这里只管翻译）：
    # 标题            -> 分组节点
    - 条目            -> 普通节点
    - [ ] 待办        -> 未完成事项
    - [x] 待办        -> 已完成事项
    缩进              -> 父子层级
代码块里的内容一律忽略。
"""

from __future__ import annotations

import json
import re
from collections import Counter
from hashlib import sha256
from datetime import datetime
from pathlib import Path

from ..domain.model import Node
from .base import FetchResult, Source, SourceError

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
LIST_RE = re.compile(r"^(\s*)(?:[-*+]|\d+[.)])\s+(.*)$")
TASK_RE = re.compile(r"^\[([ xX])\]\s*(.*)$")
FENCE_RE = re.compile(r"^\s*(?:```|~~~)")
INLINE_LINK_RE = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
INLINE_STYLE_RE = re.compile(r"(\*\*|__|\*|_|`|~~)")
HTML_TAG_RE = re.compile(r"<[^>]+>")


def clean_inline(text: str) -> str:
    text = INLINE_LINK_RE.sub(r"\1", text)
    text = INLINE_STYLE_RE.sub("", text)
    text = HTML_TAG_RE.sub("", text)
    return text.strip()


def _node_id(*parts: str | int) -> str:
    content = json.dumps(parts, ensure_ascii=False).encode("utf-8")
    return "md2:" + sha256(content).hexdigest()


def parse_markdown(text: str, *, doc_id: str = "md") -> Node:
    doc = Node(id=_node_id(doc_id), text="")
    occurrences: Counter[tuple[str, str, str]] = Counter()

    def node_id(parent: Node, kind: str, label: str) -> str:
        key = (parent.id, kind, label)
        occurrences[key] += 1
        return _node_id(*key, occurrences[key])

    heading_stack: list[tuple[int, Node]] = [(0, doc)]
    item_stack: list[tuple[int, Node]] = []

    in_fence = False
    in_front_matter = False
    lines = text.splitlines()

    for lineno, raw in enumerate(lines):
        if lineno == 0 and raw.strip() == "---":
            in_front_matter = True
            continue
        if in_front_matter:
            if raw.strip() in ("---", "..."):
                in_front_matter = False
            continue

        if FENCE_RE.match(raw):
            in_fence = not in_fence
            continue
        if in_fence or not raw.strip():
            continue

        heading = HEADING_RE.match(raw)
        if heading:
            level = len(heading.group(1))
            title = clean_inline(heading.group(2))
            while len(heading_stack) > 1 and heading_stack[-1][0] >= level:
                heading_stack.pop()
            parent = heading_stack[-1][1]
            node = Node(id=node_id(parent, "heading", heading.group(2).strip()), text=title)
            parent.children.append(node)
            heading_stack.append((level, node))
            item_stack.clear()
            continue

        item = LIST_RE.match(raw)
        if item:
            indent = len(item.group(1).expandtabs(4))
            body = item.group(2).strip()
            done: bool | None = None
            task = TASK_RE.match(body)
            if task:
                done = task.group(1).lower() == "x"
                body = task.group(2)
            while item_stack and item_stack[-1][0] >= indent:
                item_stack.pop()
            parent = item_stack[-1][1] if item_stack else heading_stack[-1][1]
            kind = "checkbox" if done is not None else "item"
            node = Node(id=node_id(parent, kind, body.strip()), text=clean_inline(body), done=done)
            parent.children.append(node)
            item_stack.append((indent, node))
            continue

    return doc


class MarkdownSource(Source):
    name = "markdown"

    def __init__(self, path: str | Path, recursive: bool = True):
        self.path = Path(path).expanduser()
        self.recursive = recursive

    def _read_file(self, file: Path) -> Node:
        try:
            text = file.read_text(encoding="utf-8-sig", errors="replace")
        except OSError as exc:
            raise SourceError(f"读不了文件 {file}：{exc}") from exc
        relative = file.relative_to(self.path) if self.path.is_dir() else Path(file.name)
        return parse_markdown(text, doc_id=relative.as_posix())

    def fetch(self) -> FetchResult:
        if not self.path.exists():
            raise SourceError(f"路径不存在：{self.path}")

        if self.path.is_file():
            tree = self._read_file(self.path)
            return FetchResult(tree=tree, source_name=self.name, display=str(self.path))

        pattern = "**/*.md" if self.recursive else "*.md"
        files = sorted(p for p in self.path.glob(pattern) if p.is_file())
        if not files:
            raise SourceError(f"这个文件夹里没有 .md 文件：{self.path}")

        root = Node(id="md:root", text=self.path.name)
        warnings: list[str] = []
        stems = Counter(file.stem for file in files)
        for file in files:
            try:
                subtree = self._read_file(file)
            except SourceError as exc:
                warnings.append(str(exc))
                continue
            label = file.stem if stems[file.stem] == 1 else file.relative_to(self.path).as_posix()
            root.children.append(Node(id=subtree.id, text=label, children=subtree.children))

        if not root.children:
            raise SourceError("\n".join(warnings))

        return FetchResult(
            tree=root,
            source_name=self.name,
            display=str(self.path),
            fetched_at=datetime.now(),
            warnings=warnings,
        )

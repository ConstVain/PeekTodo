"""数据源接口。

一个数据源只做一件事：把自家格式翻译成 Node 树。时间语义、分组规则都不归它管。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime

from ..model import Node


class SourceError(RuntimeError):
    """源不可用（文件没了、幕布没装、格式变了）。UI 据此降级显示，而不是崩。"""


@dataclass
class FetchResult:
    tree: Node
    source_name: str
    display: str  # 给用户看的来源描述，如「~/notes/plan.md」
    fetched_at: datetime = field(default_factory=datetime.now)
    warnings: list[str] = field(default_factory=list)


class Source(ABC):
    name: str = "base"

    @abstractmethod
    def fetch(self) -> FetchResult:
        """读取并解析。失败时抛 SourceError，带人能看懂的原因。"""

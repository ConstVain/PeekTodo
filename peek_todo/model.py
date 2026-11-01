"""PeekTodo 的核心数据模型。

分层原则：
    数据源（sources/）只负责把自家格式翻译成 Node 树；
    结构映射（structure.py）再把 Node 树按用户选的"根 + 模式"变成 Group/Task。

这样换数据源不用动 UI，换 UI 不用动解析。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass
class Node:
    """文档里的一个节点。Markdown 的标题/列表项、幕布的子弹，都归一到这里。"""

    id: str
    text: str
    children: list["Node"] = field(default_factory=list)
    # None 表示这只是个分组标题（比如「周一下午」），不是可勾选事项
    done: bool | None = None

    def walk(self):
        yield self
        for child in self.children:
            yield from child.walk()


@dataclass(frozen=True)
class When:
    """时间语义。两个字段都可能为 None，表示只认出其中一部分。"""

    weekday: int | None = None  # 0=周一 ... 6=周日
    period: str | None = None  # 规范化后的时段名（上午/下午/晚上…）

    def is_complete(self) -> bool:
        return self.weekday is not None and self.period is not None


@dataclass
class Task:
    id: str
    text: str
    done: bool = False
    depth: int = 0  # 0 = 顶层事项；越大字号越小
    group: str | None = None  # 所属分组标题原文，便于报告


@dataclass
class Group:
    label: str
    when: When | None
    tasks: list[Task] = field(default_factory=list)
    # 截止日模式用：这一组对应的日期
    due: date | None = None


@dataclass
class Issue:
    """识别过程中"没接住"的东西。一律上报，绝不让内容静默消失。"""

    kind: str  # structure | time | orphan | empty
    message: str
    label: str = ""


@dataclass
class MappingResult:
    groups: list[Group] = field(default_factory=list)
    orphans: list[Task] = field(default_factory=list)  # 直接挂在根下的散项
    issues: list[Issue] = field(default_factory=list)
    mode_used: str = "A"  # 实际生效的模式（可能与配置不同，见 structure.py）
    mode_configured: str = "A"

    @property
    def task_count(self) -> int:
        return sum(len(g.tasks) for g in self.groups) + len(self.orphans)

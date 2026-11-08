"""结构映射：把 Node 树按「根节点 + 模式」变成分组和事项。

两种模式：
  week（周计划）：根的直接子节点是「周一下午」这种时段，再往下才是事项
  due （截止日）：根的直接子节点是「11月2日」这种日期，再往下才是事项

设计要点：
  * 不做硬编码的标题匹配——时段靠 parse_when，日期靠 parse_date，词表可配；
  * 认不出来的东西不丢：进 orphans / issues，UI 照常显示；
  * week 模式下如果结构明显不是周计划，自动降级为 due，而不是给个空面板。
"""

from __future__ import annotations

from datetime import date
from dataclasses import dataclass, field

from .model import Group, Issue, MappingResult, Node, Task
from .vocabulary import Vocabulary, parse_date, parse_when

MODE_WEEK = "week"
MODE_DUE = "due"
MODE_MEMO = "memo"

MODE_LABELS = {MODE_WEEK: "周计划", MODE_DUE: "截止日", MODE_MEMO: "备忘单"}


def normalize_mode(value: str | None) -> str:
    """兼容旧配置里的 A / B，以及中文名。"""
    text = (value or "").strip().lower()
    if text in ("b", "due", "截止日", "截止"):
        return MODE_DUE
    if text in ("c", "memo", "备忘单", "备忘"):
        return MODE_MEMO
    return MODE_WEEK


@dataclass
class MappingConfig:
    root_path: list[str] | None = None  # 标题路径，如 ["规划"]；None = 整篇
    mode: str = MODE_WEEK  # week | due（也接受旧写法 A/B）
    aliases: dict[str, str] = field(default_factory=dict)
    vocabulary: Vocabulary = field(default_factory=Vocabulary)


def _node_key(text: str) -> str:
    return (text or "").strip()


def resolve_root(tree: Node, path: list[str] | None) -> tuple[Node, list[Issue]]:
    """按标题路径往下找根节点；找不到就退回上一层并报告。"""
    issues: list[Issue] = []
    if not path:
        return tree, issues

    current = tree
    for depth, title in enumerate(path):
        match = next((c for c in current.children if _node_key(c.text) == _node_key(title)), None)
        if match is None:
            issues.append(
                Issue(
                    kind="structure",
                    message=f"找不到标题「{title}」，已退回上一层继续解析",
                    label=" > ".join(path[: depth + 1]),
                )
            )
            return current, issues
        current = match
    return current, issues


def _collect_tasks(node: Node, depth: int, group_label: str) -> list[Task]:
    """把 node 下面所有层级摊平成事项，depth 用来控制字号。"""
    tasks: list[Task] = []
    for child in node.children:
        tasks.append(
            Task(
                id=child.id,
                text=child.text,
                done=bool(child.done),
                depth=depth,
                group=group_label,
            )
        )
        tasks.extend(_collect_tasks(child, depth + 1, group_label))
    return tasks


def map_document(tree: Node, cfg: MappingConfig, *, today: date | None = None) -> MappingResult:
    mode = normalize_mode(cfg.mode)
    root, issues = resolve_root(tree, cfg.root_path)
    result = MappingResult(mode_configured=mode, mode_used=mode, issues=list(issues))

    if not root.children:
        result.issues.append(Issue(kind="empty", message="根节点下面没有任何内容", label=root.text))
        return result

    has_grandchildren = any(child.children for child in root.children)

    # 周计划 / 截止日都需要"分组 + 事项"两层结构；平铺清单说明是备忘单
    if mode != MODE_MEMO and not has_grandchildren:
        result.issues.append(
            Issue(
                kind="structure",
                message=f"选的是「{MODE_LABELS[mode]}」，但根下面没有分组，已按「备忘单」显示",
                label=root.text,
            )
        )
        mode = MODE_MEMO
    result.mode_used = mode

    if mode == MODE_MEMO:
        tasks = _collect_tasks(root, depth=0, group_label=root.text)
        result.groups.append(Group(label=root.text, when=None, tasks=tasks))
        return result

    for child in root.children:
        # 没有子项、自己又是可勾选条目 → 散项，不能丢
        if child.done is not None and not child.children:
            result.orphans.append(
                Task(id=child.id, text=child.text, done=bool(child.done), depth=0, group=root.text)
            )
            continue

        tasks = _collect_tasks(child, depth=0, group_label=child.text)
        if not tasks:
            result.issues.append(Issue(kind="empty", message="这个分组是空的", label=child.text))

        if mode == MODE_WEEK:
            when = parse_when(child.text, cfg.vocabulary, cfg.aliases)
            result.groups.append(Group(label=child.text, when=when, tasks=tasks))
        else:
            due = parse_date(child.text, today)
            result.groups.append(Group(label=child.text, when=None, due=due, tasks=tasks))

    # 周计划模式下一条时段也没认出来、却认出了日期 → 提示换成截止日模式
    if mode == MODE_WEEK and result.groups and not any(g.when for g in result.groups):
        if any(parse_date(g.label, today) for g in result.groups):
            result.issues.append(
                Issue(
                    kind="structure",
                    message="这些标题看起来是日期而不是时段，也许该选「截止日」模式",
                    label=root.text,
                )
            )

    return result

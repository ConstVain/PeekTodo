"""结构映射：把 Node 树按「根节点 + 模式」变成分组和事项。

模式 A：根的直接子节点是时间层（周一下午…），再往下才是事项
模式 B：根的直接子节点就是事项，全部算今天，不做时段筛选

设计要点：
  * 不做硬编码的标题匹配——时间层靠 parse_when（词表可配）；
  * 认不出来的东西不丢：进 orphans / issues，UI 照常显示；
  * 配置的模式和实际结构不符时，自动降级并记录 issue，而不是给个空面板。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .model import Group, Issue, MappingResult, Node, Task
from .vocabulary import Vocabulary, parse_when


@dataclass
class MappingConfig:
    root_path: list[str] | None = None  # 标题路径，如 ["规划"]；None = 整篇
    mode: str = "A"  # "A" | "B"
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


def _is_time_layer(node: Node, cfg: MappingConfig) -> bool:
    return parse_when(node.text, cfg.vocabulary, cfg.aliases) is not None


def map_document(tree: Node, cfg: MappingConfig) -> MappingResult:
    root, issues = resolve_root(tree, cfg.root_path)
    result = MappingResult(mode_configured=cfg.mode, mode_used=cfg.mode, issues=list(issues))

    if not root.children:
        result.issues.append(Issue(kind="empty", message="根节点下面没有任何内容", label=root.text))
        return result

    has_grandchildren = any(child.children for child in root.children)
    time_layers = sum(1 for child in root.children if _is_time_layer(child, cfg))

    effective = cfg.mode
    # 配置模式与结构明显不符时自动降级，避免空面板
    if cfg.mode == "A" and not has_grandchildren:
        effective = "B"
        result.issues.append(
            Issue(
                kind="structure",
                message="配置为模式 A，但根下面直接是事项（没有时间层），已按模式 B 显示",
                label=root.text,
            )
        )
    elif cfg.mode == "B" and has_grandchildren and time_layers > 0:
        effective = "A"
        result.issues.append(
            Issue(
                kind="structure",
                message="配置为模式 B，但检测到时间层，已按模式 A 显示",
                label=root.text,
            )
        )
    result.mode_used = effective

    if effective == "A":
        for child in root.children:
            # 时间层下面没有子项、但自己是个可勾选条目 → 当作散项，不能丢
            if child.done is not None and not child.children:
                result.orphans.append(
                    Task(id=child.id, text=child.text, done=bool(child.done), depth=0, group=root.text)
                )
                continue

            when = parse_when(child.text, cfg.vocabulary, cfg.aliases)
            tasks = _collect_tasks(child, depth=0, group_label=child.text)
            if not tasks:
                result.issues.append(Issue(kind="empty", message="这是个空分组", label=child.text))
            result.groups.append(Group(label=child.text, when=when, tasks=tasks))
    else:
        tasks = _collect_tasks(root, depth=0, group_label=root.text)
        result.groups.append(Group(label=root.text, when=None, tasks=tasks))

    return result

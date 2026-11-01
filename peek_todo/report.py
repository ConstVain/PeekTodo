"""识别报告：把「程序到底看懂了多少」翻译成人话。

这份输出是给用户排错的，不是给日志看的——所以成功项也列，未识别项要能被定位和纠正。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .model import MappingResult
from .sources.base import FetchResult
from .structure import MODE_LABELS, MODE_WEEK
from .vocabulary import describe_date, describe_when


@dataclass
class GroupReport:
    label: str
    when_text: str
    recognized: bool
    task_count: int
    max_depth: int


@dataclass
class Report:
    source_name: str
    display: str
    fetched_at: str
    root_path: list[str]
    mode_configured: str
    mode_used: str
    groups: list[GroupReport] = field(default_factory=list)
    unrecognized: list[str] = field(default_factory=list)
    orphans: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    task_total: int = 0
    task_done: int = 0

    @property
    def ok(self) -> bool:
        return self.task_total > 0 or bool(self.orphans)


def build_report(fetch: FetchResult, result: MappingResult, root_path: list[str] | None) -> Report:
    report = Report(
        source_name=fetch.source_name,
        display=fetch.display,
        fetched_at=fetch.fetched_at.strftime("%Y-%m-%d %H:%M"),
        root_path=list(root_path or []),
        mode_configured=result.mode_configured,
        mode_used=result.mode_used,
    )

    for group in result.groups:
        depths = [t.depth for t in group.tasks]
        if result.mode_used == MODE_WEEK:
            recognized = group.when is not None
            when_text = describe_when(group.when)
        else:
            recognized = group.due is not None
            when_text = describe_date(group.due)
        report.groups.append(
            GroupReport(
                label=group.label,
                when_text=when_text,
                recognized=recognized,
                task_count=len(group.tasks),
                max_depth=max(depths) if depths else 0,
            )
        )
        if not recognized:
            report.unrecognized.append(group.label)
        report.task_total += len(group.tasks)
        report.task_done += sum(1 for t in group.tasks if t.done)

    for orphan in result.orphans:
        report.orphans.append(orphan.text)
    report.task_total += len(result.orphans)

    report.issues = [i.message + (f"：{i.label}" if i.label else "") for i in result.issues]
    return report


def _display_width(text: str) -> int:
    return sum(2 if ord(ch) > 0x2E80 else 1 for ch in text)


def render_report(report: Report, width: int = 26) -> str:
    lines: list[str] = []
    lines.append(f"来源   {report.display}")
    lines.append(f"      数据时间 {report.fetched_at}")
    root = " > ".join(report.root_path) if report.root_path else "（整篇文档）"
    lines.append(f"根     {root}")

    mode_note = MODE_LABELS.get(report.mode_used, report.mode_used)
    if report.mode_configured != report.mode_used:
        configured = MODE_LABELS.get(report.mode_configured, report.mode_configured)
        mode_note += f"（配置是「{configured}」，按结构自动调整）"
    lines.append(f"模式   {mode_note}")
    lines.append("─" * 46)

    if not report.groups:
        lines.append("（没有解析出任何分组）")
    for group in report.groups:
        mark = "✓" if group.recognized else "!"
        when = group.when_text if group.recognized else "未识别时间"
        label = group.label if len(group.label) <= 16 else group.label[:15] + "…"
        pad = " " * max(0, width - _display_width(label))
        extra = f"（{group.max_depth + 1} 层）" if group.max_depth > 0 else ""
        lines.append(f"{mark} {label}{pad}{when}  ·  {group.task_count} 条{extra}")

    if report.orphans:
        lines.append("─" * 46)
        lines.append(f"散项（直接挂在根下）{len(report.orphans)} 条")
        for text in report.orphans[:5]:
            lines.append(f"  · {text}")

    lines.append("─" * 46)
    lines.append(f"事项 {report.task_total} 条，其中已完成 {report.task_done} 条")

    if report.unrecognized:
        lines.append("")
        lines.append(f"! {len(report.unrecognized)} 个标题没认出时间（内容照常显示，只是不参与时段筛选）：")
        for label in report.unrecognized:
            lines.append(f"    {label}")

    if report.issues:
        lines.append("")
        for issue in report.issues:
            lines.append(f"! {issue}")

    if not report.ok:
        lines.append("")
        lines.append("上面一条事项都没有——检查一下「根」选对了吗，或者文件里有没有 - [ ] 列表。")
    return "\n".join(lines)

"""把结构映射的结果按「现在几点」切成面板要显示的样子。纯逻辑。

week（周计划）：按周几 + 时段筛选，上方是当前时段
due （截止日）：按日期筛选，上方是逾期 + 今天到期，下方是接下来
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .model import Group, MappingResult, Task
from .state import LocalState
from .structure import MODE_DUE, MODE_MEMO, MODE_WEEK
from .vocabulary import describe_date

WEEKDAY_NAMES = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


@dataclass
class View:
    headline: str
    weekday: str
    period: str
    now: datetime
    mode: str
    current: list[Task] = field(default_factory=list)  # 上方大字
    unknown: list[Task] = field(default_factory=list)  # 没识别出时间的内容
    today_groups: list[Group] = field(default_factory=list)  # 下方小字
    open_count: int = 0
    done_count: int = 0
    issues: list[str] = field(default_factory=list)
    note: str = ""
    unknown_label: str = "未识别时间"
    section_label: str = "今天全部"
    show_bottom: bool = True  # 备忘单模式没有"下方列表"

    @property
    def total(self) -> int:
        return self.open_count + self.done_count


def _minutes(hhmm: str) -> int:
    hour, minute = str(hhmm).strip().split(":")
    return int(hour) * 60 + int(minute)


def period_of(moment: datetime, periods: list[dict]) -> str:
    now = moment.hour * 60 + moment.minute
    ordered = sorted(periods, key=lambda p: _minutes(p["start"]))
    current = ordered[-1]
    for period in ordered:
        if now >= _minutes(period["start"]):
            current = period
    return current["name"]


def _apply_state(tasks: list[Task], state: LocalState | None) -> None:
    if state is None:
        return
    for task in tasks:
        task.done = state.is_done(task.id, task.done)


def _count(tasks: list[Task]) -> tuple[int, int]:
    return (
        sum(1 for t in tasks if not t.done),
        sum(1 for t in tasks if t.done),
    )


def build_view(
    result: MappingResult,
    now: datetime,
    periods: list[dict],
    state: LocalState | None = None,
) -> View:
    weekday_index = now.weekday()
    period = period_of(now, periods)
    view = View(
        headline="",
        weekday=WEEKDAY_NAMES[weekday_index],
        period=period,
        now=now,
        mode=result.mode_used,
        issues=[i.message + (f"：{i.label}" if i.label else "") for i in result.issues],
    )

    all_tasks = [t for g in result.groups for t in g.tasks] + list(result.orphans)
    _apply_state(all_tasks, state)

    if result.mode_used == MODE_MEMO:
        _build_memo_view(view, result)
    elif result.mode_used == MODE_DUE:
        _build_due_view(view, result, now)
    else:
        _build_week_view(view, result, now, weekday_index)

    return view


def _build_memo_view(view: View, result: MappingResult) -> None:
    """备忘单：没有时间，全部常驻。"""
    view.headline = "备忘单"
    view.section_label = "全部"
    view.show_bottom = False
    view.unknown_label = "未分类"
    view.current = [t for g in result.groups for t in g.tasks] + list(result.orphans)
    view.unknown = []
    view.open_count, view.done_count = _count(view.current)


def _build_week_view(view: View, result: MappingResult, now: datetime, weekday_index: int) -> None:
    view.headline = f"{view.weekday}{view.period}"
    view.unknown_label = "未识别时间"
    view.section_label = "今天全部"

    today_groups = [g for g in result.groups if g.when and g.when.weekday == weekday_index]
    view.current = [t for g in today_groups if g.when.period == view.period for t in g.tasks]
    view.unknown = [t for g in result.groups if g.when is None for t in g.tasks] + list(result.orphans)
    view.today_groups = today_groups

    counted = [t for g in today_groups for t in g.tasks] + view.unknown
    view.open_count, view.done_count = _count(counted)


def _build_due_view(view: View, result: MappingResult, now: datetime) -> None:
    today = now.date()
    view.headline = "今天到期"
    view.unknown_label = "没写日期的"
    view.section_label = "接下来"

    overdue: list[Task] = []
    today_tasks: list[Task] = []
    upcoming: list[Group] = []
    undated: list[Task] = []

    for group in result.groups:
        if group.due is None:
            undated.extend(group.tasks)
        elif group.due < today:
            overdue.extend(group.tasks)
        elif group.due == today:
            today_tasks.extend(group.tasks)
        else:
            upcoming.append(group)

    upcoming.sort(key=lambda g: g.due or today)
    view.current = overdue + today_tasks
    view.unknown = undated + list(result.orphans)
    # 下方用「11月3日 · 明天」这种相对日期标题，比原始标题更好读
    view.today_groups = [
        Group(label=describe_date(g.due, today), when=None, due=g.due, tasks=g.tasks)
        for g in upcoming
    ]

    if overdue:
        view.note = f"{len(overdue)} 条逾期"

    counted = [t for g in result.groups for t in g.tasks] + list(result.orphans)
    view.open_count, view.done_count = _count(counted)

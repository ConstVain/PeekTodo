"""面板行为相关的纯逻辑测试：边缘判定、时间切片、本地勾选。"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from peek_todo.edge import EdgeDetector, Rect
from peek_todo.model import Group, MappingResult, Task, When
from peek_todo.selection import build_view
from peek_todo.state import LocalState
from peek_todo.structure import MODE_DUE, MODE_WEEK

SCREEN = Rect(0, 0, 1920, 1080)
PERIODS = [
    {"name": "上午", "start": "06:00"},
    {"name": "下午", "start": "12:00"},
    {"name": "晚上", "start": "18:00"},
]


def _week_result():
    result = MappingResult(mode_used=MODE_WEEK, mode_configured=MODE_WEEK)
    result.groups = [
        Group("周一下午", When(0, "下午"), [Task("a", "微分流形"), Task("b", "健身", done=True)]),
        Group("周二上午", When(1, "上午"), [Task("c", "网络科学")]),
        Group("待定", None, [Task("d", "买牙膏")]),
    ]
    return result


def _due_result():
    result = MappingResult(mode_used=MODE_DUE, mode_configured=MODE_DUE)
    result.groups = [
        Group("11月1日", None, [Task("o", "逾期任务")], due=date(2026, 11, 1)),
        Group("11月2日", None, [Task("t", "今天任务")], due=date(2026, 11, 2)),
        Group("11月5日", None, [Task("u", "以后的")], due=date(2026, 11, 5)),
        Group("以后再说", None, [Task("x", "没日期")]),
    ]
    return result


def test_edge_hot_zone_only_within_panel_band():
    detector = EdgeDetector(panel_width=360, panel_height=400)
    top = (1080 - 400) // 2
    assert detector.in_hot_zone((1919, top + 10), SCREEN)
    assert not detector.in_hot_zone((1919, top - 40), SCREEN)
    assert not detector.in_hot_zone((1800, top + 10), SCREEN)


def test_edge_hides_after_delay():
    detector = EdgeDetector(panel_width=360, panel_height=400, hide_delay_ms=100)
    top = (1080 - 400) // 2
    shown, _ = detector.update((1919, top + 10), SCREEN, 0)
    assert shown
    shown, _ = detector.update((100, 100), SCREEN, 10)
    assert shown  # 还在延时窗口内
    shown, _ = detector.update((100, 100), SCREEN, 200)
    assert not shown


def test_week_view_picks_current_period():
    monday_afternoon = datetime(2026, 11, 2, 14, 0)
    view = build_view(_week_result(), monday_afternoon, PERIODS)
    assert view.headline == "周一下午"
    assert [t.text for t in view.current] == ["微分流形", "健身"]
    assert [t.text for t in view.unknown] == ["买牙膏"]
    assert view.open_count == 2
    assert view.done_count == 1


def test_due_view_splits_overdue_today_upcoming():
    now = datetime(2026, 11, 2, 9, 0)
    view = build_view(_due_result(), now, PERIODS)
    assert view.headline == "今天到期"
    assert [t.text for t in view.current] == ["逾期任务", "今天任务"]
    assert view.note == "1 条逾期"
    assert [g.label.split(" · ")[0] for g in view.today_groups] == ["11月5日"]
    assert [t.text for t in view.unknown] == ["没日期"]


def test_due_view_labels_relative_day():
    now = datetime(2026, 11, 4, 9, 0)
    view = build_view(_due_result(), now, PERIODS)
    assert view.today_groups[0].label == "11月5日 · 明天"


def test_local_state_overrides_and_expires(tmp_path):
    path = tmp_path / "state.json"
    state = LocalState(path, "test")
    state.set_done("a", True)
    assert state.is_done("a", False) is True
    assert state.is_done("b", False) is False

    import json

    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["test"]["a"]["at"] = (datetime.now() - timedelta(days=30)).isoformat()
    path.write_text(json.dumps(raw), encoding="utf-8")

    state2 = LocalState(path, "test")
    assert state2.is_done("a", False) is False


def test_view_applies_local_state(tmp_path):
    state = LocalState(tmp_path / "state.json", "x")
    state.set_done("a", True)
    view = build_view(_week_result(), datetime(2026, 11, 2, 14, 0), PERIODS, state)
    assert view.current[0].done is True
    assert view.open_count == 1

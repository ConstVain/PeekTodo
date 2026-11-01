"""结构映射与解析的单元测试：全部是纯逻辑，不碰窗口。"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from peek_todo.model import Node
from peek_todo.sources.markdown import parse_markdown
from peek_todo.structure import MODE_DUE, MODE_MEMO, MODE_WEEK, MappingConfig, map_document
from peek_todo.vocabulary import Vocabulary, parse_date, parse_when

SAMPLE = """# 周计划

## 周一下午

- [ ] 微分流形
  - 第 3 章
- [ ] 健身

## 周二上午

- [ ] 网络科学
"""

DDL = """# DDL

## 11月2日

- [ ] 交实验报告

## 11月3日

- [ ] 读完第七章
"""


def test_markdown_structure():
    tree = parse_markdown(SAMPLE)
    assert [n.text for n in tree.children] == ["周计划"]
    section = tree.children[0]
    assert [c.text for c in section.children] == ["周一下午", "周二上午"]
    first = section.children[0]
    assert first.children[0].text == "微分流形"
    assert first.children[0].done is False
    assert first.children[0].children[0].text == "第 3 章"


def test_markdown_ignores_code_fence():
    tree = parse_markdown("# A\n\n```\n- [ ] 不该出现\n```\n\n- [ ] 该出现\n")
    texts = [n.text for n in tree.walk()]
    assert "不该出现" not in texts
    assert "该出现" in texts


@pytest.mark.parametrize(
    "label,weekday,period",
    [
        ("周一下午", 0, "下午"),
        ("星期二上午", 1, "上午"),
        ("礼拜三", 2, None),
        ("礼拜天晚上", 6, "晚上"),
        ("周7 早上", 6, "上午"),
        ("周日下午（加练）", 6, "下午"),
        ("待定", None, None),
    ],
)
def test_parse_when(label, weekday, period):
    when = parse_when(label, Vocabulary())
    if weekday is None and period is None:
        assert when is None
    else:
        assert when.weekday == weekday
        assert when.period == period


@pytest.mark.parametrize(
    "label,expected",
    [
        ("11月2日", date(2026, 11, 2)),
        ("11月3号", date(2026, 11, 3)),
        ("2026-11-04", date(2026, 11, 4)),
        ("11/5", date(2026, 11, 5)),
        ("下周再说", None),
    ],
)
def test_parse_date(label, expected):
    assert parse_date(label, today=date(2026, 11, 1)) == expected


def test_parse_date_relative():
    today = date(2026, 11, 1)
    assert parse_date("明天", today=today) == date(2026, 11, 2)
    assert parse_date("今天", today=today) == today


def test_week_mode_maps_groups_and_depth():
    tree = parse_markdown(SAMPLE)
    result = map_document(tree, MappingConfig(root_path=["周计划"], mode=MODE_WEEK))
    assert result.mode_used == MODE_WEEK
    assert [g.label for g in result.groups] == ["周一下午", "周二上午"]
    first = result.groups[0]
    assert first.when.weekday == 0 and first.when.period == "下午"
    assert [(t.text, t.depth) for t in first.tasks] == [("微分流形", 0), ("第 3 章", 1), ("健身", 0)]


def test_week_mode_downgrades_to_memo_when_flat():
    tree = parse_markdown("# 杂事\n\n- [ ] 买牙膏\n- [ ] 洗衣服\n")
    result = map_document(tree, MappingConfig(root_path=["杂事"], mode=MODE_WEEK))
    assert result.mode_used == MODE_MEMO
    assert any(i.kind == "structure" for i in result.issues)


def test_memo_mode_keeps_everything_flat():
    """备忘单：平铺清单，第一级和第二级都保留。"""
    tree = parse_markdown("# 本周计划\n\n- [ ] Transformer 实践\n- [ ] 网络科学读到第七章\n")
    result = map_document(tree, MappingConfig(root_path=["本周计划"], mode=MODE_MEMO))
    assert result.mode_used == MODE_MEMO
    assert [t.text for t in result.groups[0].tasks] == ["Transformer 实践", "网络科学读到第七章"]


def test_due_mode_groups_by_date():
    tree = parse_markdown(DDL)
    result = map_document(tree, MappingConfig(root_path=["DDL"], mode=MODE_DUE))
    assert result.mode_used == MODE_DUE
    assert [g.due for g in result.groups] == [date(2026, 11, 2), date(2026, 11, 3)]
    assert [t.text for t in result.groups[0].tasks] == ["交实验报告"]


def test_due_mode_keeps_grouping_headings_as_tasks():
    """截止日模式下，日期标题本身进组，子项作为它的下级。"""
    tree = parse_markdown(
        "# DDL\n\n## 11月2日\n\n- [ ] 交实验报告\n\n## 11月3日\n\n- [ ] 读完第七章\n"
    )
    result = map_document(tree, MappingConfig(root_path=["DDL"], mode=MODE_DUE))
    assert len(result.groups) == 2
    assert result.groups[0].label == "11月2日"
    assert [(t.depth, t.text) for t in result.groups[0].tasks] == [(0, "交实验报告")]


def test_missing_root_falls_back():
    tree = parse_markdown(SAMPLE)
    result = map_document(tree, MappingConfig(root_path=["不存在"], mode=MODE_WEEK))
    assert any(i.kind == "structure" for i in result.issues)
    assert result.groups  # 仍然解析出东西，不是空面板


def test_orphan_checkbox_under_root_is_kept():
    """有时间层、同时又直接挂着散项时，散项不能被丢掉。"""
    tree = Node(
        id="root",
        text="",
        children=[
            Node(id="g", text="周一下午", children=[Node(id="a", text="看书", done=False)]),
            Node(id="b", text="买菜", done=False),
        ],
    )
    result = map_document(tree, MappingConfig(root_path=None, mode=MODE_WEEK))
    assert result.mode_used == MODE_WEEK
    assert [t.text for t in result.orphans] == ["买菜"]
    assert [t.text for t in result.groups[0].tasks] == ["看书"]

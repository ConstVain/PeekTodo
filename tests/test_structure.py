"""结构映射与解析的单元测试：全部是纯逻辑，不碰窗口。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from peek_todo.model import Node
from peek_todo.sources.markdown import parse_markdown
from peek_todo.structure import MappingConfig, map_document
from peek_todo.vocabulary import Vocabulary, parse_when

SAMPLE = """# 周计划

## 周一下午

- [ ] 微分流形
  - 第 3 章
- [ ] 健身

## 周二上午

- [ ] 网络科学
"""


def test_markdown_structure():
    tree = parse_markdown(SAMPLE)
    headings = [n.text for n in tree.children]
    assert headings == ["周计划"]
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


def test_alias_wins():
    cfg = MappingConfig(aliases={"礼拜三晚上": "周三晚上"})
    when = parse_when("礼拜三晚上", Vocabulary(), cfg.aliases)
    assert (when.weekday, when.period) == (2, "晚上")


def test_mode_a_maps_groups_and_depth():
    tree = parse_markdown(SAMPLE)
    result = map_document(tree, MappingConfig(root_path=["周计划"], mode="A"))
    assert result.mode_used == "A"
    assert [g.label for g in result.groups] == ["周一下午", "周二上午"]
    first = result.groups[0]
    assert first.when.weekday == 0 and first.when.period == "下午"
    assert [(t.text, t.depth) for t in first.tasks] == [("微分流形", 0), ("第 3 章", 1), ("健身", 0)]


def test_mode_a_downgrades_when_flat():
    tree = parse_markdown("# 杂事\n\n- [ ] 买牙膏\n- [ ] 洗衣服\n")
    result = map_document(tree, MappingConfig(root_path=["杂事"], mode="A"))
    assert result.mode_used == "B"
    assert any(i.kind == "structure" for i in result.issues)
    assert len(result.groups[0].tasks) == 2


def test_mode_b_collects_everything():
    tree = parse_markdown("# 杂事\n\n- [ ] 买牙膏\n  - 顺便买牙刷\n")
    result = map_document(tree, MappingConfig(root_path=["杂事"], mode="B"))
    texts = [t.text for t in result.groups[0].tasks]
    assert texts == ["买牙膏", "顺便买牙刷"]


def test_missing_root_falls_back():
    tree = parse_markdown(SAMPLE)
    result = map_document(tree, MappingConfig(root_path=["不存在"], mode="A"))
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
    result = map_document(tree, MappingConfig(root_path=None, mode="A"))
    assert result.mode_used == "A"
    assert [t.text for t in result.orphans] == ["买菜"]
    assert [t.text for t in result.groups[0].tasks] == ["看书"]

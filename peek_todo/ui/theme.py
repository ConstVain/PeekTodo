"""面板配色。

两套：深色（默认）和米白。所有颜色都走这里，panel.py 里不再写死色值。
强调色在浅色底上要压暗一档，否则对比度不够，所以 accent() 会做一次映射。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Theme:
    key: str
    name: str

    # 卡片
    card_top: str
    card_mid: str
    card_bottom: str
    card_border: str

    # 文字
    text: str
    text_soft: str
    text_dim: str
    text_faint: str
    text_done: str

    # 区块
    current_bg: str
    chip_bg: str
    divider: str
    hover: tuple[int, int, int, int]
    scroll_handle: str

    # 状态
    ok: str
    warn: str
    overdue: str
    done_box: str

    # 强调色是否需要压暗
    darken_accent: bool


DARK = Theme(
    key="dark",
    name="深色",
    card_top="#24262d",
    card_mid="#1a1b20",
    card_bottom="#14151a",
    card_border="#2e313a",
    text="#eef0f4",
    text_soft="#d8dce4",
    text_dim="#9aa1ad",
    text_faint="#6b7280",
    text_done="#565d69",
    current_bg="rgba(255, 255, 255, 0.035)",
    chip_bg="rgba(255,255,255,0.055)",
    divider="rgba(255,255,255,0.07)",
    hover=(255, 255, 255, 16),
    scroll_handle="rgba(255,255,255,40)",
    ok="#4ade80",
    warn="#f0b45f",
    overdue="#f87171",
    done_box="#565d69",
    darken_accent=False,
)

CREAM = Theme(
    key="cream",
    name="米白",
    card_top="#fbf7ee",
    card_mid="#f6f1e6",
    card_bottom="#efe9dc",
    card_border="#ddd4c2",
    text="#2f2a22",
    text_soft="#3f3830",
    text_dim="#6f6656",
    text_faint="#9a9080",
    text_done="#b0a693",
    current_bg="rgba(120, 100, 60, 0.07)",
    chip_bg="rgba(120, 100, 60, 0.10)",
    divider="rgba(120, 100, 60, 0.14)",
    hover=(120, 100, 60, 20),
    scroll_handle="rgba(120, 100, 60, 70)",
    ok="#2f8f4e",
    warn="#b45309",
    overdue="#c2410c",
    done_box="#b0a693",
    darken_accent=True,
)

THEMES = {DARK.key: DARK, CREAM.key: CREAM}
DEFAULT_THEME = DARK

# 浅色底上把强调色压暗一档
_LIGHT_ACCENTS = {
    "#7aa2ff": "#3b6fd4",  # 周计划：蓝
    "#f0b45f": "#b45309",  # 截止日：琥珀
    "#4ade80": "#15803d",  # 备忘单：绿
    "#a78bfa": "#6d4ad1",  # 雾紫
    "#2dd4bf": "#0f766e",  # 青绿
}


def get(key: str | None) -> Theme:
    return THEMES.get((key or "").strip().lower(), DEFAULT_THEME)


def accent(theme: Theme, color: str) -> str:
    """按主题调整强调色：浅色主题下压暗，深色主题原样。"""
    if theme.darken_accent:
        return _LIGHT_ACCENTS.get(color.lower(), color)
    return color

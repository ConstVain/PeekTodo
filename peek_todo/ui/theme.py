"""面板配色。

两套：深色（默认）和米白。所有颜色都走这里，panel.py 里不再写死色值。
强调色在浅色底上要压暗一档，否则对比度不够，所以 accent() 会做一次映射。
"""

from __future__ import annotations

from dataclasses import dataclass, replace


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
    ok="#4a8f63",
    warn="#a5641c",
    overdue="#b0452b",
    done_box="#b0a693",
    darken_accent=True,
)

THEMES = {DARK.key: DARK, CREAM.key: CREAM}
DEFAULT_THEME = CREAM

# 浅色底上把强调色压暗，并往暖里偏一点，配米白纸色。
# 参考：MIUI/HarmonyOS 的浅色主题强调色都会降饱和，避免在低对比底上过艳。
_LIGHT_ACCENTS = {
    "#7aa2ff": "#4f6f9f",  # 备忘单：石青（比纯蓝闷一档，米白上不刺眼）
    "#f0b45f": "#96622a",  # 截止日：赭石
    "#4ade80": "#4b7a5c",  # 周计划：苔绿（一眼看得出是绿，又不刺眼）
    "#a78bfa": "#6a5b86",  # 雾紫
    "#2dd4bf": "#3d6b66",  # 青绿
}


# 正文字体：按"现代手机厂商字体 > 思源/Noto > 系统雅黑"的顺序取第一个装了的
BODY_FONT_CANDIDATES = (
    "MiSans",
    "HarmonyOS Sans SC",
    "Noto Sans SC",
    "Source Han Sans SC",
    "PingFang SC",
    "Microsoft YaHei UI",
)

_BUNDLED_FONTS = ("MiSans-Regular.ttf", "SmileySans-Oblique.otf")
_body_family_cache: str | None = None


def load_bundled_fonts() -> list[str]:
    """把 assets/fonts 里的字体注册进 Qt，返回成功加载的字体族名。

    这样即使系统没装 MiSans / 得意黑，渲染也是一致的。
    需要在 QApplication 创建之后调用。
    """
    from pathlib import Path

    from PyQt5.QtGui import QFontDatabase

    folder = Path(__file__).resolve().parent.parent / "assets" / "fonts"
    loaded: list[str] = []
    if not folder.is_dir():
        return loaded
    for name in _BUNDLED_FONTS:
        path = folder / name
        if not path.exists():
            continue
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id >= 0:
            loaded.extend(QFontDatabase.applicationFontFamilies(font_id))
    return loaded


def body_font_family() -> str:
    """当前机器上可用的正文首选字体（需要在 QApplication 创建后调用）。"""
    global _body_family_cache
    if _body_family_cache:
        return _body_family_cache
    try:
        from PyQt5.QtGui import QFontDatabase

        installed = set(QFontDatabase().families())
        for name in BODY_FONT_CANDIDATES:
            if name in installed:
                _body_family_cache = name
                break
    except Exception:  # noqa: BLE001 - 取不到就用系统默认
        pass
    if not _body_family_cache:
        _body_family_cache = BODY_FONT_CANDIDATES[-1]
    return _body_family_cache


_OVERRIDABLE = {
    name for name in Theme.__dataclass_fields__ if name not in ("key", "name", "darken_accent")
}


def get(key: str | None, overrides: dict | None = None) -> Theme:
    """取主题；overrides 是 config.json 里 panel.colors 的字段覆盖。"""
    base = THEMES.get((key or "").strip().lower(), DEFAULT_THEME)
    if not overrides:
        return base
    clean = {k: v for k, v in overrides.items() if k in _OVERRIDABLE and isinstance(v, (str, int, tuple, list))}
    if not clean:
        return base
    if "hover" in clean and isinstance(clean["hover"], list):
        clean["hover"] = tuple(clean["hover"])
    try:
        return replace(base, **clean)
    except TypeError:
        return base


def accent(theme: Theme, color: str) -> str:
    """按主题调整强调色：浅色主题下压暗，深色主题原样。"""
    if theme.darken_accent:
        return _LIGHT_ACCENTS.get(color.lower(), color)
    return color

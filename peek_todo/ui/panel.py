"""右边缘滑出的待办面板（PyQt5）。

窗口固定在主屏右边缘、整块透明；内部 card 通过动画滑入。
滑出后窗口接收鼠标（可点击但永不抢焦点），缩回后整窗穿透。
"""

from __future__ import annotations

from PyQt5.QtCore import QEasingCurve, QEvent, QPoint, QPropertyAnimation, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QPainter
from PyQt5.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..domain.model import Task
from ..windows.win32 import raise_foreground, set_no_activate

from ..domain.selection import View
from .theme import MODE_ACCENTS, Theme, accent as theme_accent, body_font_family, get as get_theme

ACCENT = "#7aa2ff"  # 兜底色，实际用 theme.accent()
# 底部时间戳用的字体（得意黑，斜体）；没装就自动回落到系统默认
TIMESTAMP_FONT = "'得意黑', 'Smiley Sans Oblique', 'Microsoft YaHei UI'"


def card_qss(t: Theme) -> str:
    return f"""
#card {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                 stop:0 {t.card_top}, stop:0.38 {t.card_mid}, stop:1 {t.card_bottom});
    border-top-left-radius: 14px;
    border-bottom-left-radius: 14px;
    border-left: 1px solid {t.card_border};
}}
"""


def current_block_qss(t: Theme, accent: str) -> str:
    """当前时段：左侧一道色条 + 深/浅一档的底色，把"现在要做"分出来。"""
    return f"""
#currentBlock {{
    background: {t.current_bg};
    border-left: 3px solid {accent};
    border-radius: 9px;
}}
"""


def group_head_qss(t: Theme, first: bool) -> str:
    border = "transparent" if first else t.divider
    return f"""
QWidget#groupHead {{
    background: transparent;
    border-top: 1px solid {border};
}}
"""


def scroll_qss(t: Theme) -> str:
    return f"""
QScrollArea {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 4px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {t.scroll_handle}; border-radius: 2px; min-height: 24px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
"""


def _font(size: int, strike: bool = False) -> QFont:
    font = QFont(body_font_family())
    font.setPixelSize(size)
    font.setStrikeOut(strike)
    return font


class _Grip(QWidget):
    """左边缘的缩放把手：只有光标变化，不画任何东西。"""

    def __init__(self, panel: "Panel", corner: str, parent=None):
        super().__init__(parent or panel.card)
        self._panel = panel
        self._corner = corner
        self._start = None
        self._geo = None
        self.setCursor(Qt.SizeFDiagCursor if corner == "tl" else Qt.SizeBDiagCursor)
        self.setToolTip("拖拽调整面板大小")
        self.setAttribute(Qt.WA_TranslucentBackground, True)

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        self._panel.pin(True)
        self._start = event.globalPos()
        self._geo = self._panel.geometry()

    def mouseMoveEvent(self, event):
        if self._start is None:
            return
        self._panel.drag_resize(self._corner, self._start, self._geo, event.globalPos())

    def mouseReleaseEvent(self, event):
        if self._start is None:
            return
        self._start = None
        self._panel.end_resize()


class TaskRow(QWidget):
    toggled = pyqtSignal(str, bool)
    pressed = pyqtSignal()

    def __init__(
        self,
        task: Task,
        *,
        small: bool = False,
        muted: bool = False,
        accent: str = ACCENT,
        overdue: bool = False,
        scale: float = 1.0,
        theme: Theme | None = None,
        parent=None,
    ):
        super().__init__(parent)
        t = theme or get_theme(None)
        self._theme = t
        self.task = task
        self._hover = False
        self._small = small
        self._scale = max(0.7, min(scale, 1.8))
        self.setAttribute(Qt.WA_Hover, True)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("点方框勾选（只改面板本地状态） · 点空白处钉住面板")

        layout = QHBoxLayout(self)
        # 子项缩进：一级子项退一格，二级再退一格，视觉上明确从属关系
        indent = min(task.depth, 3) * max(6, round((16 if small else 20) * self._scale))
        layout.setContentsMargins(indent, 0, 0, 0)
        layout.setSpacing(max(4, round(8 * self._scale)))

        if task.done:
            mark = "✓" if small else "☑"
        else:
            mark = "·" if small else "☐"

        # 层级越深字号掉得越狠：0 -> 16/12，1 -> 11/9，2+ -> 9/8
        if small:
            base = 12 if task.depth == 0 else 9 if task.depth == 1 else 8
        else:
            base = 16 if task.depth == 0 else 11 if task.depth == 1 else 9
        size = max(8, round(base * self._scale))

        if task.done:
            box_color = t.done_box
        elif overdue:
            box_color = t.overdue
        elif small or muted or task.depth > 0:
            box_color = t.text_faint
        else:
            box_color = accent

        box = QLabel(mark)
        self._box_w = max(10, round((12 if small else 16) * self._scale))
        box.setFixedWidth(self._box_w)
        box.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        box.setStyleSheet(
            f"color: {box_color};"
            f"font-size: {max(9, size - 2)}px; background: transparent;"
        )

        text = QLabel(task.text)
        text.setWordWrap(True)
        text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        text.setFont(_font(size, strike=task.done))
        if task.done:
            color = t.text_done
        elif overdue:
            color = t.overdue
        elif muted:
            color = t.text_dim
        elif task.depth == 0:
            color = t.text if not small else t.text_soft
        elif task.depth == 1:
            color = t.text_soft
        else:
            color = t.text_dim
        text.setStyleSheet(f"color: {color}; background: transparent;")

        layout.addWidget(box)
        layout.addWidget(text, 1)

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        if self._hover:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(*self._theme.hover))
            painter.drawRoundedRect(self.rect(), 7, 7)
        super().paintEvent(event)

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        self.pressed.emit()
        # 只有点勾选框才切换完成状态。
        if event.pos().x() <= self._box_w + round(6 * self._scale):
            self.toggled.emit(self.task.id, not self.task.done)


class Panel(QWidget):
    task_toggled = pyqtSignal(str, bool)
    height_changed = pyqtSignal(int)
    resized = pyqtSignal(int, int)
    pinned_changed = pyqtSignal(bool)
    drag_started = pyqtSignal()
    drag_finished = pyqtSignal()

    BASE_WIDTH = 360
    MIN_WIDTH = 240
    MAX_WIDTH = 640

    def __init__(
        self,
        width: int,
        height: int,
        screen_geometry,
        animate_ms: int = 90,
        manual_height: bool = False,
        theme: Theme | None = None,
    ):
        super().__init__(None)
        self.theme = theme or get_theme(None)
        self._width = width
        self._height = height
        self._scale = max(0.75, min(width / self.BASE_WIDTH, 1.7))
        # 配置里存了高度 = 用户定过的尺寸，不要再用自动高度覆盖它
        self._explicit_height = manual_height
        self._manual_size = manual_height
        self._drag_dy = 0
        self._dragging = False
        self._pinned = False
        self._content_key = None
        self._accent_override = None
        self._last_view = None
        self._last_meta = None
        self._animate_ms = animate_ms
        self._shown = False
        self._screen_geo = screen_geometry
        self._min_h = 200
        self._max_h = height
        self._accent = ACCENT
        self._level = "ok"
        self._grips_ready = False

        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.NoFocus)
        self.setGeometry(
            screen_geometry.x() + screen_geometry.width() - width,
            screen_geometry.y() + (screen_geometry.height() - height) // 2,
            width,
            height,
        )

        self._build_ui()
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
        self._anim = QPropertyAnimation(self.card, b"pos", self)
        self._anim.setDuration(animate_ms)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.finished.connect(self._place_grips)

    # ---------- 尺寸 / 缩放 ----------

    def px(self, base: float) -> int:
        """按当前缩放换算一个像素尺寸。"""
        return max(6, round(base * self._scale))

    def _place_grips(self) -> None:
        """两个把手贴在 card 左上/左下角，跟着 card 的位置走。"""
        if not self._grips_ready:
            return
        size = self.px(14)
        self._grip_tl.setGeometry(0, 0, size, size)
        self._grip_bl.setGeometry(0, self.card.height() - size, size, size)
        for grip in (self._grip_tl, self._grip_bl):
            grip.raise_()

    def drag_resize(self, corner: str, start, start_geo, now) -> None:
        """拖左边缘：右边固定；左上角拖 → 下边固定，左下角拖 → 上边固定。"""
        # 一开拖就交给用户，否则 render 触发的 fit_height 会跟拖拽打架
        self._manual_size = True
        if not self._dragging:
            self._dragging = True
            self.drag_started.emit()
        dx = now.x() - start.x()
        dy = now.y() - start.y()

        width = max(self.MIN_WIDTH, min(start_geo.width() - dx, self.MAX_WIDTH))
        max_h = max(self._min_h, self._screen_geo.height() - self.px(24))
        if corner == "tl":
            height = max(self._min_h, min(start_geo.height() - dy, max_h))
            top = start_geo.y() + start_geo.height() - height
        else:
            height = max(self._min_h, min(start_geo.height() + dy, max_h))
            top = start_geo.y()

        right = self._screen_geo.x() + self._screen_geo.width()
        self._apply_geometry(right - width, top, width, height)
        self._drag_dy = dy

        scale = max(0.75, min(width / self.BASE_WIDTH, 1.7))
        if abs(scale - self._scale) >= 0.02:
            self._scale = scale
            self._restyle()
            if self._last_view is not None:
                self.render(self._last_view, self._last_meta or {})

    def abort_drag(self) -> None:
        """兜底：鼠标已经松开但没收到 release（比如在别的窗口上松手）。"""
        if self._dragging:
            self._dragging = False
            self.drag_finished.emit()

    def end_resize(self) -> None:
        if self._dragging:
            self._dragging = False
            self.drag_finished.emit()
        # 只拖宽不拖高的话，交回自动高度，别把面板永久钉死
        if abs(self._drag_dy) > 2:
            self._explicit_height = True
        self._manual_size = self._explicit_height
        self._max_h = max(self._height, self._max_h)
        self.resized.emit(self._width, self._height)
        if not self._manual_size:
            self.fit_height()

    def set_theme(self, theme: Theme) -> None:
        """换配色：重刷卡片/滚动条样式，再把当前内容重画一遍。"""
        if theme is self.theme:
            return
        self.theme = theme
        self.card.setStyleSheet(card_qss(theme))
        self.scroll.setStyleSheet(scroll_qss(theme))
        self._restyle()
        if self._last_view is not None:
            self.render(self._last_view, self._last_meta or {})

    def _apply_geometry(self, x: int, y: int, width: int, height: int) -> None:
        self._width = width
        self._height = height
        self.setGeometry(x, y, width, height)
        self.card.setGeometry(0 if self._shown else width, 0, width, height)
        self._place_grips()

    # ---------- 构建 ----------

    def _build_ui(self):
        self.card = QFrame(self)
        self.card.setObjectName("card")
        self.card.setStyleSheet(card_qss(self.theme))
        self.card.setGeometry(self._width, 0, self._width, self._height)

        root = QVBoxLayout(self.card)
        root.setContentsMargins(18, 14, 14, 10)
        root.setSpacing(0)

        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 10)
        left = QVBoxLayout()
        left.setSpacing(2)
        self.headline = QLabel("—")
        self.headline.setStyleSheet(
            f"color:{self.theme.text}; font-size:17px; font-weight:600;"
            f"font-family:{TIMESTAMP_FONT}; background:transparent;"
        )
        self.meta = QLabel("—")
        self.meta.setStyleSheet(f"color:{self.theme.text_faint}; font-size:11px; background:transparent;")
        left.addWidget(self.headline)
        left.addWidget(self.meta)
        self.clock = QLabel("--:--")
        self.clock.setStyleSheet(f"color:{self.theme.text_dim}; font-size:12px; background:transparent;")
        self.clock.setAlignment(Qt.AlignRight | Qt.AlignTop)
        head.addLayout(left, 1)
        head.addWidget(self.clock)
        root.addLayout(head)

        self.current_block = QFrame()
        self.current_block.setObjectName("currentBlock")
        self.current_block.setStyleSheet(current_block_qss(self.theme, theme_accent(self.theme, ACCENT)))
        self.current_box = QVBoxLayout(self.current_block)
        self.current_box.setContentsMargins(10, 9, 10, 9)
        self.current_box.setSpacing(7)
        root.addWidget(self.current_block)

        self.unknown_label = QLabel("未识别时间")
        self.unknown_label.setStyleSheet(
            f"color:{self.theme.text_faint}; font-size:10px; background:transparent; margin-bottom:2px;"
        )
        self.unknown_label.hide()
        root.addWidget(self.unknown_label)

        self.unknown_box = QVBoxLayout()
        self.unknown_box.setContentsMargins(0, 0, 0, 10)
        self.unknown_box.setSpacing(5)
        root.addLayout(self.unknown_box)

        self.divider_widget = QWidget()
        self.divider_widget.setStyleSheet("background: transparent;")
        divider = QHBoxLayout(self.divider_widget)
        divider.setContentsMargins(0, 0, 0, 8)
        divider.setSpacing(8)
        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet(f"background: {self.theme.divider};")
        self.section_label = QLabel("今天全部")
        self.section_label.setStyleSheet(
            f"color:{self.theme.text_faint}; font-size:10px; letter-spacing:1px; background:transparent;"
        )
        self.counts = QLabel("")
        self.counts.setStyleSheet(f"color:{self.theme.text_faint}; font-size:10px; background:transparent;")
        divider.addWidget(line, 1)
        divider.addWidget(self.section_label)
        divider.addWidget(self.counts)
        root.addWidget(self.divider_widget)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setStyleSheet(scroll_qss(self.theme))
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.all_host = QWidget()
        self.all_host.setStyleSheet("background: transparent;")
        self.all_box = QVBoxLayout(self.all_host)
        self.all_box.setContentsMargins(0, 0, 4, 0)
        self.all_box.setSpacing(1)
        self.all_box.addStretch(1)
        self.scroll.setWidget(self.all_host)
        root.addWidget(self.scroll, 1)

        foot = QHBoxLayout()
        foot.setContentsMargins(0, 8, 0, 0)
        foot.setSpacing(6)
        self.dot = QLabel("●")
        self.dot.setStyleSheet(f"color:{self.theme.ok}; font-size:8px; background:transparent;")
        self.status = QLabel("正在读取…")
        self.status.setStyleSheet(
            f"color:{self.theme.text_faint}; font-size:10px; font-weight:600; background:transparent;"
        )
        self.status.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        # 状态放右下角：时间在前、来源在后
        foot.addStretch(1)
        foot.addWidget(self.status)
        foot.addWidget(self.dot)
        root.addLayout(foot)

        # 左边缘的两个缩放把手
        self._grip_tl = _Grip(self, "tl", self.card)
        self._grip_bl = _Grip(self, "bl", self.card)
        self._grips_ready = True
        self._place_grips()
        self._restyle()

    def _restyle(self) -> None:
        """把字号/间距按当前 scale 重新算一遍。"""
        px = self.px
        self.headline.setStyleSheet(
            f"color:{self.theme.text}; font-size:{px(18)}px; font-weight:600;"
            f"font-family:{TIMESTAMP_FONT}; background:transparent;"
        )
        self.meta.setStyleSheet(f"color:{self.theme.text_faint}; font-size:{px(11)}px; background:transparent;")
        self.clock.setStyleSheet(f"color:{self.theme.text_dim}; font-size:{px(12)}px; background:transparent;")
        self.unknown_label.setStyleSheet(
            f"color:{self.theme.text_faint}; font-size:{px(10)}px; background:transparent; margin-bottom:2px;"
        )
        self.section_label.setStyleSheet(
            f"color:{self._accent}; font-size:{px(10)}px; letter-spacing:1px; background:transparent;"
        )
        self.counts.setStyleSheet(f"color:{self.theme.text_faint}; font-size:{px(10)}px; background:transparent;")
        self.status.setStyleSheet(
            f"color:{self.theme.text_faint}; font-size:{px(10)}px; font-weight:600;"
            f"background:transparent;"
        )
        self.dot.setStyleSheet(
            f"color:{self._dot_color()}; font-size:{px(8)}px; background:transparent;"
        )
        layout = self.card.layout()
        if layout is not None:
            layout.setContentsMargins(px(18), px(14), px(14), px(10))
        self.current_box.setContentsMargins(px(10), px(9), px(10), px(9))
        self.current_box.setSpacing(px(7))
        self.all_box.setContentsMargins(0, 0, px(4), 0)
        self.all_box.setSpacing(max(1, px(1)))
        self._place_grips()

    def _dot_color(self) -> str:
        return {"ok": self.theme.ok, "warn": self.theme.warn}.get(self._level, self.theme.overdue)

    # ---------- 动画 ----------

    def set_animate_ms(self, ms: int) -> None:
        self._animate_ms = max(40, int(ms))
        self._anim.setDuration(self._animate_ms)

    def set_shown(self, shown: bool):
        if shown == self._shown:
            return
        self._shown = shown
        self.setAttribute(Qt.WA_TransparentForMouseEvents, not shown)
        self._anim.stop()
        self._anim.setStartValue(self.card.pos())
        self._anim.setEndValue(QPoint(0 if shown else self._width, 0))
        self._anim.start()

    # ---------- 聚焦（钉住不收回） ----------

    def is_pinned(self) -> bool:
        return self._pinned

    def pin(self, state: bool) -> None:
        """钉住：拿焦点、鼠标移开也不收回；在远处点一下或按 Esc 才解除。

        要点（都踩过坑）：
        - 激活窗口必须推迟到下一轮事件循环，不能在鼠标事件里直接做；
        - 窗口本身用 WS_EX_NOACTIVATE 保持"点得到但不抢焦点"，
          只有钉住时才临时摘掉，解除时还原。
        """
        if state == self._pinned:
            return
        self._pinned = state
        if state:
            QTimer.singleShot(0, self._activate_if_pinned)
        else:
            set_no_activate(self, True)
            self.setFocusPolicy(Qt.NoFocus)
        self.pinned_changed.emit(state)

    def _activate_if_pinned(self) -> None:
        if not self._pinned:
            return
        set_no_activate(self, False)
        self.setFocusPolicy(Qt.StrongFocus)
        self.activateWindow()
        raise_foreground(self)
        self.setFocus()

    def eventFilter(self, obj, event):
        """落在面板里的任何一次按下都算"点它"，不依赖哪个子控件接住事件。"""
        if event.type() in (QEvent.MouseButtonPress, QEvent.MouseButtonDblClick):
            widget = obj if isinstance(obj, QWidget) else None
            if widget is not None and (widget is self or self.isAncestorOf(widget)):
                self.pin(True)
        return False

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.pin(True)
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.pin(False)
            return
        super().keyPressEvent(event)

    # ---------- 渲染 ----------

    def _clear(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _row(self, task: Task, *, small=False, muted=False, accent=ACCENT, overdue=False):
        row = TaskRow(
            task,
            theme=self.theme,
            small=small,
            muted=muted,
            accent=accent,
            overdue=overdue,
            scale=self._scale,
        )
        row.toggled.connect(self.task_toggled.emit)
        row.pressed.connect(lambda: self.pin(True))
        return row

    def _hint(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setStyleSheet(
            f"color:{self.theme.text_faint}; font-size:{self.px(12)}px; background:transparent;"
        )
        return label

    def _group_header(self, label: str, accent: str, *, first: bool):
        """分组标题：一个带底色的小色块 + 上方的细分隔线。"""
        host = QWidget()
        host.setObjectName("groupHead")
        host.setAttribute(Qt.WA_StyledBackground, True)
        host.setStyleSheet(group_head_qss(self.theme, first))
        row = QHBoxLayout(host)
        row.setContentsMargins(0, self.px(9) if not first else self.px(3), 0, self.px(5))
        row.setSpacing(self.px(6))

        chip = QLabel(label)
        chip.setStyleSheet(
            f"color:{accent}; font-size:{self.px(11)}px; letter-spacing:0.4px;"
            f"font-family:{TIMESTAMP_FONT};"
            f"background: {self.theme.chip_bg}; border-radius:4px;"
            f"padding:{self.px(2)}px {self.px(7)}px;"
        )
        row.addWidget(chip)
        row.addStretch(1)
        return host

    def present(self, view: View, meta: dict, accent_override: str | None = None) -> None:
        def rows(tasks):
            return tuple((task.id, task.text, task.done, task.depth) for task in tasks)

        key = (
            view.headline, view.now.date(), view.mode, view.open_count, view.done_count,
            view.show_bottom, view.section_label, view.unknown_label, view.overdue_ids,
            rows(view.current), rows(view.unknown),
            tuple((group.label, rows(group.tasks)) for group in view.today_groups),
            accent_override,
        )
        self._accent_override = accent_override
        if self._content_key != key:
            self.render(view, meta)
            self._content_key = key
        else:
            self._last_view = view
            self._last_meta = meta
            self._render_status(view, meta)

    def render(self, view: View, meta: dict):
        accent = self._accent_override or theme_accent(self.theme, MODE_ACCENTS[view.mode])
        self._last_view = view
        self._last_meta = meta
        self._accent = accent
        self._level = meta.get("level", "ok")
        self.headline.setText(view.headline)
        self.meta.setText(f"{view.weekday} · {view.now.month}月{view.now.day}日")
        self.current_block.setStyleSheet(current_block_qss(self.theme, accent))
        self._restyle()

        self._clear(self.current_box)
        if view.current:
            for task in view.current:
                self.current_box.addWidget(
                    self._row(
                        task,
                        accent=accent,
                        overdue=task.id in view.overdue_ids,
                    )
                )
        elif view.mode == "memo":
            self.current_box.addWidget(self._hint("还没有任何事项"))
        else:
            self.current_box.addWidget(self._hint("这个时间段没有安排"))

        self._clear(self.unknown_box)
        self.unknown_label.setText(view.unknown_label)
        self.unknown_label.setVisible(bool(view.unknown))
        for task in view.unknown:
            self.unknown_box.addWidget(self._row(task, small=True, muted=True, accent=accent))

        self._clear(self.all_box)
        if view.today_groups:
            shown = 0
            for group in view.today_groups:
                if not group.tasks:
                    continue
                self.all_box.addWidget(self._group_header(group.label, accent, first=shown == 0))
                shown += 1
                for task in group.tasks:
                    self.all_box.addWidget(
                        self._row(
                            task,
                            small=True,
                            accent=accent,
                            overdue=task.id in view.overdue_ids,
                        )
                    )
        elif view.current:
            self.all_box.addWidget(self._hint("上面已经列全了"))
        else:
            self.all_box.addWidget(self._hint("今天没有安排"))
        self.all_box.addStretch(1)

        self.section_label.setText(view.section_label)
        self.counts.setText(f"未完成 {view.open_count} / 已完成 {view.done_count}")

        # 备忘单模式没有下方列表：把统计挪到状态行
        self.divider_widget.setVisible(view.show_bottom)
        self.scroll.setVisible(view.show_bottom)

        self._render_status(view, meta)
        QTimer.singleShot(0, self.fit_height)

    def _render_status(self, view: View, meta: dict) -> None:
        level = meta.get("level", "ok")
        self._level = level
        self.dot.setStyleSheet(
            f"color:{self._dot_color()}; font-size:{self.px(8)}px; background:transparent;"
        )
        status = meta.get("status", "")
        if not view.show_bottom:
            status = f"未完成 {view.open_count} / 已完成 {view.done_count} · {status}"
        if view.note:
            status = f"{view.note} · {status}" if status else view.note
        self.status.setText(status)
        self.status.setToolTip(meta.get("detail", ""))

    def render_error(self, message: str, detail: str = ""):
        self._content_key = None
        self._last_view = None
        self._level = "error"
        self.headline.setText("读不到数据")
        self.meta.setText("数据源异常")
        self._clear(self.current_box)
        self.current_box.addWidget(self._hint(message))
        self._clear(self.unknown_box)
        self.unknown_label.hide()
        self._clear(self.all_box)
        self.all_box.addStretch(1)
        self.counts.setText("")
        self.dot.setStyleSheet(
            f"color:{self._dot_color()}; font-size:{self.px(8)}px; background:transparent;"
        )
        self.status.setText(detail or message)
        self.status.setToolTip(detail)
        QTimer.singleShot(0, self.fit_height)

    def fit_height(self) -> None:
        if self._manual_size:
            # 用户手动调过大小：高度由用户说了算，内容多了走滚动
            self.card.setGeometry(0 if self._shown else self._width, 0, self._width, self._height)
            return
        self.all_host.adjustSize()
        content = self.all_host.sizeHint().height()
        self.scroll.setFixedHeight(max(28, min(content, self.px(380))))
        self.card.layout().activate()
        wanted = self.card.layout().sizeHint().height()
        target = max(self._min_h, min(wanted, self._max_h))
        if target == self._height:
            return
        self._height = target
        geo = self._screen_geo
        self.setGeometry(
            geo.x() + geo.width() - self._width,
            geo.y() + (geo.height() - target) // 2,
            self._width,
            target,
        )
        self.card.setGeometry(0 if self._shown else self._width, 0, self._width, target)
        self.height_changed.emit(target)

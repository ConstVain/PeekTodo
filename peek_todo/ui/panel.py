"""右边缘滑出的待办面板（PyQt5）。

窗口固定在主屏右边缘、整块透明；内部 card 通过动画滑入。
滑出后窗口接收鼠标（可点击但永不抢焦点），缩回后整窗穿透。
"""

from __future__ import annotations

from PyQt5.QtCore import QEasingCurve, QPoint, QPropertyAnimation, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QPainter
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..model import Task
from ..selection import View

ACCENT = "#7aa2ff"
DIM = "#9aa1ad"
FAINT = "#6b7280"

CARD_QSS = """
#card {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                 stop:0 #24262d, stop:0.38 #1a1b20, stop:1 #14151a);
    border-top-left-radius: 14px;
    border-bottom-left-radius: 14px;
    border-left: 1px solid #2e313a;
}
"""

SCROLL_QSS = """
QScrollArea { background: transparent; border: none; }
QScrollBar:vertical { background: transparent; width: 4px; margin: 0; }
QScrollBar::handle:vertical { background: rgba(255,255,255,40); border-radius: 2px; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
"""


def _font(size: int, strike: bool = False) -> QFont:
    font = QFont("Microsoft YaHei UI")
    font.setPixelSize(size)
    font.setStrikeOut(strike)
    return font


class TaskRow(QWidget):
    toggled = pyqtSignal(str)
    opened = pyqtSignal(str)

    def __init__(self, task: Task, *, small: bool = False, muted: bool = False, parent=None):
        super().__init__(parent)
        self.task = task
        self._hover = False
        self._small = small
        self.setAttribute(Qt.WA_Hover, True)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("点方框勾选（仅面板） · 点文字打开源")

        layout = QHBoxLayout(self)
        # 子项缩进：一级子项退一格，二级再退一格，视觉上明确从属关系
        indent = min(task.depth, 3) * (16 if small else 20)
        layout.setContentsMargins(indent, 0, 0, 0)
        layout.setSpacing(8)

        if task.done:
            mark = "✓" if small else "☑"
        else:
            mark = "·" if small else "☐"

        # 层级越深字号掉得越狠：0 -> 16/12，1 -> 11/9，2+ -> 9/8
        if small:
            size = 12 if task.depth == 0 else 9 if task.depth == 1 else 8
        else:
            size = 16 if task.depth == 0 else 11 if task.depth == 1 else 9

        box = QLabel(mark)
        box.setFixedWidth(12 if small else 16)
        box.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        box.setStyleSheet(
            f"color: {'#565d69' if task.done else (FAINT if (small or muted or task.depth > 0) else ACCENT)};"
            f"font-size: {max(9, size - 2)}px; background: transparent;"
        )

        text = QLabel(task.text)
        text.setWordWrap(True)
        text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        text.setFont(_font(size, strike=task.done))
        if task.done:
            color = "#565d69"
        elif muted:
            color = DIM
        elif task.depth == 0:
            color = "#eef0f4" if not small else "#d8dce4"
        elif task.depth == 1:
            color = "#b6bcc7"
        else:
            color = DIM
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
            painter.setBrush(QColor(255, 255, 255, 16))
            painter.drawRoundedRect(self.rect(), 7, 7)
        super().paintEvent(event)

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        if event.pos().x() <= (12 if self._small else 16) + 6:
            self.toggled.emit(self.task.id)
        else:
            self.opened.emit(self.task.id)


class Panel(QWidget):
    open_source_requested = pyqtSignal()
    task_toggled = pyqtSignal(str)
    height_changed = pyqtSignal(int)

    def __init__(self, width: int, height: int, screen_geometry, animate_ms: int = 90):
        super().__init__(None)
        self._width = width
        self._height = height
        self._animate_ms = animate_ms
        self._shown = False
        self._screen_geo = screen_geometry
        self._min_h = 200
        self._max_h = height

        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowDoesNotAcceptFocus
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
        self._anim = QPropertyAnimation(self.card, b"pos", self)
        self._anim.setDuration(animate_ms)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

    # ---------- 构建 ----------

    def _build_ui(self):
        self.card = QFrame(self)
        self.card.setObjectName("card")
        self.card.setStyleSheet(CARD_QSS)
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
            "color:#eef0f4; font-size:17px; font-weight:600; background:transparent;"
        )
        self.meta = QLabel("—")
        self.meta.setStyleSheet(f"color:{FAINT}; font-size:11px; background:transparent;")
        left.addWidget(self.headline)
        left.addWidget(self.meta)
        self.clock = QLabel("--:--")
        self.clock.setStyleSheet(f"color:{DIM}; font-size:12px; background:transparent;")
        self.clock.setAlignment(Qt.AlignRight | Qt.AlignTop)
        head.addLayout(left, 1)
        head.addWidget(self.clock)
        root.addLayout(head)

        self.current_box = QVBoxLayout()
        self.current_box.setContentsMargins(0, 0, 0, 10)
        self.current_box.setSpacing(7)
        root.addLayout(self.current_box)

        self.unknown_label = QLabel("未识别时间")
        self.unknown_label.setStyleSheet(
            f"color:{FAINT}; font-size:10px; background:transparent; margin-bottom:2px;"
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
        line.setStyleSheet("background: rgba(255,255,255,22);")
        self.section_label = QLabel("今天全部")
        self.section_label.setStyleSheet(
            f"color:{FAINT}; font-size:10px; letter-spacing:1px; background:transparent;"
        )
        self.counts = QLabel("")
        self.counts.setStyleSheet(f"color:{FAINT}; font-size:10px; background:transparent;")
        divider.addWidget(line, 1)
        divider.addWidget(self.section_label)
        divider.addWidget(self.counts)
        root.addWidget(self.divider_widget)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setStyleSheet(SCROLL_QSS)
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
        self.dot.setStyleSheet("color:#4ade80; font-size:8px; background:transparent;")
        self.status = QLabel("正在读取…")
        self.status.setStyleSheet(f"color:{FAINT}; font-size:10px; background:transparent;")
        foot.addWidget(self.dot)
        foot.addWidget(self.status, 1)
        root.addLayout(foot)

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

    # ---------- 渲染 ----------

    def _clear(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _row(self, task: Task, *, small=False, muted=False):
        row = TaskRow(task, small=small, muted=muted)
        row.toggled.connect(self.task_toggled.emit)
        row.opened.connect(lambda _tid: self.open_source_requested.emit())
        return row

    def _hint(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setStyleSheet(f"color:{FAINT}; font-size:12px; background:transparent;")
        return label

    def render(self, view: View, meta: dict):
        self.headline.setText(view.headline)
        self.meta.setText(f"{view.weekday} · {view.now.month}月{view.now.day}日")

        self._clear(self.current_box)
        if view.current:
            for task in view.current:
                self.current_box.addWidget(self._row(task))
        elif view.mode == "A":
            self.current_box.addWidget(self._hint("这个时间段没有安排"))

        self._clear(self.unknown_box)
        self.unknown_label.setText(view.unknown_label)
        self.unknown_label.setVisible(bool(view.unknown))
        for task in view.unknown:
            self.unknown_box.addWidget(self._row(task, small=True, muted=True))

        self._clear(self.all_box)
        if view.today_groups:
            for group in view.today_groups:
                if not group.tasks:
                    continue
                label = QLabel(group.label)
                label.setStyleSheet(
                    f"color:{FAINT}; font-size:10px; margin-top:6px; background:transparent;"
                )
                self.all_box.addWidget(label)
                for task in group.tasks:
                    self.all_box.addWidget(self._row(task, small=True))
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

        level = meta.get("level", "ok")
        self.dot.setStyleSheet(
            "color:#4ade80; font-size:8px; background:transparent;"
            if level == "ok"
            else "color:#f0b45f; font-size:8px; background:transparent;"
            if level == "warn"
            else "color:#f87171; font-size:8px; background:transparent;"
        )
        status = meta.get("status", "")
        if not view.show_bottom:
            status = f"未完成 {view.open_count} / 已完成 {view.done_count} · {status}"
        if view.note:
            status = f"{view.note} · {status}" if status else view.note
        self.status.setText(status)
        self.status.setToolTip(meta.get("detail", ""))

        QTimer.singleShot(0, self.fit_height)

    def render_error(self, message: str, detail: str = ""):
        self.headline.setText("读不到数据")
        self.meta.setText("数据源异常")
        self._clear(self.current_box)
        self.current_box.addWidget(self._hint(message))
        self._clear(self.unknown_box)
        self.unknown_label.hide()
        self._clear(self.all_box)
        self.all_box.addStretch(1)
        self.counts.setText("")
        self.dot.setStyleSheet("color:#f87171; font-size:8px; background:transparent;")
        self.status.setText(detail or message)
        self.status.setToolTip(detail)
        QTimer.singleShot(0, self.fit_height)

    def fit_height(self) -> None:
        self.all_host.adjustSize()
        content = self.all_host.sizeHint().height()
        self.scroll.setFixedHeight(max(28, min(content, 380)))
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

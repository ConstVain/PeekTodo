"""连接 Qt 事件、窗口和应用流程。"""

from __future__ import annotations

import time
import traceback
from datetime import datetime
from functools import wraps

from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QCursor, QIcon
from PyQt5.QtWidgets import QAction, QApplication, QMenu, QMessageBox, QSystemTrayIcon

from ..application.session import TaskSession
from ..domain.edge import EdgeDetector, Rect
from ..sources.base import SourceError
from ..storage.config import Config
from ..storage.paths import assets_dir, state_path
from ..windows import autostart
from ..windows.win32 import left_button_down, set_no_activate
from .panel import Panel, PanelSection
from .settings import SettingsDialog
from .settings_flow import save_settings
from .theme import get as get_theme, panel_accent


def far_from_panel(rect, pos, pad: int = 60) -> bool:
    """点击位置是否离面板足够远（用来判断"点到别处去了"）。"""
    return not rect.adjusted(-pad, -pad, pad, pad).contains(pos)


def safe_slot(func):
    """定时器/菜单槽里抛异常会让 PyQt5 直接 abort，包一层只记日志。

    之前踩过：槽里一个 NameError 就整进程闪退，日志里只剩 0xc0000409。
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            return None

    return wrapper


class DesktopController:
    def __init__(self, app: QApplication, cfg: Config, force_shown: bool = False):
        self.app = app
        self.forced = force_shown
        self.cfg = cfg

        panel_cfg = cfg.panel
        self.width = int(panel_cfg["width"])
        geo = app.primaryScreen().geometry()
        self.screen = Rect(geo.x(), geo.y(), geo.width(), geo.height())
        default_height = min(
            int(geo.height() * float(panel_cfg["heightRatio"])),
            int(panel_cfg["maxHeight"]),
        )
        height = int(panel_cfg.get("height") or default_height)

        self.panel = Panel(
            self.width,
            height,
            geo,
            animate_ms=int(panel_cfg["animateMs"]),
            manual_height=bool(panel_cfg.get("height")),
            theme=get_theme(panel_cfg.get("theme"), panel_cfg.get("colors")),
        )
        self.panel.task_toggled.connect(self.on_toggle)
        self.panel.add_section_requested.connect(self.add_section)
        self.panel.remove_section_requested.connect(self.remove_section)
        self.panel.show()
        set_no_activate(self.panel, True)

        self.detector = EdgeDetector(
            panel_width=self.width,
            panel_height=height,
            hot_zone=int(panel_cfg["hotZone"]),
            hide_delay_ms=int(panel_cfg["hideDelayMs"]),
            hot_zone_pad=int(panel_cfg.get("hotZonePad", 0)),
        )
        self.panel.height_changed.connect(self._on_height_changed)
        self.panel.resized.connect(self._on_panel_resized)
        self._was_down = False
        self._dragging = False
        self.panel.drag_started.connect(self._on_drag_started)
        self.panel.drag_finished.connect(self._on_drag_finished)
        self._sync_detector()

        self.session = TaskSession(cfg, state_path())
        self.refresh()

        self.tick_timer = QTimer()
        self.tick_timer.timeout.connect(self.tick)
        self.tick_timer.start(int(panel_cfg["pollMs"]))

        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.refresh)
        self.refresh_timer.start(int(cfg.behavior["refreshMs"]))

        self.clock_timer = QTimer()
        self.clock_timer.timeout.connect(self.update_clock)
        self.clock_timer.start(10000)
        self.update_clock()

        if force_shown:
            self.panel.set_shown(True)

        self.make_tray()

    @safe_slot
    def refresh(self) -> None:
        snapshot = self.session.refresh(datetime.now())
        if snapshot.view is None:
            self.panel.render_error("读不到数据", snapshot.detail)
        else:
            panel_cfg = self.cfg.panel
            color = panel_accent(self.panel.theme, panel_cfg, snapshot.view.mode)
            sections = tuple(
                PanelSection(section.title, section.view, panel_accent(self.panel.theme, panel_cfg, section.view.mode))
                for section in snapshot.sections
            )
            self.panel.present(snapshot.view, snapshot.meta, color, sections)

    def update_clock(self) -> None:
        self.panel.clock.setText(datetime.now().strftime("%H:%M"))

    @safe_slot
    def on_toggle(self, task_id: str, done: bool) -> None:
        try:
            self.session.set_done(task_id, done)
        except OSError as exc:
            QMessageBox.warning(self.panel, "勾选保存失败", str(exc))
            return
        self.refresh()

    @safe_slot
    def tick(self) -> None:
        if self.forced:
            return
        if self._dragging:
            # 正在拖角落调大小：既不收回，也不解除钉住。
            # 但如果鼠标早就松了（松在别的窗口上），要自己恢复，否则面板会一直卡住不动
            if not left_button_down():
                self.panel.abort_drag()
                self._dragging = False
            return
        if self.panel.is_pinned():
            # 钉住期间不自动收回；只在离面板够远的空白处单击一下才解除
            self._maybe_unpin()
            return
        pos = QCursor.pos()
        shown, _ = self.detector.update(
            (pos.x(), pos.y()), self.screen, time.monotonic() * 1000
        )
        self.panel.set_shown(shown)

    def _on_drag_started(self) -> None:
        self._dragging = True

    def _on_drag_finished(self) -> None:
        self._dragging = False

    def _maybe_unpin(self) -> None:
        down = left_button_down()
        pressed_edge = down and not self._was_down
        self._was_down = down
        if not pressed_edge:
            return
        if far_from_panel(self.panel.geometry(), QCursor.pos()):
            self.panel.pin(False)

    def _on_height_changed(self, height: int) -> None:
        self.detector.panel_height = height
        self._sync_detector()

    def _on_panel_resized(self, width: int, height: int) -> None:
        """用户拖拽改变了面板大小：同步命中区域并记住。"""
        self.width = width
        rect = self.panel.geometry()
        self.detector.set_geometry(rect.x(), rect.y(), width, height)
        panel_cfg = self.cfg.raw.setdefault("panel", {})
        panel_cfg["width"] = width
        panel_cfg["height"] = height
        try:
            self.cfg.save()
        except OSError:
            pass

    def _sync_detector(self) -> None:
        rect = self.panel.geometry()
        self.detector.set_geometry(rect.x(), rect.y(), rect.width(), rect.height())

    # ---------- 托盘 ----------

    def make_tray(self) -> None:
        icon_path = assets_dir() / "tray.png"
        icon = QIcon(str(icon_path)) if icon_path.exists() else QIcon()
        self.tray = QSystemTrayIcon(icon, self.app)
        self.tray.setToolTip("PeekTodo · 贴右边缘滑出")

        menu = QMenu()
        act_refresh = QAction("立即刷新", menu)
        act_refresh.triggered.connect(lambda: self.refresh())

        act_setup = QAction("设置…", menu)
        act_setup.triggered.connect(lambda: self.rerun_wizard())

        act_auto = QAction("开机自启", menu)
        act_auto.setCheckable(True)
        act_auto.setChecked(autostart.is_enabled())
        act_auto.toggled.connect(self._toggle_autostart)

        act_quit = QAction("退出", menu)
        act_quit.triggered.connect(self.app.quit)

        menu.addAction(act_refresh)
        menu.addAction(act_setup)
        menu.addSeparator()
        menu.addAction(act_auto)
        menu.addSeparator()
        menu.addAction(act_quit)

        self.tray.setContextMenu(menu)
        self.tray.show()

    @safe_slot
    def _toggle_autostart(self, enabled: bool) -> None:
        try:
            autostart.toggle(enabled)
        except OSError as exc:
            QMessageBox.warning(self.panel, "无法更新开机自启", str(exc))

    def _save_theme(self, theme_key: str) -> None:
        if self.cfg.panel["theme"] == theme_key:
            return
        panel = {**(self.cfg.raw.get("panel") or {}), "theme": theme_key}
        updated = Config(self.cfg.path, {**self.cfg.raw, "panel": panel})
        try:
            updated.save()
        except OSError as exc:
            QMessageBox.warning(self.panel, "配色保存失败", str(exc))
            return
        self.cfg.raw["panel"] = panel
        self.panel.set_theme(get_theme(theme_key, panel.get("colors")))
        self.refresh()

    def add_section(self) -> None:
        self.rerun_wizard(add_section=True)

    @safe_slot
    def remove_section(self, index: int) -> None:
        sections = self.cfg.sections
        if not 0 <= index < len(sections):
            return
        sections.pop(index)
        mapping = {**self.cfg.mapping, "sections": sections}
        cfg = Config(self.cfg.path, {**self.cfg.raw, "mapping": mapping})
        try:
            cfg.save()
        except OSError as exc:
            QMessageBox.warning(self.panel, "移除区块失败", str(exc))
            return
        self.cfg = cfg
        self.session.remove_section(index)
        self.refresh()

    @safe_slot
    def rerun_wizard(self, *, add_section: bool = False) -> None:
        dialog = SettingsDialog(self.panel if add_section else None, add_section=add_section)
        try:
            dialog.prefill(self.cfg.raw, self.cfg.path.parent)
            if not add_section:
                dialog.theme_combo.setToolTip("选中配色后立即应用并保存")
                dialog.theme_selected.connect(self._save_theme)
            if dialog.exec_() != SettingsDialog.Accepted or not dialog.result_config:
                return
            cfg = Config(self.cfg.path, dialog.result_config)
        finally:
            dialog.deleteLater()
        try:
            session = TaskSession(cfg, state_path())
            if add_section:
                cfg.save()
            else:
                save_settings(cfg)
        except (OSError, ValueError, SourceError) as exc:
            QMessageBox.warning(self.panel, "保存失败", str(exc))
            return
        self.cfg = cfg
        self.session = session
        self.refresh_timer.setInterval(int(cfg.behavior["refreshMs"]))
        self.panel.set_theme(
            get_theme(cfg.panel.get("theme"), cfg.panel.get("colors"))
        )
        self.refresh()

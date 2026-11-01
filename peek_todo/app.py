"""PeekTodo 入口：窗口、托盘、边缘轮询、数据刷新。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from PyQt5.QtCore import QSharedMemory, Qt, QTimer
from PyQt5.QtGui import QCursor, QIcon
from PyQt5.QtWidgets import QAction, QApplication, QMenu, QSystemTrayIcon

from . import autostart
from .config import Config, build_mapping, build_source
from .doctor import main as doctor_main
from .edge import EdgeDetector, Rect
from .selection import build_view
from .sources.base import SourceError
from .state import LocalState
from .structure import map_document
from .ui.panel import Panel
from .ui.wizard import SetupWizard


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def config_path() -> Path:
    return app_dir() / "config.json"


def state_path() -> Path:
    return app_dir() / ".state.json"


def make_no_activate(panel: Panel) -> None:
    """WS_EX_NOACTIVATE + WS_EX_TOOLWINDOW：点得到，但永远不抢焦点、不进 Alt-Tab。"""
    try:
        import win32con
        import win32gui
    except ImportError:
        return
    try:
        hwnd = int(panel.winId())
        style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
        win32gui.SetWindowLong(
            hwnd,
            win32con.GWL_EXSTYLE,
            style | win32con.WS_EX_NOACTIVATE | win32con.WS_EX_TOOLWINDOW,
        )
    except Exception:  # noqa: BLE001
        pass


class Runner:
    def __init__(self, app: QApplication, cfg: Config, force_shown: bool = False):
        self.app = app
        self.forced = force_shown
        self.cfg = cfg

        panel_cfg = cfg.panel
        self.width = int(panel_cfg["width"])
        geo = app.primaryScreen().geometry()
        self.screen = Rect(geo.x(), geo.y(), geo.width(), geo.height())
        height = min(
            int(geo.height() * float(panel_cfg["heightRatio"])),
            int(panel_cfg["maxHeight"]),
        )

        self.panel = Panel(self.width, height, geo, animate_ms=int(panel_cfg["animateMs"]))
        self.panel.open_source_requested.connect(self.open_source)
        self.panel.task_toggled.connect(self.on_toggle)
        self.panel.show()
        make_no_activate(self.panel)

        self.detector = EdgeDetector(
            panel_width=self.width,
            panel_height=height,
            hot_zone=int(panel_cfg["hotZone"]),
            hide_delay_ms=int(panel_cfg["hideDelayMs"]),
            hot_zone_pad=int(panel_cfg.get("hotZonePad", 0)),
        )
        self.panel.height_changed.connect(self._on_height_changed)

        self._last_ok = None
        self.rebuild()
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

    # ---------- 数据 ----------

    def rebuild(self) -> None:
        """按当前配置重建数据源、映射与本地状态。"""
        self.source = build_source(self.cfg)
        self.mapping_cfg = build_mapping(self.cfg)
        key = self._source_key()
        self.state = LocalState(state_path(), key)

    def _source_key(self) -> str:
        source = self.cfg.source
        if source.get("type") == "mubu":
            return f"mubu:{source.get('docId')}"
        return f"markdown:{self.cfg.source_path()}"

    def refresh(self) -> None:
        try:
            fetch = self.source.fetch()
            result = map_document(fetch.tree, self.mapping_cfg)
            view = build_view(result, datetime.now(), self.cfg.periods, self.state)
        except SourceError as exc:
            self._render_failure(str(exc))
            return

        stamp = fetch.fetched_at.strftime("%H:%M")
        level = "warn" if (fetch.warnings or view.unknown) else "ok"
        status = f"{fetch.source_name} · {stamp}"
        if fetch.warnings:
            status += " · 数据偏旧"
        elif view.unknown:
            status += f" · {len(view.unknown)} 条未识别时间"

        meta = {
            "level": level,
            "status": status,
            "detail": "\n".join(fetch.warnings + view.issues),
        }
        self.panel.render(view, meta)
        self._last_ok = (view, meta)

    def _render_failure(self, message: str) -> None:
        if self._last_ok:
            view, meta = self._last_ok
            meta = {**meta, "level": "error", "status": "读取失败，显示上次数据", "detail": message}
            self.panel.render(view, meta)
        else:
            self.panel.render_error("读不到数据", message)

    def update_clock(self) -> None:
        self.panel.clock.setText(datetime.now().strftime("%H:%M"))

    # ---------- 交互 ----------

    def on_toggle(self, task_id: str) -> None:
        current = None
        if self._last_ok:
            view = self._last_ok[0]
            for task in view.current + view.unknown:
                if task.id == task_id:
                    current = task.done
                    break
        self.state.set_done(task_id, not (current or False))
        self.refresh()

    def open_source(self) -> None:
        source = self.cfg.source
        if source.get("type") == "markdown":
            path = self.cfg.source_path()
            if path and path.exists():
                os.startfile(str(path))  # noqa: S606 - 用户自己的文件
        elif source.get("type") == "mubu":
            exe = source.get("mubuExe")
            doc_id = source.get("docId", "")
            if exe and Path(exe).exists():
                subprocess.Popen([exe, f"shortcut-{doc_id}"], close_fds=True)

    def tick(self) -> None:
        if self.forced:
            return
        pos = QCursor.pos()
        shown, _ = self.detector.update(
            (pos.x(), pos.y()), self.screen, time.monotonic() * 1000
        )
        self.panel.set_shown(shown)

    def _on_height_changed(self, height: int) -> None:
        self.detector.panel_height = height

    # ---------- 托盘 ----------

    def make_tray(self) -> None:
        icon_path = app_dir() / "assets" / "tray.png"
        icon = QIcon(str(icon_path)) if icon_path.exists() else QIcon()
        self.tray = QSystemTrayIcon(icon, self.app)
        self.tray.setToolTip("PeekTodo · 贴右边缘滑出")

        menu = QMenu()
        act_refresh = QAction("立即刷新", menu)
        act_refresh.triggered.connect(self.refresh)

        act_setup = QAction("重新设置…", menu)
        act_setup.triggered.connect(self.rerun_wizard)

        act_auto = QAction("开机自启", menu)
        act_auto.setCheckable(True)
        act_auto.setChecked(autostart.is_enabled())
        act_auto.toggled.connect(self._toggle_autostart)

        act_open = QAction("打开数据源", menu)
        act_open.triggered.connect(self.open_source)

        act_quit = QAction("退出", menu)
        act_quit.triggered.connect(self.app.quit)

        menu.addAction(act_refresh)
        menu.addAction(act_setup)
        menu.addSeparator()
        menu.addAction(act_auto)
        menu.addAction(act_open)
        menu.addSeparator()
        menu.addAction(act_quit)

        self.tray.setContextMenu(menu)
        self.tray.show()

    def _toggle_autostart(self, enabled: bool) -> None:
        autostart.toggle(enabled)

    def rerun_wizard(self) -> None:
        wizard = SetupWizard()
        if wizard.exec_() != SetupWizard.Accepted or not wizard.result_config:
            return
        config_path().write_text(
            json.dumps(wizard.result_config, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        self.cfg = Config.load(config_path())
        self.rebuild()
        self.refresh()


def ensure_config(force: bool = False) -> Config | None:
    path = config_path()
    if path.exists() and not force:
        try:
            return Config.load(path)
        except (OSError, ValueError):
            pass
    wizard = SetupWizard()
    if wizard.exec_() != SetupWizard.Accepted or not wizard.result_config:
        return None
    path.write_text(
        json.dumps(wizard.result_config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return Config.load(path)


def single_instance_lock():
    """用文件锁做单实例：进程退出（哪怕崩溃）时由系统自动释放。

    不用 QSharedMemory——它会在进程异常残留时把后续启动全挡掉。
    """
    import msvcrt

    path = app_dir() / ".lock"
    try:
        handle = open(path, "a+")
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        return handle
    except OSError:
        return None


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if "--doctor" in argv:
        return doctor_main([])

    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("PeekTodo")

    lock = single_instance_lock()
    if lock is None:
        return 0

    cfg = ensure_config(force="--setup" in argv)
    if cfg is None:
        return 0

    runner = Runner(app, cfg, force_shown="--force-shown" in argv)
    _ = (runner, lock)
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())

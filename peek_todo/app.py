"""PeekTodo 入口：窗口、托盘、边缘轮询、数据刷新。"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QCursor, QIcon
from PyQt5.QtWidgets import QAction, QApplication, QMenu, QMessageBox, QSystemTrayIcon

from . import autostart
from .config import Config, build_mapping, build_source
from .doctor import main as doctor_main
from .edge import EdgeDetector, Rect
from .selection import ACCENT_PRESETS, build_view
from .sources.base import SourceError
from .opener import open_source as open_source_item
from .state import LocalState
from .structure import map_document
from .ui.panel import Panel
from .ui.settings import SettingsDialog


def assets_dir() -> Path:
    """图标等静态资源：跟着包走，安装后也能找到。"""
    return Path(__file__).resolve().parent / "assets"


def app_dir() -> Path:
    """配置和状态放哪。

    - 打包后：exe 所在目录（便携）
    - 源码运行：仓库根目录（能改配置、能调试）
    - pip 安装后：%APPDATA%\\PeekTodo（包目录通常无写权限）
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent

    package_root = Path(__file__).resolve().parent.parent
    if (package_root / "pyproject.toml").exists() or (package_root / ".git").exists():
        return package_root

    target = Path(os.environ.get("APPDATA", Path.home())) / "PeekTodo"
    target.mkdir(parents=True, exist_ok=True)
    return target


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
        self._render_sig: tuple | None = None
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

        # 设置里选了固定强调色就覆盖模式色
        preset = ACCENT_PRESETS.get(self.cfg.panel.get("accent", "auto"))
        if preset:
            view.accent = preset

        # 内容没变就不重建控件——5 秒一次轮询时才不会闪
        signature = self._signature(view)
        changed = signature != self._render_sig
        self._render_sig = signature

        if os.environ.get("PEEK_DEBUG"):
            import tempfile

            try:
                with open(
                    Path(tempfile.gettempdir()) / "peektodo-debug.log", "a", encoding="utf-8"
                ) as fh:
                    fh.write(
                        f"{datetime.now():%H:%M:%S} refresh tasks={view.total} "
                        f"open={view.open_count} current={len(view.current)} "
                        f"render={'yes' if changed else 'no'}\n"
                    )
            except OSError:
                pass

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
        self._last_ok = (view, meta)
        if changed:
            self.panel.render(view, meta)

    @staticmethod
    def _signature(view) -> tuple:
        """决定"要不要重画"的摘要：文字、勾选、分组、统计都算进去。"""
        return (
            view.headline,
            view.mode,
            view.open_count,
            view.done_count,
            view.note,
            tuple((t.id, t.text, t.done, t.depth) for t in view.current),
            tuple((t.id, t.text) for t in view.unknown),
            tuple(
                (g.label, tuple((t.id, t.text, t.done, t.depth) for t in g.tasks))
                for g in view.today_groups
            ),
        )

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
        open_source_item(self.cfg.source)

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
        icon_path = assets_dir() / "tray.png"
        icon = QIcon(str(icon_path)) if icon_path.exists() else QIcon()
        self.tray = QSystemTrayIcon(icon, self.app)
        self.tray.setToolTip("PeekTodo · 贴右边缘滑出")

        menu = QMenu()
        act_refresh = QAction("立即刷新", menu)
        act_refresh.triggered.connect(self.refresh)

        act_setup = QAction("设置…", menu)
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
        dialog = SettingsDialog()
        dialog.prefill(self.cfg.raw)
        if dialog.exec_() != SettingsDialog.Accepted or not dialog.result_config:
            return
        config_path().write_text(
            json.dumps(dialog.result_config, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        autostart.toggle(bool(dialog.result_config["behavior"].get("autostart")))
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
    dialog = SettingsDialog()
    if path.exists():
        try:
            dialog.prefill(json.loads(path.read_text(encoding="utf-8-sig")))
        except (OSError, ValueError):
            pass
    if dialog.exec_() != SettingsDialog.Accepted or not dialog.result_config:
        return None
    path.write_text(
        json.dumps(dialog.result_config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    autostart.toggle(bool(dialog.result_config["behavior"].get("autostart")))
    return Config.load(path)


def _lock_path() -> Path:
    """锁文件优先放临时目录；拿不到（权限/环境异常）就退回程序目录。

    PEEK_LOCK_PATH 可覆盖，用于调试时开第二个实例。
    """
    override = os.environ.get("PEEK_LOCK_PATH")
    if override:
        return Path(override)
    try:
        import tempfile

        return Path(tempfile.gettempdir()) / "peektodo.lock"
    except Exception:  # noqa: BLE001 - 任何异常都不该让程序起不来
        return app_dir() / "peektodo.lock"


def single_instance_lock():
    """用文件锁做单实例：进程退出（哪怕崩溃）时由系统自动释放。

    这里任何失败都只降级为"不做单实例"，绝不能让启动直接崩掉。
    PID 写在文件开头；锁打在第 4096 字节上——LockFile 会连读一起挡住，
    两者错开，别的实例才读得到 PID。
    """
    try:
        import msvcrt

        handle = open(_lock_path(), "a+")
        try:
            handle.seek(0)
            handle.truncate()
            handle.write(str(os.getpid()))
            handle.flush()
        except OSError:
            pass
        handle.seek(4096)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        return handle
    except OSError:
        return None
    except Exception:  # noqa: BLE001
        return True  # 加锁本身出错：放行，别挡住启动


def running_instance_pid() -> int | None:
    """读锁文件里记录的 PID，用来提示用户是哪个进程占着。"""
    try:
        text = _lock_path().read_text(encoding="ascii", errors="ignore").strip()
        return int(text) if text.isdigit() else None
    except OSError:
        return None


def _acquire_lock(retry: bool):
    """后台自启的子进程可能比父进程晚一步退出，抢锁要等一下。"""
    lock = single_instance_lock()
    if lock is None and retry:
        import time

        for _ in range(10):
            time.sleep(0.2)
            lock = single_instance_lock()
            if lock is not None:
                break
    return lock


def _detach_to_background(argv: list[str]) -> bool:
    """从终端启动时，改为无控制台的后台进程，然后让终端立刻返回。

    这样关掉命令行窗口不会顺带把面板杀掉。带 --doctor/--setup 的不转，
    因为这些要在当前终端里看输出。
    """
    if getattr(sys, "frozen", False) or sys.platform != "win32":
        return False
    if "--no-detach" in argv or "--doctor" in argv or "--setup" in argv:
        return False
    forced = "--detach" in argv
    if not forced and not (
        sys.stdout is not None and getattr(sys.stdout, "isatty", lambda: False)()
    ):
        return False

    pythonw = Path(sys.executable).with_name("pythonw.exe")
    if not pythonw.exists():
        return False

    import subprocess

    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
        subprocess, "CREATE_NEW_PROCESS_GROUP", 0
    )
    try:
        subprocess.Popen(
            [str(pythonw), "-m", "peek_todo", "--silent", "--detached-child"]
            + [a for a in argv if a not in ("--silent", "--detach")],
            creationflags=flags,
            close_fds=True,
        )
    except OSError:
        return False

    print("PeekTodo 已在后台启动（关掉这个窗口不影响它）。")
    print("托盘图标在右下角；要停掉它，右键托盘图标选「退出」。")
    return True


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if "--doctor" in argv:
        # 把其余参数透传给 doctor，例如 --doctor --config config.example.json
        return doctor_main([arg for arg in argv if arg != "--doctor"])

    if _detach_to_background(argv):
        return 0

    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("PeekTodo")

    lock = None if "--force" in argv else _acquire_lock("--detached-child" in argv)
    if lock is None and "--force" not in argv:
        # 已经在跑了。开机自启带 --silent，静默退出；手动双击则明确告诉用户
        if "--silent" not in argv:
            pid = running_instance_pid()
            who = f"（进程 PID {pid}）" if pid else ""
            QMessageBox.information(
                None,
                "PeekTodo 已在运行",
                f"面板已经在跑了{who}，把鼠标贴到屏幕最右边即可打开。\n\n"
                "如果它卡住了、看不到面板：在任务管理器里结束这个进程，"
                "或者用 peektodo --force 强制再开一个。\n\n"
                "（托盘图标在右下角，右键可以退出或重新设置）",
            )
        return 0

    cfg = ensure_config(force="--setup" in argv)
    if cfg is None:
        return 0

    runner = Runner(app, cfg, force_shown="--force-shown" in argv)
    _ = (runner, lock)
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())

"""PeekTodo 启动入口。"""

from __future__ import annotations

import sys

from .doctor import main as doctor_main
from .storage.paths import assets_dir, config_path, package_dir, state_path
from .windows.launch import acquire_lock, detach_to_background, running_instance_pid


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if "--doctor" in argv:
        # 把其余参数透传给 doctor，例如 --doctor --config config.example.json
        return doctor_main([arg for arg in argv if arg != "--doctor"])

    if "--where" in argv:
        print(f"程序目录 {package_dir()}\n配置 {config_path()}\n勾选状态 {state_path()}")
        return 0

    if detach_to_background(argv):
        return 0

    from PyQt5.QtCore import Qt
    from PyQt5.QtGui import QFont, QIcon
    from PyQt5.QtWidgets import QApplication, QMessageBox

    from .sources.base import SourceError
    from .ui.desktop import DesktopController
    from .ui.settings_flow import ensure_config, migrate_checkmarks
    from .ui.theme import body_font_family, load_bundled_fonts

    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(False)
    load_bundled_fonts()
    app.setFont(QFont(body_font_family()))
    app.setApplicationName("PeekTodo")
    app.setWindowIcon(QIcon(str(assets_dir() / "app.ico")))

    lock = None if "--force" in argv else acquire_lock("--detached-child" in argv)
    if lock is None and "--force" not in argv:
        # 已经在跑了。开机自启带 --silent，静默退出；手动双击则明确告诉用户
        if "--silent" not in argv:
            pid = running_instance_pid()
            who = f"（进程 PID {pid}）" if pid else ""
            QMessageBox.information(
                None,
                "PeekTodo 已在运行",
                f"面板已经在跑了{who}，如果你要切换版本，请先从托盘退出当前实例，再启动这一份。\n\n"
                "如果它卡住了、看不到面板：在任务管理器里结束这个进程，"
                "或者用 peektodo --force 强制再开一个。\n\n"
                "（托盘图标在右下角，右键可以退出或重新设置）",
            )
        return 0

    try:
        migrate_checkmarks()
        cfg = ensure_config(force="--setup" in argv)
        if cfg is None:
            return 0
        runner = DesktopController(app, cfg, force_shown="--force-shown" in argv)
    except (OSError, ValueError, SourceError) as exc:
        QMessageBox.warning(None, "PeekTodo 启动失败", str(exc))
        return 1
    _ = (runner, lock)
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())

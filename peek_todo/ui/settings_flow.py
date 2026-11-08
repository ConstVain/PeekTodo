"""Configuration dialogs and desktop integration."""

from PyQt5.QtWidgets import QMessageBox

from ..storage.config import Config
from ..storage.paths import config_path, portable_dir, state_path
from ..storage.state import migrate_state
from ..windows import autostart, shortcut
from .settings import SettingsDialog


def migrate_checkmarks() -> None:
    directories = [portable_dir(), shortcut.working_directory()]
    migrate_state(state_path(), [directory / ".state.json" for directory in directories if directory])


def save_settings(cfg: Config) -> None:
    cfg.save()
    try:
        autostart.toggle(bool(cfg.behavior["autostart"]))
        if cfg.behavior["desktopShortcut"]:
            if shortcut.create() is None:
                QMessageBox.warning(None, "桌面快捷方式", "无法更新 PeekTodo 桌面快捷方式。")
        else:
            shortcut.remove()
    except OSError as exc:
        QMessageBox.warning(None, "设置已保存，启动项更新失败", str(exc))


def ensure_config(force: bool = False) -> Config | None:
    path = config_path()
    cfg = None
    if path.exists():
        try:
            cfg = Config.load(path)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(None, "config.json 读取失败", f"{path}\n\n{exc}")
    if cfg is not None and not force:
        return cfg

    dialog = SettingsDialog()
    dialog.prefill(cfg.raw if cfg else None, path.parent)
    if dialog.exec_() != SettingsDialog.Accepted or not dialog.result_config:
        return None
    cfg = Config(path, dialog.result_config)
    save_settings(cfg)
    return cfg

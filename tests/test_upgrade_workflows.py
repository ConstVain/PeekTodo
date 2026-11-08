"""Regression checks for the desktop workflow and upgrades."""

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta

import pytest

from peek_todo.application.session import TaskSession
from peek_todo.sources.markdown import MarkdownSource, parse_markdown
from peek_todo.storage.config import Config
from peek_todo.storage.paths import state_path
from peek_todo.storage.state import LocalState, migrate_state
from peek_todo.windows import launch


def test_shared_state_merges_old_checkmarks_and_survives_restart(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "profile"))
    legacy = tmp_path / ".state.json"
    target = state_path()
    older = (datetime.now() - timedelta(days=1)).isoformat()
    expired = (datetime.now() - timedelta(days=8)).isoformat()
    legacy.write_text(json.dumps({
        "mubu:doc": {
            "task": {"at": older, "done": True},
            "conflict": {"at": older, "done": True},
            "expired": {"at": expired, "done": True},
        },
        "markdown:old": {"plan:l4": {"at": older, "done": True}},
    }), encoding="utf-8")
    LocalState(target, "mubu:doc").set_done("conflict", False)
    migrate_state(target, [legacy])

    restored = LocalState(state_path(), "mubu:doc")
    assert restored.is_done("task", False)
    assert not restored.is_done("conflict", True)
    assert restored.count() == 2
    assert LocalState(target, "markdown:old").count() == 0
    assert legacy.exists()


def test_state_write_failure_does_not_change_in_memory_status(tmp_path, monkeypatch):
    from peek_todo.storage import state

    store = LocalState(tmp_path / ".state.json", "mubu:doc")

    def denied(*args):
        raise PermissionError("test")

    monkeypatch.setattr(state, "write_json", denied)
    with pytest.raises(PermissionError):
        store.set_done("task", True)
    assert not store.is_done("task", False)


def test_markdown_ids_survive_insert_and_reorder_and_distinguish_files(tmp_path):
    before = parse_markdown("# Plan\n- [ ] A\n- [ ] B")
    after = parse_markdown("# Plan\n- [ ] B\n- [ ] C\n- [x] A")
    before_ids = {node.text: node.id for node in before.walk()}
    after_ids = {node.text: node.id for node in after.walk()}
    assert after_ids["A"] == before_ids["A"]
    assert after_ids["B"] == before_ids["B"]
    for directory in ("one", "two"):
        folder = tmp_path / directory
        folder.mkdir()
        (folder / "plan.md").write_text("- [ ] A", encoding="utf-8")
    nodes = list(MarkdownSource(tmp_path).fetch().tree.walk())
    assert len({node.id for node in nodes}) == len(nodes)


def test_launch_pins_module_path_even_from_another_checkout(tmp_path, monkeypatch):
    expected = tmp_path / "expected copy"
    other = tmp_path / "other copy"
    for parent in (expected, other):
        package = parent / "peek_todo"
        package.mkdir(parents=True)
        (package / "__init__.py").touch()
        (package / "__main__.py").write_text(
            "import sys; print(__file__); print(sys.argv[1])", encoding="utf-8"
        )
    monkeypatch.setattr(launch, "package_dir", lambda: expected / "peek_todo")
    _, *args = launch.launch_arguments("--where")
    result = subprocess.check_output([sys.executable, *args], cwd=other, text=True)
    assert str(expected) in result
    assert "--where" in result


@pytest.mark.skipif(sys.platform != "win32", reason="Windows file locking")
def test_second_instance_cannot_overwrite_owner_pid(tmp_path, monkeypatch):
    monkeypatch.setenv("PEEK_LOCK_PATH", str(tmp_path / "peektodo.lock"))
    lock = launch.single_instance_lock()
    assert lock is not None and lock is not True
    try:
        subprocess.run(
            [sys.executable, "-c",
             "from peek_todo.windows.launch import single_instance_lock;"
             "assert single_instance_lock() is None"],
            check=True,
        )
        assert launch.running_instance_pid() == os.getpid()
    finally:
        lock.close()


def test_lower_row_can_check_and_uncheck_and_failure_clears(tmp_path, monkeypatch):
    from PyQt5.QtCore import QPoint, Qt
    from PyQt5.QtTest import QTest
    from PyQt5.QtWidgets import QApplication

    from peek_todo.ui.panel import Panel, TaskRow

    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    doc = tmp_path / "plan.md"
    text = "# Plan\n## 周一下午\n- [ ] A"
    doc.write_text(text, encoding="utf-8")
    cfg = Config(tmp_path / "config.json", {
        "source": {"type": "markdown", "path": doc.name},
        "mapping": {"root_path": ["Plan"], "mode": "week"},
    })
    state = tmp_path / ".state.json"
    session = TaskSession(cfg, state)
    now = datetime(2026, 11, 2, 9)
    panel = Panel(360, 400, app.primaryScreen().geometry())
    panel.task_toggled.connect(session.set_done)
    try:
        for expected in (True, False):
            snapshot = session.refresh(now)
            assert not snapshot.view.current
            panel.present(snapshot.view, snapshot.meta)
            row = next(
                widget for index in range(panel.all_box.count())
                if isinstance(widget := panel.all_box.itemAt(index).widget(), TaskRow)
            )
            QTest.mouseClick(row, Qt.LeftButton, pos=QPoint(3, 8))
            restored = TaskSession(cfg, state).refresh(now).view
            assert restored.today_groups[0].tasks[0].done is expected

        snapshot = session.refresh(now)
        panel.present(snapshot.view, snapshot.meta)
        doc.unlink()
        failed = session.refresh(now)
        panel.present(failed.view, failed.meta)
        assert panel._level == "error"
        doc.write_text(text, encoding="utf-8")
        recovered = session.refresh(now)
        panel.present(recovered.view, recovered.meta)
        assert panel._level == "ok"
    finally:
        panel.close()
def test_tray_actions_open_settings_and_refresh(tmp_path, monkeypatch):
    from PyQt5.QtCore import QCoreApplication, QEvent
    from PyQt5.QtWidgets import QApplication, QPushButton, QSystemTrayIcon

    from peek_todo.ui import desktop
    from peek_todo.ui.theme import CREAM, DARK
    from peek_todo.windows import shortcut

    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setattr(QSystemTrayIcon, "show", lambda self: None)
    monkeypatch.setattr(desktop.autostart, "is_enabled", lambda: False)
    monkeypatch.setattr(shortcut, "desktop_path", lambda: tmp_path / "absent.lnk")
    app = QApplication.instance() or QApplication([])
    doc = tmp_path / "plan.md"
    doc.write_text("- A", encoding="utf-8")
    cfg = Config(tmp_path / "config.json", {
        "source": {"type": "markdown", "path": doc.name},
        "mapping": {"root_path": ["A"], "mode": "memo"},
        "panel": {"theme": "cream", "width": 380},
        "behavior": {"refreshMs": 5000},
    })
    cfg.save()
    opened_themes = []
    rendered_backgrounds = []
    saved_themes = []

    def edit_and_close(dialog):
        opened_themes.append(dialog.theme_combo.currentData())
        dialog.show()
        app.processEvents()
        rendered_backgrounds.append(dialog.grab().toImage().pixelColor(4, 4).name())
        if len(opened_themes) == 1:
            dialog.refresh_combo.setCurrentIndex(dialog.refresh_combo.findData(30000))
            dark = dialog.theme_combo.findData("dark")
            dialog.theme_combo.setCurrentIndex(dark)
            dialog.theme_combo.activated.emit(dark)
        if len(opened_themes) == 2:
            dialog.findChild(QPushButton, "primary").click()
        else:
            dialog.close()
        return dialog.result()

    def save_without_launch_changes(config):
        config.save()
        saved_themes.append(config.panel["theme"])

    monkeypatch.setattr(desktop.SettingsDialog, "exec_", edit_and_close)
    monkeypatch.setattr(desktop, "save_settings", save_without_launch_changes)
    monkeypatch.setattr(desktop, "state_path", lambda: tmp_path / ".state.json")
    controller = desktop.DesktopController(app, cfg)
    try:
        actions = {action.text(): action for action in controller.tray.contextMenu().actions()}
        actions["设置…"].trigger()
        assert controller.panel.theme.key == "dark"
        saved = Config.load(cfg.path)
        assert saved.raw["panel"] == {"theme": "dark", "width": 380}
        assert saved.behavior["refreshMs"] == 5000
        actions["设置…"].trigger()
        actions["设置…"].trigger()
        assert opened_themes == ["cream", "dark", "dark"]
        assert rendered_backgrounds == [CREAM.card_mid, DARK.card_mid, DARK.card_mid]
        assert saved_themes == ["dark"]

        doc.write_text("- B", encoding="utf-8")
        actions["立即刷新"].trigger()
        assert controller.session.last_view.current[0].text == "B"
    finally:
        for timer in (controller.tick_timer, controller.refresh_timer, controller.clock_timer):
            timer.stop()
        controller.panel.close()
        controller.panel.deleteLater()
        controller.tray.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def test_settings_preserve_custom_fields_and_resolve_relative_paths(tmp_path, monkeypatch):
    from PyQt5.QtWidgets import QApplication

    from peek_todo.ui.settings import SettingsDialog
    from peek_todo.windows import autostart, shortcut

    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setattr(autostart, "is_enabled", lambda: False)
    monkeypatch.setattr(shortcut, "desktop_path", lambda: tmp_path / "absent.lnk")
    app = QApplication.instance() or QApplication([])
    (tmp_path / "plan.md").write_text("# Plan\n- A", encoding="utf-8")
    original = {
        "source": {"type": "markdown", "path": "plan.md"},
        "mapping": {"root_path": ["Plan"], "mode": "memo", "aliases": {"label": "周一下午"}},
        "panel": {"colors": {"text": "#123456"}},
        "vocabulary": {"weekdays": {"周一": ["星期一"]}},
        "periods": [{"name": "上午", "start": "08:00"}],
    }
    dialog = SettingsDialog()
    try:
        dialog.prefill(original, tmp_path)
        dialog._save_inner()
        result = dialog.result_config
        assert result["source"] == original["source"]
        assert result["mapping"]["aliases"] == original["mapping"]["aliases"]
        assert result["vocabulary"] == original["vocabulary"]
        assert result["periods"] == original["periods"]
        assert result["panel"]["colors"] == original["panel"]["colors"]
    finally:
        dialog.close()
        app.processEvents()

def test_markdown_dialogs_share_last_folder_and_select_new_plan(tmp_path, monkeypatch):
    from PyQt5.QtCore import Qt
    from PyQt5.QtTest import QTest
    from PyQt5.QtWidgets import QApplication, QDialog

    from peek_todo.ui import settings

    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setattr(settings, "user_data_dir", lambda: tmp_path / "profile")
    app = QApplication.instance() or QApplication([])
    source = tmp_path / "existing" / "plan.md"
    source.parent.mkdir()
    source.write_text("# Plan\n- A", encoding="utf-8")
    destination = tmp_path / "new"
    destination.mkdir()
    picked = []

    class FileDialog:
        AcceptSave = 1
        ExistingFile = 2
        Accept = 3

        @staticmethod
        def getOpenFileName(parent, title, initial_path, file_filter):
            picked.append((title, initial_path))
            return str(source), file_filter

        def __init__(self, parent, title, folder, file_filter):
            self.template_picker = title == "选择模板"
            expected_folder = settings.DEFAULT_TEMPLATE.parent if self.template_picker else source.parent
            assert folder == str(expected_folder)
            self.name = None

        def setFileMode(self, mode):
            assert self.template_picker and mode == self.ExistingFile

        def setLabelText(self, label, text):
            assert self.template_picker and label == self.Accept and text == "确定"

        def setAcceptMode(self, mode):
            assert mode == self.AcceptSave

        def setDefaultSuffix(self, suffix):
            assert suffix == "md"

        def selectFile(self, name):
            expected_name = (
                settings.DEFAULT_TEMPLATE.name if self.template_picker
                else f"{datetime.now():%y%m%d}_目标与事项.md"
            )
            assert name == expected_name
            self.name = name

        def exec_(self):
            return QDialog.Accepted

        def selectedFiles(self):
            if self.template_picker:
                picked.append(("选择模板", str(settings.DEFAULT_TEMPLATE)))
                return [str(settings.DEFAULT_TEMPLATE)]
            return [str(destination / self.name)]

    opened = []
    monkeypatch.setattr(settings, "QFileDialog", FileDialog)
    monkeypatch.setattr(settings, "open_source", opened.append)
    first = settings.SettingsDialog()
    first._pick_file()
    first.close()

    second = settings.SettingsDialog()
    second.show()
    second._new_markdown()
    target = destination / settings.default_filename()
    assert picked[-1] == ("选择模板", str(settings.DEFAULT_TEMPLATE))
    assert target.read_bytes() == settings.DEFAULT_TEMPLATE.read_bytes()

    # Some editors save by replacing the original file.
    edited = destination / "draft.md"
    text = target.read_text(encoding="utf-8")
    edited.write_text(text.replace("* 周一上午", "* 周一上午\n  * 新增事项"), encoding="utf-8")
    edited.replace(target)
    match = Qt.MatchExactly | Qt.MatchRecursive
    for _ in range(20):
        if second.tree.findItems("新增事项", match):
            break
        QTest.qWait(100)
    assert second.tree.findItems("新增事项", match)

    second._save_inner()
    assert second.result_config["source"]["path"] == str(target)
    assert second.result_config["mapping"]["root_path"] == ["目标与事项", "规划"]
    assert second.result_config["mapping"]["mode"] == "week"
    assert opened == [{"type": "markdown", "path": str(target)}]
    second.close()

    third = settings.SettingsDialog()
    third._pick_file()
    assert picked[-1] == ("选择 Markdown 文件", str(destination))
    third.close()
    app.processEvents()

def test_settings_preview_and_persist_custom_accent(tmp_path, monkeypatch):
    from PyQt5.QtCore import QPoint, Qt
    from PyQt5.QtTest import QTest
    from PyQt5.QtWidgets import QApplication, QDialog, QStyle, QStyleOptionButton

    from peek_todo.ui import settings
    from peek_todo.ui.theme import CREAM, DARK, panel_accent
    from peek_todo.windows import autostart, shortcut

    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setattr(settings, "user_data_dir", lambda: tmp_path / "profile")
    monkeypatch.setattr(autostart, "is_enabled", lambda: False)
    monkeypatch.setattr(shortcut, "desktop_path", lambda: tmp_path / "absent.lnk")
    app = QApplication.instance() or QApplication([])
    doc = tmp_path / "plan.md"
    doc.write_text("# Plan\n- A", encoding="utf-8")
    cfg = Config(tmp_path / "config.json", {
        "source": {"type": "markdown", "path": doc.name},
        "mapping": {"root_path": ["Plan"], "mode": "week"},
        "panel": {"theme": "dark", "accent": "blue", "accents": {"week": "#aa0000"}},
    })

    dialog = settings.SettingsDialog()
    dialog.prefill(cfg.raw, tmp_path)
    assert f"QDialog {{ background: {DARK.card_mid}; }}" in dialog.styleSheet()
    assert all(not dialog.theme_combo.itemIcon(i).isNull() for i in range(dialog.theme_combo.count()))
    assert all(not dialog.accent_combo.itemIcon(i).isNull() for i in range(dialog.accent_combo.count()))
    dialog.theme_combo.setCurrentIndex(dialog.theme_combo.findData("cream"))
    assert f"QDialog {{ background: {CREAM.card_mid}; }}" in dialog.styleSheet()

    custom_index = dialog.accent_combo.findData("custom")
    monkeypatch.setattr(settings.AccentPicker, "exec_", lambda self: QDialog.Rejected)
    dialog.accent_combo.setCurrentIndex(custom_index)
    dialog.accent_combo.activated.emit(custom_index)
    assert dialog.accent_combo.currentData() == "blue"

    chosen = []

    def choose_color(picker):
        QTest.mouseClick(picker.surface, Qt.LeftButton, pos=QPoint(254, 120))
        QTest.mousePress(picker.surface, Qt.LeftButton, pos=QPoint(120, 60))
        QTest.mouseMove(picker.surface, QPoint(176, 64))
        QTest.mouseRelease(picker.surface, Qt.LeftButton, pos=QPoint(176, 64))
        color = picker.color()
        assert color.hsvHueF() == pytest.approx(0.5, abs=0.01)
        assert color.hsvSaturationF() == pytest.approx(0.75, abs=0.01)
        assert color.valueF() == pytest.approx(0.75, abs=0.01)
        chosen.append(color.name())
        return QDialog.Accepted

    monkeypatch.setattr(settings.AccentPicker, "exec_", choose_color)
    dialog.accent_combo.setCurrentIndex(custom_index)
    dialog.accent_combo.activated.emit(custom_index)
    assert f"background: {chosen[0]};" in dialog.styleSheet()
    dialog.shortcut_check.setChecked(True)
    dialog.show()
    app.processEvents()
    for control, element, offset in (
        (dialog.radio_week, QStyle.SE_RadioButtonIndicator, None),
        (dialog.shortcut_check, QStyle.SE_CheckBoxIndicator, QPoint(3, 3)),
    ):
        option = QStyleOptionButton()
        control.initStyleOption(option)
        rect = control.style().subElementRect(element, option, control)
        point = rect.center() if offset is None else rect.topLeft() + offset
        image = control.grab().toImage()
        assert image.pixelColor(point * image.devicePixelRatio()).name() == chosen[0]
    dialog._save_inner()

    Config(cfg.path, dialog.result_config).save()
    saved = Config.load(cfg.path)
    assert saved.panel["customAccent"] == chosen[0]
    assert saved.panel["accents"] == {"week": "#aa0000"}
    assert panel_accent(CREAM, saved.panel, "week") == chosen[0]

    reopened = settings.SettingsDialog()
    reopened.prefill(saved.raw, tmp_path)
    assert reopened.accent_combo.currentData() == "custom"
    assert f"background: {chosen[0]};" in reopened.styleSheet()
    reopened.close()
    dialog.close()
    app.processEvents()

def test_named_accents_can_be_saved_and_removed_from_dropdown(tmp_path, monkeypatch):
    from PyQt5.QtCore import QPoint, Qt
    from PyQt5.QtTest import QTest
    from PyQt5.QtWidgets import QApplication, QDialog, QPushButton

    from peek_todo.ui import settings
    from peek_todo.ui.accent_picker import QInputDialog
    from peek_todo.ui.theme import CREAM, panel_accent
    from peek_todo.windows import autostart, shortcut

    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setattr(settings, "user_data_dir", lambda: tmp_path / "profile")
    monkeypatch.setattr(autostart, "is_enabled", lambda: False)
    monkeypatch.setattr(shortcut, "desktop_path", lambda: tmp_path / "absent.lnk")
    app = QApplication.instance() or QApplication([])
    doc = tmp_path / "plan.md"
    doc.write_text("# Plan\n- A", encoding="utf-8")
    cfg = Config(tmp_path / "config.json", {
        "source": {"type": "markdown", "path": doc.name},
        "mapping": {"root_path": ["Plan"], "mode": "memo"},
    })
    monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kwargs: ("暮紫", True))
    chosen = []

    def add_color(picker):
        button = next(button for button in picker.findChildren(QPushButton)
                      if button.text() == "添加到列表")
        chosen.append(picker.color().name())
        button.click()
        assert picker.result() == QDialog.Accepted
        return picker.result()

    monkeypatch.setattr(settings.AccentPicker, "exec_", add_color)
    dialog = settings.SettingsDialog()
    dialog.prefill(cfg.raw, tmp_path)
    index = dialog.accent_combo.findData("custom")
    dialog.accent_combo.setCurrentIndex(index)
    dialog.accent_combo.activated.emit(index)
    color = chosen[0]
    key = f"saved:{color}"
    assert dialog.accent_combo.currentData() == key
    assert dialog.accent_combo.currentText() == "暮紫"
    dialog._save_inner()
    Config(cfg.path, dialog.result_config).save()
    saved = Config.load(cfg.path)
    assert panel_accent(CREAM, saved.panel, "memo") == color

    reopened = settings.SettingsDialog()
    reopened.prefill(saved.raw, tmp_path)
    reopened.show()
    app.processEvents()
    combo = reopened.accent_combo
    assert combo.currentData() == key

    def click_trash(color_key):
        combo.showPopup()
        app.processEvents()
        row = combo.view().visualRect(combo.model().index(combo.findData(color_key), 0))
        QTest.mouseClick(combo.view().viewport(), Qt.LeftButton,
                         pos=QPoint(row.right() - 12, row.center().y()))
        assert combo.findData(color_key) == -1

    click_trash(key)
    assert combo.currentData() == "auto"
    click_trash("blue")
    reopened._save_inner()
    Config(cfg.path, reopened.result_config).save()

    final = settings.SettingsDialog()
    final.prefill(Config.load(cfg.path).raw, tmp_path)
    assert final.accent_combo.findData(key) == -1
    assert final.accent_combo.findData("blue") == -1
    assert final.accent_combo.currentData() == "auto"
    final.close()
    reopened.close()
    dialog.close()
    app.processEvents()

def test_shortcut_icon_path_changes_only_when_icon_bytes_change(tmp_path, monkeypatch):
    from peek_todo.windows import shortcut

    assets = tmp_path / "assets"
    assets.mkdir()
    source = assets / "app.ico"
    monkeypatch.setattr(shortcut, "assets_dir", lambda: assets)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))

    source.write_bytes(b"old icon")
    first = shortcut.icon_path()
    assert first.read_bytes() == b"old icon"
    assert shortcut.icon_path() == first

    source.write_bytes(b"new icon")
    updated = shortcut.icon_path()
    assert updated != first
    assert updated.read_bytes() == b"new icon"
    assert shortcut.icon_path() == updated

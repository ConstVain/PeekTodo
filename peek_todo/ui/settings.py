"""PeekTodo 设置面板。

第一次运行和之后的"设置"共用一个对话框：选数据源、选根节点、选模式，
外加刷新间隔、强调色、开机自启。
"""

from __future__ import annotations

from pathlib import Path
from stat import S_ISREG

from PyQt5.QtCore import QSettings, QStandardPaths, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PyQt5.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QAbstractItemView,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..application.configuration import build_source
from ..storage.config import Config, DEFAULT_BEHAVIOR, DEFAULT_PANEL
from ..storage.paths import assets_dir, user_data_dir
from ..domain.model import Node
from ..windows.opener import open_source
from ..sources.base import SourceError
from ..sources.mubu import list_documents
from ..application.template import DEFAULT_TEMPLATE, default_filename, write_template
from .accent_menu import REMOVABLE_ROLE, AccentComboBox
from .accent_picker import AccentPicker
from .theme import (
    ACCENT_PRESETS, SAVED_ACCENT_PREFIX, THEMES, Theme, accent as themed_accent,
    custom_accent, get as get_theme, panel_accent, saved_accents,
)
from ..domain.structure import (
    MODE_DUE,
    MODE_LABELS,
    MODE_MEMO,
    MODE_WEEK,
    MappingConfig,
    map_document,
    normalize_mode,
)

PRESET_NAMES = {"blue": "湖蓝", "violet": "雾紫", "teal": "青绿"}
REFRESH_CHOICES = [3000, 5000, 10000, 30000, 60000]


def _settings_style(theme: Theme, color: str) -> str:
    rgb = QColor(color).getRgbF()[:3]
    linear = [channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
              for channel in rgb]
    luminance = sum(channel * weight for channel, weight in zip(linear, (0.2126, 0.7152, 0.0722)))
    foreground = "#000000" if luminance >= 0.179 else "#ffffff"
    checkmark = "check-dark.svg" if luminance >= 0.179 else "check-light.svg"
    checkmark_path = (assets_dir() / checkmark).as_posix()
    return f"""
QDialog {{ background: {theme.card_mid}; }}
QLabel {{ color: {theme.text_soft}; }}
QLabel#title {{ color: {theme.text}; font-size: 19px; font-weight: 600; }}
QLabel#sectionTitle {{ color: {theme.text_dim}; font-size: 11px; letter-spacing: 1.2px; }}
QLabel#hint {{ color: {theme.text_dim}; font-size: 12px; }}
QLabel#ok {{ color: {theme.ok}; font-size: 12px; }}
QLabel#warn {{ color: {theme.warn}; font-size: 12px; }}
QLabel#source {{ color: {theme.text_soft}; font-size: 12px; }}
QFrame#section {{
    background: {theme.card_top}; border: 1px solid {theme.card_border}; border-radius: 10px;
}}
QPushButton {{
    background: {theme.card_bottom}; color: {theme.text_soft}; border: 1px solid {theme.card_border};
    border-radius: 7px; padding: 7px 14px; font-size: 13px;
}}
QPushButton:hover {{ background: {theme.chip_bg}; border-color: {color}; }}
QPushButton:pressed {{ background: {theme.chip_bg}; }}
QPushButton#primary {{
    background: {color}; border-color: {color}; color: {foreground}; font-weight: 600;
}}
QPushButton#primary:hover {{ background: {color}; }}
QPushButton#ghost {{ background: transparent; border-color: {theme.card_border}; }}
QPushButton#ghost:hover, QPushButton#ghost:focus {{ border-color: {color}; }}
QPushButton:focus, QComboBox:focus, QComboBox:hover {{ border-color: {color}; }}
QTreeWidget {{
    background: {theme.card_bottom}; color: {theme.text_soft}; border: 1px solid {theme.card_border};
    border-radius: 8px; outline: none; font-size: 13px; padding: 4px;
}}
QTreeWidget::item {{ padding: 3px 2px; }}
QTreeWidget::item:hover:!selected {{ background: {theme.chip_bg}; }}
QTreeWidget::item:selected {{ background: {color}; color: {foreground}; border-radius: 4px; }}
QRadioButton {{ color: {theme.text_soft}; font-size: 13px; spacing: 6px; }}
QComboBox {{
    background: {theme.card_bottom}; color: {theme.text_soft}; border: 1px solid {theme.card_border};
    border-radius: 7px; padding: 6px 10px; font-size: 13px; min-width: 110px;
}}
QComboBox QAbstractItemView {{
    background: {theme.card_top}; color: {theme.text_soft}; border: 1px solid {theme.card_border};
    selection-background-color: {color}; selection-color: {foreground};
}}
QCheckBox {{ color: {theme.text_soft}; font-size: 13px; spacing: 8px; }}
QRadioButton::indicator, QCheckBox::indicator {{
    width: 14px; height: 14px;
    background: {theme.card_top}; border: 1px solid {theme.text_dim};
}}
QRadioButton::indicator {{ border-radius: 8px; }}
QCheckBox::indicator {{ border-radius: 4px; }}
QRadioButton::indicator:hover, QCheckBox::indicator:hover {{
    border-color: {color};
}}
QRadioButton::indicator:checked {{
    border-color: {color};
    background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5,
        stop:0 {color}, stop:0.56 {color}, stop:0.65 {theme.card_top}, stop:1 {theme.card_top});
}}
QCheckBox::indicator:checked {{
    background: {color}; border-color: {color}; image: url("{checkmark_path}");
}}
"""


def _swatch(color: str, border: str) -> QIcon:
    dot = QPixmap(16, 16)
    dot.fill(Qt.transparent)
    painter = QPainter(dot)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor(border)))
    painter.setBrush(QColor(color))
    painter.drawEllipse(2, 2, 11, 11)
    painter.end()
    return QIcon(dot)


class Section(QFrame):
    """带标题的卡片容器。"""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("section")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 12, 16, 14)
        outer.setSpacing(10)
        label = QLabel(title)
        label.setObjectName("sectionTitle")
        outer.addWidget(label)
        self.body = QVBoxLayout()
        self.body.setSpacing(8)
        outer.addLayout(self.body)


class SettingsDialog(QDialog):
    theme_selected = pyqtSignal(str)

    def __init__(self, parent=None, *, add_section: bool = False):
        super().__init__(parent)
        self._add_section = add_section
        self._sections: list[dict] = []
        self.setWindowTitle("PeekTodo 设置 · 添加区块" if add_section else "PeekTodo 设置")
        self.resize(760, 500 if add_section else 720)
        self.result_config: dict | None = None

        self._source: dict = {}
        self._tree_root: Node | None = None
        self._node_by_item: dict[int, Node] = {}
        self._restoring = False
        # 已有的面板设置（宽度/高度等），保存时原样带回去，别被默认值覆盖
        self._original: dict = {}
        self._custom_accent: str | None = None
        self._saved_accents: dict[str, str] = {}
        self._hidden_accents: set[str] = set()
        self._accent_key = "auto"
        self._config_dir = Path.cwd()
        self._preferences = QSettings(str(user_data_dir() / "dialogs.ini"), QSettings.IniFormat)
        self._markdown_path: Path | None = None
        self._markdown_revision: tuple[int, int, int] | None = None
        self._preview_timer = QTimer(self)
        self._preview_timer.setInterval(250)
        self._preview_timer.timeout.connect(self._refresh_markdown_preview)

        self._build_ui()
        self._apply_appearance()

    def showEvent(self, event):
        super().showEvent(event)
        # Qt may keep the palette from before prefill until the visible dialog is repolished.
        style = self.styleSheet()
        self.setStyleSheet("")
        self.setStyleSheet(style)
        self._preview_timer.start()

    def hideEvent(self, event):
        self._preview_timer.stop()
        super().hideEvent(event)

    # ---------- 构建 ----------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 18)
        root.setSpacing(14)

        title = QLabel("添加面板区块" if self._add_section else "PeekTodo 设置")
        title.setObjectName("title")
        root.addWidget(title)

        source = self._source_section()
        root.addWidget(source)
        source.setHidden(self._add_section)
        root.addWidget(self._structure_section(), 1)
        appearance = self._appearance_section()
        root.addWidget(appearance)
        appearance.setHidden(self._add_section)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        btn_cancel = QPushButton("取消")
        btn_cancel.setObjectName("ghost")
        btn_save = QPushButton("添加" if self._add_section else "保存")
        btn_save.setObjectName("primary")
        btn_save.setDefault(True)
        btn_cancel.clicked.connect(self.reject)
        btn_save.clicked.connect(self._save)
        bottom.addWidget(btn_cancel)
        bottom.addWidget(btn_save)
        root.addLayout(bottom)

    def _source_section(self) -> Section:
        section = Section("数据源")
        row = QHBoxLayout()
        row.setSpacing(8)
        btn_new = QPushButton("新建 Markdown 文档")
        btn_new.setObjectName("ghost")
        btn_new.setToolTip("生成一份带示例内容的模板，并直接打开让你改")
        btn_new.clicked.connect(self._new_markdown)
        btn_file = QPushButton("选择 Markdown 文件")
        btn_mubu = QPushButton("幕布文档")
        btn_file.clicked.connect(self._pick_file)
        btn_mubu.clicked.connect(self._pick_mubu)
        row.addWidget(btn_new)
        row.addWidget(btn_file)
        row.addWidget(btn_mubu)
        row.addStretch(1)

        self.btn_open = QPushButton("打开数据源")
        self.btn_open.setObjectName("ghost")
        self.btn_open.setEnabled(False)
        self.btn_open.setToolTip("用系统默认程序打开，方便直接改几行")
        self.btn_open.clicked.connect(self._open_source)
        row.addWidget(self.btn_open)

        section.body.addLayout(row)

        self.source_label = QLabel("还没有选择数据源")
        self.source_label.setObjectName("hint")
        section.body.addWidget(self.source_label)
        return section

    def _open_source(self) -> None:
        if not self._source:
            return
        cfg = Config(self._config_dir / "config.json", {"source": self._source})
        reason = open_source(cfg.resolved_source())
        if reason:
            QMessageBox.warning(self, "打不开数据源", reason)

    def _structure_section(self) -> Section:
        section = Section("结构")
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setMinimumHeight(220)
        self.tree.itemSelectionChanged.connect(self._on_select)
        section.body.addWidget(self.tree, 1)

        hint = QLabel(
            "从当前数据源选择一个节点，新区块会显示在面板底部"
            if self._add_section else "在树里点一个节点，作为解析的起点"
        )
        hint.setObjectName("hint")
        section.body.addWidget(hint)

        modes = QHBoxLayout()
        modes.setSpacing(18)
        self.radio_week = QRadioButton("周计划：下一级是时段")
        self.radio_due = QRadioButton("截止日：下一级是日期")
        self.radio_memo = QRadioButton("备忘单：平铺清单")
        self.radio_week.setChecked(True)
        group = QButtonGroup(self)
        for radio in (self.radio_week, self.radio_due, self.radio_memo):
            group.addButton(radio)
            modes.addWidget(radio)
        group.buttonToggled.connect(self._on_mode_toggled)
        modes.addStretch(1)
        section.body.addLayout(modes)

        self.detect_label = QLabel("")
        self.detect_label.setObjectName("hint")
        self.detect_label.setWordWrap(True)
        section.body.addWidget(self.detect_label)

        self.sections_row = QWidget()
        row = QHBoxLayout(self.sections_row)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self._plain("附加区块"))
        self.sections_combo = QComboBox()
        self.sections_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.sections_combo.setMinimumContentsLength(14)
        row.addWidget(self.sections_combo, 1)
        remove = QPushButton("移除区块")
        remove.clicked.connect(self._remove_section)
        row.addWidget(remove)
        section.body.addWidget(self.sections_row)
        self.sections_row.hide()
        return section

    def _show_sections(self) -> None:
        self.sections_combo.clear()
        for section in self._sections:
            mode = MODE_LABELS[normalize_mode(section.get("mode"))]
            self.sections_combo.addItem(f"{section['root_path'][-1]} · {mode}")
        self.sections_row.setVisible(bool(self._sections) and not self._add_section)

    def _remove_section(self) -> None:
        index = self.sections_combo.currentIndex()
        if index >= 0:
            self._sections.pop(index)
            self._show_sections()

    def _appearance_section(self) -> Section:
        section = Section("显示与行为")

        row1 = QHBoxLayout()
        row1.setSpacing(10)
        row1.addWidget(self._plain("刷新间隔"))
        self.refresh_combo = QComboBox()
        for ms in REFRESH_CHOICES:
            self.refresh_combo.addItem(f"{ms // 1000} 秒", ms)
        row1.addWidget(self.refresh_combo)
        row1.addSpacing(18)
        row1.addWidget(self._plain("强调色"))
        self.accent_combo = AccentComboBox()
        self._populate_accents("auto")
        self.accent_combo.activated.connect(self._choose_accent)
        self.accent_combo.remove_requested.connect(self._remove_accent)
        row1.addWidget(self.accent_combo)
        row1.addSpacing(18)
        row1.addWidget(self._plain("配色"))
        self.theme_combo = QComboBox()
        for key, theme in THEMES.items():
            self.theme_combo.addItem(_swatch(theme.card_mid, theme.text_dim), theme.name, key)
        self.theme_combo.setCurrentIndex(self.theme_combo.findData(DEFAULT_PANEL["theme"]))
        self.theme_combo.currentIndexChanged.connect(self._apply_appearance)
        self.theme_combo.activated.connect(self._select_theme)
        row1.addWidget(self.theme_combo)
        row1.addStretch(1)
        self.autostart_check = QCheckBox("开机自启")
        row1.addWidget(self.autostart_check)
        self.shortcut_check = QCheckBox("桌面快捷方式")
        self.shortcut_check.setToolTip("在桌面放一个带图标的入口")
        row1.addWidget(self.shortcut_check)
        section.body.addLayout(row1)

        return section

    def _panel_preferences(self) -> dict:
        panel = {
            **(self._original.get("panel") or {}),
            "theme": self.theme_combo.currentData(),
            "accent": self.accent_combo.currentData(),
        }
        if self._custom_accent is not None:
            panel["customAccent"] = self._custom_accent
        if self._saved_accents or "savedAccents" in panel:
            panel["savedAccents"] = dict(self._saved_accents)
        if self._hidden_accents or "hiddenAccents" in panel:
            panel["hiddenAccents"] = sorted(self._hidden_accents)
        return panel

    def _populate_accents(self, selected: str) -> None:
        combo = self.accent_combo
        combo.clear()
        combo.addItem("跟随模式", "auto")
        colors = [(key, name) for key, name in PRESET_NAMES.items() if key not in self._hidden_accents]
        colors.extend((SAVED_ACCENT_PREFIX + color, name) for color, name in self._saved_accents.items())
        for key, name in colors:
            combo.addItem(name, key)
            combo.setItemData(combo.count() - 1, True, REMOVABLE_ROLE)
        combo.addItem("自定义…", "custom")
        combo.setCurrentIndex(max(0, combo.findData(selected)))
        self._accent_key = combo.currentData()

    def _remove_accent(self, key: str) -> None:
        if key in PRESET_NAMES:
            self._hidden_accents.add(key)
        else:
            self._saved_accents.pop(key.removeprefix(SAVED_ACCENT_PREFIX), None)
        self._populate_accents(self._accent_key)
        self._apply_appearance()

    def _select_theme(self, index: int) -> None:
        self.theme_selected.emit(self.theme_combo.itemData(index))

    def _apply_appearance(self) -> None:
        panel = self._panel_preferences()
        theme = get_theme(panel["theme"], panel.get("colors"))
        mode = self._selected_mode()
        style = _settings_style(theme, panel_accent(theme, panel, mode))
        if style != self.styleSheet():
            self.setStyleSheet(style)
        colors = {key: themed_accent(theme, color) for key, color in ACCENT_PRESETS.items()}
        colors["auto"] = panel_accent(theme, {**panel, "accent": "auto"}, mode)
        colors["custom"] = self._custom_accent or colors["auto"]
        colors.update({SAVED_ACCENT_PREFIX + color: color for color in self._saved_accents})
        for index in range(self.accent_combo.count()):
            key = self.accent_combo.itemData(index)
            self.accent_combo.setItemIcon(index, _swatch(colors[key], theme.text_dim))

    def _choose_accent(self, index: int) -> None:
        key = self.accent_combo.itemData(index)
        if key == "custom":
            panel = self._panel_preferences()
            theme = get_theme(panel["theme"], panel.get("colors"))
            previous = {**panel, "accent": self._accent_key}
            initial = self._custom_accent or panel_accent(theme, previous, self._selected_mode())
            picker = AccentPicker(QColor(initial), self)
            try:
                if picker.exec_() != QDialog.Accepted:
                    self.accent_combo.setCurrentIndex(self.accent_combo.findData(self._accent_key))
                    return
                color = picker.color().name()
                if picker.saved_name is None:
                    self._custom_accent = color
                else:
                    self._saved_accents[color] = picker.saved_name
                    key = SAVED_ACCENT_PREFIX + color
                    self._populate_accents(key)
            finally:
                picker.deleteLater()
        self._accent_key = key
        self._apply_appearance()

    def _on_mode_toggled(self, _button, checked: bool) -> None:
        if checked:
            self._on_mode_changed()
            self._apply_appearance()

    @staticmethod
    def _plain(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("hint")
        return label

    # ---------- 数据源 ----------

    @staticmethod
    def _file_revision(path: Path | None) -> tuple[int, int, int] | None:
        if path is None:
            return None
        try:
            info = path.stat()
        except OSError:
            return None
        if S_ISREG(info.st_mode):
            return info.st_mtime_ns, info.st_size, info.st_ino
        return None

    def _load(self, source: dict, display: str, quiet: bool = False) -> bool:
        try:
            cfg = Config(self._config_dir / "config.json", {"source": source})
            path = cfg.source_path() if source.get("type") == "markdown" else None
            revision = self._file_revision(path)
            result = build_source(cfg).fetch()
        except SourceError as exc:
            if quiet:
                self.source_label.setText(f"{display}（读不到：{exc}）")
            else:
                QMessageBox.warning(self, "读不到这个数据源", str(exc))
            return False

        if self._source:
            previous = Config(cfg.path, {"source": self._source})
            previous_source = previous.resolved_source()
            current_source = cfg.resolved_source()
            if any(previous_source.get(key) != current_source.get(key) for key in ("type", "path", "docId")):
                self._sections.clear()
                self._show_sections()
        self._source = source
        self._markdown_path = path
        self._markdown_revision = revision
        self.source_label.setText(display)
        self.source_label.setObjectName("source")
        self.source_label.style().unpolish(self.source_label)
        self.source_label.style().polish(self.source_label)
        self.btn_open.setEnabled(True)
        self._tree_root = result.tree
        self._fill_tree(result.tree)
        self.detect_label.setText("")
        return True

    def _refresh_markdown_preview(self) -> None:
        revision = self._file_revision(self._markdown_path)
        if revision is None or revision == self._markdown_revision:
            return

        root_path = self._root_path()
        self._restoring = True
        try:
            if self._load(self._source, self._source["path"], quiet=True) and root_path:
                self._select_path(root_path, focus=False)
        finally:
            self._restoring = False
        self._on_mode_changed()

    def _markdown_folder(self) -> Path:
        last = self._preferences.value("markdown/folder", "", type=str)
        if last and Path(last).is_dir():
            return Path(last)
        documents = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
        return Path(documents) if documents and Path(documents).is_dir() else Path.home()

    def _remember_markdown_folder(self, path: Path) -> None:
        self._preferences.setValue("markdown/folder", str(path.parent))
        self._preferences.sync()

    def _pick_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 Markdown 文件", str(self._markdown_folder()),
            "Markdown (*.md *.markdown);;所有文件 (*)",
        )
        if path and self._load({"type": "markdown", "path": path}, path):
            self._remember_markdown_folder(Path(path))

    def _new_markdown(self):
        picker = QFileDialog(
            self, "选择模板", str(DEFAULT_TEMPLATE.parent), "Markdown (*.md *.markdown)",
        )
        picker.setFileMode(QFileDialog.ExistingFile)
        picker.setLabelText(QFileDialog.Accept, "确定")
        picker.selectFile(DEFAULT_TEMPLATE.name)
        if picker.exec_() != QDialog.Accepted or not (templates := picker.selectedFiles()):
            return

        dialog = QFileDialog(self, "保存位置", str(self._markdown_folder()), "Markdown (*.md *.markdown)")
        dialog.setAcceptMode(QFileDialog.AcceptSave)
        dialog.setDefaultSuffix("md")
        dialog.selectFile(default_filename())
        if dialog.exec_() != QDialog.Accepted or not (files := dialog.selectedFiles()):
            return
        target = Path(files[0])
        try:
            write_template(Path(templates[0]), target)
        except OSError as exc:
            QMessageBox.warning(self, "写不了这个位置", str(exc))
            return

        self._remember_markdown_folder(target)
        source = {"type": "markdown", "path": str(target)}
        if self._load(source, str(target)):
            self.source_label.setText(f"{target}（新建，可直接编辑）")
            # 两份内置模板都把一周的时段放在「目标与事项 → 规划」下。
            if self._tree_root is not None and any(
                node.text == "目标与事项" and any(child.text == "规划" for child in node.children)
                for node in self._tree_root.children
            ):
                self._select_path(["目标与事项", "规划"])
                self._restoring = False
                self.radio_week.setChecked(True)
                self._on_mode_changed()
        open_source(source)

    def _pick_mubu(self):
        docs = list_documents()
        if not docs:
            QMessageBox.information(
                self,
                "没找到幕布文档",
                "没有在 %APPDATA%\\Mubu 下找到本地备份。\n请先打开幕布桌面端并打开一篇文档。",
            )
            return
        items = [f"{doc_id}   （最后保存 {stamp}）" for doc_id, stamp in docs]
        choice, ok = QInputDialog.getItem(self, "选择幕布文档", "本地缓存里的文档：", items, 0, False)
        if not ok or not choice:
            return
        doc_id = choice.split("（")[0].strip()
        self._load({"type": "mubu", "docId": doc_id}, f"幕布 / {doc_id}")

    # ---------- 结构树 ----------

    def _fill_tree(self, root: Node) -> None:
        self.tree.clear()
        self._node_by_item.clear()
        for child in root.children[:80]:
            self.tree.addTopLevelItem(self._make_item(child, 0))
        self.tree.expandToDepth(1)

    def _make_item(self, node: Node, depth: int) -> QTreeWidgetItem:
        text = node.text or "(无标题)"
        if len(text) > 44:
            text = text[:43] + "…"
        item = QTreeWidgetItem([text])
        item.setData(0, Qt.UserRole, node.text)
        self._node_by_item[id(item)] = node
        if depth < 3:
            for child in node.children[:60]:
                item.addChild(self._make_item(child, depth + 1))
        return item

    def _root_path(self) -> list[str] | None:
        items = self.tree.selectedItems()
        if not items:
            return None
        path: list[str] = []
        item: QTreeWidgetItem | None = items[0]
        while item is not None:
            path.append(_node_text(item))
            item = item.parent()
        return list(reversed(path))

    def _selected_node(self) -> Node | None:
        items = self.tree.selectedItems()
        return self._node_by_item.get(id(items[0])) if items else None

    # ---------- 检测 ----------

    def _on_select(self) -> None:
        if self._restoring:
            # 回填时保留用户原来的模式，不要被自动检测覆盖
            return
        node = self._selected_node()
        if node is None:
            return
        wrapped = _wrap(node)
        week = map_document(wrapped, MappingConfig(root_path=None, mode=MODE_WEEK))
        due = map_document(wrapped, MappingConfig(root_path=None, mode=MODE_DUE))
        timed = [g for g in week.groups if g.when is not None]
        dated = [g for g in due.groups if g.due is not None]
        tasks = due.task_count or week.task_count

        if timed and len(timed) >= len(dated):
            self.radio_week.setChecked(True)
            self._detect(
                "ok",
                f"检测到 {len(timed)} 个时段（如「{timed[0].label}」），共 {tasks} 条内容 → 建议「周计划」",
            )
        elif dated:
            self.radio_due.setChecked(True)
            self._detect(
                "ok",
                f"检测到 {len(dated)} 个日期（如「{dated[0].label}」），共 {tasks} 条内容 → 建议「截止日」",
            )
        else:
            self.radio_memo.setChecked(True)
            self._detect(
                "warn", f"没有时段也没有日期，共 {tasks} 条内容 → 按「备忘单」显示"
            )

    def _on_mode_changed(self) -> None:
        node = self._selected_node()
        if node is None:
            return
        mode = self._selected_mode()
        result = map_document(_wrap(node), MappingConfig(root_path=None, mode=mode))
        self._detect("hint", f"按「{MODE_LABELS[mode]}」解析：{result.task_count} 条事项")

    def _detect(self, kind: str, text: str) -> None:
        self.detect_label.setObjectName(kind)
        self.detect_label.style().unpolish(self.detect_label)
        self.detect_label.style().polish(self.detect_label)
        self.detect_label.setText(text)

    def _selected_mode(self) -> str:
        if self.radio_week.isChecked():
            return MODE_WEEK
        if self.radio_due.isChecked():
            return MODE_DUE
        return MODE_MEMO

    # ---------- 保存 ----------

    def prefill(self, config: dict | None, config_dir: Path | None = None) -> None:
        """用现有配置回填：数据源、根节点、模式，以及刷新间隔/强调色/自启。"""
        config = config or {}
        behavior = {**DEFAULT_BEHAVIOR, **(config.get("behavior") or {})}
        panel = {**DEFAULT_PANEL, **(config.get("panel") or {})}
        self._original = config
        if config_dir is not None:
            self._config_dir = config_dir
        self._sections = Config(self._config_dir / "config.json", config).sections
        self._show_sections()

        index = self.refresh_combo.findData(int(behavior.get("refreshMs", 5000)))
        if index < 0:
            self.refresh_combo.addItem(f"{int(behavior.get('refreshMs', 5000)) // 1000} 秒",
                                       int(behavior.get("refreshMs", 5000)))
            index = self.refresh_combo.count() - 1
        self.refresh_combo.setCurrentIndex(index)

        self._custom_accent = custom_accent(panel)
        self._saved_accents = saved_accents(panel)
        hidden = panel.get("hiddenAccents")
        self._hidden_accents = {key for key in PRESET_NAMES if isinstance(hidden, list) and key in hidden}
        self._populate_accents(panel.get("accent", "auto"))

        theme_index = self.theme_combo.findData(panel.get("theme", "cream"))
        self.theme_combo.setCurrentIndex(max(0, theme_index))

        from ..windows import autostart, shortcut

        self.autostart_check.setChecked(bool(behavior.get("autostart")) or autostart.is_enabled())
        self.shortcut_check.setChecked(
            bool(behavior.get("desktopShortcut", True)) or shortcut.desktop_path().exists()
        )

        # 数据源 + 之前选过的根节点：打开设置时直接定位到那儿
        source = config.get("source") or {}
        if source.get("type"):
            display = source.get("path") or f"幕布 / {source.get('docId', '')}"
            if self._load(source, display, quiet=not self._add_section) and not self._add_section:
                saved = (config.get("mapping") or {}).get("root_path") or []
                self._select_path(saved)
                mode = (config.get("mapping") or {}).get("mode")
                radio = {
                    MODE_WEEK: self.radio_week,
                    MODE_DUE: self.radio_due,
                    MODE_MEMO: self.radio_memo,
                }.get(mode)
                self._restoring = False
                if radio is not None:
                    radio.setChecked(True)
                self._on_mode_changed()
        self._apply_appearance()

    def _select_path(self, path: list[str], *, focus: bool = True) -> None:
        """按 root_path 在树里定位并滚动到对应节点。"""
        if not path:
            return
        self._restoring = True
        item = None
        for i in range(self.tree.topLevelItemCount()):
            candidate = self.tree.topLevelItem(i)
            if _node_text(candidate) == path[0]:
                item = candidate
                break
        if item is None:
            self._restoring = False
            return
        for name in path[1:]:
            found = None
            for j in range(item.childCount()):
                child = item.child(j)
                if _node_text(child) == name:
                    found = child
                    break
            if found is None:
                break
            item = found

        parent = item.parent()
        while parent is not None:
            parent.setExpanded(True)
            parent = parent.parent()
        self.tree.setCurrentItem(item)
        item.setSelected(True)
        self.tree.scrollToItem(item, QAbstractItemView.PositionAtCenter)
        if focus:
            self.tree.setFocus()

    def _save(self):
        # 槽函数里抛异常会让 PyQt5 直接 abort（表现为闪退），这里兜住
        try:
            self._save_inner()
        except Exception as exc:  # noqa: BLE001
            import traceback

            traceback.print_exc()
            QMessageBox.warning(self, "保存失败", f"{type(exc).__name__}: {exc}")

    def _save_inner(self):
        if not self._source:
            QMessageBox.warning(self, "还没选数据源", "先选一个 Markdown 文件、文件夹或幕布文档。")
            return
        path = self._root_path()
        if not path:
            QMessageBox.warning(self, "还没选根节点", "在中间的树里点一个节点，作为解析起点。")
            return

        mapping = dict(self._original.get("mapping") or {})
        mode = self._selected_mode()
        if self._add_section:
            if any(
                section.get("root_path") == path and normalize_mode(section.get("mode")) == mode
                for section in [mapping, *self._sections]
            ):
                QMessageBox.information(self, "区块已存在", "这个节点已经用同样的模式显示在面板上。")
                return
            mapping["sections"] = [*self._sections, {"root_path": path, "mode": mode}]
            self.result_config = {**self._original, "mapping": mapping}
            self.accept()
            return

        mapping.update(root_path=path, mode=mode)
        if self._sections or "sections" in mapping:
            mapping["sections"] = list(self._sections)

        refresh_ms = int(self.refresh_combo.currentData() or 5000)

        self.result_config = {
            **self._original,
            "version": self._original.get("version", 1),
            "source": self._source,
            "mapping": mapping,
            "panel": self._panel_preferences(),
            "behavior": {
                **(self._original.get("behavior") or {}),
                "refreshMs": refresh_ms,
                "autostart": self.autostart_check.isChecked(),
                "desktopShortcut": self.shortcut_check.isChecked(),
            },
        }
        self.accept()


def _wrap(node: Node) -> Node:
    """把选中的节点当成根：包一层虚拟根，便于复用 map_document 的逻辑。"""
    root = Node(id="settings-root", text=node.text)
    root.children = node.children
    return root


def _node_text(item: QTreeWidgetItem) -> str:
    return (item.data(0, Qt.UserRole) or item.text(0)).strip()

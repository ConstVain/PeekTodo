"""PeekTodo 设置面板。

第一次运行和之后的"设置"共用一个对话框：选数据源、选根节点、选模式，
外加刷新间隔、强调色、开机自启。
"""

from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import Qt
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
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from ..config import DEFAULT_BEHAVIOR, DEFAULT_PANEL, DEFAULT_PERIODS
from ..model import Node
from ..opener import open_source
from ..sources.base import SourceError
from ..sources.markdown import MarkdownSource
from ..sources.mubu import MubuSource, list_documents
from ..template import DEFAULT_FILENAME, write_template
from ..structure import (
    MODE_DUE,
    MODE_LABELS,
    MODE_MEMO,
    MODE_WEEK,
    MappingConfig,
    map_document,
)

ACCENT_CHOICES = [
    ("auto", "跟随模式", "#7aa2ff"),
    ("blue", "湖蓝", "#7aa2ff"),
    ("violet", "雾紫", "#a78bfa"),
    ("teal", "青绿", "#2dd4bf"),
]
REFRESH_CHOICES = [3000, 5000, 10000, 30000, 60000]

QSS = """
QDialog { background: #17181d; }
QLabel { color: #d8dce4; }
QLabel#title { color: #f2f4f8; font-size: 19px; font-weight: 600; }
QLabel#subtitle { color: #7c8391; font-size: 12px; }
QLabel#sectionTitle { color: #9aa1ad; font-size: 11px; letter-spacing: 1.2px; }
QLabel#hint { color: #7c8391; font-size: 12px; }
QLabel#ok { color: #6ee7a8; font-size: 12px; }
QLabel#warn { color: #f0b45f; font-size: 12px; }
QLabel#source { color: #b6bcc7; font-size: 12px; }
QFrame#section {
    background: #1e2027; border: 1px solid #262932; border-radius: 10px;
}
QPushButton {
    background: #262932; color: #d8dce4; border: 1px solid #333744;
    border-radius: 7px; padding: 7px 14px; font-size: 13px;
}
QPushButton:hover { background: #2e323d; border-color: #434858; }
QPushButton:pressed { background: #22252d; }
QPushButton#primary {
    background: #3b5bdb; border-color: #4c6ef5; color: #ffffff; font-weight: 600;
}
QPushButton#primary:hover { background: #4c6ef5; }
QPushButton#ghost { background: transparent; border-color: #2c303a; }
QTreeWidget {
    background: #14151a; color: #d8dce4; border: 1px solid #2a2d37;
    border-radius: 8px; outline: none; font-size: 13px; padding: 4px;
}
QTreeWidget::item { padding: 3px 2px; }
QTreeWidget::item:selected { background: #2b3350; border-radius: 4px; }
QTreeWidget::item:hover { background: #22252d; }
QRadioButton { color: #d8dce4; font-size: 13px; spacing: 6px; }
QComboBox {
    background: #262932; color: #d8dce4; border: 1px solid #333744;
    border-radius: 7px; padding: 6px 10px; font-size: 13px; min-width: 110px;
}
QComboBox::drop-down { border: none; width: 18px; }
QComboBox QAbstractItemView {
    background: #202229; color: #d8dce4; border: 1px solid #333744;
    selection-background-color: #2b3350;
}
QCheckBox { color: #d8dce4; font-size: 13px; spacing: 8px; }
"""


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
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PeekTodo 设置")
        self.resize(760, 720)
        self.setStyleSheet(QSS)
        self.result_config: dict | None = None

        self._source: dict = {}
        self._tree_root: Node | None = None
        self._node_by_item: dict[int, Node] = {}

        self._build_ui()

    # ---------- 构建 ----------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 18)
        root.setSpacing(14)

        title = QLabel("PeekTodo 设置")
        title.setObjectName("title")
        subtitle = QLabel("选好数据源和结构后保存；以后想改随时从托盘菜单打开这里")
        subtitle.setObjectName("subtitle")
        root.addWidget(title)
        root.addWidget(subtitle)

        root.addWidget(self._source_section())
        root.addWidget(self._structure_section(), 1)
        root.addWidget(self._appearance_section())

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        btn_cancel = QPushButton("取消")
        btn_cancel.setObjectName("ghost")
        btn_save = QPushButton("保存")
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
        reason = open_source(self._source)
        if reason:
            QMessageBox.warning(self, "打不开数据源", reason)

    def _structure_section(self) -> Section:
        section = Section("结构")
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setMinimumHeight(220)
        self.tree.itemSelectionChanged.connect(self._on_select)
        section.body.addWidget(self.tree, 1)

        hint = QLabel("在树里点一个节点，作为解析的起点")
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
        self.radio_week.toggled.connect(self._on_mode_changed)
        modes.addStretch(1)
        section.body.addLayout(modes)

        self.detect_label = QLabel("")
        self.detect_label.setObjectName("hint")
        self.detect_label.setWordWrap(True)
        section.body.addWidget(self.detect_label)
        return section

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
        self.accent_combo = QComboBox()
        for key, label, color in ACCENT_CHOICES:
            self.accent_combo.addItem(label, key)
            self.accent_combo.setItemData(self.accent_combo.count() - 1, color, Qt.ToolTipRole)
        row1.addWidget(self.accent_combo)
        row1.addStretch(1)
        self.autostart_check = QCheckBox("开机自启")
        row1.addWidget(self.autostart_check)
        section.body.addLayout(row1)

        note = QLabel("强调色选「跟随模式」时，周计划用蓝、截止日用琥珀、备忘单用绿")
        note.setObjectName("hint")
        section.body.addWidget(note)
        return section

    @staticmethod
    def _plain(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("hint")
        return label

    # ---------- 数据源 ----------

    def _load(self, source: dict, display: str) -> None:
        try:
            fetcher = (
                MarkdownSource(source["path"], recursive=source.get("recursive", True))
                if source["type"] == "markdown"
                else MubuSource(source["docId"])
            )
            result = fetcher.fetch()
        except SourceError as exc:
            QMessageBox.warning(self, "读不到这个数据源", str(exc))
            return

        self._source = source
        self.source_label.setText(display)
        self.source_label.setObjectName("source")
        self.source_label.setStyleSheet("color:#b6bcc7; font-size:12px;")
        self.btn_open.setEnabled(True)
        self._tree_root = result.tree
        self._fill_tree(result.tree)
        self.detect_label.setText("")

    def _pick_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 Markdown 文件", "", "Markdown (*.md *.markdown);;所有文件 (*)"
        )
        if path:
            self._load({"type": "markdown", "path": path}, path)

    def _new_markdown(self):
        default = str(Path.home() / "Documents" / DEFAULT_FILENAME)
        path, _ = QFileDialog.getSaveFileName(self, "新建计划文档", default, "Markdown (*.md)")
        if not path:
            return
        if not path.lower().endswith((".md", ".markdown")):
            path += ".md"
        try:
            target = write_template(path)
        except OSError as exc:
            QMessageBox.warning(self, "写不了这个位置", str(exc))
            return

        self._load({"type": "markdown", "path": str(target)}, str(target))
        self.source_label.setText(f"{target}（新建，可直接编辑）")
        open_source({"type": "markdown", "path": str(target)})

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
            path.append(item.text(0).rstrip("…"))
            item = item.parent()
        return list(reversed(path))

    def _selected_node(self) -> Node | None:
        items = self.tree.selectedItems()
        return self._node_by_item.get(id(items[0])) if items else None

    # ---------- 检测 ----------

    def _on_select(self) -> None:
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
        self.detect_label.setStyleSheet(
            {"ok": "#6ee7a8", "warn": "#f0b45f", "hint": "#7c8391"}[kind] + "; font-size:12px;"
        )
        self.detect_label.setText(text)

    def _selected_mode(self) -> str:
        if self.radio_week.isChecked():
            return MODE_WEEK
        if self.radio_due.isChecked():
            return MODE_DUE
        return MODE_MEMO

    # ---------- 保存 ----------

    def prefill(self, config: dict | None) -> None:
        """用现有配置回填：刷新间隔、强调色、开机自启。"""
        config = config or {}
        behavior = {**DEFAULT_BEHAVIOR, **(config.get("behavior") or {})}
        panel = {**DEFAULT_PANEL, **(config.get("panel") or {})}

        index = self.refresh_combo.findData(int(behavior.get("refreshMs", 5000)))
        if index < 0:
            self.refresh_combo.addItem(f"{int(behavior.get('refreshMs', 5000)) // 1000} 秒",
                                       int(behavior.get("refreshMs", 5000)))
            index = self.refresh_combo.count() - 1
        self.refresh_combo.setCurrentIndex(index)

        accent = self.accent_combo.findData(panel.get("accent", "auto"))
        self.accent_combo.setCurrentIndex(max(0, accent))

        from .. import autostart

        self.autostart_check.setChecked(bool(behavior.get("autostart")) or autostart.is_enabled())

    def _save(self):
        if not self._source:
            QMessageBox.warning(self, "还没选数据源", "先选一个 Markdown 文件、文件夹或幕布文档。")
            return
        path = self._root_path()
        if not path:
            QMessageBox.warning(self, "还没选根节点", "在中间的树里点一个节点，作为解析起点。")
            return

        refresh_ms = int(self.refresh_combo.currentData() or 5000)
        accent = self.accent_combo.currentData() or "auto"

        self.result_config = {
            "version": 1,
            "source": self._source,
            "mapping": {
                "root_path": path,
                "mode": self._selected_mode(),
                "aliases": {},
            },
            "vocabulary": {"weekdays": {}, "periods": {}},
            "periods": DEFAULT_PERIODS,
            "panel": {**DEFAULT_PANEL, "accent": accent},
            "behavior": {**DEFAULT_BEHAVIOR, "refreshMs": refresh_ms,
                         "autostart": self.autostart_check.isChecked()},
        }
        self.accept()


def _wrap(node: Node) -> Node:
    """把选中的节点当成根：包一层虚拟根，便于复用 map_document 的逻辑。"""
    root = Node(id="settings-root", text=node.text)
    root.children = node.children
    return root

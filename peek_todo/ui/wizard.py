"""首次运行向导：选数据源 -> 选根节点 -> 选模式 -> 写出 config.json。

设计原则：不让用户写任何语法。点一个节点，看一段"我读到了什么"，确认即可。
"""

from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFileDialog,
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
from ..sources.base import SourceError
from ..sources.markdown import MarkdownSource
from ..sources.mubu import MubuSource, list_documents
from ..structure import (
    MODE_DUE,
    MODE_LABELS,
    MODE_MEMO,
    MODE_WEEK,
    MappingConfig,
    map_document,
)

TITLE_QSS = "font-size:15px; font-weight:600; color:#eef0f4;"
HINT_QSS = "color:#9aa1ad; font-size:12px;"
OK_QSS = "color:#6ee7a8; font-size:12px;"
WARN_QSS = "color:#f0b45f; font-size:12px;"

DIALOG_QSS = """
QDialog { background: #1a1b20; }
QLabel { color: #d8dce4; }
QPushButton {
    background: #2a2c34; color: #e6e8ee; border: 1px solid #3a3d47;
    border-radius: 6px; padding: 6px 14px;
}
QPushButton:hover { background: #33363f; }
QPushButton:default { border-color: #4f6ef7; }
QTreeWidget {
    background: #14151a; color: #d8dce4; border: 1px solid #2e313a;
    border-radius: 6px; outline: none;
}
QTreeWidget::item:selected { background: #2b3350; }
QRadioButton { color: #d8dce4; spacing: 6px; }
QLineEdit, QInputDialog { background: #14151a; color: #e6e8ee; }
"""


class SetupWizard(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PeekTodo · 首次设置")
        self.resize(720, 620)
        self.setStyleSheet(DIALOG_QSS)
        self.result_config: dict | None = None

        self._source: dict = {}
        self._tree_root: Node | None = None
        self._node_by_item: dict[int, Node] = {}

        self._build_ui()

    # ---------- UI ----------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 16)
        root.setSpacing(10)

        root.addWidget(self._label("1. 数据从哪来", TITLE_QSS))
        source_row = QHBoxLayout()
        btn_file = QPushButton("选择 Markdown 文件…")
        btn_dir = QPushButton("选择文件夹…")
        btn_mubu = QPushButton("幕布文档…")
        btn_file.clicked.connect(self._pick_file)
        btn_dir.clicked.connect(self._pick_dir)
        btn_mubu.clicked.connect(self._pick_mubu)
        for btn in (btn_file, btn_dir, btn_mubu):
            source_row.addWidget(btn)
        source_row.addStretch(1)
        root.addLayout(source_row)

        self.source_label = self._label("还没有选择数据源", HINT_QSS)
        root.addWidget(self.source_label)

        root.addWidget(self._label("2. 从哪一层开始（点一个节点当根）", TITLE_QSS))
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setMinimumHeight(280)
        self.tree.itemSelectionChanged.connect(self._on_select)
        root.addWidget(self.tree, 1)

        root.addWidget(self._label("3. 结构", TITLE_QSS))
        mode_row = QHBoxLayout()
        self.radio_week = QRadioButton("周计划：下一级是时段（周一下午…）")
        self.radio_due = QRadioButton("截止日：下一级是日期（11月2日…）")
        self.radio_memo = QRadioButton("备忘单：平铺清单，没有时间")
        self.radio_week.setChecked(True)
        group = QButtonGroup(self)
        group.addButton(self.radio_week)
        group.addButton(self.radio_due)
        group.addButton(self.radio_memo)
        self.radio_week.toggled.connect(self._on_mode_changed)
        mode_row.addWidget(self.radio_week)
        mode_row.addWidget(self.radio_due)
        mode_row.addWidget(self.radio_memo)
        mode_row.addStretch(1)
        root.addLayout(mode_row)

        self.detect_label = self._label("", HINT_QSS)
        self.detect_label.setWordWrap(True)
        root.addWidget(self.detect_label)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        btn_cancel = QPushButton("取消")
        btn_save = QPushButton("保存并启动")
        btn_save.setDefault(True)
        btn_cancel.clicked.connect(self.reject)
        btn_save.clicked.connect(self._save)
        bottom.addWidget(btn_cancel)
        bottom.addWidget(btn_save)
        root.addLayout(bottom)

    @staticmethod
    def _label(text: str, style: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet(style)
        return label

    # ---------- 数据源 ----------

    def _set_source(self, source: dict, display: str, fetch_ok: bool = True):
        self._source = source
        self.source_label.setText(display)
        self.source_label.setStyleSheet(HINT_QSS if fetch_ok else WARN_QSS)

    def _load(self, source: dict, display: str) -> None:
        try:
            if source["type"] == "markdown":
                fetcher = MarkdownSource(source["path"], recursive=source.get("recursive", True))
            else:
                fetcher = MubuSource(source["docId"])
            result = fetcher.fetch()
        except SourceError as exc:
            QMessageBox.warning(self, "读不到这个数据源", str(exc))
            return

        self._set_source(source, display)
        self._tree_root = result.tree
        self._fill_tree(result.tree)
        self.detect_label.setText("")

    def _pick_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择 Markdown 文件", "", "Markdown (*.md *.markdown);;所有文件 (*)")
        if path:
            self._load({"type": "markdown", "path": path}, path)

    def _pick_dir(self):
        path = QFileDialog.getExistingDirectory(self, "选择包含 Markdown 的文件夹")
        if path:
            self._load({"type": "markdown", "path": path, "recursive": True}, path)

    def _pick_mubu(self):
        docs = list_documents()
        if not docs:
            QMessageBox.information(
                self, "没找到幕布文档",
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
            item = self._make_item(child, 0)
            self.tree.addTopLevelItem(item)
        self.tree.expandToDepth(1)

    def _make_item(self, node: Node, depth: int) -> QTreeWidgetItem:
        text = node.text or "(无标题)"
        if len(text) > 44:
            text = text[:43] + "…"
        item = QTreeWidgetItem([text])
        self._node_by_item[id(item)] = node
        item.setData(0, Qt.UserRole, node.text)
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
        if not items:
            return None
        return self._node_by_item.get(id(items[0]))

    # ---------- 检测 ----------

    def _on_select(self) -> None:
        node = self._selected_node()
        if node is None:
            return
        probe = map_document(_wrap(node), MappingConfig(root_path=None, mode=MODE_WEEK))
        due_probe = map_document(_wrap(node), MappingConfig(root_path=None, mode=MODE_DUE))
        timed = [g for g in probe.groups if g.when is not None]
        dated = [g for g in due_probe.groups if g.due is not None]
        tasks = due_probe.task_count or probe.task_count

        if timed and len(timed) >= len(dated):
            self.radio_week.setChecked(True)
            self.detect_label.setStyleSheet(OK_QSS)
            self.detect_label.setText(
                f"这个节点下面有 {len(timed)} 个时段（如「{timed[0].label}」）、共 {tasks} 条内容 → 像「周计划」"
            )
        elif dated:
            self.radio_due.setChecked(True)
            self.detect_label.setStyleSheet(OK_QSS)
            self.detect_label.setText(
                f"这个节点下面有 {len(dated)} 个日期（如「{dated[0].label}」）、共 {tasks} 条内容 → 像「截止日」"
            )
        else:
            self.radio_memo.setChecked(True)
            self.detect_label.setStyleSheet(WARN_QSS)
            self.detect_label.setText(
                f"这个节点下面既没有时段也没有日期，共 {tasks} 条内容 → 按「备忘单」显示"
            )

    def _selected_mode(self) -> str:
        if self.radio_week.isChecked():
            return MODE_WEEK
        if self.radio_due.isChecked():
            return MODE_DUE
        return MODE_MEMO

    def _on_mode_changed(self) -> None:
        node = self._selected_node()
        if node is None:
            return
        mode = self._selected_mode()
        result = map_document(_wrap(node), MappingConfig(root_path=None, mode=mode))
        self.detect_label.setStyleSheet(HINT_QSS)
        self.detect_label.setText(f"按「{MODE_LABELS[mode]}」解析：{result.task_count} 条事项")

    # ---------- 保存 ----------

    def _save(self):
        if not self._source:
            QMessageBox.warning(self, "还没选数据源", "先选一个 Markdown 文件、文件夹或幕布文档。")
            return
        path = self._root_path()
        if not path:
            QMessageBox.warning(self, "还没选根节点", "在中间的树里点一个节点，作为解析起点。")
            return

        config = {
            "version": 1,
            "source": self._source,
            "mapping": {
                "root_path": path,
                "mode": self._selected_mode(),
                "aliases": {},
            },
            "vocabulary": {"weekdays": {}, "periods": {}},
            "periods": DEFAULT_PERIODS,
            "panel": DEFAULT_PANEL,
            "behavior": DEFAULT_BEHAVIOR,
        }
        self.result_config = config
        self.accept()


def _wrap(node: Node) -> Node:
    """把选中的节点当成根：包一层虚拟根，便于复用 map_document 的逻辑。"""
    root = Node(id="wizard-root", text=node.text)
    root.children = node.children
    return root

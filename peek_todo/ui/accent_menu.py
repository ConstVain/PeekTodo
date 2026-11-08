"""Accent menu rows with a separate remove target."""

from PyQt5.QtCore import QEvent, QRect, Qt, pyqtSignal
from PyQt5.QtGui import QPainter, QPen
from PyQt5.QtWidgets import QComboBox, QListView, QStyle, QStyledItemDelegate, QStyleOptionViewItem

REMOVABLE_ROLE = Qt.UserRole + 1


def _remove_rect(row: QRect) -> QRect:
    return QRect(row.right() - 25, row.top(), 26, row.height())


class _AccentRows(QStyledItemDelegate):
    def paint(self, painter, option, index):
        if not index.data(REMOVABLE_ROLE):
            super().paint(painter, option, index)
            return
        area = _remove_rect(option.rect)
        label = QStyleOptionViewItem(option)
        label.rect.setRight(area.left() - 1)
        super().paint(painter, label, index)

        selected = bool(option.state & QStyle.State_Selected)
        painter.save()
        if selected:
            painter.fillRect(area, option.palette.highlight())
        color = option.palette.highlightedText() if selected else option.palette.text()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(color.color(), 1.2))
        center = area.center()
        x, y = center.x(), center.y()
        painter.drawLine(x - 6, y - 4, x + 6, y - 4)
        painter.drawLine(x - 2, y - 6, x + 2, y - 6)
        painter.drawRect(x - 4, y - 2, 8, 8)
        painter.drawLine(x, y, x, y + 4)
        painter.restore()

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        if index.data(REMOVABLE_ROLE):
            size.setWidth(size.width() + 26)
        return size


class AccentComboBox(QComboBox):
    remove_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        view = QListView(self)
        self.setView(view)
        self.setItemDelegate(_AccentRows(view))
        view.viewport().installEventFilter(self)
        self._pressed_remove = None

    def eventFilter(self, watched, event):
        if watched == self.view().viewport() and event.type() in (
            QEvent.MouseButtonPress, QEvent.MouseButtonRelease,
        ) and event.button() == Qt.LeftButton:
            view = self.view()
            index = view.indexAt(event.pos())
            over_remove = index.data(REMOVABLE_ROLE) and _remove_rect(view.visualRect(index)).contains(event.pos())
            if event.type() == QEvent.MouseButtonPress:
                self._pressed_remove = index.data(Qt.UserRole) if over_remove else None
                if self._pressed_remove is not None:
                    return True
            elif self._pressed_remove is not None:
                key, self._pressed_remove = self._pressed_remove, None
                if over_remove and index.data(Qt.UserRole) == key:
                    self.hidePopup()
                    self.remove_requested.emit(key)
                return True
        return super().eventFilter(watched, event)

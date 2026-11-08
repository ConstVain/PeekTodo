"""HSV accent picker with a saturation/value square and a vertical hue strip."""

from PyQt5.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QLinearGradient, QPainter, QPen
from PyQt5.QtWidgets import QDialog, QDialogButtonBox, QHBoxLayout, QInputDialog, QLabel, QVBoxLayout, QWidget


class ColorSurface(QWidget):
    changed = pyqtSignal(QColor)

    def __init__(self, color: QColor, parent=None):
        super().__init__(parent)
        self.setFixedSize(272, 240)
        self.setCursor(Qt.CrossCursor)
        self._square = QRectF(8, 8, 224, 224)
        self._strip = QRectF(244, 8, 20, 224)
        self._hue = max(0.0, color.hsvHueF())
        self._saturation = color.hsvSaturationF()
        self._value = color.valueF()
        self._drag_area = None

    def color(self) -> QColor:
        return QColor.fromHsvF(self._hue % 1.0, self._saturation, self._value)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        square, strip = self._square, self._strip
        saturation = QLinearGradient(square.topLeft(), square.topRight())
        saturation.setColorAt(0, QColor(Qt.white))
        saturation.setColorAt(1, QColor.fromHsvF(self._hue % 1.0, 1, 1))
        painter.fillRect(square, saturation)

        value = QLinearGradient(square.topLeft(), square.bottomLeft())
        value.setColorAt(0, QColor(0, 0, 0, 0))
        value.setColorAt(1, QColor(Qt.black))
        painter.fillRect(square, value)

        hue = QLinearGradient(strip.topLeft(), strip.bottomLeft())
        for step in range(7):
            hue.setColorAt(step / 6, QColor.fromHsvF((step % 6) / 6, 1, 1))
        painter.fillRect(strip, hue)

        selected = QPointF(square.left() + self._saturation * square.width(),
                           square.top() + (1 - self._value) * square.height())
        marker_y = strip.top() + self._hue * strip.height()
        painter.setBrush(Qt.NoBrush)
        for color, width in ((Qt.black, 3), (Qt.white, 1)):
            painter.setPen(QPen(color, width))
            painter.drawEllipse(selected, 5, 5)
            painter.drawLine(QPointF(strip.left() - 2, marker_y),
                             QPointF(strip.right() + 2, marker_y))

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        for area in (self._square, self._strip):
            if area.contains(event.localPos()):
                self._drag_area = area
                self._select_at(event.localPos())
                break

    def mouseMoveEvent(self, event):
        if self._drag_area is not None:
            self._select_at(event.localPos())

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._drag_area is not None:
            self._select_at(event.localPos())
            self._drag_area = None

    def _select_at(self, position: QPointF) -> None:
        area = self._drag_area
        y = max(0.0, min(1.0, (position.y() - area.top()) / area.height()))
        if area == self._strip:
            self._hue = y
        else:
            self._saturation = max(0.0, min(1.0, (position.x() - area.left()) / area.width()))
            self._value = 1 - y
        self.update()
        self.changed.emit(self.color())


class AccentPicker(QDialog):
    def __init__(self, color: QColor, parent=None):
        super().__init__(parent)
        self.setWindowTitle("自定义强调色")
        self.saved_name: str | None = None
        layout = QVBoxLayout(self)
        self.surface = ColorSurface(color, self)
        layout.addWidget(self.surface)
        preview_row = QHBoxLayout()
        self.swatch = QLabel()
        self.swatch.setFixedSize(18, 18)
        self.preview = QLabel()
        self.surface.changed.connect(self._preview_color)
        self._preview_color(color)
        preview_row.addWidget(self.swatch)
        preview_row.addWidget(self.preview)
        preview_row.addStretch()
        layout.addLayout(preview_row)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("确定")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        add = buttons.addButton("添加到列表", QDialogButtonBox.ActionRole)
        add.clicked.connect(self._add_to_list)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _add_to_list(self) -> None:
        hex_color = self.color().name().upper()
        name, accepted = QInputDialog.getText(self, "添加到强调色列表", "颜色名称", text=hex_color)
        if accepted:
            self.saved_name = name.strip() or hex_color
            self.accept()

    def _preview_color(self, color: QColor) -> None:
        self.preview.setText(color.name().upper())
        self.swatch.setStyleSheet(f"background: {color.name()}; border-radius: 4px;")

    def color(self) -> QColor:
        return self.surface.color()

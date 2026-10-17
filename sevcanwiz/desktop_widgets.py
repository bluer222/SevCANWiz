"""Native controls and instrument plots for the commissioning workspace."""

import math
from html import escape
from PySide6.QtCore import Qt, Signal, QRectF, QPointF, QSignalBlocker
from PySide6.QtGui import QColor, QPainter, QPen, QFont, QPainterPath, QPixmap, QIcon
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QHBoxLayout, QVBoxLayout, QComboBox,
    QDoubleSpinBox, QLineEdit, QCheckBox, QPushButton, QStackedWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QDialog, QDialogButtonBox,
    QFormLayout, QScrollArea,
)
from .desktop_state import number_text

INSTRUMENT = {
    "face": "#f4f5f6", "field": "#ffffff", "ink": "#283138",
    "label": "#626d76", "rule": "#d3d8dc", "trace": "#286a9d",
    "proposal": "#edf4fa", "warning": "#94621b", "fault": "#b03c35",
}


def system_icon(key):
    pixmap = QPixmap(32, 32)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor("#3c566b"), 1.8))
    painter.setFont(QFont("Noto Sans", 10, QFont.Weight.DemiBold))
    if key in ("motor", "aux"):
        painter.drawEllipse(QRectF(6, 6, 20, 20))
        painter.drawLine(2, 16, 6, 16)
        painter.drawLine(26, 16, 30, 16)
        painter.drawText(QRectF(6, 6, 20, 20), Qt.AlignmentFlag.AlignCenter, "M" if key == "motor" else "P")
    elif key == "battery":
        painter.drawRect(QRectF(3, 8, 24, 16))
        painter.drawRect(QRectF(27, 13, 3, 6))
        painter.drawLine(8, 16, 14, 16)
        painter.drawLine(11, 13, 11, 19)
        painter.drawLine(18, 16, 23, 16)
    elif key == "pedals":
        painter.drawLine(6, 26, 26, 26)
        painter.drawLine(10, 25, 22, 10)
        painter.drawRoundedRect(QRectF(16, 3, 10, 10), 2, 2)
    elif key == "drive":
        painter.drawRect(QRectF(4, 10, 24, 12))
        painter.drawEllipse(QRectF(6, 20, 6, 6))
        painter.drawEllipse(QRectF(20, 20, 6, 6))
        painter.drawLine(8, 10, 12, 5)
        painter.drawLine(12, 5, 23, 5)
        painter.drawLine(23, 5, 26, 10)
    elif key in ("instruments", "diagnostics"):
        painter.drawRoundedRect(QRectF(3, 4, 26, 23), 2, 2)
        path = QPainterPath(QPointF(6, 20))
        for x, y in ((10, 20), (13, 10), (17, 23), (21, 15), (26, 15)):
            path.lineTo(x, y)
        painter.drawPath(path)
    elif key in ("can", "io"):
        painter.drawLine(5, 16, 27, 16)
        for x, y in ((5, 5), (23, 5), (14, 23)):
            painter.drawRect(QRectF(x, y, 5, 5))
            painter.drawLine(x+2, y+5 if y < 16 else y, x+2, 16)
    elif key == "backups":
        painter.drawRoundedRect(QRectF(5, 3, 22, 26), 2, 2)
        painter.drawRect(QRectF(10, 4, 12, 8))
        painter.drawRect(QRectF(10, 20, 12, 8))
    else:
        for y in (8, 16, 24):
            painter.drawLine(4, y, 28, y)
            painter.drawRect(QRectF(9 if y == 16 else 20, y-3, 4, 6))
    painter.end()
    return QIcon(pixmap)


def help_button(callback, name):
    button = QPushButton("?")
    button.setObjectName("contextHelp")
    button.setFixedSize(22, 22)
    button.setAccessibleName(f"Help for {name}")
    button.setToolTip(f"Explain {name}")
    button.clicked.connect(lambda checked=False: callback())
    return button


class SettingEditor(QWidget):
    def __init__(self, state, key, help_requested, label=None, parent=None):
        super().__init__(parent)
        self.state, self.key = state, key
        self.setting = state.settings[key]
        self.setObjectName(f"setting_{key.replace(':', '_')}")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        heading = QHBoxLayout()
        heading.addWidget(QLabel(label or self.setting["name"]), 1)
        heading.addWidget(help_button(lambda: help_requested(key), label or self.setting["name"]))
        layout.addLayout(heading)
        self.stack = QStackedWidget()
        self.waiting = QLabel("Read controller to load value")
        self.waiting.setObjectName("secondaryText")
        self.stack.addWidget(self.waiting)
        self.editor = self.make_editor()
        self.stack.addWidget(self.editor)
        value_row = QHBoxLayout()
        value_row.addWidget(self.stack, 1)
        if self.setting["unit"]:
            unit = QLabel(self.setting["unit"])
            unit.setObjectName("secondaryText")
            value_row.addWidget(unit)
        layout.addLayout(value_row)
        self.permission = QLabel()
        self.permission.setObjectName("permissionText")
        self.permission.setWordWrap(True)
        layout.addWidget(self.permission)
        state.values_changed.connect(self.sync)
        state.permissions_changed.connect(self.sync)
        state.drafts_changed.connect(self.sync)
        self.sync()

    def make_editor(self):
        setting = self.setting
        if not setting["editable"]:
            return QLabel()
        if setting["bits"]:
            button = QPushButton("Edit fields...")
            button.clicked.connect(lambda: BitFieldsDialog(self.state, self.key, self.window()).exec())
            return button
        if setting["labels"]:
            editor = QComboBox()
            for raw, text in setting["labels"].items():
                editor.addItem(text, raw)
            editor.activated.connect(lambda _: self.state.stage(self.key, editor.currentText()))
        elif setting["type"] == "BOOLEAN":
            editor = QCheckBox("Enabled")
            editor.clicked.connect(lambda checked: self.state.stage(self.key, checked))
        elif setting["type"].startswith(("INTEGER", "UNSIGNED", "REAL")):
            editor = QDoubleSpinBox()
            step = setting["step"]
            editor.setDecimals(min(9, max(0, math.ceil(-math.log10(step))+1)) if isinstance(step, (int, float)) and step > 0 else 4)
            editor.setRange(setting["low"] if setting["low"] is not None else -1e12,
                            setting["high"] if setting["high"] is not None else 1e12)
            editor.setSingleStep(step if isinstance(step, (int, float)) else 0.1)
            editor.setKeyboardTracking(False)
            editor.editingFinished.connect(lambda: self.state.stage(self.key, editor.value()))
        else:
            editor = QLineEdit()
            editor.editingFinished.connect(lambda: self.state.stage(self.key, editor.text()))
        editor.setAccessibleName(setting["name"])
        editor.setToolTip(f"{setting['help']['range']}\nRequires {self.state.required(setting)}")
        return editor

    def sync(self):
        reading = self.state.readings.get(self.key, {})
        allowed = self.state.permitted(self.setting)
        self.permission.setText(f"{self.state.required(self.setting)}  |  {self.state.permission_text(self.setting)}")
        self.permission.setProperty("locked", self.setting["editable"] and not allowed)
        self.permission.style().unpolish(self.permission)
        self.permission.style().polish(self.permission)
        self.editor.setEnabled(allowed and bool(reading.get("bytes")) and not self.state.busy)
        if not reading.get("bytes"):
            self.waiting.setText(reading.get("error", "Read controller to load value"))
            self.stack.setCurrentIndex(0)
            return
        self.stack.setCurrentIndex(1)
        value = self.state.value(self.key)
        if isinstance(self.editor, QLabel):
            self.editor.setText(self.state.display(self.key, reading.get("label") if isinstance(reading.get("label"), str) else value))
            self.editor.setEnabled(True)
            return
        focused = QApplication.focusWidget()
        if focused and (focused is self.editor or self.editor.isAncestorOf(focused)):
            return
        with QSignalBlocker(self.editor):
            if isinstance(self.editor, QComboBox):
                index = self.editor.findData(value)
                if index < 0:
                    index = self.editor.findText(self.state.display(self.key, value))
                self.editor.setCurrentIndex(index)
            elif isinstance(self.editor, QCheckBox):
                self.editor.setChecked(bool(value))
            elif isinstance(self.editor, QDoubleSpinBox):
                self.editor.setValue(float(value or 0))
            elif isinstance(self.editor, QLineEdit):
                self.editor.setText(str(value or ""))
        self.editor.setProperty("draft", self.key in self.state.drafts)
        self.editor.style().unpolish(self.editor)
        self.editor.style().polish(self.editor)


class BitFieldsDialog(QDialog):
    def __init__(self, state, key, parent=None):
        super().__init__(parent)
        self.setWindowTitle(state.settings[key]["name"])
        self.resize(650, 550)
        self.state, self.key = state, key
        layout = QVBoxLayout(self)
        note = QLabel(f"Required: {state.required(state.settings[key])}. Your access: {state.role()}.\nFields are staged together and use the normal Apply workflow.")
        note.setWordWrap(True)
        layout.addWidget(note)
        body = QWidget()
        form = QFormLayout(body)
        form.setSpacing(8)
        self.controls = []
        self.stage_button = None
        setting = state.settings[key]
        raw = int(state.value(key) or 0)
        for field in setting["bits"]:
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            if field["labels"]:
                control = QComboBox()
                for value, label in field["labels"].items():
                    control.addItem(label, int(value))
                control.setCurrentIndex(control.findData((raw & field["mask"]) >> field["shift"]))
            else:
                control = QDoubleSpinBox()
                control.setDecimals(0)
                control.setRange(field["low"] or 0, field["high"] if field["high"] is not None else field["mask"] >> field["shift"])
                control.setValue((raw & field["mask"]) >> field["shift"])
            control.setAccessibleName(field["name"])
            row_layout.addWidget(control)
            def show(field=field):
                from .desktop_dialogs import ExplanationDialog
                ExplanationDialog(field["help"], self).exec()
            row_layout.addWidget(help_button(show, field["name"]))
            form.addRow(field["name"], row)
            self.controls.append((field, control))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(body)
        layout.addWidget(scroll, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        stage = buttons.addButton("Stage fields", QDialogButtonBox.ButtonRole.AcceptRole)
        self.stage_button = stage
        def sync_access():
            allowed = state.permitted(setting) and not state.busy and bool(state.readings.get(key, {}).get("bytes"))
            stage.setEnabled(allowed)
            for field, control in self.controls:
                control.setEnabled(allowed)
        state.permissions_changed.connect(sync_access)
        sync_access()
        stage.clicked.connect(self.stage)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def stage(self):
        raw = int(self.state.value(self.key) or 0)
        for field, control in self.controls:
            value = control.currentData() if isinstance(control, QComboBox) else int(control.value())
            raw = (raw & ~field["mask"]) | ((value << field["shift"]) & field["mask"])
        if self.state.stage(self.key, raw):
            self.accept()


class CurvePlot(QWidget):
    point_moved = Signal(int, float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.points = []
        self.controller_points = []
        self.percent = False
        self.editable = False
        self.x_label, self.y_label = "Input", "Output"
        self.selected = 0
        self.dragging = False
        self.setMinimumSize(300, 260)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName("Controller response curve")
        self.setMouseTracking(True)

    def bounds(self):
        if self.percent:
            return (0, 100, 0, 100)
        valid = [(x, y) for x, y in self.points if x is not None and y is not None]
        if not valid:
            return (0, 100, 0, 100)
        xlo, xhi = min(0, min(x for x, _ in valid)), max(x for x, _ in valid)
        ylo, yhi = min(0, min(y for _, y in valid)), max(y for _, y in valid)
        return (xlo, xhi+(xhi-xlo)*.06 if xhi>xlo else xlo+1,
                ylo, yhi+(yhi-ylo)*.06 if yhi>ylo else ylo+1)

    def plot_rect(self):
        return QRectF(64, 38, max(1, self.width()-88), max(1, self.height()-86))

    def coordinate(self, x, y):
        rect = self.plot_rect()
        xlo, xhi, ylo, yhi = self.bounds()
        return QPointF(rect.left()+(x-xlo)/(xhi-xlo)*rect.width(), rect.bottom()-(y-ylo)/(yhi-ylo)*rect.height())

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(INSTRUMENT["field"]))
        rect = self.plot_rect()
        xlo, xhi, ylo, yhi = self.bounds()
        painter.setFont(QFont(self.font().family(), 8))
        for i in range(5):
            f = i/4
            x, y = rect.left()+rect.width()*f, rect.bottom()-rect.height()*f
            painter.setPen(QPen(QColor(INSTRUMENT["rule"]), 1, Qt.PenStyle.DotLine))
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            painter.setPen(QColor(INSTRUMENT["label"]))
            suffix = "%" if self.percent else ""
            painter.drawText(QRectF(x-35, rect.bottom()+8, 70, 20), Qt.AlignmentFlag.AlignCenter, number_text(xlo+(xhi-xlo)*f, 0)+suffix)
            painter.drawText(QRectF(0, y-10, 54, 20), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, number_text(ylo+(yhi-ylo)*f, 1)+suffix)
        painter.drawText(QRectF(64, 8, rect.width(), 22), self.y_label+(" / %" if self.percent else ""))
        painter.drawText(QRectF(rect.left(), self.height()-24, rect.width(), 20), Qt.AlignmentFlag.AlignCenter, self.x_label+(" / %" if self.percent else ""))
        if not self.points or any(x is None or y is None for x, y in self.points):
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "Read controller to load curve points")
            return
        points = [(0, 0), *self.points, (100, 100)] if self.percent else self.points
        comparison = self.controller_points and self.controller_points != self.points and all(None not in p for p in self.controller_points)
        if comparison:
            actual = [(0, 0), *self.controller_points, (100, 100)] if self.percent else self.controller_points
            path = QPainterPath()
            path.moveTo(self.coordinate(*actual[0]))
            for point in actual[1:]:
                path.lineTo(self.coordinate(*point))
            painter.setPen(QPen(QColor("#8696a3"), 1.5, Qt.PenStyle.DashLine))
            painter.drawPath(path)
            painter.drawText(QRectF(rect.right()-225, 8, 225, 22), Qt.AlignmentFlag.AlignRight,
                             "Dashed: controller  /  Solid: proposed")
        if self.percent:
            painter.setPen(QPen(QColor("#b9c2c9"), 1, Qt.PenStyle.DashLine))
            painter.drawLine(self.coordinate(0, 0), self.coordinate(100, 100))
        path = QPainterPath()
        path.moveTo(self.coordinate(*points[0]))
        for point in points[1:]:
            path.lineTo(self.coordinate(*point))
        painter.setPen(QPen(QColor(INSTRUMENT["trace"] if self.editable else "#9aa4ad"), 2))
        painter.drawPath(path)
        for i, point in enumerate(self.points):
            center = self.coordinate(*point)
            painter.setBrush(QColor(INSTRUMENT["field"]))
            painter.setPen(QPen(QColor(INSTRUMENT["trace"] if self.editable else INSTRUMENT["label"]), 2))
            painter.drawEllipse(center, 5, 5)
            painter.drawText(QRectF(center.x()+9, center.y()-21, 45, 20), str(i+1))
            if self.hasFocus() and self.selected == i and self.editable:
                painter.setPen(QPen(QColor(INSTRUMENT["trace"]), 1, Qt.PenStyle.DotLine))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(center, 10, 10)

    def mousePressEvent(self, event):
        if not self.editable:
            return
        for i, point in enumerate(self.points):
            if None not in point:
                center = self.coordinate(*point)
                if (center-event.position()).manhattanLength() < 18:
                    self.selected, self.dragging = i, True
                    self.setFocus()
                    self.update()
                    break

    def mouseMoveEvent(self, event):
        if not self.dragging:
            return
        rect = self.plot_rect()
        xlo, xhi, ylo, yhi = self.bounds()
        x = xlo+(event.position().x()-rect.left())/rect.width()*(xhi-xlo)
        y = ylo+(rect.bottom()-event.position().y())/rect.height()*(yhi-ylo)
        self.move_point(x, y)

    def mouseReleaseEvent(self, event):
        self.dragging = False

    def move_point(self, x, y):
        i = self.selected
        xlo, xhi, ylo, yhi = self.bounds()
        epsilon = .1 if self.percent else max((xhi-xlo)*.00001, .001)
        xlo = self.points[i-1][0]+epsilon if i else .1 if self.percent else xlo
        xhi = self.points[i+1][0]-epsilon if i<len(self.points)-1 else 99.9 if self.percent else xhi
        if self.percent:
            ylo = self.points[i-1][1] if i else 0
            yhi = self.points[i+1][1] if i<len(self.points)-1 else 100
        self.point_moved.emit(i, min(xhi, max(xlo, x)), min(yhi, max(ylo, y)))

    def keyPressEvent(self, event):
        if not self.editable or not self.points or any(None in p for p in self.points):
            return super().keyPressEvent(event)
        key = event.key()
        if key == Qt.Key.Key_Space:
            self.selected = (self.selected+1) % len(self.points)
            self.update()
            return
        if key not in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down):
            return super().keyPressEvent(event)
        x, y = self.points[self.selected]
        xlo, xhi, ylo, yhi = self.bounds()
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            x += (xhi-xlo)/100 * (1 if key == Qt.Key.Key_Right else -1)
        else:
            y += (yhi-ylo)/100 * (1 if key == Qt.Key.Key_Up else -1)
        self.move_point(x, y)


class TrendPlot(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.samples = []
        self.title = "Live measurements"
        self.unit = ""
        self.setMinimumSize(320, 250)
        self.setAccessibleName("Live signal trend")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(INSTRUMENT["field"]))
        rect = QRectF(65, 35, max(1, self.width()-90), max(1, self.height()-78))
        valid = [(t, v) for t, v in self.samples if isinstance(v, (int, float)) and math.isfinite(v)]
        painter.setPen(QColor(INSTRUMENT["label"]))
        painter.drawText(QRectF(65, 6, rect.width(), 24), self.title+f" / {self.unit}")
        if not valid:
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "Waiting for controller samples")
            return
        low, high = min(v for _, v in valid), max(v for _, v in valid)
        padding = (high-low)*.15 or max(1, abs(high)*.05)
        low, high = low-padding, high+padding
        first, last = valid[0][0], valid[-1][0]
        span = max(.5, (last or 0)-(first or 0))
        for i in range(5):
            f = i/4
            y = rect.bottom()-rect.height()*f
            painter.setPen(QPen(QColor(INSTRUMENT["rule"]), 1, Qt.PenStyle.DotLine))
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            painter.setPen(QColor(INSTRUMENT["label"]))
            painter.drawText(QRectF(0, y-10, 57, 20), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, number_text(low+(high-low)*f, 1))
        path = QPainterPath()
        move = True
        for t, value in self.samples:
            if t is None or value is None:
                move = True
                continue
            point = QPointF(rect.left()+((t-first)/span)*rect.width(), rect.bottom()-(value-low)/(high-low)*rect.height())
            if move:
                path.moveTo(point)
                move = False
            else:
                path.lineTo(point)
        painter.setPen(QPen(QColor(INSTRUMENT["trace"]), 2))
        painter.drawPath(path)
        painter.setPen(QColor(INSTRUMENT["label"]))
        painter.drawText(QRectF(rect.left(), self.height()-26, rect.width(), 20), Qt.AlignmentFlag.AlignLeft, f"{span:.1f} seconds / {len(self.samples)} samples")
        painter.drawText(QRectF(rect.left(), self.height()-26, rect.width(), 20), Qt.AlignmentFlag.AlignRight, "SDO polling")


class InstrumentStrip(QWidget):
    SIGNALS = [("5100:01", "Battery voltage", "V", 70), ("5100:02", "Battery current", "A", 275),
               ("5100:04", "Heatsink", "°C", 100), ("606C:00", "Motor speed", "rpm", 6000)]

    def __init__(self, state, help_requested, parent=None):
        super().__init__(parent)
        self.state = state
        self.setFixedHeight(83)
        self.labels = {}
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(20)
        for key, name, unit, maximum in self.SIGNALS:
            box = QWidget()
            column = QVBoxLayout(box)
            column.setContentsMargins(0, 0, 0, 0)
            column.setSpacing(0)
            top = QHBoxLayout()
            label = QLabel(name)
            label.setObjectName("secondaryText")
            top.addWidget(label, 1)
            top.addWidget(help_button(lambda key=key: help_requested(key), name))
            column.addLayout(top)
            value = QLabel("-- "+unit)
            value.setObjectName("instrumentValue")
            column.addWidget(value)
            meter = QLabel()
            meter.setFixedHeight(5)
            column.addWidget(meter)
            self.labels[key] = value, meter, unit, maximum
            layout.addWidget(box, 1)
        state.values_changed.connect(self.sync)

    def sync(self):
        for key, (value, meter, unit, maximum) in self.labels.items():
            reading = self.state.readings.get(key, {})
            physical = reading.get("value") if not reading.get("error") else None
            value.setText(number_text(physical, 1)+" "+unit)
            fraction = min(1, abs(float(physical))/maximum) if isinstance(physical, (int, float)) else 0
            pixmap = QPixmap(max(1, meter.width()), 5)
            pixmap.fill(QColor(INSTRUMENT["rule"]))
            painter = QPainter(pixmap)
            painter.fillRect(QRectF(0, 0, pixmap.width()*fraction, 5), QColor(INSTRUMENT["trace"]))
            painter.end()
            meter.setPixmap(pixmap)
            meter.setToolTip(f"Display scale: 0 to {maximum} {unit}. This is an instrument scale, not the controller's configured limit.")
            value.setToolTip("Example measurement" if self.state.connection.get("simulated") else reading.get("error", "Live controller measurement"))

"""Named parameter tables with native editors and explicit write permissions."""

from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QStyledItemDelegate, QComboBox, QDoubleSpinBox, QLineEdit
from .desktop_widgets import INSTRUMENT


class ParameterModel(QAbstractTableModel):
    HEADERS = ["Parameter", "Controller", "Proposed", "Unit", "Access", "Required role", "Help"]

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self.rows = []
        self.group = None
        self.parent_filter = ""
        self.search = ""
        self.access = ""
        state.values_changed.connect(self.refresh_values)
        state.permissions_changed.connect(self.filter)
        state.catalog_changed.connect(self.filter)

    def filter(self):
        self.beginResetModel()
        self.rows = []
        for setting in self.state.settings.values():
            if self.group and setting["group"] != self.group:
                continue
            if self.parent_filter and setting["parent"] != self.parent_filter:
                continue
            if self.search and self.search.lower() not in (setting["path"]+" "+setting["unit"]+" "+setting["key"]).lower():
                continue
            if self.access == "available" and not self.state.permitted(setting):
                continue
            if self.access == "locked" and (not setting["editable"] or self.state.permitted(setting)):
                continue
            if self.access == "readonly" and setting["editable"]:
                continue
            self.rows.append(setting)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section]

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        setting = self.rows[index.row()]
        key, column = setting["key"], index.column()
        reading, draft = self.state.readings.get(key, {}), self.state.drafts.get(key)
        if role == Qt.ItemDataRole.UserRole:
            return key
        if role == Qt.ItemDataRole.EditRole:
            return self.state.value(key)
        if role == Qt.ItemDataRole.DisplayRole:
            if column == 0:
                return setting["name"]
            if column == 1:
                return "Read error" if reading.get("error") else self.state.display(key, reading.get("label") if isinstance(reading.get("label"), str) else reading.get("value")) if reading else "--"
            if column == 2:
                return self.state.display(key, draft["value"]) if draft else "Edit fields..." if setting["bits"] and setting["editable"] else ""
            if column == 3:
                return setting["unit"]
            if column == 4:
                return self.state.permission_text(setting)
            if column == 5:
                return self.state.required(setting) if setting["writable"] else "Read only"
            if column == 6:
                return "?"
        if role == Qt.ItemDataRole.ToolTipRole:
            return (f"{setting['path']}\n{reading.get('error', setting['help']['range'])}\n"
                    f"Required: {self.state.required(setting)}\nYour access: {self.state.role()}\n"
                    f"{self.state.permission_text(setting)}. " + ("Configuration state required." if setting["preop"] else "Drafts wait for Apply."))
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter) if column in (1, 2) else int(Qt.AlignmentFlag.AlignCenter) if column == 6 else None
        locked = setting["editable"] and not self.state.permitted(setting)
        if role == Qt.ItemDataRole.BackgroundRole:
            if locked and column != 6:
                return QColor("#edf0f2")
            if draft and column == 2:
                return QColor(INSTRUMENT["proposal"])
        if role == Qt.ItemDataRole.ForegroundRole:
            if locked and column != 6:
                return QColor("#84909a")
            if reading.get("error") and column == 1:
                return QColor(INSTRUMENT["fault"])
            if column == 5 or not setting["editable"] and column == 2:
                return QColor(INSTRUMENT["label"])

    def flags(self, index):
        flags = super().flags(index)
        if index.isValid() and index.column() == 2:
            setting = self.rows[index.row()]
            if self.state.permitted(setting) and self.state.readings.get(setting["key"], {}).get("bytes") and not self.state.busy and not setting["bits"]:
                flags |= Qt.ItemFlag.ItemIsEditable
        return flags

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if role != Qt.ItemDataRole.EditRole or not index.isValid() or index.column() != 2:
            return False
        return self.state.stage(self.rows[index.row()]["key"], value)

    def refresh_values(self):
        if self.rows:
            self.dataChanged.emit(self.index(0, 0), self.index(len(self.rows)-1, self.columnCount()-1))


class ValueDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        model = index.model()
        setting = model.rows[index.row()]
        if setting["labels"] or setting["type"] == "BOOLEAN":
            editor = QComboBox(parent)
            if setting["labels"]:
                for raw, label in setting["labels"].items():
                    editor.addItem(label, raw)
            else:
                editor.addItem("Disabled", False)
                editor.addItem("Enabled", True)
            editor.activated.connect(lambda _: self.commitData.emit(editor))
        elif setting["type"].startswith(("INTEGER", "UNSIGNED", "REAL")):
            editor = QDoubleSpinBox(parent)
            import math
            step = setting["step"]
            editor.setDecimals(min(9, max(0, math.ceil(-math.log10(step))+1)) if isinstance(step, (int, float)) and step > 0 else 4)
            editor.setRange(setting["low"] if setting["low"] is not None else -1e12,
                            setting["high"] if setting["high"] is not None else 1e12)
            editor.setSingleStep(step if isinstance(step, (int, float)) else .1)
            editor.setKeyboardTracking(False)
        else:
            editor = QLineEdit(parent)
        editor.setAccessibleName(setting["name"])
        return editor

    def setEditorData(self, editor, index):
        value = index.data(Qt.ItemDataRole.EditRole)
        if isinstance(editor, QComboBox):
            selected = editor.findData(value)
            if selected < 0:
                selected = editor.findText(str(value))
            editor.setCurrentIndex(selected)
        elif isinstance(editor, QDoubleSpinBox):
            editor.setValue(float(value or 0))
        else:
            editor.setText(str(value or ""))

    def setModelData(self, editor, model, index):
        setting = model.rows[index.row()]
        value = editor.currentText() if isinstance(editor, QComboBox) and setting["labels"] else editor.currentData() if isinstance(editor, QComboBox) else editor.value() if isinstance(editor, QDoubleSpinBox) else editor.text()
        model.setData(index, value)

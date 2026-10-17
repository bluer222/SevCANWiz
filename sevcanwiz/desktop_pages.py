"""Task pages: curves, compact parameters, live instruments, network, and faults."""

import time
from PySide6.QtCore import Qt, QTimer, QSignalBlocker
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QLineEdit, QPushButton,
    QTableView, QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox, QSplitter,
    QScrollArea, QFormLayout, QDoubleSpinBox, QCheckBox, QListWidget,
    QTabWidget, QMessageBox,
)
from .desktop_widgets import CurvePlot, TrendPlot, InstrumentStrip, SettingEditor, BitFieldsDialog, help_button
from .desktop_models import ParameterModel, ValueDelegate
from .desktop_state import number_text


class ParameterPage(QWidget):
    def __init__(self, state, group, help_requested, trace_requested, parent=None):
        super().__init__(parent)
        self.state = state
        self.help_requested = help_requested
        self.trace_requested = trace_requested
        self.model = ParameterModel(state, self)
        self.model.group = group
        self.model.filter()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        filters = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Find a named parameter...")
        self.search.setAccessibleName("Find parameters")
        filters.addWidget(self.search, 2)
        self.group_select = QComboBox()
        self.group_select.setAccessibleName("Parameter group")
        self.group_select.addItem("All groups", "")
        for name in sorted({s["parent"] for s in state.settings.values() if not group or s["group"] == group}):
            self.group_select.addItem(name, name)
        filters.addWidget(self.group_select, 2)
        self.access = QComboBox()
        self.access.setAccessibleName("Filter by access")
        for name, key in [("All permissions", ""), ("I can edit", "available"), ("Needs higher access", "locked"), ("Read only / dedicated", "readonly")]:
            self.access.addItem(name, key)
        filters.addWidget(self.access, 1)
        layout.addLayout(filters)
        self.summary = QLabel()
        self.summary.setObjectName("secondaryText")
        layout.addWidget(self.summary)
        self.table = QTableView()
        self.table.setObjectName("parameterTable")
        self.table.setModel(self.model)
        self.table.setItemDelegateForColumn(2, ValueDelegate(self.table))
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(28)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column, width in [(1, 105), (2, 110), (3, 65), (4, 98), (5, 160), (6, 45)]:
            self.table.setColumnWidth(column, width)
        self.table.setEditTriggers(QTableView.EditTrigger.DoubleClicked | QTableView.EditTrigger.EditKeyPressed)
        self.table.clicked.connect(self.clicked)
        self.table.doubleClicked.connect(self.double_clicked)
        self.table.selectionModel().currentRowChanged.connect(lambda current, previous: self.select_help(current))
        self.table.verticalScrollBar().valueChanged.connect(self.schedule_read)
        layout.addWidget(self.table, 1)
        lower = QHBoxLayout()
        hint = QLabel("Edit the Proposed column. Controller values remain unchanged until Apply.")
        hint.setObjectName("secondaryText")
        lower.addWidget(hint, 1)
        trace = QPushButton("Plot selected signal")
        trace.clicked.connect(self.plot_selected)
        lower.addWidget(trace)
        layout.addLayout(lower)
        self.debounce = QTimer(self)
        self.debounce.setSingleShot(True)
        self.debounce.setInterval(180)
        self.debounce.timeout.connect(self.update_filter)
        self.search.textChanged.connect(lambda _: self.debounce.start())
        self.group_select.currentIndexChanged.connect(self.update_filter)
        self.access.currentIndexChanged.connect(self.update_filter)
        self.read_debounce = QTimer(self)
        self.read_debounce.setSingleShot(True)
        self.read_debounce.setInterval(200)
        self.read_debounce.timeout.connect(self.read_visible)
        state.permissions_changed.connect(self.update_summary)
        self.update_summary()

    def update_filter(self):
        self.model.search = self.search.text()
        self.model.parent_filter = self.group_select.currentData()
        self.model.access = self.access.currentData()
        self.model.filter()
        self.update_summary()
        self.schedule_read()

    def update_summary(self):
        settings = [s for s in self.state.settings.values() if not self.model.group or s["group"] == self.model.group]
        granted = sum(self.state.permitted(s) for s in settings)
        locked = sum(s["editable"] and not self.state.permitted(s) for s in settings)
        self.summary.setText(f"{len(self.model.rows)} parameters shown  |  Your access: {self.state.role()}  |  {granted} available, {locked} locked")

    def schedule_read(self, *_):
        if self.isVisible():
            self.read_debounce.start()

    def read_visible(self, refresh=False):
        if not self.isVisible():
            return
        start = max(0, self.table.rowAt(0))
        end = self.table.rowAt(max(0, self.table.viewport().height()-1))
        end = end if end >= start else min(len(self.model.rows)-1, start+35)
        rows = self.model.rows[start:min(len(self.model.rows), end+12)]
        keys = [s["key"] for s in rows if s["readable"] and (refresh or s["key"] not in self.state.readings)]
        self.state.read_settings(keys, rebase=refresh)

    def clicked(self, index):
        if index.column() == 6:
            self.help_requested(index.data(Qt.ItemDataRole.UserRole))

    def select_help(self, index):
        if index.isValid():
            self.help_requested(index.data(Qt.ItemDataRole.UserRole))

    def double_clicked(self, index):
        key = index.data(Qt.ItemDataRole.UserRole)
        if index.column() == 2 and self.state.settings[key]["bits"]:
            if not self.state.readings.get(key, {}).get("bytes"):
                self.state.message.emit("Read this parameter before opening its fields.")
                self.state.read_settings([key])
                return
            BitFieldsDialog(self.state, key, self).exec()

    def plot_selected(self):
        index = self.table.currentIndex()
        if index.isValid():
            self.trace_requested(index.data(Qt.ItemDataRole.UserRole))


class CurvePage(QWidget):
    def __init__(self, state, curve, help_requested, parent=None):
        super().__init__(parent)
        self.state, self.curve = state, curve
        self.help_requested = help_requested
        self.setObjectName("curve_"+curve["id"])
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        self.access_note = QLabel()
        self.access_note.setObjectName("secondaryText")
        self.access_note.setWordWrap(True)
        layout.addWidget(self.access_note)
        split = QSplitter(Qt.Orientation.Horizontal)
        chart_body = QWidget()
        chart_layout = QVBoxLayout(chart_body)
        chart_layout.setContentsMargins(0, 0, 0, 0)
        chart_layout.setSpacing(8)
        controls = QHBoxLayout()
        label = QLabel(curve["name"])
        label.setObjectName("sectionHeading")
        controls.addWidget(label, 1)
        self.templates = []
        if curve["percent"]:
            for name in ("Gentle", "Linear", "Responsive"):
                button = QPushButton(name)
                button.clicked.connect(lambda checked=False, name=name: self.template(name))
                self.templates.append(button)
                controls.addWidget(button)
        revert = QPushButton("Revert curve")
        revert.clicked.connect(self.revert)
        controls.addWidget(revert)
        controls.addWidget(help_button(lambda: help_requested("curve" if curve["percent"] else curve["points"][0]["x"]), curve["name"]))
        chart_layout.addLayout(controls)
        self.mode_note = QLabel()
        self.mode_note.setWordWrap(True)
        self.mode_note.setObjectName("warningText")
        chart_layout.addWidget(self.mode_note)
        self.plot = CurvePlot()
        self.plot.percent = curve["percent"]
        self.plot.x_label, self.plot.y_label = curve["xLabel"], curve["yLabel"]
        self.plot.point_moved.connect(self.move_point)
        chart_layout.addWidget(self.plot, 1)
        self.coordinates = QTableWidget(len(curve["points"]), 3)
        self.coordinates.setObjectName("curveCoordinates")
        self.coordinates.setHorizontalHeaderLabels(["Point", "Input / %" if curve["percent"] else curve["xLabel"], "Output / %" if curve["percent"] else curve["yLabel"]])
        self.coordinates.verticalHeader().hide()
        self.coordinates.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.coordinates.setMaximumHeight(180 if len(curve["points"])>3 else 135)
        self.point_editors = []
        for i, point in enumerate(curve["points"]):
            self.coordinates.setItem(i, 0, QTableWidgetItem(str(i+1)))
            for column, axis in enumerate(("x", "y"), 1):
                setting = state.settings[point[axis]]
                editor = QDoubleSpinBox()
                multiplier = 100 if curve["percent"] else 1
                editor.setDecimals(3)
                editor.setRange((setting["low"] or 0)*multiplier, (setting["high"] if setting["high"] is not None else 1e9)*multiplier)
                editor.setSingleStep(.1 if curve["percent"] else 1)
                editor.setKeyboardTracking(False)
                editor.setAccessibleName(f"Point {i+1} {'input' if axis=='x' else 'output'}")
                editor.setObjectName(f"point_{i}_{axis}")
                editor.editingFinished.connect(lambda i=i, axis=axis, editor=editor: self.stage_coordinate(i, axis, editor.value()))
                cell = QWidget()
                row = QHBoxLayout(cell)
                row.setContentsMargins(0, 0, 3, 0)
                row.setSpacing(3)
                row.addWidget(editor, 1)
                row.addWidget(help_button(lambda key=point[axis]: help_requested(key), setting["name"]))
                self.coordinates.setCellWidget(i, column, cell)
                self.point_editors.append((i, axis, editor))
        chart_layout.addWidget(self.coordinates)
        hint = QLabel("Drag a point, or edit exact coordinates. Arrow keys move the selected point; Space selects the next point.")
        hint.setWordWrap(True)
        hint.setObjectName("secondaryText")
        chart_layout.addWidget(hint)
        split.addWidget(chart_body)
        if curve["id"] in ("throttle", "brake"):
            calibration = QGroupBox("Pedal calibration")
            body = QWidget()
            form = QVBoxLayout(body)
            form.setContentsMargins(8, 8, 8, 8)
            form.setSpacing(12)
            index = "2910" if curve["id"] == "throttle" else "2911"
            subs = [(2, "Input characteristic"), (3, "Released pedal voltage"), (4, "Request at released pedal"), (5, "Fully pressed voltage"), (6, "Request at fully pressed pedal"), (21, "Throttle fault threshold")] if index == "2910" else [(3, "Input characteristic"), (4, "Released pedal voltage"), (5, "Request at released pedal"), (6, "Fully pressed voltage"), (7, "Request at fully pressed pedal"), (2, "Braking exit speed")]
            self.calibration_keys = []
            for sub, name in subs:
                key = f"{index}:{sub:02X}"
                if key in state.settings:
                    form.addWidget(SettingEditor(state, key, help_requested, name))
                    self.calibration_keys.append(key)
            form.addStretch()
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(body)
            cal_layout = QVBoxLayout(calibration)
            cal_layout.setContentsMargins(4, 8, 4, 4)
            cal_layout.addWidget(scroll)
            calibration.setMinimumWidth(255)
            split.addWidget(calibration)
            split.setStretchFactor(0, 3)
            split.setStretchFactor(1, 1)
            split.setSizes([600, 290])
        else:
            self.calibration_keys = []
        layout.addWidget(split, 1)
        state.values_changed.connect(self.sync)
        state.permissions_changed.connect(self.sync)
        self.sync()

    def keys(self):
        keys = [p[axis] for p in self.curve["points"] for axis in ("x", "y")]+self.calibration_keys
        if self.curve["selector"]:
            keys.append(self.curve["selector"])
        return keys

    def read(self, refresh=False):
        self.state.read_settings([key for key in self.keys() if refresh or key not in self.state.readings], refresh)

    def sync(self):
        multiplier = 100 if self.curve["percent"] else 1
        keys = [p[axis] for p in self.curve["points"] for axis in ("x", "y")]
        if self.curve["selector"]:
            keys.append(self.curve["selector"])
        required = max(self.state.settings[key]["level"] or 0 for key in keys)
        allowed = all(self.state.permitted(self.state.settings[key]) for key in keys) and not self.state.busy
        ready = all(self.state.readings.get(key, {}).get("bytes") for key in keys)
        self.access_note.setText(f"Curve editing: {self.state.role(required)} required  |  Your access: {self.state.role()}  |  {'Available' if allowed else 'Locked'}  |  Edits remain proposed until Apply")
        self.plot.editable = allowed and ready
        self.plot.points = [(self.state.value(point["x"])*multiplier if self.state.value(point["x"]) is not None else None,
                             self.state.value(point["y"])*multiplier if self.state.value(point["y"]) is not None else None) for point in self.curve["points"]]
        self.plot.controller_points = [(self.state.readings.get(point["x"], {}).get("value"),
                                        self.state.readings.get(point["y"], {}).get("value")) for point in self.curve["points"]]
        self.plot.controller_points = [(x*multiplier if x is not None else None,
                                        y*multiplier if y is not None else None) for x, y in self.plot.controller_points]
        self.plot.update()
        for i, axis, editor in self.point_editors:
            editor.setEnabled(allowed and ready)
            value = self.state.value(self.curve["points"][i][axis])
            if value is not None and not editor.hasFocus() and not editor.lineEdit().hasFocus():
                with QSignalBlocker(editor):
                    editor.setValue(value*multiplier)
        for button in self.templates:
            button.setEnabled(allowed and ready)
        selector = self.curve["selector"]
        builtin = selector and self.state.value(selector) is not None and self.state.value(selector) != 0
        self.mode_note.setVisible(bool(builtin))
        if builtin:
            self.mode_note.setText("A built-in characteristic is selected. The graph shows stored user points; editing them selects User defined.")

    def stage_coordinate(self, i, axis, value):
        if self.state.stage(self.curve["points"][i][axis], value/(100 if self.curve["percent"] else 1)):
            selector = self.curve["selector"]
            if selector:
                self.state.stage(selector, self.state.settings[selector]["labels"][0])

    def move_point(self, i, x, y):
        self.stage_coordinate(i, "x", x)
        self.stage_coordinate(i, "y", y)

    def template(self, name):
        for i in range(len(self.curve["points"])):
            f = (i+1)/(len(self.curve["points"])+1)
            y = f**1.6 if name == "Gentle" else f**.65 if name == "Responsive" else f
            self.move_point(i, f*100, y*100)

    def revert(self):
        keys = [p[axis] for p in self.curve["points"] for axis in ("x", "y")]
        if self.curve["selector"]:
            keys.append(self.curve["selector"])
        self.state.discard(keys)


class InstrumentsPage(QWidget):
    def __init__(self, state, help_requested, parent=None):
        super().__init__(parent)
        self.state = state
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        layout.addWidget(InstrumentStrip(state, help_requested))
        options = QHBoxLayout()
        options.addWidget(QLabel("Trend signal"))
        self.signal = QComboBox()
        self.signal.setAccessibleName("Live trace signal")
        for setting in state.settings.values():
            if setting["readable"] and setting["type"].startswith(("INTEGER", "UNSIGNED", "REAL")):
                self.signal.addItem(setting["path"]+(" / "+setting["unit"] if setting["unit"] else ""), setting["key"])
        self.signal.setCurrentIndex(self.signal.findData("5100:02"))
        self.signal.currentIndexChanged.connect(self.select_signal)
        options.addWidget(self.signal, 1)
        self.pause = QPushButton("Pause readings")
        self.pause.clicked.connect(self.toggle_pause)
        options.addWidget(self.pause)
        options.addWidget(help_button(lambda: help_requested("monitor"), "Live instruments"))
        layout.addLayout(options)
        self.plot = TrendPlot()
        layout.addWidget(self.plot, 1)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Signal", "Measurement", "Unit", "Read status"])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.setMaximumHeight(220)
        layout.addWidget(self.table)
        state.values_changed.connect(self.sync)
        self.sync()

    def select_signal(self):
        self.state.trace_keys = [self.signal.currentData()]
        self.sync()
        self.state.poll_live()

    def show_signal(self, key):
        index = self.signal.findData(key)
        if index >= 0:
            self.signal.setCurrentIndex(index)

    def toggle_pause(self):
        self.state.paused = not self.state.paused
        self.pause.setText("Resume readings" if self.state.paused else "Pause readings")
        self.state.poll_live()

    def sync(self):
        key = self.signal.currentData()
        if key:
            setting = self.state.settings[key]
            self.plot.title, self.plot.unit = setting["name"], setting["unit"] or "unitless"
            self.plot.samples = list(self.state.histories.get(key, []))
            self.plot.update()
        keys = list(dict.fromkeys(["5100:01", "5100:02", "5100:04", "606C:00", "6077:00", "2790:01", key]))
        self.table.setRowCount(len(keys))
        for i, key in enumerate(keys):
            setting = self.state.settings.get(key, {})
            reading = self.state.readings.get(key, {})
            for j, text in enumerate([setting.get("name", key), number_text(reading.get("value"), 2) if not reading.get("error") else "--", setting.get("unit", ""), reading.get("error", "Paused" if self.state.paused else "Simulation" if self.state.connection.get("simulated") else "Live" if reading else "Waiting")]):
                self.table.setItem(i, j, QTableWidgetItem(str(text)))


class DiagnosticsPage(QWidget):
    def __init__(self, state, help_requested, trace_requested, parent=None):
        super().__init__(parent)
        self.state = state
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget()
        faults = QWidget()
        body = QVBoxLayout(faults)
        controls = QHBoxLayout()
        self.fault_summary = QLabel("Waiting for controller fault list")
        controls.addWidget(self.fault_summary, 1)
        reset = QPushButton("Request fault reset...")
        reset.clicked.connect(self.reset_fault)
        controls.addWidget(reset)
        controls.addWidget(help_button(lambda: help_requested("faults"), "Controller faults"))
        body.addLayout(controls)
        self.faults = QTableWidget(0, 4)
        self.faults.setHorizontalHeaderLabels(["Fault", "Level", "Description", "Suggested action"])
        self.faults.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.faults.verticalHeader().hide()
        self.faults.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        body.addWidget(self.faults, 1)
        identity_box = QGroupBox("Controller identity and dictionary")
        identity_layout = QVBoxLayout(identity_box)
        self.identity = QLabel()
        self.identity.setWordWrap(True)
        self.identity.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        identity_layout.addWidget(self.identity)
        body.addWidget(identity_box)
        self.tabs.addTab(faults, "Faults and identity")
        reference = QWidget()
        ref_layout = QVBoxLayout(reference)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Find a fault by description or fault code...")
        self.search.setAccessibleName("Find fault descriptions")
        self.search.textChanged.connect(self.filter_faults)
        ref_layout.addWidget(self.search)
        self.reference = QTableWidget(0, 4)
        self.reference.setHorizontalHeaderLabels(["Fault", "Description", "Explanation", "Action"])
        self.reference.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.reference.verticalHeader().hide()
        self.reference.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        ref_layout.addWidget(self.reference)
        self.tabs.addTab(reference, "Fault reference")
        self.parameters = ParameterPage(state, "diagnostics", help_requested, trace_requested)
        self.tabs.addTab(self.parameters, "Logs and counters")
        self.tabs.currentChanged.connect(lambda _: self.parameters.schedule_read())
        layout.addWidget(self.tabs)
        state.connection_changed.connect(self.sync)
        self.filter_faults()
        self.sync()

    def sync(self):
        faults = self.state.live.get("faults")
        self.fault_summary.setText(f"{len(faults)} active faults reported" if faults is not None else "Fault state unavailable")
        self.faults.setRowCount(len(faults or []))
        for i, fault in enumerate(faults or []):
            info = fault.get("info") or {}
            for j, text in enumerate([f"0x{fault['fault_id']:04X}", str(info.get("level", "")), info.get("description") or info.get("message") or "Unknown firmware fault", info.get("action", "")]):
                self.faults.setItem(i, j, QTableWidgetItem(text))
        identity = self.state.connection.get("identity")
        if identity:
            live = identity["identity"]
            text = "  |  ".join(f"{name}: 0x{value:X}" if isinstance(value, int) else f"{name}: {value}" for name, value in live.items())
            text += "\n"+("Identity matches the selected EDS header." if identity["matches"] else "Dictionary identity differs from controller. Check the installed firmware EDS.")
            text += "\nDictionary: "+identity["dictionary"]
            self.identity.setText(text)
        else:
            self.identity.setText("Connect to read identity.")

    def filter_faults(self):
        search = self.search.text().lower()
        faults = [f for f in self.state.catalog.get("fault_catalog", []) if search in f"{f['message']} {f['description']} {f['action']} {f['fid']:04X}".lower()]
        self.reference.setRowCount(len(faults))
        for i, fault in enumerate(faults):
            for j, text in enumerate([f"0x{fault['fid']:04X}", fault["message"], fault["description"], fault["action"]]):
                item = QTableWidgetItem(text)
                item.setToolTip(text)
                self.reference.setItem(i, j, item)

    def reset_fault(self):
        if QMessageBox.question(self, "Request fault reset", "Correct the cause first. This sends a CiA 402 reset edge and does not override interlocks. Request the reset?") == QMessageBox.StandardButton.Yes:
            self.state.command("fault-reset")

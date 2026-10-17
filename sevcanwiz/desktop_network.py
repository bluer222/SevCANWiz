"""Dedicated PDO remapping page, separate from ordinary parameters."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QSpinBox, QCheckBox,
    QPushButton, QFormLayout, QTableWidget, QTableWidgetItem, QHeaderView, QDoubleSpinBox,
    QMessageBox, QTabWidget,
)
from .desktop_pages import ParameterPage
from .desktop_widgets import help_button


class NetworkPage(QWidget):
    def __init__(self, state, help_requested, trace_requested, parent=None):
        super().__init__(parent)
        self.state = state
        self.config = None
        self.number, self.transmit = 1, True
        self.signals = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget()
        mapping = QWidget()
        body = QVBoxLayout(mapping)
        body.setSpacing(8)
        self.access = QLabel()
        self.access.setWordWrap(True)
        body.addWidget(self.access)
        selector = QHBoxLayout()
        self.direction = QComboBox()
        self.direction.addItem("TPDO / controller sends values", True)
        self.direction.addItem("RPDO / controller receives values", False)
        self.direction.setAccessibleName("PDO direction")
        self.direction.currentIndexChanged.connect(self.selected)
        selector.addWidget(self.direction, 2)
        selector.addWidget(help_button(lambda: help_requested("pdo"), "PDO direction"))
        self.pdo = QComboBox()
        for number in range(1, 6):
            self.pdo.addItem(f"PDO {number}", number)
        self.pdo.currentIndexChanged.connect(self.selected)
        selector.addWidget(self.pdo)
        reload = QPushButton("Read mapping")
        reload.clicked.connect(self.read)
        selector.addWidget(reload)
        selector.addWidget(help_button(lambda: help_requested("pdo"), "Process data mapping"))
        body.addLayout(selector)
        form = QFormLayout()
        self.identifier = QSpinBox()
        self.identifier.setAccessibleName("CAN message identifier")
        self.identifier.setRange(1, 2047)
        self.transmission = QComboBox()
        self.transmission.setAccessibleName("Transmission type")
        self.transmission.addItem("0 / synchronous, acyclic", 0)
        for value in range(1, 241):
            self.transmission.addItem(f"{value} / every {value} SYNC cycle{'s' if value>1 else ''}", value)
        self.transmission.addItem("254 / asynchronous, manufacturer", 254)
        self.transmission.addItem("255 / asynchronous, profile", 255)
        self.enabled = QCheckBox("Enable this PDO after remapping")
        self.enabled.setAccessibleName("Enable this PDO")
        self.event_timer = QSpinBox()
        self.event_timer.setAccessibleName("TPDO periodic transmit interval")
        self.event_timer.setRange(0, 65535)
        self.event_timer.setSuffix(" ms")
        self.event_timer.setSpecialValueText("Off / no periodic timer")
        self.inhibit_time = QDoubleSpinBox()
        self.inhibit_time.setAccessibleName("TPDO minimum transmit interval")
        self.inhibit_time.setDecimals(1)
        self.inhibit_time.setRange(0, 6553.5)
        self.inhibit_time.setSingleStep(.1)
        self.inhibit_time.setSuffix(" ms")
        self.inhibit_time.setSpecialValueText("Off / no minimum interval")
        for label, widget, topic in [("CAN message identifier", self.identifier, "pdo-identifier"),
                                     ("Transmission", self.transmission, "pdo-transmission"),
                                     ("Periodic transmit interval", self.event_timer, "pdo-event-timer"),
                                     ("Minimum transmit interval", self.inhibit_time, "pdo-inhibit"),
                                     ("Message state", self.enabled, "pdo-enable")]:
            row = QHBoxLayout()
            row.addWidget(widget, 1)
            row.addWidget(help_button(lambda topic=topic: help_requested(topic), label))
            form.addRow(label, row)
        body.addLayout(form)
        self.timing_note = QLabel()
        self.timing_note.setWordWrap(True)
        self.timing_note.setObjectName("secondaryText")
        body.addWidget(self.timing_note)
        self.transmission.currentIndexChanged.connect(self.update_timing_note)
        self.table = QTableWidget(0, 3)
        self.table.setObjectName("pdoMappingTable")
        self.table.setHorizontalHeaderLabels(["Order", "Mapped signal", "Size / bits"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        body.addWidget(self.table, 1)
        add = QHBoxLayout()
        self.signal_select = QComboBox()
        self.signal_select.setAccessibleName("Signal to add to PDO")
        add.addWidget(self.signal_select, 1)
        add.addWidget(help_button(lambda: help_requested("pdo-signal"), "Mapped signals"))
        self.add_button = QPushButton("Add signal")
        self.add_button.clicked.connect(self.add_signal)
        add.addWidget(self.add_button)
        self.remove_button = QPushButton("Remove selected")
        self.remove_button.clicked.connect(self.remove_selected)
        add.addWidget(self.remove_button)
        body.addLayout(add)
        actions = QHBoxLayout()
        self.payload_size = QLabel()
        actions.addWidget(self.payload_size, 1)
        self.apply_button = QPushButton("Review and apply PDO...")
        self.apply_button.clicked.connect(lambda: self.apply_pdo())
        actions.addWidget(self.apply_button)
        body.addLayout(actions)
        self.note = QLabel("Applying uses the dedicated disable, clear, map, and enable sequence. A failed sequence can leave the PDO disabled. Save separately to retain it.")
        self.note.setObjectName("secondaryText")
        self.note.setWordWrap(True)
        body.addWidget(self.note)
        self.tabs.addTab(mapping, "TPDO / RPDO mapping and timing")
        self.parameters = ParameterPage(state, "can", help_requested, trace_requested)
        self.tabs.addTab(self.parameters, "Network parameters")
        self.tabs.currentChanged.connect(lambda _: self.parameters.schedule_read())
        layout.addWidget(self.tabs)
        state.permissions_changed.connect(self.sync_access)
        state.connection_changed.connect(self.sync_access)
        self.sync_access()

    def required_level(self):
        comm = (0x1800 if self.transmit else 0x1400)+self.number-1
        mapping = (0x1A00 if self.transmit else 0x1600)+self.number-1
        return max([0]+[s["level"] or 0 for s in self.state.settings.values() if s["index"] in (comm, mapping)])

    def sync_access(self):
        required = self.required_level()
        allowed = self.state.connection.get("connected") and self.state.level is not None and self.state.level >= required and not self.state.busy
        self.access.setText(f"PDO configuration requires {self.state.role(required)}. Your access: {self.state.role()}. {'Available' if allowed else 'Locked'}. Configuration state required.")
        for widget in (self.identifier, self.transmission, self.enabled, self.add_button, self.remove_button, self.apply_button):
            widget.setEnabled(bool(self.config) and allowed and not self.config["cob_id"] & 0x20000000)
        for widget in (self.event_timer, self.inhibit_time):
            widget.setEnabled(bool(self.config) and allowed and self.transmit and not self.config["cob_id"] & 0x20000000)
        self.signal_select.setEnabled(self.add_button.isEnabled())
        self.update_timing_note()

    def update_timing_note(self):
        if not self.transmit:
            self.timing_note.setText("RPDOs receive messages. Transmit timers apply to TPDOs.")
        elif self.transmission.currentData() in (254, 255):
            self.timing_note.setText("The periodic timer requests automatic TPDO transmission in milliseconds. Zero disables the timer. Minimum interval limits how often this message can be sent.")
        else:
            self.timing_note.setText("Synchronous mode uses incoming SYNC messages. Select asynchronous 254 or 255 to use a periodic transmit timer. Timing values stay visible for review.")

    def selected(self):
        self.number, self.transmit = self.pdo.currentData(), self.direction.currentData()
        self.config = None
        self.signals = []
        self.sync_access()
        self.read()

    def read(self):
        if not self.state.connection.get("connected"):
            return
        selection = self.number, self.transmit
        def received(config):
            if selection != (self.number, self.transmit):
                return
            self.config = config
            self.signals = [f"{index:04X}:{sub:02X}" for index, sub, bits in config["mapping"]]
            self.identifier.setValue(config["cob_id"] & 0x7FF)
            self.transmission.setCurrentIndex(self.transmission.findData(config["transmission_type"]))
            self.enabled.setChecked(config["enabled"])
            self.event_timer.setValue(config.get("event_timer", 0))
            self.inhibit_time.setValue(config.get("inhibit_time", 0)/10)
            comm = 0x1800+self.number-1
            for sub, widget, multiplier in ((3, self.inhibit_time, .1), (5, self.event_timer, 1)):
                setting = self.state.settings.get(f"{comm:04X}:{sub:02X}")
                if setting and setting["high"] is not None:
                    maximum = setting["high"]/setting["step"]*multiplier
                    widget.setMaximum(maximum if isinstance(widget, QDoubleSpinBox) else int(maximum))
            self.update_table()
            self.sync_access()
            if config["cob_id"] & 0x20000000:
                self.apply_button.setEnabled(False)
                self.note.setText("This PDO uses an extended identifier. Inspection is available; the editor supports standard 11-bit identifiers only.")
        self.state.request("pdo-read", {"number": self.number, "transmit": self.transmit}, received)

    def update_table(self):
        self.table.setRowCount(len(self.signals))
        for i, key in enumerate(self.signals):
            setting = self.state.settings.get(key, {})
            for j, value in enumerate([str(i+1), setting.get("path", key), str(setting.get("size", "?"))]):
                self.table.setItem(i, j, QTableWidgetItem(value))
        size = sum(self.state.settings.get(key, {}).get("size") or 0 for key in self.signals)
        self.payload_size.setText(f"{size} / 64 payload bits  |  {len(self.signals)} mapped signals")
        self.signal_select.clear()
        for setting in self.state.settings.values():
            if setting["mappable"] and setting["size"] and (setting["readable"] if self.transmit else setting["writable"]) and setting["key"] not in self.signals:
                self.signal_select.addItem(f"{setting['path']} / {setting['size']} bits", setting["key"])

    def add_signal(self):
        key = self.signal_select.currentData()
        if not key:
            return
        size = sum(self.state.settings.get(k, {}).get("size") or 0 for k in self.signals)+self.state.settings[key]["size"]
        if size > 64 or len(self.signals) >= 8:
            self.state.error.emit("A PDO can hold up to 64 bits and eight mapped entries.")
            return
        self.signals.append(key)
        self.update_table()

    def remove_selected(self):
        row = self.table.currentRow()
        if row >= 0:
            self.signals.pop(row)
            self.update_table()

    def apply_pdo(self, confirmed=False):
        if not confirmed:
            text = f"Apply {'transmit' if self.transmit else 'receive'} PDO {self.number}?\nIdentifier: {self.identifier.value()}. {len(self.signals)} signals."
            if self.transmit:
                text += f"\nPeriodic interval: {self.event_timer.value()} ms. Minimum interval: {self.inhibit_time.value():.1f} ms."
            text += "\nThe message will be disabled while remapping. A failure may leave it disabled."
            if QMessageBox.question(self, "Apply PDO mapping", text) != QMessageBox.StandardButton.Yes:
                return
        self.state.busy = True
        self.state.permissions_changed.emit()
        payload = {"session": self.state.connection.get("session"), "number": self.number, "transmit": self.transmit,
                   "identifier": self.identifier.value(), "transmission": self.transmission.currentData(),
                   "enabled": self.enabled.isChecked(), "signals": self.signals, "expected": self.config}
        if self.transmit:
            payload.update(event_timer=self.event_timer.value(), inhibit_time=round(self.inhibit_time.value()*10))
        def completed(job):
            self.state.busy = False
            self.state.connection["unsaved"] = True
            self.state.permissions_changed.emit()
            self.state.connection_changed.emit()
            self.read()
            self.state.message.emit("PDO mapping applied and read back. Save separately to controller memory.")
        def failed(error):
            self.state.busy = False
            self.state.permissions_changed.emit()
            self.state.connection_changed.emit()
            self.state.error.emit(error)
            self.read()
            self.state.poll_live()
        self.state.start_job("pdo-apply", payload, completed, failed=failed)

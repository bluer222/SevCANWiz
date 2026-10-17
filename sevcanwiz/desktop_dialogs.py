"""Native connection, access, explanation, and Apply dialogs."""

from html import escape
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit,
    QComboBox, QSpinBox, QPushButton, QDialogButtonBox, QFileDialog,
    QTableWidget, QTableWidgetItem, QHeaderView, QTextBrowser, QMessageBox, QListWidget, QListWidgetItem,
)
from .desktop_widgets import help_button


class MenuSearchDialog(QDialog):
    def __init__(self, entries, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Search menus and commands")
        self.resize(700, 480)
        self.entries = entries
        layout = QVBoxLayout(self)
        self.search = QLineEdit()
        self.search.setAccessibleName("Search menus and commands")
        self.search.setPlaceholderText("Find a window or command, such as TPDO, throttle, or backup...")
        layout.addWidget(self.search)
        self.results = QListWidget()
        self.results.setAccessibleName("Matching menu commands")
        layout.addWidget(self.results, 1)
        self.details = QLabel()
        self.details.setWordWrap(True)
        layout.addWidget(self.details)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.open_button = buttons.addButton("Open / run selected", QDialogButtonBox.ButtonRole.AcceptRole)
        self.open_button.clicked.connect(self.execute)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.search.textChanged.connect(self.filter)
        self.search.returnPressed.connect(self.execute)
        self.results.itemDoubleClicked.connect(lambda: self.execute())
        self.results.currentItemChanged.connect(self.selected)
        self.filter()
        self.search.setFocus()

    def filter(self):
        self.results.clear()
        words = self.search.text().lower().split()
        for path, action, keywords in self.entries:
            if all(word in (path+" "+keywords).lower() for word in words):
                shortcut = action.shortcut().toString()
                item = QListWidgetItem(path+("    "+shortcut if shortcut else ""))
                item.setData(Qt.ItemDataRole.UserRole, action)
                if not action.isEnabled():
                    item.setForeground(self.palette().color(self.palette().ColorGroup.Disabled, self.palette().ColorRole.Text))
                self.results.addItem(item)
        if self.results.count():
            self.results.setCurrentRow(0)
        else:
            self.details.setText("No matching commands.")
            self.open_button.setEnabled(False)

    def selected(self, current, previous=None):
        action = current.data(Qt.ItemDataRole.UserRole) if current else None
        self.open_button.setEnabled(bool(action and action.isEnabled()))
        self.details.setText((action.toolTip() or action.text())+("\nCurrently unavailable. Check controller connection, access, and pending operations." if not action.isEnabled() else "") if action else "")

    def execute(self):
        item = self.results.currentItem()
        action = item.data(Qt.ItemDataRole.UserRole) if item else None
        if action and action.isEnabled():
            self.accept()
            action.trigger()


def explanation_html(help, state=None, setting=None, technical=False):
    chunks = [f"<h2>{escape(help['title'])}</h2>"]
    for title, key in [("What this does", "what"), ("When to change it", "adjust"),
                       ("Interactions", "interactions"), ("Applying this setting", "access")]:
        if help.get(key):
            chunks.append(f"<h3>{title}</h3><p>{escape(help[key])}</p>")
    if help.get("range"):
        chunks.append(f"<h3>Accepted range</h3><p>{escape(help['range'])}</p>")
    if help.get("choices"):
        chunks.append("<h3>Available choices</h3><ul>"+"".join(f"<li>{escape(c['label'])}: {c['value']}</li>" for c in help["choices"])+"</ul>")
    if state and setting:
        chunks.append(f"<h3>Your access</h3><p>{escape(state.role())}<br>Required: {escape(state.required(setting))}<br>{escape(state.permission_text(setting))}</p>")
    if technical and help.get("address"):
        chunks.append(f"<h3>Technical reference</h3><p>{escape(help['address'])}<br>{escape(help.get('source', ''))}</p>")
    return "".join(chunks)


class ExplanationDialog(QDialog):
    def __init__(self, help, parent=None):
        super().__init__(parent)
        self.setWindowTitle(help["title"])
        self.resize(540, 620)
        layout = QVBoxLayout(self)
        browser = QTextBrowser()
        browser.setHtml(explanation_html(help, technical=True))
        layout.addWidget(browser)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


def add_help_field(form, label, widget, state, topic, parent):
    row = QHBoxLayout()
    row.addWidget(widget, 1)
    row.addWidget(help_button(lambda: ExplanationDialog(state.catalog["topics"][topic], parent).exec(), label))
    form.addRow(label, row)


class ConnectionDialog(QDialog):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.setObjectName("connectionDialog")
        self.setWindowTitle("Controller connection")
        self.resize(580, 430)
        self.state = state
        layout = QVBoxLayout(self)
        label = QLabel("Choose the adapter's actual protocol and the installed firmware dictionary.")
        label.setWordWrap(True)
        layout.addWidget(label)
        form = QFormLayout()
        form.setSpacing(8)
        self.backend = QComboBox()
        for key, text in [("simulator", "Simulator / no hardware"), ("socketcan", "SocketCAN / Linux interface"),
                          ("gs_usb", "Candlelight / direct USB"), ("slcan", "SLCAN / serial"),
                          ("pcan", "PEAK PCAN"), ("kvaser", "Kvaser")]:
            self.backend.addItem(text, key)
        self.backend.setAccessibleName("Connection type")
        self.backend.setCurrentIndex(max(0, self.backend.findData(state.connection.get("backend"))))
        add_help_field(form, "Connection type", self.backend, state, "connection", self)
        self.node = QSpinBox()
        self.node.setRange(1, 127)
        self.node.setValue(state.connection.get("node") or 32)
        self.node.setAccessibleName("Controller node")
        add_help_field(form, "Controller node", self.node, state, "node", self)
        self.channel = QLineEdit("can0")
        self.channel.setAccessibleName("Interface or serial port")
        add_help_field(form, "Interface / port", self.channel, state, "connection", self)
        self.bitrate = QComboBox()
        for rate in (125000, 250000, 500000, 800000, 1000000):
            self.bitrate.addItem(f"{rate//1000} kbit/s", rate)
        self.bitrate.setCurrentIndex(4)
        add_help_field(form, "CAN bitrate", self.bitrate, state, "bitrate", self)
        self.usb_index = QSpinBox()
        self.usb_index.setRange(0, 255)
        add_help_field(form, "USB device index", self.usb_index, state, "usb-index", self)
        self.serial_rate = QSpinBox()
        self.serial_rate.setRange(1, 4000000)
        self.serial_rate.setValue(115200)
        add_help_field(form, "Serial baudrate", self.serial_rate, state, "serial-rate", self)
        self.eds = QLineEdit()
        self.eds.setPlaceholderText("Bundled Gen4 dictionary")
        path_row = QHBoxLayout()
        path_row.addWidget(self.eds, 1)
        browse = QPushButton("Browse...")
        browse.clicked.connect(self.browse)
        path_row.addWidget(browse)
        path_row.addWidget(help_button(lambda: ExplanationDialog(state.catalog["topics"]["eds"], self).exec(), "Controller dictionary"))
        form.addRow("EDS / DCF", path_row)
        layout.addLayout(form)
        self.notice = QLabel()
        self.notice.setWordWrap(True)
        self.notice.setObjectName("secondaryText")
        layout.addWidget(self.notice)
        discover = QPushButton("Find local adapters")
        discover.clicked.connect(self.discover)
        layout.addWidget(discover, 0, Qt.AlignmentFlag.AlignLeft)
        if state.drafts:
            label = QLabel("Connecting discards the current proposed changes. Export them or apply them before switching.")
            label.setWordWrap(True)
            label.setObjectName("warningText")
            layout.addWidget(label)
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setObjectName("faultText")
        layout.addWidget(self.error_label)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.connect_button = buttons.addButton("Discard drafts and connect" if state.drafts else "Connect", QDialogButtonBox.ButtonRole.AcceptRole)
        self.connect_button.clicked.connect(self.connect_controller)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.backend.currentIndexChanged.connect(self.update_fields)
        self.update_fields()

    def update_fields(self):
        backend = self.backend.currentData()
        self.channel.setEnabled(backend not in ("simulator", "gs_usb"))
        self.bitrate.setEnabled(backend not in ("simulator", "socketcan"))
        self.usb_index.setEnabled(backend == "gs_usb")
        self.serial_rate.setEnabled(backend == "slcan")
        self.notice.setText("SocketCAN must already be configured and brought up at the controller's bitrate." if backend == "socketcan" else "Simulation uses example maps and animated measurements." if backend == "simulator" else "Direct adapter access needs the matching python-can driver and platform permissions.")
        if backend == "slcan" and self.channel.text() == "can0":
            self.channel.setText("/dev/ttyACM0")

    def browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select firmware dictionary", "", "Controller dictionaries (*.eds *.dcf);;All files (*)")
        if path:
            self.eds.setText(path)

    def discover(self):
        def done(result):
            self.notice.setText(f"CAN: {', '.join(result['socketcan']) or 'none found'}. Serial: {', '.join(result['serial']) or 'none found'}. USB: {len(result['usb'])} candidates. "+" ".join(result["notes"]))
        self.state.request("adapters", done=done, failed=self.error_label.setText)

    def connect_controller(self):
        self.connect_button.setEnabled(False)
        options = {"backend": self.backend.currentData(), "node": self.node.value(),
                   "channel": self.channel.text(), "bitrate": self.bitrate.currentData(),
                   "usb_index": self.usb_index.value(), "serial_baudrate": self.serial_rate.value(),
                   "eds": self.eds.text() or None}
        def failed(message):
            self.error_label.setText(message)
            self.connect_button.setEnabled(True)
        self.state.connect_controller(options, self.accept, failed)


class AccessDialog(QDialog):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.setObjectName("accessDialog")
        self.setWindowTitle("Controller access and login")
        self.resize(650, 530)
        self.state = state
        layout = QVBoxLayout(self)
        self.current = QLabel()
        self.current.setObjectName("accessHeading")
        layout.addWidget(self.current)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.table = QTableWidget(6, 4)
        self.table.setHorizontalHeaderLabels(["Level", "Role", "Your grant", "Settings requiring this level"])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.setMaximumHeight(222)
        layout.addWidget(self.table)
        note = QLabel("Read access is separate from write authentication. Configuration state and dictionary restrictions still apply.")
        note.setWordWrap(True)
        note.setObjectName("secondaryText")
        layout.addWidget(note)
        form = QFormLayout()
        self.user = QSpinBox()
        self.user.setRange(0, 65535)
        self.user.setAccessibleName("User ID")
        add_help_field(form, "User ID", self.user, state, "login", self)
        self.password = QLineEdit()
        self.password.setAccessibleName("Password")
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setPlaceholderText("Decimal or 0x hexadecimal")
        add_help_field(form, "Password", self.password, state, "login", self)
        layout.addLayout(form)
        if state.connection.get("simulated"):
            layout.addWidget(QLabel("Simulator credentials: user 0, password 0x4BDF."))
        self.error_label = QLabel()
        self.error_label.setObjectName("faultText")
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.login = buttons.addButton("Log in", QDialogButtonBox.ButtonRole.AcceptRole)
        self.login.clicked.connect(self.login_controller)
        self.logout = buttons.addButton("Log out", QDialogButtonBox.ButtonRole.ActionRole)
        self.logout.clicked.connect(lambda: state.command("logout", done=lambda _: self.sync(), failed=self.error_label.setText))
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        state.permissions_changed.connect(self.sync)
        self.sync()

    def sync(self):
        editable = [s for s in self.state.settings.values() if s["editable"]]
        available = sum(self.state.permitted(s) for s in editable)
        self.current.setText("Your granted access: "+self.state.role())
        self.summary.setText(f"{available} settings available; {len(editable)-available} locked or unverified.\n"+f"{sum(s['level'] is None for s in editable)} settings have no declared login restriction.")
        for level, name in self.state.catalog.get("access_levels", {}).items():
            granted = self.state.level is not None and self.state.level >= level
            for column, text in enumerate([str(level), name, "Available" if granted else "Locked", str(sum(s["level"] == level for s in editable))]):
                self.table.setItem(level, column, QTableWidgetItem(text))
        self.login.setEnabled(self.state.connection.get("connected") and not self.state.busy)
        self.logout.setEnabled(bool(self.state.level) and not self.state.busy)

    def login_controller(self):
        payload = {"password": self.password.text(), "user": self.user.value()}
        self.password.clear()
        self.state.command("login", payload, done=lambda _: self.accept(), failed=self.error_label.setText)


class ReviewDialog(QDialog):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.setObjectName("reviewDialog")
        self.setWindowTitle("Review and apply changes")
        self.resize(920, 470)
        self.state = state
        self.keys = list(state.drafts)
        layout = QVBoxLayout(self)
        self.requirements = QLabel()
        self.requirements.setWordWrap(True)
        layout.addWidget(self.requirements)
        row = QHBoxLayout()
        configure = QPushButton("Enter configuration state")
        configure.clicked.connect(lambda: state.command("preop", done=lambda _: self.sync(), failed=self.requirements.setText))
        access = QPushButton("Access and login...")
        access.clicked.connect(lambda: (AccessDialog(state, self).exec(), self.sync()))
        row.addWidget(configure)
        row.addWidget(access)
        row.addStretch()
        row.addWidget(help_button(lambda: ExplanationDialog(state.catalog["topics"]["apply"], self).exec(), "Apply changes"))
        layout.addLayout(row)
        table = QTableWidget(len(self.keys), 5)
        self.table = table
        table.setHorizontalHeaderLabels(["Parameter", "Controller", "Proposed", "Required role", "Access"])
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.verticalHeader().hide()
        for i, key in enumerate(self.keys):
            draft, setting = state.drafts[key], state.settings[key]
            for j, text in enumerate([setting["path"], state.display(key, draft["before"]), state.display(key, draft["value"]), state.required(setting), state.permission_text(setting)]):
                table.setItem(i, j, QTableWidgetItem(text))
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(table, 1)
        label = QLabel("Every value is checked before the first write. Writes are sequential and read back. Save to memory is a separate command.")
        label.setWordWrap(True)
        label.setObjectName("secondaryText")
        layout.addWidget(label)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.apply_button = buttons.addButton(f"Apply {len(self.keys)} changes", QDialogButtonBox.ButtonRole.AcceptRole)
        self.apply_button.clicked.connect(self.apply_changes)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        state.permissions_changed.connect(self.sync)
        self.sync()

    def sync(self):
        missing = [key for key in self.keys if not self.state.permitted(self.state.settings[key])]
        for row, key in enumerate(self.keys):
            self.table.item(row, 4).setText(self.state.permission_text(self.state.settings[key]))
        preop = self.state.live.get("state") == 127
        self.requirements.setText(f"Your access: {self.state.role()}. "+(f"{len(missing)} changes need higher access. " if missing else "Access granted for all selected settings. ")+("Controller is in configuration state." if preop else "Enter configuration state before Apply."))
        self.apply_button.setEnabled(not missing and preop and not self.state.busy)

    def apply_changes(self):
        self.state.apply(self.keys)
        self.accept()

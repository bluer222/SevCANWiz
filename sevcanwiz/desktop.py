"""Native Qt commissioning application. No browser or HTTP server is involved."""

import csv
import io
import json
import time
from pathlib import Path
from html import escape
from PySide6.QtCore import Qt, QSettings, QTimer, QSaveFile, QIODevice, QSize
from PySide6.QtGui import QAction, QKeySequence, QFont, QColor, QPalette
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QToolBar, QDockWidget, QStackedWidget,
    QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView, QTextBrowser,
    QPushButton, QCheckBox, QLineEdit, QProgressBar, QDialog, QDialogButtonBox,
    QFileDialog, QMessageBox, QGroupBox, QStyle,
)
from .desktop_state import DesktopState, number_text
from .desktop_pages import ParameterPage, CurvePage, InstrumentsPage, DiagnosticsPage
from .desktop_network import NetworkPage
from .desktop_dialogs import AccessDialog, ConnectionDialog, ReviewDialog, MenuSearchDialog, explanation_html
from .desktop_widgets import help_button, system_icon
from .desktop_windows import ConfigurationWindow


STYLE = """
QWidget { color: #283138; font-family: "Noto Sans"; font-size: 9pt; }
QMainWindow { background: #e8ecef; }
QMenuBar, QToolBar { background: #eef0f2; spacing: 4px; }
QToolBar { border-bottom: 1px solid #c6cdd3; padding: 4px; }
QToolButton { padding: 4px 7px; min-height: 22px; }
QPushButton { min-height: 24px; padding: 2px 8px; }
QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox { min-height: 24px; }
QPushButton#contextHelp { min-height: 16px; padding: 0px; font-weight: bold; color: #4c6577; }
QTabWidget::pane { border: 1px solid #c8cfd5; background: #f4f5f6; }
QTabBar::tab { padding: 6px 12px; }
QDockWidget::title { background: #e7ebee; padding: 5px 8px; font-weight: bold; }
QLabel#workspaceTitle { font-size: 16px; font-weight: 600; }
QLabel#sectionHeading { font-weight: 600; }
QLabel#instrumentValue { font-family: "DejaVu Sans Mono"; font-size: 21px; font-weight: 600; }
QLabel#secondaryText, QLabel#permissionText { color: #626d76; }
QLabel#permissionText[locked="true"], QLabel#warningText { color: #94621b; }
QLineEdit:disabled, QComboBox:disabled, QDoubleSpinBox:disabled, QSpinBox:disabled { background: #e9edf0; color: #84909a; }
QPushButton:disabled, QToolButton:disabled { color: #84909a; }
QLabel#faultText { color: #b03c35; }
QLabel#accessHeading { font-size: 16px; font-weight: 600; }
QLabel#sessionStrip { background: #e5e9ed; border-bottom: 1px solid #bfc8d0; padding: 5px 8px; }
QLabel#sessionStrip[simulation="true"] { color: #805d20; }
QTableView { gridline-color: #e0e4e7; selection-background-color: #d5e6f3; selection-color: #243c4e; }
QHeaderView::section { background: #e9edf0; padding: 5px; border: 0; border-bottom: 1px solid #bcc6cd; font-weight: 600; }
QGroupBox { border: 1px solid #cbd2d8; margin-top: 8px; padding-top: 6px; }
QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }
QComboBox[draft="true"], QDoubleSpinBox[draft="true"], QLineEdit[draft="true"] { background: #edf4fa; border: 1px solid #87abc6; }
QProgressBar { min-height: 10px; max-height: 16px; border: 1px solid #b8c3cb; }
QProgressBar::chunk { background: #6c98b9; }
QTextBrowser { border: 0; padding: 4px; background: #f4f5f6; }
"""


def configure_application(app):
    app.setStyle("Fusion")
    app.setFont(QFont("Noto Sans", 9))
    palette = QPalette()
    for role, color in {
        "Window": "#eef0f2", "WindowText": "#283138", "Base": "#ffffff",
        "AlternateBase": "#f4f5f6", "Text": "#283138", "Button": "#e9edf0",
        "ButtonText": "#283138", "ToolTipBase": "#ffffec", "ToolTipText": "#283138",
        "Highlight": "#d5e6f3", "HighlightedText": "#243c4e", "PlaceholderText": "#727e88",
        "Light": "#ffffff", "Midlight": "#f1f3f5", "Mid": "#bfc8d0",
        "Dark": "#7f8d98", "Shadow": "#65727d", "BrightText": "#ffffff",
    }.items():
        palette.setColor(getattr(QPalette.ColorRole, role), QColor(color))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.WindowText, QPalette.ColorRole.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor("#84909a"))
    app.setPalette(palette)
    app.setStyleSheet(STYLE)


def save_text(path, content):
    file = QSaveFile(str(path))
    if not file.open(QIODevice.OpenModeFlag.WriteOnly):
        raise OSError(file.errorString())
    encoded = content.encode("utf-8")
    if file.write(encoded) != len(encoded) or not file.commit():
        raise OSError(file.errorString())


class MainWindow(QMainWindow):
    SYSTEMS = [("instruments", "Live instruments"), ("pedals", "Pedals and throttle"),
               ("drive", "Drive and braking"), ("motor", "Motor and encoder"),
               ("battery", "Battery and power"), ("io", "Inputs and outputs"),
               ("aux", "Pump and steering"), ("can", "CAN and network"),
               ("diagnostics", "Diagnostics and logs"), ("backups", "Backups and restore"),
               ("all", "All parameters")]

    def __init__(self, state=None, save_preferences=True):
        super().__init__()
        self.setObjectName("commissioningWindow")
        self.setWindowTitle("SevCANWiz / Gen4 commissioning")
        self.resize(1280, 880)
        self.setMinimumSize(1000, 700)
        self.state = state or DesktopState(parent=self)
        self.save_preferences = save_preferences
        self.preferences = QSettings("SevCANWiz", "Desktop")
        self.pages = {}
        self.windows = {}
        self.active_page = "instruments"
        self.help_key = "monitor"
        self._ui_log = []
        self._operation_id = None
        self._closing = False
        self.make_actions()
        self.make_window()
        self.state.catalog_changed.connect(self.build_pages)
        self.state.connection_changed.connect(self.update_status)
        self.state.permissions_changed.connect(self.update_status)
        self.state.permissions_changed.connect(lambda: self.show_help(self.help_key) if self.help_dock.isVisible() else None)
        self.state.drafts_changed.connect(self.update_drafts)
        self.state.values_changed.connect(self.update_drafts)
        self.state.message.connect(self.report_message)
        self.state.error.connect(self.report_error)
        self.state.progress.connect(self.update_progress)
        if self.state.catalog:
            self.build_pages()
        if save_preferences:
            geometry, layout = self.preferences.value("monitor/geometry"), self.preferences.value("monitor/layout")
            if geometry:
                self.restoreGeometry(geometry)
            if layout:
                self.restoreState(layout)

    def make_action(self, text, callback, shortcut=None, standard=None):
        action = QAction(text, self)
        action.triggered.connect(lambda checked=False: callback())
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        if standard is not None:
            action.setIcon(self.style().standardIcon(standard))
        return action

    def make_actions(self):
        self.connect_action = self.make_action("Connect...", self.connect_dialog, "Ctrl+K", QStyle.StandardPixmap.SP_DriveNetIcon)
        self.disconnect_action = self.make_action("Disconnect", self.disconnect)
        self.access_action = self.make_action("Access and login...", self.access_dialog, standard=QStyle.StandardPixmap.SP_DialogApplyButton)
        self.read_action = self.make_action("Read controller", self.refresh_page, "F5", QStyle.StandardPixmap.SP_BrowserReload)
        self.apply_action = self.make_action("Apply changes...", self.review_changes, "Ctrl+Return", QStyle.StandardPixmap.SP_DialogApplyButton)
        self.store_action = self.make_action("Save to controller...", self.store, "Ctrl+S", QStyle.StandardPixmap.SP_DialogSaveButton)
        self.preop_action = self.make_action("Configuration state", lambda: self.state.command("preop"))
        self.operational_action = self.make_action("Return to operational...", self.operational)
        self.discard_action = self.make_action("Discard proposed changes...", self.discard)
        self.export_action = self.make_action("Export configuration backup...", self.export_backup)
        self.import_action = self.make_action("Compare and restore backup...", self.import_backup)
        self.dump_action = self.make_action("Export all readable values...", self.export_values)
        self.record_action = self.make_action("Start measurement recording", self.toggle_recording)
        self.csv_action = self.make_action("Export measurement CSV...", self.export_csv)
        self.log_action = self.make_action("Export activity log...", self.export_log)
        self.find_action = self.make_action("Find parameter...", self.find_parameter, "Ctrl+F")
        self.help_action = self.make_action("Explain selected setting", lambda: self.show_help(self.help_key), "F1")
        self.menu_search_action = self.make_action("Search menus...", self.search_menus, "Ctrl+Shift+P")
        self.window_actions = {}
        short_names = {"instruments": "Monitor", "pedals": "Pedals", "drive": "Drive",
                       "motor": "Motor", "battery": "Battery", "io": "I/O", "aux": "Auxiliary",
                       "can": "CAN / TPDO", "diagnostics": "Diagnostics", "backups": "Backups", "all": "Parameters"}
        for key, title in self.SYSTEMS:
            action = self.make_action(title, lambda key=key: self.navigate(key))
            action.setIcon(system_icon(key))
            action.setIconText(short_names[key])
            action.setToolTip("Open "+title.lower()+" window" if key != "instruments" else "Activate the monitoring window")
            self.window_actions[key] = action

    def make_window(self):
        file_menu = self.menuBar().addMenu("&File")
        for action in (self.export_action, self.import_action, self.dump_action):
            file_menu.addAction(action)
        file_menu.addSeparator()
        for action in (self.record_action, self.csv_action, self.log_action):
            file_menu.addAction(action)
        file_menu.addSeparator()
        file_menu.addAction(self.make_action("Exit", self.close, "Ctrl+Q"))
        controller_menu = self.menuBar().addMenu("&Controller")
        for action in (self.connect_action, self.disconnect_action, self.access_action, self.read_action):
            controller_menu.addAction(action)
        controller_menu.addSeparator()
        for action in (self.preop_action, self.operational_action):
            controller_menu.addAction(action)
        configuration_menu = self.menuBar().addMenu("&Configuration")
        for action in (self.apply_action, self.discard_action, self.store_action):
            configuration_menu.addAction(action)
        self.view_menu = self.menuBar().addMenu("&View")
        self.view_menu.addAction(self.find_action)
        self.view_menu.addAction(self.make_action("Restore default layout", self.restore_layout))
        windows_menu = self.menuBar().addMenu("&Windows")
        windows_menu.addActions(list(self.window_actions.values()))
        help_menu = self.menuBar().addMenu("&Help")
        help_menu.addAction(self.menu_search_action)
        help_menu.addAction(self.help_action)
        help_menu.addAction(self.make_action("Apply and save guide", lambda: self.show_help("apply")))
        help_menu.addAction(self.make_action("About SevCANWiz", self.about))
        toolbar = QToolBar("Controller commands")
        toolbar.setObjectName("controllerCommands")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        for action in (self.connect_action, self.access_action):
            toolbar.addAction(action)
        toolbar.addSeparator()
        for action in (self.preop_action, self.operational_action):
            toolbar.addAction(action)
        toolbar.addSeparator()
        for action in (self.read_action, self.apply_action, self.store_action):
            toolbar.addAction(action)
        self.addToolBar(toolbar)
        self.addToolBarBreak()
        windows_toolbar = QToolBar("Controller windows", self)
        windows_toolbar.setObjectName("controllerWindows")
        windows_toolbar.setMovable(False)
        windows_toolbar.setIconSize(QSize(24, 24))
        windows_toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        windows_toolbar.addActions(list(self.window_actions.values()))
        self.addToolBar(windows_toolbar)
        central = QWidget()
        body = QVBoxLayout(central)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        self.session_strip = QLabel("No controller / waiting for dictionary")
        self.session_strip.setObjectName("sessionStrip")
        self.session_strip.setWordWrap(True)
        body.addWidget(self.session_strip)
        heading = QWidget()
        heading_layout = QHBoxLayout(heading)
        heading_layout.setContentsMargins(10, 8, 10, 8)
        self.workspace_title = QLabel("Live monitoring")
        self.workspace_title.setObjectName("workspaceTitle")
        heading_layout.addWidget(self.workspace_title, 1)
        body.addWidget(heading)
        self.workspaces = QStackedWidget()
        self.loading = QLabel("Loading controller dictionary...")
        self.loading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.workspaces.addWidget(self.loading)
        body.addWidget(self.workspaces, 1)
        self.notice = QLabel()
        self.notice.setObjectName("faultText")
        self.notice.setWordWrap(True)
        self.notice.hide()
        body.addWidget(self.notice)
        self.setCentralWidget(central)
        self.help_dock = QDockWidget("Setting explanation", self)
        self.help_dock.setObjectName("explanationDock")
        self.help_dock.setMinimumWidth(260)
        help_body = QWidget()
        help_layout = QVBoxLayout(help_body)
        help_layout.setContentsMargins(4, 4, 4, 4)
        self.help_browser = QTextBrowser()
        self.help_browser.setAccessibleName("Complete setting explanation")
        self.help_browser.document().setDefaultStyleSheet("h2 {font-size: 16px;} h3 {font-size: 12px; color:#3b5467;} p, li {line-height:145%;}")
        help_layout.addWidget(self.help_browser, 1)
        self.technical = QCheckBox("Show technical reference")
        self.technical.toggled.connect(lambda _: self.show_help(self.help_key))
        help_layout.addWidget(self.technical)
        self.help_dock.setWidget(help_body)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.help_dock)
        self.help_dock.hide()
        self.changes_dock = QDockWidget("Configuration changes and activity", self)
        self.changes_dock.setObjectName("changesDock")
        self.change_tabs = QTabWidget()
        proposals = QWidget()
        proposal_layout = QVBoxLayout(proposals)
        proposal_layout.setContentsMargins(4, 4, 4, 4)
        row = QHBoxLayout()
        self.draft_summary = QLabel("No proposed changes")
        row.addWidget(self.draft_summary, 1)
        apply = QPushButton("Review and apply...")
        apply.clicked.connect(self.review_changes)
        self.dock_apply = apply
        row.addWidget(apply)
        discard = QPushButton("Discard...")
        discard.clicked.connect(self.discard)
        self.dock_discard = discard
        row.addWidget(discard)
        row.addWidget(help_button(lambda: self.show_help("apply"), "Configuration changes"))
        proposal_layout.addLayout(row)
        self.draft_table = QTableWidget(0, 5)
        self.draft_table.setObjectName("pendingChangesTable")
        self.draft_table.setHorizontalHeaderLabels(["Parameter", "Controller", "Proposed", "Required role", "Access"])
        self.draft_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.draft_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.draft_table.verticalHeader().hide()
        self.draft_table.verticalHeader().setDefaultSectionSize(25)
        self.draft_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.draft_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.draft_table.itemClicked.connect(lambda item: self.show_help(self.draft_table.item(item.row(), 0).data(Qt.ItemDataRole.UserRole)))
        proposal_layout.addWidget(self.draft_table)
        self.change_tabs.addTab(proposals, "Pending changes")
        self.activity = QTableWidget(0, 3)
        self.activity.setHorizontalHeaderLabels(["Time", "Event", "Type"])
        self.activity.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.activity.verticalHeader().hide()
        self.activity.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.change_tabs.addTab(self.activity, "Activity and verification")
        self.changes_dock.setWidget(self.change_tabs)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.changes_dock)
        self.changes_dock.setMinimumHeight(155)
        self.changes_dock.hide()
        for dock in (self.help_dock, self.changes_dock):
            self.view_menu.addAction(dock.toggleViewAction())
        self.status = QLabel("Disconnected")
        self.statusBar().addWidget(self.status, 1)
        self.progress = QProgressBar()
        self.progress.setFixedWidth(200)
        self.progress.hide()
        self.statusBar().addPermanentWidget(self.progress)
        self.resizeDocks([self.help_dock], [330], Qt.Orientation.Horizontal)
        self.resizeDocks([self.changes_dock], [180], Qt.Orientation.Vertical)
        self.update_status()

    def build_pages(self):
        if "instruments" in self.pages:
            previous = self.pages["instruments"]
            self.workspaces.removeWidget(previous)
            previous.deleteLater()
        self.pages["instruments"] = InstrumentsPage(self.state, self.show_help)
        self.workspaces.addWidget(self.pages["instruments"])
        self.workspaces.setCurrentWidget(self.pages["instruments"])
        for window in self.windows.values():
            window.rebuild()
        self.update_status()

    def make_page(self, key, help_requested):
        if key == "diagnostics":
            return DiagnosticsPage(self.state, help_requested, self.show_trace)
        if key == "can":
            return NetworkPage(self.state, help_requested, self.show_trace)
        if key == "backups":
            return self.backup_page(help_requested)
        if key in ("pedals", "motor", "battery", "aux"):
            page = QTabWidget()
            page.tabBar().setUsesScrollButtons(False)
            page.tabBar().setElideMode(Qt.TextElideMode.ElideRight)
            names = {"map-4611": "Torque / speed", "map-4615": "Secondary torque",
                     "map-4612": "Voltage cutback", "map-461E": "Thermal cutback",
                     "map-461F": "Thermistor", "steer-outer": "Outer steering",
                     "steer-inner": "Inner steering", "pump-2A10": "Pump 1",
                     "pump-2A11": "Pump 2"}
            for curve in self.state.catalog["curves"]:
                if curve["group"] == key:
                    tab = page.addTab(CurvePage(self.state, curve, help_requested),
                                      names.get(curve["id"], curve["name"]))
                    page.setTabToolTip(tab, curve["name"])
            page.addTab(ParameterPage(self.state, key, help_requested, self.show_trace), "All settings")
            page.currentChanged.connect(lambda: self.read_widget(page.currentWidget()))
            return page
        return ParameterPage(self.state, None if key == "all" else key, help_requested, self.show_trace)

    def navigate(self, key):
        if key == "instruments":
            self.show()
            self.raise_()
            self.activateWindow()
            return self
        if not self.state.catalog:
            return
        if key not in self.windows:
            title = next(title for name, title in self.SYSTEMS if name == key)
            self.windows[key] = ConfigurationWindow(self, key, title)
        window = self.windows[key]
        window.show()
        window.raise_()
        window.activateWindow()
        QTimer.singleShot(0, window, lambda: self.read_widget(window.page))
        return window

    def read_widget(self, widget, refresh=False):
        if isinstance(widget, CurvePage):
            widget.read(refresh)
        elif isinstance(widget, ParameterPage):
            QTimer.singleShot(0, widget, lambda: widget.read_visible(refresh))
        elif isinstance(widget, QTabWidget):
            self.read_widget(widget.currentWidget(), refresh)
        elif isinstance(widget, NetworkPage):
            if widget.tabs.currentIndex() == 0:
                if refresh or widget.config is None:
                    widget.read()
            else:
                self.read_widget(widget.parameters, refresh)
        elif isinstance(widget, DiagnosticsPage):
            self.read_widget(widget.tabs.currentWidget(), refresh)

    def refresh_page(self):
        active = QApplication.activeWindow()
        if isinstance(active, ConfigurationWindow):
            self.read_widget(active.page, True)
        else:
            self.state.poll_live()

    def show_help(self, key):
        self.help_key = key
        setting = self.state.settings.get(key)
        help = setting["help"] if setting else self.state.catalog.get("topics", {}).get(key)
        if help:
            self.help_browser.setHtml(explanation_html(help, self.state, setting, self.technical.isChecked()))
            self.help_dock.show()

    def show_trace(self, key):
        setting = self.state.settings.get(key)
        if not setting or not setting["readable"] or not setting["type"].startswith(("INTEGER", "UNSIGNED", "REAL")):
            self.report_message("Choose a readable numeric signal to plot.")
            return
        self.navigate("instruments")
        self.pages["instruments"].show_signal(key)

    def find_parameter(self):
        window = self.navigate("all")
        if window:
            window.page.search.setFocus()
            window.page.search.selectAll()

    def search_menus(self, parent=None):
        MenuSearchDialog(self.menu_entries(), parent or self).exec()

    def menu_entries(self):
        entries = []
        aliases = {"can": "tpdo rpdo transmit receive timing interval event timer inhibit process data automatic sent",
                   "pedals": "throttle footbrake response calibration curve", "aux": "pump steering",
                   "motor": "encoder thermistor thermal temperature torque cutback"}
        def collect(menu, prefix):
            for action in menu.actions():
                if action.isSeparator():
                    continue
                path = prefix+" > "+action.text().replace("&", "")
                if action.menu():
                    collect(action.menu(), path)
                else:
                    key = next((k for k, a in self.window_actions.items() if a is action), "")
                    entries.append((path, action, aliases.get(key, "")))
        for action in self.menuBar().actions():
            if action.menu():
                collect(action.menu(), action.text().replace("&", ""))
        return entries

    def update_status(self):
        connection, live = self.state.connection, self.state.live
        connected = connection.get("connected")
        network = {127: "Configuration / pre-operational", 5: "Operational", 4: "Stopped"}.get(live.get("state"), "State unknown")
        faults = live.get("faults")
        fault_count = f"{len(faults)} active faults" if faults is not None else "Fault state unknown"
        identity = connection.get("identity")
        dictionary = "Dictionary identity differs" if identity and not identity["matches"] else "Dictionary matched" if identity else "No identity"
        self.session_strip.setText(f"{'SIMULATION' if connection.get('simulated') else 'CONTROLLER' if connected else 'DISCONNECTED'}  |  Node {connection.get('node') or '--'}  |  {network}  |  {self.state.role()}  |  {fault_count}  |  {dictionary}")
        self.session_strip.setProperty("simulation", connection.get("simulated", False))
        self.session_strip.style().unpolish(self.session_strip)
        self.session_strip.style().polish(self.session_strip)
        self.access_action.setText(self.state.role()+"...")
        self.status.setText(("Applied configuration is not saved to memory" if connection.get("unsaved") else "Controller parameters unchanged" if not self.state.drafts else "Proposed changes await Apply")+f"  |  {len(self.state.drafts)} pending  |  {'Recording' if self.state.recording else 'Live paused' if self.state.paused else 'SDO monitoring'}")
        self.disconnect_action.setEnabled(connected and not self.state.busy)
        self.read_action.setEnabled(connected and not self.state.busy)
        self.preop_action.setEnabled(connected and not self.state.busy and live.get("state") != 127)
        self.operational_action.setEnabled(connected and not self.state.busy and live.get("state") != 5)
        self.connect_action.setEnabled(not self.state.busy)
        self.access_action.setEnabled(connected and not self.state.busy)
        store = self.state.settings.get("1010:01")
        required = store["level"] if store else 4
        permitted = self.state.level is not None and (required is None or self.state.level >= required)
        self.store_action.setEnabled(connected and not self.state.busy and not self.state.drafts and permitted)
        self.store_action.setToolTip(f"Required: {self.state.required(store) if store else 'Engineering / level 4'}. Your access: {self.state.role()}. Configuration state required.")
        for action in (self.export_action, self.import_action, self.dump_action, self.record_action):
            action.setEnabled(connected and not self.state.busy)
        self.csv_action.setEnabled(bool(self.state.samples))
        self.update_drafts()
        self.update_activity()

    def update_drafts(self):
        count = len(self.state.drafts)
        self.draft_summary.setText(f"{count} proposed change{'s' if count != 1 else ''}. Controller writes require Apply." if count else "No proposed changes. Save applied changes separately to memory." if self.state.connection.get("unsaved") else "No proposed changes")
        self.apply_action.setText(f"Apply {count} changes..." if count else "Apply changes...")
        self.apply_action.setEnabled(bool(count) and not self.state.busy)
        self.discard_action.setEnabled(bool(count) and not self.state.busy)
        self.dock_apply.setEnabled(self.apply_action.isEnabled())
        self.dock_discard.setEnabled(self.discard_action.isEnabled())
        self.draft_table.setRowCount(count)
        for i, (key, draft) in enumerate(self.state.drafts.items()):
            setting = self.state.settings[key]
            for j, value in enumerate([setting["path"], self.state.display(key, draft["before"]), self.state.display(key, draft["value"]), self.state.required(setting), self.state.permission_text(setting)]):
                item = QTableWidgetItem(value)
                if j == 0:
                    item.setData(Qt.ItemDataRole.UserRole, key)
                self.draft_table.setItem(i, j, item)
        if count:
            self.store_action.setEnabled(False)

    def update_activity(self):
        log = [*self._ui_log, *self.state.live.get("log", [])]
        log = sorted(log, key=lambda event: event["time"], reverse=True)[:250]
        self.activity.setRowCount(len(log))
        for i, event in enumerate(log):
            for j, text in enumerate([time.strftime("%H:%M:%S", time.localtime(event["time"])), event["message"], event["kind"]]):
                item = QTableWidgetItem(text)
                item.setToolTip(text)
                self.activity.setItem(i, j, item)

    def update_progress(self, kind, completed, total):
        self.progress.setVisible(bool(kind))
        if kind:
            self.progress.setRange(0, max(1, total))
            self.progress.setValue(completed)
            self.progress.setFormat(f"{completed} / {total}")
            self.progress.setToolTip(kind)
        if self._operation_id and hasattr(self, "operation_progress"):
            self.operation_progress.setRange(0, max(1, total))
            self.operation_progress.setValue(completed)

    def report_message(self, message):
        self.statusBar().showMessage(message, 8000)
        self._ui_log.insert(0, {"time": time.time(), "message": message, "kind": "info"})
        self._ui_log = self._ui_log[:100]
        self.update_activity()

    def report_error(self, message):
        self.notice.setText("Operation failed: "+message)
        self.notice.show()
        self._ui_log.insert(0, {"time": time.time(), "message": message, "kind": "error"})
        self._ui_log = self._ui_log[:100]
        self.change_tabs.setCurrentIndex(1)
        self.update_activity()

    def connect_dialog(self):
        if self.state.catalog:
            ConnectionDialog(self.state, self).exec()

    def access_dialog(self, parent=None):
        if self.state.catalog:
            AccessDialog(self.state, parent or self).exec()

    def review_changes(self, parent=None):
        if self.state.drafts and not self.state.busy:
            self.notice.hide()
            ReviewDialog(self.state, parent or self).exec()

    def discard(self):
        if self.state.drafts and QMessageBox.question(self, "Discard proposed changes", "Discard all proposed changes? No controller writes will occur.") == QMessageBox.StandardButton.Yes:
            self.state.discard()
            self.update_status()

    def disconnect(self):
        if self.state.drafts:
            self.report_error("Apply or discard proposed changes before disconnecting.")
            return
        def disconnected(connection):
            self.state.connection = connection
            self.state.live = {}
            self.state.readings.clear()
            self.state.connection_changed.emit()
            self.state.permissions_changed.emit()
            self.state.values_changed.emit()
        self.state.request("disconnect", done=disconnected)

    def operational(self, parent=None):
        if QMessageBox.question(parent or self, "Return to operational", "Operational state permits normal process data and the vehicle application to resume. It does not send an enable-drive command. Continue?") == QMessageBox.StandardButton.Yes:
            self.state.command("operational")

    def store(self, parent=None):
        if self.state.drafts:
            self.report_error("Apply or discard all proposed changes before saving to memory.")
            return
        if QMessageBox.question(parent or self, "Save to controller memory", "Save the controller's current configuration to nonvolatile memory? This includes changes made by other clients. Acknowledgement does not verify persistence after a power cycle.") == QMessageBox.StandardButton.Yes:
            self.state.command("store", done=lambda _: self.report_message("Controller acknowledged Save."))

    def restore_layout(self):
        for dock in (self.help_dock, self.changes_dock):
            dock.setFloating(False)
            dock.show()
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.help_dock)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.changes_dock)
        self.resizeDocks([self.help_dock], [330], Qt.Orientation.Horizontal)
        self.resizeDocks([self.changes_dock], [180], Qt.Orientation.Vertical)

    def backup_page(self, help_requested):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)
        for title, description, button_text, callback in [
            ("Controller backup", "Read all readable EEPROM-backed parameters, exact bytes, live identity, and any failed reads. This does not write parameter values.", "Export backup...", self.export_backup),
            ("Selected restore", "Compare an existing SevconCAN snapshot with this controller. Review differences, select values, and stage them for the normal Apply workflow.", "Compare and restore...", self.import_backup),
            ("Diagnostic value dump", "Read all readable dictionary entries, including live measurements and counters. Cancellation exports partial results. This file is diagnostic data and cannot be used as a restore snapshot.", "Export all values...", self.export_values),
        ]:
            group = QGroupBox(title)
            body = QVBoxLayout(group)
            label = QLabel(description)
            label.setWordWrap(True)
            body.addWidget(label)
            row = QHBoxLayout()
            button = QPushButton(button_text)
            button.clicked.connect(callback)
            row.addWidget(button)
            row.addWidget(help_button(lambda title=title: help_requested("dump" if title == "Diagnostic value dump" else "backup"), title))
            row.addStretch()
            body.addLayout(row)
            layout.addWidget(group)
        layout.addStretch()
        return page

    def operation_dialog(self, title, cancelable=True):
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.resize(520, 180)
        layout = QVBoxLayout(dialog)
        label = QLabel("Reading controller data. No configuration values are being written.")
        label.setWordWrap(True)
        layout.addWidget(label)
        self.operation_progress = QProgressBar()
        layout.addWidget(self.operation_progress)
        if cancelable:
            cancel = QPushButton("Cancel read operation")
            cancel.clicked.connect(lambda: self.state.request("cancel", {"id": self._operation_id}) if self._operation_id else None)
            layout.addWidget(cancel)
        dialog.setModal(True)
        dialog.show()
        return dialog

    def export_backup(self):
        if not self.state.connection.get("connected"):
            return self.report_error("Connect to a controller before exporting.")
        path, _ = QFileDialog.getSaveFileName(self, "Export configuration backup", "sevcon-configuration.json", "JSON snapshot (*.json)")
        if not path:
            return
        self.export_backup_to(path)

    def export_backup_to(self, path, done=None):
        dialog = self.operation_dialog("Export configuration backup")
        def update(job):
            self._operation_id = job["id"]
        def completed(job):
            self._operation_id = None
            dialog.accept()
            if job["state"] == "cancelled":
                self.report_message("Backup cancelled. No controller parameters changed.")
                return
            try:
                save_text(path, job["result"]["snapshot"])
                self.report_message(f"Backup saved. {job['result']['errors']} failed reads are recorded in the file.")
                if done:
                    done(job)
            except OSError as error:
                self.report_error(str(error))
        def failed(error):
            dialog.reject()
            self.report_error(error)
        self.state.start_job("backup", done=completed, changed=update, failed=failed)

    def import_backup(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select configuration snapshot", "", "JSON snapshot (*.json)")
        if not path:
            return
        try:
            if Path(path).stat().st_size > 4*1024*1024:
                raise ValueError("Snapshot files must be smaller than 4 MiB.")
            self.compare_snapshot(Path(path).read_text())
        except (OSError, ValueError) as error:
            self.report_error(str(error))

    def compare_snapshot(self, text, done=None):
        dialog = self.operation_dialog("Compare configuration snapshot")
        def completed(job):
            self._operation_id = None
            dialog.accept()
            if job["state"] == "cancelled":
                return
            if done:
                done(job["result"])
            else:
                self.restore_selection(job["result"])
        def failed(error):
            dialog.reject()
            self.report_error(error)
        self.state.start_job("import", {"text": text, "session": self.state.connection.get("session")}, completed,
                             lambda job: setattr(self, "_operation_id", job["id"]), failed)

    def restore_selection(self, plan):
        dialog = QDialog(self)
        dialog.setWindowTitle("Select settings to restore")
        dialog.resize(900, 500)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(f"{len(plan['changes'])} differences. {plan['skipped']} dedicated or unsupported entries excluded; {plan['errors']} read errors."))
        table = QTableWidget(len(plan["changes"]), 4)
        table.setHorizontalHeaderLabels(["Restore", "Parameter", "Live", "Snapshot"])
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.verticalHeader().hide()
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for i, change in enumerate(plan["changes"]):
            choice = QTableWidgetItem()
            choice.setFlags(choice.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            choice.setCheckState(Qt.CheckState.Unchecked)
            table.setItem(i, 0, choice)
            for j, value in enumerate([change["name"], number_text(change["before"]), number_text(change["value"])], 1):
                table.setItem(i, j, QTableWidgetItem(value))
        layout.addWidget(table, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        stage = buttons.addButton("Stage selected settings", QDialogButtonBox.ButtonRole.AcceptRole)
        def selected():
            changes = [change for i, change in enumerate(plan["changes"]) if table.item(i, 0).checkState() == Qt.CheckState.Checked]
            if not changes:
                return
            self.stage_restore(changes)
            dialog.accept()
        stage.clicked.connect(selected)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    def stage_restore(self, changes):
        for change in changes:
            key = change["key"]
            self.state.readings[key] = {"key": key, "value": change["before"], "bytes": change["expected"]}
            self.state.drafts[key] = {"value": change["value"], "before": change["before"], "expected": change["expected"]}
        self.state.drafts_changed.emit()
        self.state.values_changed.emit()
        self.report_message(f"{len(changes)} selected settings proposed. Review and Apply when ready.")

    def export_values(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export all readable values", "sevcon-values.json", "JSON values (*.json)")
        if not path:
            return
        dialog = self.operation_dialog("Export all readable values")
        connection = dict(self.state.connection)
        started = time.time()
        keys = [s["key"] for s in self.state.settings.values() if s["readable"]]
        def completed(job):
            self._operation_id = None
            dialog.accept()
            output = {"schema": "sevcanwiz.values.v1", "complete": job["state"] == "done", "simulated": connection.get("simulated"),
                      "identity": connection.get("identity"), "dictionary": self.state.catalog["source"], "started_at": started, "finished_at": time.time(),
                      "values": [{**row, "path": self.state.settings[row["key"]]["path"], "unit": self.state.settings[row["key"]]["unit"]} for row in job["rows"]],
                      "skipped": [{"key": s["key"], "path": s["path"], "reason": "Write only"} for s in self.state.settings.values() if not s["readable"]]}
            try:
                save_text(path, json.dumps(output, indent=2))
                self.report_message(f"{len(job['rows'])} values saved"+(" / partial scan" if not output["complete"] else ""))
            except OSError as error:
                self.report_error(str(error))
        self.state.start_job("read", {"keys": keys}, completed, lambda job: setattr(self, "_operation_id", job["id"]), lambda error: (dialog.reject(), self.report_error(error)))

    def toggle_recording(self):
        if not self.state.recording:
            self.state.samples.clear()
        self.state.recording = not self.state.recording
        self.state.paused = False
        self.record_action.setText("Stop measurement recording" if self.state.recording else "Start measurement recording")
        self.update_status()

    def export_csv(self):
        if not self.state.samples:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export measurement recording", "sevcon-measurements.csv", "CSV recording (*.csv)")
        if not path:
            return
        try:
            save_text(path, self.csv_text())
            self.report_message(f"{len(self.state.samples)} measurement samples saved.")
        except OSError as error:
            self.report_error(str(error))

    def csv_text(self):
        keys = list(dict.fromkeys(key for sample in self.state.samples for key in sample["values"]))
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["UTC timestamp"]+[self.state.settings[key]["path"]+f" [{self.state.settings[key]['unit']}]" for key in keys])
        for sample in self.state.samples:
            timestamp = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(sample["time"]))+f".{int(sample['time']%1*1000):03d}Z"
            writer.writerow([timestamp]+[sample["values"].get(key, "") for key in keys])
        return output.getvalue()

    def export_log(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export activity log", "sevcon-activity.json", "JSON log (*.json)")
        if path:
            try:
                save_text(path, json.dumps([*self._ui_log, *self.state.live.get("log", [])], indent=2))
            except OSError as error:
                self.report_error(str(error))

    def about(self):
        QMessageBox.about(self, "SevCANWiz", "SevCANWiz 0.2\nNative Qt controller commissioning\nPowered by SevconCAN\nAGPL-3.0-only\n\nSimulation and software verification do not establish physical hardware compatibility.")

    def closeEvent(self, event):
        if self._closing:
            event.accept()
            return
        if self.state.busy:
            self.report_error("Wait for the active controller operation to finish before closing.")
            event.ignore()
            return
        if self.state.drafts or self.state.recording:
            if QMessageBox.question(self, "Close commissioning application", "There are proposed changes or an active measurement recording. Close and discard this local work?") != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        if self.save_preferences:
            self.preferences.setValue("monitor/geometry", self.saveGeometry())
            self.preferences.setValue("monitor/layout", self.saveState())
        self._closing = True
        for window in self.windows.values():
            window.close()
        self.state.close()
        event.accept()


def run_desktop(eds=None, disconnected=False):
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("SevCANWiz")
    app.setApplicationVersion("0.2.0")
    configure_application(app)
    from .runtime import Runtime
    state = DesktopState(Runtime(eds))
    window = MainWindow(state)
    window.show()
    state.initialize(not disconnected, eds)
    return app.exec()

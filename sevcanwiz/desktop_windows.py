"""Independent configuration windows sharing one monitored controller session."""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QToolBar,
    QDockWidget, QTextBrowser, QCheckBox,
)
from .desktop_dialogs import explanation_html


class ConfigurationWindow(QMainWindow):
    def __init__(self, owner, key, title):
        super().__init__(owner, Qt.WindowType.Window)
        self.owner, self.state, self.key = owner, owner.state, key
        self.help_key = "pdo" if key == "can" else "curve" if key == "pedals" else "apply"
        self.setObjectName("configurationWindow_"+key)
        self.setWindowTitle("SevCANWiz / "+title)
        self.resize(1250, 850)
        self.setMinimumSize(940, 640)
        toolbar = QToolBar("Configuration commands", self)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        self.read_action = self.action("Read controller", lambda: owner.read_widget(self.page, True), "F5")
        self.access_action = self.action("Access and login...", lambda: owner.access_dialog(self))
        self.apply_action = self.action("Review and apply...", lambda: owner.review_changes(self), "Ctrl+Return")
        self.store_action = self.action("Save to controller...", lambda: owner.store(self), "Ctrl+S")
        self.preop_action = self.action("Configuration state", lambda: self.state.command("preop"))
        self.operational_action = self.action("Return to operational...", lambda: owner.operational(self))
        commands = [self.read_action, self.access_action, self.preop_action, self.operational_action, self.apply_action, self.store_action]
        for action in commands:
            toolbar.addAction(action)
        self.menuBar().addMenu("&Configuration").addActions(commands)
        help_menu = self.menuBar().addMenu("&Help")
        help_menu.addAction(self.action("Search menus...", lambda: owner.search_menus(self), "Ctrl+Shift+P"))
        help_menu.addAction(self.action("Explain selected setting", lambda: self.show_help(self.help_key), "F1"))
        self.central = QWidget()
        self.body = QVBoxLayout(self.central)
        self.body.setContentsMargins(0, 0, 0, 0)
        self.session = QLabel()
        self.session.setObjectName("sessionStrip")
        self.session.setWordWrap(True)
        self.body.addWidget(self.session)
        self.error_notice = QLabel()
        self.error_notice.setObjectName("faultText")
        self.error_notice.setWordWrap(True)
        self.error_notice.hide()
        self.body.addWidget(self.error_notice)
        self.state.error.connect(self.show_error)
        self.read_action.triggered.connect(self.error_notice.hide)
        self.setCentralWidget(self.central)
        self.help_dock = QDockWidget("Setting explanation", self)
        self.help_dock.setObjectName("settingExplanation")
        self.help_dock.setMinimumWidth(280)
        explanation = QWidget()
        layout = QVBoxLayout(explanation)
        layout.setContentsMargins(4, 4, 4, 4)
        self.help_browser = QTextBrowser()
        self.help_browser.setAccessibleName("Complete setting explanation")
        self.help_browser.document().setDefaultStyleSheet("h2 {font-size:16px;} h3 {font-size:12px;color:#3b5467;}")
        layout.addWidget(self.help_browser, 1)
        self.technical = QCheckBox("Show technical reference")
        self.technical.toggled.connect(lambda: self.show_help(self.help_key))
        layout.addWidget(self.technical)
        self.help_dock.setWidget(explanation)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.help_dock)
        self.help_dock.hide()
        self.resizeDocks([self.help_dock], [330], Qt.Orientation.Horizontal)
        self.status = QLabel()
        self.statusBar().addWidget(self.status, 1)
        self.rebuild()
        self.state.permissions_changed.connect(self.update_status)
        self.state.permissions_changed.connect(lambda: self.show_help(self.help_key) if self.help_dock.isVisible() else None)
        self.state.connection_changed.connect(self.update_status)
        self.state.drafts_changed.connect(self.update_status)
        self.update_status()
        geometry = owner.preferences.value("windows/"+key) if owner.save_preferences else None
        if geometry:
            self.restoreGeometry(geometry)

    def action(self, title, callback, shortcut=None):
        action = QAction(title, self)
        action.triggered.connect(lambda checked=False: callback())
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        return action

    def rebuild(self):
        if hasattr(self, "page"):
            self.body.removeWidget(self.page)
            self.page.deleteLater()
        self.page = self.owner.make_page(self.key, self.show_help)
        self.body.insertWidget(1, self.page, 1)
        self.owner.pages[self.key] = self.page
        if self.isVisible():
            QTimer.singleShot(0, self, lambda: self.owner.read_widget(self.page))

    def show_help(self, key):
        setting = self.state.settings.get(key)
        help = setting["help"] if setting else self.state.catalog.get("topics", {}).get(key)
        if not help:
            self.state.error.emit(f"No explanation is available for {key}.")
            return
        self.help_key = key
        self.help_browser.setHtml(explanation_html(help, self.state, setting, self.technical.isChecked()))
        self.help_dock.show()

    def show_error(self, message):
        self.error_notice.setText("Operation failed: "+message)
        self.error_notice.show()

    def update_status(self):
        self.session.setText(self.owner.session_strip.text())
        self.access_action.setText(self.state.role()+"...")
        self.read_action.setEnabled(self.owner.read_action.isEnabled())
        self.access_action.setEnabled(self.owner.access_action.isEnabled())
        self.preop_action.setEnabled(self.owner.preop_action.isEnabled())
        self.operational_action.setEnabled(self.owner.operational_action.isEnabled())
        self.apply_action.setEnabled(bool(self.state.drafts) and not self.state.busy)
        self.apply_action.setText(f"Review and apply {len(self.state.drafts)} changes..." if self.state.drafts else "Review and apply...")
        self.store_action.setEnabled(self.owner.store_action.isEnabled())
        self.store_action.setToolTip(self.owner.store_action.toolTip())
        self.status.setText(self.owner.status.text())

    def closeEvent(self, event):
        if self.owner.save_preferences:
            self.owner.preferences.setValue("windows/"+self.key, self.saveGeometry())
        event.accept()

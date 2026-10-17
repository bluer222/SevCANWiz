"""Native Qt interactions against SevconCAN's CANopen-frame simulator."""

import csv
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtGui import QFont
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QDoubleSpinBox, QMessageBox, QPushButton, QToolBar
    from sevcanwiz.library import load_library
    load_library()
    from sevcanwiz.runtime import Runtime
    from sevcanwiz.desktop_state import DesktopState
    from sevcanwiz.desktop import MainWindow, configure_application, save_text
    from sevcanwiz.desktop_dialogs import AccessDialog, ConnectionDialog, ReviewDialog, MenuSearchDialog
    from sevcanwiz.desktop_models import ParameterModel
    from sevcanwiz.desktop_widgets import BitFieldsDialog
except ModuleNotFoundError as error:
    if error.name != "PySide6":
        raise
    QApplication = None


@unittest.skipUnless(QApplication, "Run in the PySide6 environment for native GUI tests")
class DesktopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)
        configure_application(cls.app)

    def wait_for(self, condition, timeout=12):
        deadline = time.monotonic()+timeout
        while not condition() and time.monotonic() < deadline:
            self.app.processEvents()
            QTest.qWait(20)
        self.assertTrue(condition(), f"Native operation timed out. Errors: {self.errors}")
        self.assertFalse(self.slot_errors, self.slot_errors)

    def setUp(self):
        self.errors, self.slot_errors = [], []
        self.excepthook = sys.excepthook
        sys.excepthook = lambda kind, error, tb: self.slot_errors.append(str(error))
        self.runtime = Runtime()
        self.runtime.call("connect", {"backend": "simulator"})
        self.state = DesktopState(self.runtime)
        self.state.set_catalog(self.runtime.call("catalog"))
        self.state.error.connect(self.errors.append)
        self.window = MainWindow(self.state, save_preferences=False)
        self.window.show()
        self.state.poll_live()
        self.wait_for(lambda: self.state.level == 0)
        self.assertEqual(set(self.window.pages), {"instruments"})
        self.window.navigate("pedals")
        self.wait_for(lambda: self.state.level == 0 and "2910:0E" in self.state.readings)

    def tearDown(self):
        self.state.drafts.clear()
        self.state.recording = False
        self.state.busy = False
        self.window.close()
        self.app.processEvents()
        self.window.deleteLater()
        self.app.processEvents()
        sys.excepthook = self.excepthook
        self.assertFalse(self.slot_errors, self.slot_errors)

    def login(self):
        self.state.command("login", {"password": "0x4BDF", "user": 0})
        self.wait_for(lambda: self.state.level == 4)

    def preop(self):
        self.state.command("preop")
        self.wait_for(lambda: self.state.live.get("state") == 127)

    def test_access_is_granted_not_requested_and_every_system_is_visible(self):
        self.assertIn("Logged out / level 0", self.window.session_strip.text())
        curve = self.window.pages["pedals"].widget(0)
        self.assertFalse(curve.plot.editable)
        self.assertIn("Engineering / level 4 required", curve.access_note.text())
        self.assertIn("Locked", curve.access_note.text())
        self.assertFalse(hasattr(self.window, "navigator"))
        self.assertEqual(len(self.window.window_actions), 11)
        self.assertEqual([a.text() for a in self.window.menuBar().actions()],
                         ["&File", "&Controller", "&Configuration", "&View", "&Windows", "&Help"])
        self.login()
        self.assertIn("Engineering / level 4", self.window.session_strip.text())
        self.assertTrue(curve.plot.editable)
        dialog = AccessDialog(self.state, self.window)
        self.assertEqual(dialog.table.item(4, 2).text(), "Available")
        self.assertEqual(dialog.table.item(5, 2).text(), "Locked")
        self.assertFalse(self.window.store_action.toolTip().find("Engineering") < 0)

    def test_numeric_curve_edit_is_a_draft_and_review_applies_readback(self):
        self.login()
        self.preop()
        page = self.window.pages["pedals"].widget(0)
        editor = page.findChild(QDoubleSpinBox, "point_1_y")
        before = self.state.readings["2910:0E"]["bytes"]
        editor.setFocus()
        editor.selectAll()
        QTest.keyClicks(editor, "60")
        QTest.keyClick(editor, Qt.Key.Key_Return)
        self.wait_for(lambda: "2910:0E" in self.state.drafts)
        self.assertAlmostEqual(self.state.drafts["2910:0E"]["value"], .6)
        reading = self.runtime.call("live", {"keys": ["2910:0E"]})
        self.assertEqual(next(r["bytes"] for r in reading["rows"] if r["key"] == "2910:0E"), before)
        self.window.navigate("battery")
        self.window.navigate("pedals")
        self.assertIn("2910:0E", self.state.drafts)
        self.assertEqual(self.window.draft_table.rowCount(), len(self.state.drafts))
        dialog = ReviewDialog(self.state, self.window)
        dialog.show()
        self.assertTrue(dialog.apply_button.isEnabled())
        QTest.mouseClick(dialog.apply_button, Qt.MouseButton.LeftButton)
        self.wait_for(lambda: not self.state.busy and not self.state.drafts)
        self.assertAlmostEqual(self.state.value("2910:0E"), .6, places=3)
        self.assertTrue(self.state.connection["unsaved"])
        self.state.command("store")
        self.wait_for(lambda: not self.state.connection["unsaved"])
        self.assertFalse(self.errors)

    def test_drag_and_keyboard_use_the_visual_curve(self):
        self.login()
        page = self.window.pages["pedals"].widget(0)
        plot = page.plot
        point = plot.coordinate(*plot.points[1]).toPoint()
        target = plot.coordinate(50, 58).toPoint()
        QTest.mousePress(plot, Qt.MouseButton.LeftButton, pos=point)
        QTest.mouseMove(plot, target, 40)
        QTest.mouseRelease(plot, Qt.MouseButton.LeftButton, pos=target)
        self.assertIn("2910:0E", self.state.drafts)
        self.assertAlmostEqual(self.state.value("2910:0E"), .58, delta=.015)
        plot.setFocus()
        prior = self.state.value("2910:0E")
        QTest.keyClick(plot, Qt.Key.Key_Up)
        self.assertGreater(self.state.value("2910:0E"), prior)
        page.revert()
        self.assertFalse(self.state.drafts)

    def test_parameter_table_roles_filters_and_edit_permissions(self):
        model = ParameterModel(self.state)
        model.search = "throttle"
        model.access = "locked"
        model.filter()
        self.assertTrue(model.rows)
        for row in range(model.rowCount()):
            self.assertEqual(model.index(row, 4).data(), "Locked")
            self.assertFalse(model.flags(model.index(row, 2)) & Qt.ItemFlag.ItemIsEditable)
            self.assertEqual(model.index(row, 2).data(Qt.ItemDataRole.ForegroundRole).name(), "#84909a")
        bit_key = next(s["key"] for s in self.state.settings.values() if s["editable"] and s["bits"] and s["level"])
        bit_dialog = BitFieldsDialog(self.state, bit_key, self.window)
        self.assertTrue(all(not control.isEnabled() for field, control in bit_dialog.controls))
        self.login()
        model.access = "available"
        model.filter()
        row = next(i for i, s in enumerate(model.rows) if s["key"] == "2910:0E")
        self.assertTrue(model.setData(model.index(row, 2), .57, Qt.ItemDataRole.EditRole))
        self.assertIn("2910:0E", self.state.drafts)
        self.assertIsNotNone(model.index(row, 2).data(Qt.ItemDataRole.BackgroundRole))

    def test_help_has_full_content_and_technical_fields_are_optional(self):
        self.window.show_help("2910:0E")
        text = self.window.help_browser.toPlainText()
        for section in ("What this does", "When to change it", "Interactions", "Accepted range", "Your access"):
            self.assertIn(section, text)
        self.assertNotIn("Technical reference", text)
        self.window.technical.setChecked(True)
        self.assertIn("Technical reference", self.window.help_browser.toPlainText())
        self.assertIn("2910:0E", self.window.help_browser.toPlainText())
        connection = ConnectionDialog(self.state, self.window)
        self.assertEqual(connection.backend.count(), 6)

    def test_review_stays_locked_after_logout(self):
        self.login()
        self.preop()
        self.assertTrue(self.state.stage("2910:0E", .6))
        self.state.command("logout")
        self.wait_for(lambda: self.state.level == 0)
        dialog = ReviewDialog(self.state, self.window)
        self.assertFalse(dialog.apply_button.isEnabled())
        self.assertIn("higher access", dialog.requirements.text())
        self.assertIn("2910:0E", self.state.drafts)

    def test_failed_preflight_keeps_drafts_and_does_not_mark_written(self):
        self.login()
        self.state.command("operational")
        self.wait_for(lambda: self.state.live.get("state") == 5)
        self.assertTrue(self.state.stage("2910:0E", .6))
        self.state.apply()
        self.wait_for(lambda: not self.state.busy)
        self.assertTrue(self.errors)
        self.assertIn("2910:0E", self.state.drafts)
        self.assertFalse(self.state.connection["unsaved"])
        self.assertTrue(self.window.notice.isVisible())

    def test_pd_mapping_uses_native_fields_and_dedicated_apply(self):
        self.login()
        self.preop()
        self.window.navigate("can")
        page = self.window.pages["can"]
        self.wait_for(lambda: page.config is not None)
        page.identifier.setValue(0x1B5)
        page.transmission.setCurrentIndex(page.transmission.findData(255))
        page.event_timer.setValue(100)
        page.inhibit_time.setValue(10.5)
        page.signals = ["5100:01", "5100:02"]
        page.update_table()
        self.assertEqual(page.identifier.value(), 0x1B5)
        self.assertIn("32 / 64", page.payload_size.text())
        page.apply_pdo(confirmed=True)
        self.wait_for(lambda: not self.state.busy and page.config["cob_id"] & 0x7FF == 0x1B5)
        self.assertEqual(page.config["mapping"], [[0x5100, 1, 16], [0x5100, 2, 16]])
        self.assertTrue(self.state.connection["unsaved"])
        self.assertEqual(page.config["event_timer"], 100)
        self.assertEqual(page.config["inhibit_time"], 105)
        page.config["cob_id"] |= 0x20000000
        page.sync_access()
        self.assertFalse(page.apply_button.isEnabled())
        self.assertFalse(self.errors)

    def test_backup_atomic_file_compare_and_selected_restore(self):
        self.login()
        self.preop()
        initial = self.state.value("2910:0E")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"configuration.json"
            finished = []
            self.window.export_backup_to(path, finished.append)
            self.wait_for(lambda: bool(finished), timeout=25)
            snapshot = path.read_text()
            self.assertTrue(json.loads(snapshot))
            self.assertFalse(self.state.connection["unsaved"])
            self.state.stage("2910:0E", .6)
            self.state.apply()
            self.wait_for(lambda: not self.state.busy)
            compared = []
            self.window.compare_snapshot(snapshot, compared.append)
            self.wait_for(lambda: bool(compared), timeout=25)
            plan = compared[0]
            self.assertEqual([c["key"] for c in plan["changes"]], ["2910:0E"])
            self.window.stage_restore(plan["changes"])
            self.assertIn("2910:0E", self.state.drafts)
            self.assertAlmostEqual(self.state.drafts["2910:0E"]["value"], initial, places=3)
            save_text(path, snapshot)
            self.assertEqual(path.read_text(), snapshot)
        self.assertFalse(self.errors)

    def test_csv_has_units_timestamp_and_blanks_for_failed_samples(self):
        self.state.samples = [{"time": 1735689600.125, "values": {"5100:01": 48.5, "5100:02": 3.2}},
                              {"time": 1735689601.125, "values": {"5100:01": 48.6}}]
        rows = list(csv.reader(io.StringIO(self.window.csv_text())))
        self.assertIn("[V]", rows[0][1])
        self.assertEqual(rows[1][0], "2025-01-01T00:00:00.125Z")
        self.assertEqual(rows[2][2], "")
        self.window.toggle_recording()
        self.state.poll_live()
        self.wait_for(lambda: bool(self.state.samples))
        self.window.toggle_recording()
        self.assertFalse(self.state.recording)

    def test_search_and_all_screens_remain_reachable(self):
        self.window.find_parameter()
        self.window.pages["all"].search.setText("throttle")
        self.window.pages["all"].update_filter()
        self.assertEqual(self.window.active_page, "instruments")
        self.assertGreater(self.window.pages["all"].model.rowCount(), 5)
        for key, title in self.window.SYSTEMS:
            opened = self.window.navigate(key)
            self.app.processEvents()
            self.assertFalse(opened.grab().isNull())
            if key != "instruments":
                self.assertIn(title, opened.windowTitle())
                self.assertTrue(opened.isWindow())
        self.window.help_dock.hide()
        self.window.restore_layout()
        self.assertTrue(self.window.help_dock.isVisible())

    def test_toolbar_opens_independent_reusable_windows_without_replacing_monitor(self):
        monitor = self.window.workspaces.currentWidget()
        self.window.window_actions["motor"].trigger()
        motor = self.window.windows["motor"]
        self.assertTrue(motor.isVisible())
        self.assertIs(self.window.workspaces.currentWidget(), monitor)
        self.assertTrue(self.window.windows["pedals"].isVisible())
        motor.close()
        self.assertFalse(motor.isVisible())
        self.window.window_actions["motor"].trigger()
        self.assertIs(self.window.windows["motor"], motor)
        self.assertTrue(motor.isVisible())
        self.assertFalse(self.window.window_actions["motor"].icon().isNull())

    def test_search_menus_finds_tpdo_timing_and_executes_window_action(self):
        dialog = MenuSearchDialog(self.window.menu_entries(), self.window)
        dialog.search.setText("event timer")
        self.assertEqual(dialog.results.count(), 1)
        self.assertIn("CAN and network", dialog.results.item(0).text())
        dialog.execute()
        self.assertTrue(self.window.windows["can"].isVisible())
        dialog = MenuSearchDialog(self.window.menu_entries(), self.window)
        dialog.search.setText("save to controller")
        self.assertFalse(dialog.open_button.isEnabled())
        self.assertIn("unavailable", dialog.details.text())

    def test_all_question_marks_deliver_their_intended_help_entry(self):
        for button in self.window.pages["instruments"].findChildren(QPushButton, "contextHelp"):
            self.window.help_key = None
            button.click()
            self.assertIsInstance(self.window.help_key, str)
        for key, title in self.window.SYSTEMS:
            if key == "instruments":
                continue
            feature = self.window.navigate(key)
            for button in feature.page.findChildren(QPushButton, "contextHelp"):
                feature.help_key = None
                button.click()
                self.assertIsInstance(feature.help_key, str, (key, button.accessibleName()))
                self.assertTrue(feature.help_browser.toPlainText())
        self.assertFalse(self.slot_errors)
        bit_key = next(s["key"] for s in self.state.settings.values() if s["editable"] and s["bits"])
        bit_dialog = BitFieldsDialog(self.state, bit_key, self.window)
        with patch("sevcanwiz.desktop_dialogs.ExplanationDialog.exec", return_value=0) as execute:
            for button in bit_dialog.findChildren(QPushButton, "contextHelp"):
                button.click()
            self.assertTrue(execute.called)
        self.assertFalse(self.slot_errors)
        self.assertFalse(self.errors)

    def test_startup_is_async_and_reconnect_clears_old_controller_drafts(self):
        self.login()
        self.state.stage("2910:0E", .6)
        old_session = self.state.connection["session"]
        self.state.connect_controller({"backend": "simulator"})
        self.wait_for(lambda: not self.state.busy and self.state.level == 0 and self.state.connection["session"] != old_session)
        self.assertFalse(self.state.drafts)
        self.state.close()
        self.state.close()

    def test_z_capture_native_screens(self):
        self.login()
        self.preop()
        self.state.stage("2910:0E", .6)
        feature = self.window.windows["pedals"]
        feature.show_help("2910:0E")
        directory = Path(__file__).resolve().parents[1]/"docs"/"screenshots"
        directory.mkdir(parents=True, exist_ok=True)
        self.app.processEvents()
        self.assertTrue(feature.grab().save(str(directory/"pedals.png")))
        access = AccessDialog(self.state, self.window)
        access.show()
        self.app.processEvents()
        self.assertTrue(access.grab().save(str(directory/"access.png")))
        access.close()
        self.window.navigate("instruments")
        for _ in range(12):
            self.state.poll_live()
            self.app.processEvents()
            QTest.qWait(60)
        self.app.processEvents()
        self.assertTrue(self.window.grab().save(str(directory/"instruments.png")))
        can = self.window.navigate("can")
        self.wait_for(lambda: can.page.config is not None)
        can.page.transmission.setCurrentIndex(can.page.transmission.findData(255))
        can.page.event_timer.setValue(100)
        can.page.inhibit_time.setValue(10)
        can.show_help("pdo-event-timer")
        self.app.processEvents()
        self.assertTrue(can.grab().save(str(directory/"tpdo.png")))


if __name__ == "__main__":
    unittest.main()

import asyncio
import json
import unittest
from unittest.mock import patch

from sevcanwiz.library import load_library
load_library()
from sevcanwiz.service import ControllerService
from sevcon_can.configuration import ConfigurationSnapshot, export_configuration
from sevcanwiz.catalog import build_catalog


class ControllerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.service = ControllerService()
        await self.service.connect({"backend": "simulator"})
        self.dev = self.service.device

    async def asyncTearDown(self):
        await self.service.close()

    async def login(self):
        await self.service.command({"action": "login", "password": "0x4BDF", "session": self.service.session})

    async def change(self, key, value):
        reading = await self.service.reading(self.dev, key)
        return {"key": key, "value": value, "expected": reading["bytes"]}

    def progress(self):
        return {"rows": [], "completed": 0, "total": 0}

    async def apply(self, changes, progress=None):
        return await self.service.apply({"session": self.service.session, "changes": changes}, progress or self.progress())

    async def test_complete_catalog_and_help(self):
        catalog = build_catalog(self.service.od)
        self.assertEqual(catalog["count"], 1340)
        self.assertEqual(len(catalog["curves"]), 12)
        for setting in catalog["settings"]:
            for section in ("what", "adjust", "interactions", "access", "source"):
                self.assertGreater(len(setting["help"][section]), 20, setting["key"])
        throttle = next(c for c in catalog["curves"] if c["id"] == "throttle")
        self.assertEqual(throttle["points"][0], {"x": "2910:0B", "y": "2910:0C"})
        torque = next(c for c in catalog["curves"] if c["id"] == "map-4611")
        self.assertEqual(torque["points"][0], {"x": "4611:02", "y": "4611:01"})

    async def test_read_and_live_do_not_write_parameters(self):
        before = await self.dev.read_raw(0x2910, 3)
        progress = self.progress()
        await self.service.scan(["2910:03", "5100:01"], progress)
        live = await self.service.live([])
        self.assertIsInstance(live["rows"][0]["value"], float)
        self.assertEqual(await self.dev.read_raw(0x2910, 3), before)
        self.assertFalse(self.service.unsaved)

    async def test_signed_dictionary_limits_and_simulated_current(self):
        setting = next(s for s in build_catalog(self.service.od)["settings"] if s["key"] == "5100:02")
        self.assertEqual(setting["low"], -2048)
        self.assertEqual(setting["high"], 2047.9375)
        self.service.set_sim("5100:02", -12.5)
        self.assertEqual((await self.service.reading(self.dev, "5100:02"))["value"], -12.5)
        live = await self.service.live([])
        current = next(r for r in live["rows"] if r["key"] == "5100:02")
        self.assertGreaterEqual(current["value"], 12)
        self.assertLessEqual(current["value"], 36)

    async def test_apply_quantizes_and_verifies_without_saving(self):
        await self.login()
        change = await self.change("2910:03", 0.751)
        progress = self.progress()
        with patch.object(self.dev, "store") as store:
            await self.apply([change], progress)
            store.assert_not_called()
        self.assertEqual(progress["completed"], 1)
        self.assertEqual(progress["rows"][0]["value"], 0.75)
        self.assertTrue(self.service.unsaved)

    async def test_no_login_prevents_all_writes(self):
        change = await self.change("2910:03", 0.8)
        with self.assertRaisesRegex(Exception, "login level"):
            await self.apply([change])
        self.assertEqual((await self.service.reading(self.dev, change["key"]))["bytes"], change["expected"])

    async def test_store_checks_access_and_configuration_state(self):
        with self.assertRaisesRegex(Exception, "login level"):
            await self.service.command({"action": "store", "session": self.service.session})
        await self.login()
        await self.dev.goto_operational()
        with self.assertRaisesRegex(ValueError, "configuration state"):
            await self.service.command({"action": "store", "session": self.service.session})
        await self.dev.goto_preop()
        await self.service.command({"action": "store", "session": self.service.session})

    async def test_access_read_failure_does_not_reuse_cached_grant(self):
        await self.login()
        change = await self.change("2910:03", 0.8)
        read = self.dev.read_raw
        async def fail_access(index, sub):
            if (index, sub) == (0x5000, 1):
                raise OSError("injected permission read failure")
            return await read(index, sub)
        with patch.object(self.dev, "read_raw", fail_access):
            live = await self.service.live([])
            self.assertIsNone(live["level"])
            with self.assertRaisesRegex(OSError, "permission read failure"):
                await self.apply([change])
        self.assertEqual((await self.service.reading(self.dev, change["key"]))["bytes"], change["expected"])

    async def test_range_preflight_prevents_earlier_write(self):
        await self.login()
        first = await self.change("2910:03", 0.8)
        second = await self.change("2910:05", 100000)
        with self.assertRaises(Exception):
            await self.apply([first, second])
        self.assertEqual((await self.service.reading(self.dev, first["key"]))["bytes"], first["expected"])

    async def test_stale_read_prevents_all_writes(self):
        await self.login()
        change = await self.change("2910:03", 0.8)
        await self.dev.write(0x2910, 3, 0.9)
        with self.assertRaisesRegex(ValueError, "changed since"):
            await self.apply([change])
        self.assertNotEqual((await self.service.reading(self.dev, change["key"]))["value"], 0.8)

    async def test_apply_does_not_implicitly_enter_preop(self):
        await self.login()
        change = await self.change("2910:03", 0.8)
        await self.dev.goto_operational()
        with self.assertRaisesRegex(ValueError, "configuration state"):
            await self.apply([change])
        self.assertEqual(await self.dev.nmt_state(cached=False), 5)

    async def test_previous_session_is_rejected(self):
        await self.login()
        change = await self.change("2910:03", 0.8)
        with self.assertRaisesRegex(ValueError, "connection changed"):
            await self.service.apply({"session": "old", "changes": [change]}, self.progress())

    async def test_curve_order_and_selector_are_validated(self):
        await self.login()
        with self.assertRaisesRegex(ValueError, "must increase"):
            await self.apply([await self.change("2910:0B", 0.9)])
        await self.dev.write(0x2910, 2, "Linear")
        with self.assertRaisesRegex(ValueError, "User defined"):
            await self.apply([await self.change("2910:0C", 0.12)])
        await self.apply([await self.change("2910:0C", 0.12), await self.change("2910:02", "User Defd")])
        self.assertEqual((await self.dev.read(0x2910, 2)).raw, 0)

    async def test_pedal_output_must_not_decrease(self):
        await self.login()
        with self.assertRaisesRegex(ValueError, "must not decrease"):
            await self.apply([await self.change("2910:0C", 0.9)])

    async def test_battery_threshold_relationship_is_checked(self):
        await self.login()
        with self.assertRaisesRegex(ValueError, "wrong order"):
            await self.apply([await self.change("2C01:01", 65)])

    async def test_dedicated_network_objects_are_not_generic_settings(self):
        await self.login()
        with self.assertRaisesRegex(ValueError, "dedicated procedure"):
            await self.apply([await self.change("5900:01", 1)])

    async def test_partial_failure_reports_verified_rows(self):
        await self.login()
        first = await self.change("2910:03", 0.8)
        second = await self.change("2910:05", 4.4)
        write = self.dev.write_raw
        async def fail_second(index, sub, data):
            if (index, sub) == (0x2910, 5):
                raise OSError("injected bus failure")
            await write(index, sub, data)
        progress = self.progress()
        with patch.object(self.dev, "write_raw", fail_second):
            with self.assertRaisesRegex(ValueError, "after 1 verified changes"):
                await self.apply([first, second], progress)
        self.assertEqual(progress["failed_key"], second["key"])
        self.assertEqual(progress["rows"][0]["key"], first["key"])
        self.assertEqual((await self.service.reading(self.dev, second["key"]))["bytes"], second["expected"])

    async def test_readback_failure_is_not_reported_as_success(self):
        await self.login()
        change = await self.change("2910:03", 0.8)
        write = self.dev.write_raw
        async def ignore_write(index, sub, data):
            if (index, sub) != (0x2910, 3):
                await write(index, sub, data)
        progress = self.progress()
        with patch.object(self.dev, "write_raw", ignore_write):
            with self.assertRaisesRegex(ValueError, "Read-back"):
                await self.apply([change], progress)
        self.assertEqual(progress["completed"], 0)
        self.assertTrue(self.service.unsaved)

    async def test_backup_and_import_do_not_restore_implicitly(self):
        await self.login()
        snapshot = await export_configuration(self.dev, [(0x2910, 3), (0x2910, 5)])
        await self.dev.write(0x2910, 3, 0.9)
        progress = self.progress()
        result = await self.service.import_plan({"session": self.service.session, "text": snapshot.to_json()}, progress)
        self.assertEqual(len(result["changes"]), 1)
        self.assertEqual(result["changes"][0]["key"], "2910:03")
        self.assertAlmostEqual((await self.dev.read(0x2910, 3)).physical, 0.9, delta=0.004)
        snapshot.identity["serial"] += 1
        with self.assertRaisesRegex(Exception, "identity"):
            await self.service.import_plan({"session": self.service.session, "text": snapshot.to_json()}, self.progress())

    async def test_full_backup_round_trip_compares_only_changed_values(self):
        await self.login()
        exported = await self.service.backup(self.progress())
        await self.dev.write(0x2910, 3, 0.95)
        result = await self.service.import_plan({"session": self.service.session, "text": exported["snapshot"]}, self.progress())
        self.assertEqual([c["key"] for c in result["changes"]], ["2910:03"])

    async def test_pdo_config_uses_real_mapping_and_readback(self):
        await self.login()
        before = await self.service.pdo_read({"number": 1, "transmit": True})
        result = await self.service.pdo_apply({"session": self.service.session, "number": 1,
            "transmit": True, "identifier": 0x222, "transmission": 255, "enabled": True,
            "signals": ["5100:01", "5100:02"], "expected": before}, self.progress())
        self.assertTrue(result["enabled"])
        self.assertEqual(result["mapping"], [[0x5100, 1, 16], [0x5100, 2, 16]])
        with self.assertRaisesRegex(ValueError, "changed"):
            await self.service.pdo_apply({"session": self.service.session, "number": 1,
                "transmit": True, "identifier": 0x222, "transmission": 255, "enabled": True,
                "signals": ["5100:01"], "expected": before}, self.progress())

    async def test_tpdo_timing_is_written_while_disabled_and_verified(self):
        await self.login()
        before = await self.service.pdo_read({"number": 1, "transmit": True})
        writes = []
        original = self.dev.write_raw
        async def record(index, sub, wire):
            if index == 0x1800 and sub in (3, 5):
                cob_id = self.dev.variable(0x1800, 1).decode_raw(await self.dev.read_raw(0x1800, 1))
                writes.append((sub, bool(cob_id & 0x80000000)))
            return await original(index, sub, wire)
        with patch.object(self.dev, "write_raw", record):
            result = await self.service.pdo_apply({"session": self.service.session, "number": 1,
                "transmit": True, "identifier": 0x222, "transmission": 255, "enabled": True,
                "signals": ["5100:01", "5100:02"], "inhibit_time": 105, "event_timer": 100,
                "expected": before}, self.progress())
        self.assertEqual(writes, [(3, True), (5, True)])
        self.assertEqual(result["inhibit_time"], 105)
        self.assertEqual(result["event_timer"], 100)
        self.assertTrue(result["enabled"])
        self.assertTrue(self.service.unsaved)

    async def test_invalid_tpdo_timing_preflights_before_any_mapping_write(self):
        await self.login()
        before = await self.service.pdo_read({"number": 1, "transmit": True})
        payload = {"session": self.service.session, "number": 1, "transmit": True,
                   "identifier": 0x222, "transmission": 255, "enabled": True,
                   "signals": ["5100:01"], "inhibit_time": 50, "event_timer": 40000, "expected": before}
        with self.assertRaisesRegex(ValueError, "HighLimit"):
            await self.service.pdo_apply(payload, self.progress())
        self.assertEqual(await self.service.pdo_read({"number": 1, "transmit": True}), before)
        self.assertFalse(self.service.unsaved)
        await self.service.command({"session": self.service.session, "action": "logout"})
        payload["event_timer"] = 100
        with self.assertRaisesRegex(Exception, "login level"):
            await self.service.pdo_apply(payload, self.progress())
        self.assertEqual(await self.service.pdo_read({"number": 1, "transmit": True}), before)
        self.assertFalse(self.service.unsaved)

    async def test_faults_use_named_catalog_descriptions(self):
        self.service.simulator.inject_fault(0x4681)
        live = await self.service.live([])
        self.assertEqual(live["faults"][0]["fault_id"], 0x4681)
        if live["faults"][0]["info"]:
            self.assertIn("message", live["faults"][0]["info"])

    async def test_reconnect_resets_access_and_session(self):
        await self.login()
        old_session = self.service.session
        await self.service.connect({"backend": "simulator", "node": 33})
        self.assertNotEqual(old_session, self.service.session)
        self.assertEqual(await self.service.device.access_level(cached=False), 0)
        self.assertFalse(self.service.unsaved)


if __name__ == "__main__":
    unittest.main()

"""One controller session, serialized configuration writes, and background reads."""

import asyncio
import math
import time
import uuid
from collections import deque
from dataclasses import asdict
from pathlib import Path

from sevcon_can import AsyncSevconGen4, datatypes as dt
from sevcon_can.configuration import ConfigurationSnapshot, export_configuration, plan_configuration_restore
from sevcon_can.od import gen4_od, load_eds
from sevcon_can.simulator import create_pair
from sevcon_can.tables import GEN4_FAULTS
from .catalog import build_catalog, key_of, restricted, raw_bounds
from .helptext import TOPICS


def clean(value):
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    return value


def parse_key(key):
    if not isinstance(key, str) or len(key) != 7 or key[4] != ":":
        raise ValueError("Invalid setting identifier")
    index, sub = int(key[:4], 16), int(key[5:], 16)
    if not 0 <= index <= 0xFFFF or not 0 <= sub <= 0xFF:
        raise ValueError("Invalid setting identifier")
    return index, sub


def integer(value):
    if isinstance(value, bool):
        raise ValueError("Expected a number")
    if isinstance(value, str):
        return int(value, 0)
    if not isinstance(value, (int, float)) or not math.isfinite(value) or int(value) != value:
        raise ValueError("Expected a whole number")
    return int(value)


class ControllerService:
    def __init__(self, eds=None):
        self.od = load_eds(eds) if eds else gen4_od()
        self.device = None
        self.simulator = None
        self.session = None
        self.backend = None
        self.identity = None
        self.lock = asyncio.Lock()
        self.jobs = {}
        self.log = deque(maxlen=250)
        self.emcy_task = None
        self.sim_time = time.monotonic()
        self.unsaved = False

    def event(self, message, kind="info"):
        self.log.appendleft({"time": time.time(), "message": message, "kind": kind})

    def require_device(self, session=None):
        if self.device is None:
            raise ValueError("Connect to a controller first")
        if session is not None and session != self.session:
            raise ValueError("The controller connection changed. Re-read settings before applying.")
        return self.device

    async def close(self):
        for job in self.jobs.values():
            task = job.get("task")
            if task and not task.done():
                if job["kind"] not in ("Apply settings", "Apply PDO"):
                    task.cancel()
        tasks = [j["task"] for j in self.jobs.values() if j.get("task")]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self.jobs.clear()
        if self.emcy_task:
            self.emcy_task.cancel()
            await asyncio.gather(self.emcy_task, return_exceptions=True)
            self.emcy_task = None
        async with self.lock:
            if self.device:
                await self.device.close()
            if self.simulator:
                await self.simulator.close()
                await self.simulator.network.close()
            self.device = self.simulator = None
            self.session = None
            self.unsaved = False

    async def connect(self, options):
        node = integer(options.get("node", 32))
        if not 1 <= node <= 127:
            raise ValueError("Controller node must be between 1 and 127")
        backend = options.get("backend", "simulator")
        if backend not in ("simulator", "socketcan", "gs_usb", "slcan", "pcan", "kvaser"):
            raise ValueError("Unsupported adapter backend")
        od = load_eds(Path(options["eds"]).expanduser()) if options.get("eds") else gen4_od()
        await self.close()
        async with self.lock:
            dev = sim = None
            try:
                if backend == "simulator":
                    dev, sim = create_pair(node_id=node, od=od)
                    await dev.start()
                    await sim.start()
                elif backend == "socketcan":
                    channel = str(options.get("channel", "can0"))
                    dev = AsyncSevconGen4.from_socketcan(channel, node, od=od, sdo_timeout=0.6)
                    await dev.start()
                else:
                    bitrate = integer(options.get("bitrate", 1000000))
                    if bitrate not in (10000, 20000, 50000, 100000, 125000, 250000, 500000, 800000, 1000000):
                        raise ValueError("Select a supported classic CAN bitrate")
                    kwargs = {"interface": backend, "bitrate": bitrate,
                              "channel": options.get("channel", "can0")}
                    if backend == "gs_usb":
                        kwargs.update(channel=integer(options.get("usb_index", 0)), index=integer(options.get("usb_index", 0)))
                    if backend == "slcan":
                        kwargs["tty_baudrate"] = integer(options.get("serial_baudrate", 115200))
                    dev = AsyncSevconGen4.from_python_can(node, od=od, sdo_timeout=0.6, **kwargs)
                    await dev.start()
                identity = await dev.validate_identity()
                if not identity.get("identity") or identity.get("missing"):
                    raise ValueError("The controller did not return a complete identity. Check adapter, node, bitrate, and power.")
            except Exception:
                if dev:
                    await dev.close()
                if sim:
                    await sim.close()
                    await sim.network.close()
                raise
            self.device, self.simulator, self.od = dev, sim, od
            self.identity = identity
            self.backend = backend
            self.session = uuid.uuid4().hex
            self.sim_time = time.monotonic()
            if sim:
                self.seed_simulation()
            self.emcy_task = asyncio.create_task(self.consume_emcy(dev))
            self.event(f"Connected to {'simulation' if sim else backend}, node {node}")
            return self.connection_info()

    def connection_info(self):
        return {"connected": self.device is not None, "session": self.session,
                "backend": self.backend, "simulated": self.simulator is not None,
                "node": self.device.node_id if self.device else None,
                "identity": clean(self.identity), "unsaved": self.unsaved}

    async def consume_emcy(self, dev):
        async for message in dev.emcy_notifications():
            self.event(f"Controller emergency: {message}", "error")

    def set_sim(self, key, physical):
        try:
            var = self.device.variable(parse_key(key))
            raw = var.from_physical(physical)
            if var.data_type in dt.INTEGER_TYPES:
                raw = int(round(raw))
                low, high = raw_bounds(var)
                if low is not None:
                    raw = max(low, raw)
                if high is not None:
                    raw = min(high, raw)
            self.simulator._store[var.key] = var.encode_raw(raw)
        except (ValueError, KeyError, TypeError):
            pass

    def seed_simulation(self):
        defaults = {
            "2910:02": 0, "2911:03": 0,
            "2910:03": 0.7, "2910:04": 0, "2910:05": 4.3, "2910:06": 1,
            "2910:07": 4.3, "2910:08": 0, "2910:09": 0.7, "2910:0A": 1,
            "2911:04": 0.8, "2911:05": 0, "2911:06": 4.2, "2911:07": 1,
            "2C00:00": 48, "2C01:01": 57, "2C01:02": 60,
            "2C02:01": 38, "2C02:02": 32, "4621:03": 120,
            "2920:01": 80, "2920:05": 4500, "2920:06": 2000,
        }
        for key, value in defaults.items():
            self.set_sim(key, value)
        catalog = build_catalog(self.od)
        for curve in catalog["curves"]:
            for i, point in enumerate(curve["points"]):
                f = (i+1)/(len(curve["points"])+1)
                if curve["percent"]:
                    x, y = f, f**1.6
                elif curve["id"] == "map-2C31":
                    x, y = 35+i*5, i*25
                elif curve["id"] in ("map-4611", "map-4615"):
                    x, y = i*750, 70 if i < 4 else 70-(i-3)*8
                elif curve["id"] == "map-461E":
                    x, y = 40+i*16, max(0, 1-i*0.2)
                elif curve["id"] == "map-4612":
                    x, y = 24+i*6, min(1, (i+1)/4)
                elif curve["id"] == "map-461F":
                    x, y = 300+i*600, 110-i*18
                else:
                    x, y = i*20, 1-i*0.2
                self.set_sim(point["x"], x)
                self.set_sim(point["y"], y)

    def animate_simulation(self):
        if not self.simulator:
            return
        t = time.monotonic()-self.sim_time
        for key, value in {
            "5100:01": 50.5+0.6*math.sin(t/11),
            "5100:02": 24+12*math.sin(t/4),
            "5100:03": 50.3+0.5*math.sin(t/11),
            "5100:04": 34+2*math.sin(t/18),
            "606C:00": 1800+350*math.sin(t/7),
            "6077:00": 22+8*math.sin(t/4),
            "6078:00": 36+15*math.sin(t/4),
            "2721:00": 22+4*math.sin(t/7),
            "2790:01": 76,
            "2220:00": 1.8+0.4*math.sin(t/7),
            "2620:00": 0.3+0.1*math.sin(t/7),
        }.items():
            self.set_sim(key, value)

    async def reading(self, dev, key):
        var = dev.variable(parse_key(key))
        if not var.readable:
            raise ValueError(f"{var.path} is write only")
        wire = await dev.read_raw(var.index, var.subindex)
        raw = var.decode_raw(wire)
        return {"key": key, "value": clean(var.to_physical(raw)),
                "raw": clean(raw), "bytes": wire.hex(), "label": clean(var.describe(raw)),
                "time": time.time()}

    async def refresh_access(self, dev):
        level = await dev.access_level(cached=False)
        if not 0 <= level <= 5:
            raise ValueError("Controller returned an unknown access level")
        return level

    def start_job(self, kind, coroutine):
        if sum(not j["task"].done() for j in self.jobs.values()) >= 3:
            raise ValueError("Wait for a current operation to finish or cancel a scan")
        id = uuid.uuid4().hex
        job = {"id": id, "kind": kind, "state": "running", "completed": 0,
               "total": 0, "rows": [], "result": None, "error": None}
        self.jobs[id] = job

        async def run():
            try:
                job["result"] = await coroutine(job)
                job["state"] = "done"
            except asyncio.CancelledError:
                job["state"] = "cancelled"
            except Exception as error:
                job["state"] = "failed"
                job["error"] = str(error)
                self.event(f"{kind}: {error}", "error")
        job["task"] = asyncio.create_task(run())
        # Completed job payloads are bounded for a long-lived workshop session.
        for old_id in list(self.jobs)[:-12]:
            if self.jobs[old_id]["task"].done():
                del self.jobs[old_id]
        return {"job": id}

    async def scan(self, keys, job):
        dev = self.require_device()
        session = self.session
        if not isinstance(keys, list) or len(keys) > 2000:
            raise ValueError("Invalid setting selection")
        for key in keys:
            dev.variable(parse_key(key))
        job["total"] = len(keys)
        for key in keys:
            async with self.lock:
                self.require_device(session)
                try:
                    row = await self.reading(dev, key)
                except Exception as error:
                    row = {"key": key, "error": str(error)}
            job["rows"].append(row)
            job["completed"] += 1
            await asyncio.sleep(0)
        return {"count": len(keys)}

    async def live(self, extra):
        dev = self.require_device()
        if not isinstance(extra, list) or len(extra) > 8:
            raise ValueError("Choose up to eight extra live signals")
        base = ["5100:01", "5100:02", "5100:04", "606C:00", "6077:00", "2790:01"]
        rows = []
        async with self.lock:
            self.animate_simulation()
            for key in dict.fromkeys(base+extra):
                try:
                    rows.append(await self.reading(dev, key))
                except Exception as error:
                    rows.append({"key": key, "error": str(error)})
            try:
                state = await dev.nmt_state(cached=False)
                level = await self.refresh_access(dev)
                drive = asdict(await dev.status())
                faults = [asdict(f) for f in await dev.active_faults()]
                # FaultInfo is a named tuple and needs named fields for the UI.
                for fault in faults:
                    info = GEN4_FAULTS.get(fault["fault_id"])
                    fault["info"] = info._asdict() if info else None
                error = None
            except Exception as failure:
                state = level = drive = faults = None
                error = str(failure)
        return {**self.connection_info(), "rows": rows, "state": state,
                "level": level, "drive": clean(drive), "faults": clean(faults),
                "error": error, "log": list(self.log)}

    async def validate_curves(self, dev, proposed):
        touched = set(proposed)
        for curve in build_catalog(self.od)["curves"]:
            keys = [p[axis] for p in curve["points"] for axis in ("x", "y")]
            if not touched.intersection(keys):
                continue
            vals = {}
            for key in keys:
                var = dev.variable(parse_key(key))
                vals[key] = var.to_physical(proposed[key][1]) if key in proposed else (await dev.read(var.key)).physical
            xs = [vals[p["x"]] for p in curve["points"]]
            ys = [vals[p["y"]] for p in curve["points"]]
            if any(b <= a for a, b in zip(xs, xs[1:])):
                raise ValueError(f"{curve['name']}: input points must increase")
            if curve["percent"]:
                if not 0 < xs[0] or not xs[-1] < 1 or any(not 0 <= y <= 1 for y in ys):
                    raise ValueError(f"{curve['name']}: interior inputs must be between 0% and 100%; output must be 0% to 100%")
                if any(b < a for a, b in zip(ys, ys[1:])):
                    raise ValueError(f"{curve['name']}: pedal output must not decrease")
                selector = curve["selector"]
                choice = proposed[selector][1] if selector in proposed else (await dev.read(parse_key(selector))).raw
                if choice != 0:
                    raise ValueError(f"{curve['name']}: select User defined to apply this curve")
        # Cross-field checks use live values when only one side is edited.
        for index, first, second, relation in [(0x2C01, 1, 2, "lt"), (0x2C02, 2, 1, "lt")]:
            keys = [f"{index:04X}:{s:02X}" for s in (first, second)]
            if touched.intersection(keys):
                vals = [proposed[k][1] if k in proposed else (await dev.read(parse_key(k))).raw for k in keys]
                if vals[0] >= vals[1]:
                    raise ValueError("Battery protection limiting and cutback thresholds are in the wrong order")
        if "2915:02" in proposed and proposed["2915:02"][1] == 0:
            raise ValueError("The gear-ratio denominator cannot be zero")

    async def apply(self, payload, job):
        if not payload.get("session"):
            raise ValueError("The controller session is required")
        dev = self.require_device(payload.get("session"))
        changes = payload.get("changes")
        if not isinstance(changes, list) or not 1 <= len(changes) <= 1000:
            raise ValueError("Select between one and 1000 draft settings")
        job["total"] = len(changes)
        proposed = {}
        async with self.lock:
            if await dev.nmt_state(cached=False) != 127:
                raise ValueError("Enter configuration state before applying settings")
            await self.refresh_access(dev)
            for change in changes:
                key = change["key"]
                if key in proposed:
                    raise ValueError("Duplicate draft setting")
                var = dev.variable(parse_key(key))
                if restricted(var) or not var.readable or not var.writable:
                    raise ValueError(f"{var.path} needs its dedicated procedure or is read only")
                value = change["value"]
                if isinstance(value, float) and not math.isfinite(value):
                    raise ValueError("Setting values must be finite")
                raw = dev._coerce_write(var, value)
                wire = var.encode_raw(raw)
                await dev._check_writable(var, raw)
                before = await dev.read_raw(var.index, var.subindex)
                if not isinstance(change.get("expected"), str) or before.hex() != change["expected"]:
                    raise ValueError(f"{var.path} changed since it was read. Refresh it before applying.")
                proposed[key] = (var, raw, wire, before)
            await self.validate_curves(dev, proposed)
            for key, (var, raw, wire, before) in proposed.items():
                try:
                    if await dev.nmt_state(cached=False) != 127:
                        raise ValueError("Controller left configuration state")
                    await dev._check_writable(var, raw)
                    if await dev.read_raw(var.index, var.subindex) != before:
                        raise ValueError("Value changed after preflight")
                    self.unsaved = True
                    await dev.write_raw(var.index, var.subindex, wire)
                    row = await self.reading(dev, key)
                    if row["bytes"] != wire.hex():
                        raise ValueError("Read-back does not match the written value")
                    job["rows"].append(row)
                    job["completed"] += 1
                    self.event(f"Applied {var.path}: {row['value']} {var.units or ''}")
                except Exception as error:
                    job["failed_key"] = key
                    raise ValueError(f"Stopped at {var.path} after {job['completed']} verified changes. The failed setting may have been written. {error}") from error
        return {"verified": job["completed"], "unsaved": self.unsaved}

    async def backup(self, job):
        dev = self.require_device()
        session = self.session
        # Export in small units so live polling and cancellation remain responsive.
        async with self.lock:
            snapshot = await export_configuration(dev, [])
        variables = [v for v in dev.od.variables() if v.eeprom and v.readable]
        job["total"] = len(variables)
        for var in variables:
            async with self.lock:
                self.require_device(session)
                try:
                    snapshot.values[key_of(var)] = (await dev.read_raw(var.index, var.subindex)).hex()
                except Exception as error:
                    snapshot.errors[key_of(var)] = str(error)
            job["completed"] += 1
            await asyncio.sleep(0)
        self.event(f"Exported backup: {len(snapshot.values)} values, {len(snapshot.errors)} read errors")
        return {"snapshot": snapshot.to_json(), "errors": len(snapshot.errors)}

    async def import_plan(self, payload, job):
        if not payload.get("session"):
            raise ValueError("The controller session is required")
        dev = self.require_device(payload.get("session"))
        snapshot = ConfigurationSnapshot.from_json(payload["text"])
        keys = []
        skipped = []
        for key in snapshot.values:
            try:
                var = dev.variable(parse_key(key))
                if var.eeprom and var.readable and var.writable and not restricted(var) and var.index >= 0x2000 and key not in snapshot.errors:
                    keys.append(var.key)
                else:
                    skipped.append(key)
            except Exception:
                skipped.append(key)
        session = self.session
        async with self.lock:
            await self.refresh_access(dev)
            await plan_configuration_restore(dev, snapshot, [])
        job["total"] = len(keys)
        changed = []
        read_errors = []
        for key in keys:
            async with self.lock:
                self.require_device(session)
                try:
                    current = await dev.read_raw(*key)
                    stored = bytes.fromhex(snapshot.values[f"{key[0]:04X}:{key[1]:02X}"])
                    if current != stored:
                        changed.append(key)
                except Exception as error:
                    read_errors.append({"key": f"{key[0]:04X}:{key[1]:02X}", "error": str(error)})
            job["completed"] += 1
            await asyncio.sleep(0)
        async with self.lock:
            self.require_device(session)
            await self.refresh_access(dev)
            # Unchanged records need no restore and may contain firmware defaults
            # outside declared limits. Validate only bytes that would be changed.
            plan = await plan_configuration_restore(dev, snapshot, changed)
        result = []
        for change in plan:
            var = dev.variable((change.index, change.subindex))
            result.append({"key": key_of(var), "name": var.path,
                           "value": clean(var.to_physical(var.decode_raw(change.after))),
                           "before": clean(var.to_physical(var.decode_raw(change.before))),
                           "expected": change.before.hex()})
        return {"changes": result, "skipped": len(skipped), "errors": len(snapshot.errors)+len(read_errors), "read_errors": read_errors}

    async def pdo_read(self, payload):
        dev = self.require_device()
        async with self.lock:
            return clean(await dev.read_pdo_configuration(bool(payload.get("transmit", True)), integer(payload.get("number", 1))))

    async def pdo_apply(self, payload, job):
        if not payload.get("session"):
            raise ValueError("The controller session is required")
        dev = self.require_device(payload.get("session"))
        number = integer(payload["number"])
        transmit = payload["transmit"]
        if type(transmit) is not bool or type(payload.get("enabled")) is not bool:
            raise ValueError("Invalid PDO direction or enable state")
        identifier = integer(payload["identifier"])
        if not 1 <= identifier <= 0x7FF:
            raise ValueError("This editor requires a standard CAN identifier from 1 to 2047")
        mapping = []
        for key in payload["signals"]:
            var = dev.variable(parse_key(key))
            mapping.append((*var.key, dt.bit_length(var.data_type)))
        if payload["enabled"] and not mapping:
            raise ValueError("An enabled PDO needs at least one mapped signal")
        async with self.lock:
            before = await dev.read_pdo_configuration(transmit, number)
            if clean(before) != payload.get("expected"):
                raise ValueError("PDO configuration changed. Reload it before applying.")
            if await dev.nmt_state(cached=False) != 127:
                raise ValueError("Enter configuration state before applying PDO settings")
            await self.refresh_access(dev)
            timing = {field: integer(payload[field]) for field in ("inhibit_time", "event_timer") if field in payload}
            for field, raw in timing.items():
                if not transmit:
                    raise ValueError("Transmit timing is only supported for TPDOs")
                var = dev.variable(0x1800+number-1, 3 if field == "inhibit_time" else 5)
                var.check_range(raw)
                await dev._check_writable(var, raw)
            selected = (before["cob_id"] & 0x40000000) | identifier
            try:
                result = await dev.configure_pdo(transmit, number, mapping, cob_id=selected,
                    transmission_type=integer(payload["transmission"]), enabled=payload["enabled"], **timing)
            except Exception:
                self.unsaved = True
                raise
            self.unsaved = True
            if (result["mapping"] != mapping or result["enabled"] != payload["enabled"] or
                result["transmission_type"] != integer(payload["transmission"]) or result["cob_id"] & 0x7FF != identifier):
                raise ValueError("PDO read-back differs from the requested configuration")
            if any(result[field] != raw for field, raw in timing.items()):
                raise ValueError("PDO timing read-back differs from the requested configuration")
            self.event(f"Applied {'transmit' if transmit else 'receive'} PDO {number}")
            return clean(result)

    async def command(self, payload):
        if not payload.get("session"):
            raise ValueError("The controller session is required")
        dev = self.require_device(payload.get("session"))
        action = payload["action"]
        async with self.lock:
            if action == "login":
                result = await dev.login(integer(payload["password"]), integer(payload.get("user", 0)))
                self.event(f"Controller granted access level {result}")
            elif action == "logout":
                result = await dev.logout()
                self.event("Logged out of controller")
            elif action == "preop":
                result = await dev.goto_preop()
                self.event("Requested configuration state")
            elif action == "operational":
                result = await dev.goto_operational()
                self.event("Requested operational state")
            elif action == "store":
                await self.refresh_access(dev)
                if await dev.nmt_state(cached=False) != 127:
                    raise ValueError("Enter configuration state before saving to controller memory")
                var = dev.variable(0x1010, 1)
                await dev._check_writable(var, 0x65766173)
                await dev.store()
                self.unsaved = False
                result = "Controller acknowledged the store command"
                self.event(result)
            elif action == "fault-reset":
                result = asdict(await dev.fault_reset())
                self.event("Requested drive fault reset")
            else:
                raise ValueError("Unsupported controller action")
        return {"result": clean(result), **self.connection_info()}

    async def dispatch(self, action, payload):
        if action == "catalog":
            return {**build_catalog(self.od, self.device.node_id if self.device else 32),
                    "topics": TOPICS, "fault_catalog": [v._asdict() for v in GEN4_FAULTS.values()],
                    "connection": self.connection_info()}
        if action == "connect":
            return await self.connect(payload)
        if action == "disconnect":
            await self.close()
            self.event("Disconnected")
            return self.connection_info()
        if action == "live":
            return await self.live(payload.get("keys", []))
        if action == "read":
            keys = payload.get("keys", [])
            return self.start_job("Read settings", lambda job: self.scan(keys, job))
        if action == "apply":
            return self.start_job("Apply settings", lambda job: self.apply(payload, job))
        if action == "backup":
            return self.start_job("Export backup", self.backup)
        if action == "import":
            return self.start_job("Read restore plan", lambda job: self.import_plan(payload, job))
        if action == "pdo-read":
            return await self.pdo_read(payload)
        if action == "pdo-apply":
            return self.start_job("Apply PDO", lambda job: self.pdo_apply(payload, job))
        if action == "command":
            return await self.command(payload)
        if action == "job":
            job = self.jobs.get(payload.get("id"))
            if job is None:
                raise ValueError("Operation expired or connection changed")
            return clean({k: v for k, v in job.items() if k != "task"})
        if action == "cancel":
            job = self.jobs.get(payload.get("id"))
            if job and job["kind"] in ("Read settings", "Export backup", "Read restore plan"):
                job["task"].cancel()
                return {"cancelled": True}
            raise ValueError("Only read operations can be cancelled")
        if action == "adapters":
            from .runtime import discover_adapters
            return discover_adapters()
        raise ValueError("Unknown request")

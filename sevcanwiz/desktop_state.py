"""Qt-facing controller state. CAN work never runs on the GUI thread."""

import math
import time
from collections import defaultdict, deque
from PySide6.QtCore import QObject, Signal, QTimer
from .runtime import Runtime


def number_text(value, decimals=4):
    if value is None:
        return "--"
    if isinstance(value, bool):
        return "Enabled" if value else "Disabled"
    if isinstance(value, float):
        return f"{value:.{decimals}f}".rstrip("0").rstrip(".") if decimals else f"{value:.0f}"
    if isinstance(value, dict):
        return "; ".join(f"{key}: {text}" for key, text in value.items())
    return str(value)


class DesktopState(QObject):
    catalog_changed = Signal()
    values_changed = Signal()
    permissions_changed = Signal()
    drafts_changed = Signal()
    connection_changed = Signal()
    message = Signal(str)
    error = Signal(str)
    progress = Signal(str, int, int)
    _finished = Signal(int, object, object)

    def __init__(self, runtime=None, parent=None):
        super().__init__(parent)
        self.runtime = runtime or Runtime()
        self.catalog = {}
        self.settings = {}
        self.readings = {}
        self.drafts = {}
        self.connection = {"connected": False}
        self.live = {}
        self.busy = False
        self.paused = False
        self.histories = defaultdict(lambda: deque(maxlen=180))
        self.trace_keys = ["5100:02"]
        self.recording = False
        self.samples = []
        self._callbacks = {}
        self._counter = 0
        self._closed = False
        self._live_pending = False
        self._read_job = None
        self._read_inflight = False
        self._pending_reads = {}
        self._finished.connect(self._receive)
        self.live_timer = QTimer(self)
        self.live_timer.setInterval(500)
        self.live_timer.timeout.connect(self.poll_live)

    def request(self, action, payload=None, done=None, failed=None):
        if self._closed:
            return
        self._counter += 1
        request_id = self._counter
        self._callbacks[request_id] = (done, failed)
        future = self.runtime.submit(action, payload or {})
        def complete(future):
            if self._closed:
                return
            try:
                self._finished.emit(request_id, future.result(), None)
            except Exception as error:
                self._finished.emit(request_id, None, str(error) or type(error).__name__)
        future.add_done_callback(complete)

    def _receive(self, request_id, result, error):
        done, failed = self._callbacks.pop(request_id, (None, None))
        if error is not None:
            (failed or self.error.emit)(error)
        elif done:
            done(result)

    def initialize(self, simulated=True, eds=None):
        def loaded(result):
            self.set_catalog(result)
            if simulated:
                self.connect_controller({"backend": "simulator", "eds": eds})
        self.request("catalog", done=loaded)

    def set_catalog(self, result):
        self.catalog = result
        self.settings = {s["key"]: s for s in result["settings"]}
        self.connection = result["connection"]
        self.catalog_changed.emit()
        self.connection_changed.emit()

    @property
    def level(self):
        return self.live.get("level") if self.connection.get("connected") else None

    def role(self, level=None):
        level = self.level if level is None else level
        if level is None:
            return "Access unknown"
        return f"{self.catalog.get('access_levels', {}).get(level, 'Custom')} / level {level}"

    def required(self, setting):
        if setting["level"] is None:
            return "No login specified"
        return self.role(setting["level"])

    def permitted(self, setting):
        return (setting["editable"] and self.connection.get("connected") and
                self.level is not None and (setting["level"] is None or self.level >= setting["level"]))

    def permission_text(self, setting):
        if not setting["writable"]:
            return "Read only"
        if not setting["editable"]:
            return "Dedicated procedure"
        if not self.connection.get("connected") or self.level is None:
            return "Access unknown"
        return "Available" if self.permitted(setting) else "Locked"

    def value(self, key):
        if key in self.drafts:
            value = self.drafts[key]["value"]
            if isinstance(value, str):
                for raw, label in self.settings[key]["labels"].items():
                    if label == value:
                        return int(raw)
            return value
        reading = self.readings.get(key, {})
        if self.settings.get(key, {}).get("labels"):
            return reading.get("raw")
        return reading.get("value")

    def display(self, key, value):
        setting = self.settings[key]
        if setting["labels"]:
            return setting["labels"].get(value, str(value))
        step = setting["step"]
        decimals = min(9, max(0, math.ceil(-math.log10(step))+1)) if isinstance(step, (int, float)) and step > 0 else 4
        return number_text(value, decimals)

    def stage(self, key, value):
        setting = self.settings[key]
        reading = self.readings.get(key, {})
        if not self.permitted(setting) or not reading.get("bytes") or self.busy:
            self.message.emit(f"Cannot edit {setting['name']}. Requires {self.required(setting)}; your access is {self.role()}.")
            return False
        if isinstance(value, float) and not math.isfinite(value):
            self.error.emit("The value must be a finite number.")
            return False
        original = self.drafts.get(key)
        before = original["before"] if original else reading["value"]
        comparable = value
        if isinstance(value, str) and setting["labels"]:
            comparable = next((int(raw) for raw, label in setting["labels"].items() if label == value), value)
            baseline = original.get("before_raw") if original else reading.get("raw")
        else:
            baseline = before
        if isinstance(comparable, (int, float)):
            if setting["low"] is not None and comparable < setting["low"] or setting["high"] is not None and comparable > setting["high"]:
                self.error.emit(f"{setting['name']}: value outside the dictionary range.")
                return False
        same = comparable == baseline
        step = setting["step"]
        if isinstance(comparable, (int, float)) and isinstance(baseline, (int, float)) and isinstance(step, (int, float)):
            same = same or abs(comparable-baseline) < step/2
        if same:
            self.drafts.pop(key, None)
        else:
            self.drafts[key] = {"value": value, "before": before,
                                "before_raw": original.get("before_raw") if original else reading.get("raw"),
                                "expected": original["expected"] if original else reading["bytes"]}
        self.drafts_changed.emit()
        self.values_changed.emit()
        return True

    def receive_rows(self, rows, rebase=False):
        for row in rows:
            self.readings[row["key"]] = row
            if rebase and row.get("bytes") and row["key"] in self.drafts:
                self.drafts[row["key"]].update(before=row["value"], before_raw=row.get("raw"), expected=row["bytes"])
        self.values_changed.emit()

    def start_job(self, action, payload=None, done=None, changed=None, failed=None):
        def started(result):
            job_id = result["job"]
            if action == "read":
                self._read_job = job_id
            def update(job):
                self.progress.emit(job["kind"], job["completed"], job["total"])
                if changed:
                    changed(job)
                if job["state"] == "running":
                    QTimer.singleShot(150, lambda: self.request("job", {"id": job_id}, update, failed))
                else:
                    if self._read_job == job_id:
                        self._read_job = None
                    self.progress.emit("", 0, 0)
                    if job["state"] == "failed":
                        if failed:
                            failed(job["error"])
                        else:
                            self.error.emit(job["error"])
                    elif done:
                        done(job)
            self.request("job", {"id": job_id}, update, failed)
        self.request(action, payload, started, failed)

    def read_settings(self, keys, rebase=False):
        keys = list(dict.fromkeys(keys))
        if not self.connection.get("connected") or not keys:
            return
        for key in keys:
            self._pending_reads[key] = rebase or self._pending_reads.get(key, False)
        if self._read_inflight:
            return
        self._read_inflight = True
        selected, self._pending_reads = self._pending_reads, {}
        session = self.connection.get("session")
        def received(job):
            if session == self.connection.get("session"):
                for rebase in (False, True):
                    rows = [row for row in job["rows"] if selected[row["key"]] == rebase]
                    if rows:
                        self.receive_rows(rows, rebase)
        def finish(job=None, error=None):
            if session != self.connection.get("session"):
                return
            self._read_inflight = False
            if error:
                self.error.emit(error)
            if self._pending_reads:
                self.read_settings(list(self._pending_reads))
        self.start_job("read", {"keys": list(selected)}, finish, received,
                       lambda error: finish(error=error))

    def connect_controller(self, options, done=None, failed=None):
        if self.busy:
            return
        self.busy = True
        self.permissions_changed.emit()
        def finish(connection):
            self.connection = connection
            self.live = {}
            self.readings.clear()
            self._pending_reads.clear()
            self._read_inflight = False
            self._read_job = None
            self.drafts.clear()
            self.histories.clear()
            self.samples.clear()
            self.recording = False
            self.request("catalog", done=loaded, failed=fail)
        def loaded(catalog):
            self.busy = False
            self.set_catalog(catalog)
            self.drafts_changed.emit()
            self.permissions_changed.emit()
            self.live_timer.start()
            self.poll_live()
            if done:
                done()
        def fail(error):
            self.busy = False
            self.live = {}
            self.request("catalog", done=self.set_catalog)
            self.permissions_changed.emit()
            (failed or self.error.emit)(error)
        self.request("connect", options, finish, fail)

    def command(self, action, payload=None, done=None, failed=None):
        if self.busy:
            return
        data = {"action": action, "session": self.connection.get("session"), **(payload or {})}
        def finish(result):
            self.connection.update(result)
            if action in ("login", "logout"):
                self.live["level"] = result["result"]
                self.permissions_changed.emit()
            if action in ("preop", "operational"):
                self.live["state"] = 127 if action == "preop" else 5
            self.connection_changed.emit()
            if done:
                done(result)
            self.poll_live()
        self.request("command", data, finish, failed)

    def apply(self, keys=None, done=None):
        keys = list(keys or self.drafts)
        if self.busy or not keys:
            return
        self.busy = True
        self.permissions_changed.emit()
        changes = [{"key": key, "value": self.drafts[key]["value"], "expected": self.drafts[key]["expected"]} for key in keys]
        def updated(job):
            self.receive_rows(job["rows"])
            for row in job["rows"]:
                self.drafts.pop(row["key"], None)
            if job["completed"] or job.get("failed_key"):
                self.connection["unsaved"] = True
            if job.get("failed_key"):
                self.readings.pop(job["failed_key"], None)
            self.drafts_changed.emit()
        def finish(job):
            self.busy = False
            self.connection["unsaved"] = True
            self.permissions_changed.emit()
            self.connection_changed.emit()
            self.message.emit(f"{job['completed']} changes applied and verified. Save separately to controller memory.")
            if done:
                done(job)
        def failure(error):
            self.busy = False
            self.permissions_changed.emit()
            self.connection_changed.emit()
            self.values_changed.emit()
            self.error.emit(error)
        self.start_job("apply", {"session": self.connection.get("session"), "changes": changes}, finish, updated, failure)

    def discard(self, keys=None):
        for key in list(keys or self.drafts):
            self.drafts.pop(key, None)
        self.drafts_changed.emit()
        self.values_changed.emit()

    def poll_live(self):
        if self._closed or self._live_pending or self.paused or self.busy or not self.connection.get("connected"):
            return
        self._live_pending = True
        session = self.connection.get("session")
        def received(live):
            self._live_pending = False
            if session != self.connection.get("session"):
                return
            old_level = self.level
            self.live = live
            self.connection.update({k: live[k] for k in ("connected", "session", "backend", "simulated", "node", "identity", "unsaved")})
            for row in live["rows"]:
                self.histories[row["key"]].append((row.get("time"), row.get("value") if not row.get("error") else None))
            if self.recording:
                self.samples.append({"time": time.time(), "values": {r["key"]: r["value"] for r in live["rows"] if not r.get("error")}})
                if len(self.samples) >= 50000:
                    self.recording = False
                    self.message.emit("Recording reached 50,000 samples. Export the recording to keep it.")
            self.receive_rows(live["rows"])
            if old_level != self.level:
                self.permissions_changed.emit()
            self.connection_changed.emit()
        def fail(error):
            self._live_pending = False
            self.live.update(level=None, state=None, error=error)
            for key in list(self.histories):
                self.histories[key].append((None, None))
                self.readings[key] = {"key": key, "error": error}
            self.permissions_changed.emit()
            self.connection_changed.emit()
            self.values_changed.emit()
        self.request("live", {"keys": self.trace_keys[:8]}, received, fail)

    def close(self):
        if self._closed:
            return
        self._closed = True
        self.live_timer.stop()
        self.runtime.close()

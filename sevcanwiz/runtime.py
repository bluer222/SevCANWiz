"""CAN service on its own asyncio thread, shared by native UI operations."""

import asyncio
import threading
from pathlib import Path
from .service import ControllerService


def discover_adapters():
    interfaces = []
    net = Path("/sys/class/net")
    if net.is_dir():
        for interface in net.iterdir():
            try:
                if (interface / "type").read_text().strip() == "280":
                    interfaces.append(interface.name)
            except OSError:
                pass
    serial = sorted(str(p) for prefix in ("ttyACM*", "ttyUSB*", "cu.usb*") for p in Path("/dev").glob(prefix))
    usb, notes = [], []
    try:
        from serial.tools import list_ports
        serial = sorted(set(serial + [p.device for p in list_ports.comports()]))
    except ImportError:
        notes.append("Install SevconCAN's slcan extra for serial adapter support.")
    try:
        import can
        usb = can.detect_available_configs(interfaces=["gs_usb"])
    except Exception:
        notes.append("Direct USB discovery needs python-can with gs_usb and platform USB permissions.")
    return {"socketcan": interfaces, "serial": serial, "usb": usb, "notes": notes}


class Runtime:
    def __init__(self, eds=None):
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, daemon=True, name="sevcanwiz-can")
        self.thread.start()
        self.service = ControllerService(eds)

    def submit(self, action, payload=None):
        return asyncio.run_coroutine_threadsafe(self.service.dispatch(action, payload or {}), self.loop)

    def call(self, action, payload=None, timeout=20):
        return self.submit(action, payload).result(timeout)

    def close(self):
        asyncio.run_coroutine_threadsafe(self.service.close(), self.loop).result(30)
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(5)
        self.loop.close()

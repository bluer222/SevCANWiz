"""Present the complete EDS as named settings and editable curve coordinates."""

import re
from sevcon_can import datatypes as dt
from .helptext import explain, explain_bit

GROUPS = [
    {"id": "pedals", "name": "Pedals & throttle", "description": "Shape pedal response, calibrate inputs, and set brake priority."},
    {"id": "drive", "name": "Drive & braking", "description": "Tune driveability profiles, speed limits, ramps, and interlocks."},
    {"id": "motor", "name": "Motor & encoder", "description": "Set motor data, torque maps, feedback, and temperature protection."},
    {"id": "battery", "name": "Battery & power", "description": "Configure voltage protection, current limits, and the charge indicator."},
    {"id": "io", "name": "Inputs & outputs", "description": "Map signals, configure wire-off detection, and set contactor outputs."},
    {"id": "aux", "name": "Pump & steering", "description": "Configure hydraulic pumps, steering assistance, and auxiliary profiles."},
    {"id": "can", "name": "CAN & network", "description": "Inspect communication, configure PDOs, and supervise connected nodes."},
    {"id": "diagnostics", "name": "Diagnostics & logs", "description": "Inspect faults, counters, controller identity, and firmware diagnostics."},
]

ACCESS_LEVELS = {0: "Logged out", 1: "User", 2: "Dealer", 3: "Production", 4: "Engineering", 5: "Sevcon"}


def key_of(var):
    return f"{var.index:04X}:{var.subindex:02X}"


def group_of(var):
    index = var.index
    section = (var.section or "").lower()
    name = var.path.lower()
    if index in (0x2910, 0x2911, 0x2912, 0x2220, 0x2221, 0x2222, 0x2224, 0x2620, 0x2621, 0x2622, 0x2626):
        return "pedals"
    if 0x2C00 <= index <= 0x2CFF or index in (0x2870, 0x2871, 0x2872, 0x4623, 0x2790):
        return "battery"
    if 0x2A00 <= index <= 0x2BFF or "pump" in section or "psteer" in section or index == 0x2913:
        return "aux"
    if 0x3000 <= index <= 0x3400 or 0x4680 <= index <= 0x46DF or 0x6800 <= index <= 0x6FFF or 0x2D00 <= index <= 0x2DFF or "mapping" in section:
        return "io"
    if index < 0x2000 or index in (0x2800, 0x2810, 0x2830, 0x5110, 0x5800, 0x5900, 0x5901, 0x5902):
        return "can" if index not in (0x1000, 0x1008, 0x1009, 0x100A, 0x1018) else "diagnostics"
    if 0x4600 <= index <= 0x467F or 0x6040 <= index <= 0x67FF or "motor" in section or "encoder" in section:
        return "motor"
    if 0x4000 <= index <= 0x45FF or 0x5000 <= index <= 0x57FF or "log" in section or "counter" in section:
        return "diagnostics"
    return "drive"


def restricted(var):
    # These services need a sequence, or can change the SDO connection mid-write.
    return (var.index < 0x2000 and var.index != 0x1017) or var.index in (
        0x2800, 0x5000, 0x5001, 0x5400, 0x5601, 0x5602, 0x5603,
        0x5900, 0x5901, 0x5902, 0x6040, 0x6071, 0x60FF,
    ) or var.data_type in (dt.OCTET_STRING, dt.DOMAIN)


def raw_bounds(var):
    limits = dt.limits(var.data_type)
    lo = var.low if var.low is not None else limits[0] if limits else None
    hi = var.high if var.high is not None else limits[1] if limits else None
    if limits and limits[0] < 0:
        modulus = 1 << dt.bit_length(var.data_type)
        lo = lo-modulus if lo is not None and lo > limits[1] else lo
        hi = hi-modulus if hi is not None and hi > limits[1] else hi
    if lo is not None and hi is not None and lo > hi:
        return limits or (None, None)
    return lo, hi


def metadata(var, node=0x20):
    lo, hi = raw_bounds(var)
    factor = var.scaling if var.scaling is not None else 1
    low, high = (lo * factor if lo is not None else None,
                 hi * factor if hi is not None else None)
    if factor < 0:
        low, high = high, low
    try:
        default = var.to_physical(var.default(node))
    except (ValueError, TypeError):
        default = None
    if isinstance(default, bytes):
        default = default.hex()
    return {
        "key": key_of(var), "index": var.index, "sub": var.subindex,
        "name": var.name, "parent": var.parent_name or var.name,
        "path": var.path, "group": group_of(var), "unit": var.units or "",
        "type": dt.NAMES.get(var.data_type, "UNKNOWN"),
        "readable": var.readable, "writable": var.writable,
        "editable": var.readable and var.writable and not restricted(var),
        "preop": var.preop_only, "level": var.access_level,
        "eeprom": bool(var.eeprom), "low": low, "high": high,
        "step": abs(factor) if var.data_type in dt.INTEGER_TYPES else "any",
        "default": default, "labels": var.labels,
        "bits": [{"name": b.name, "mask": b.mask, "shift": b.shift,
                  "low": b.low, "high": b.high, "labels": b.labels,
                  "help": explain_bit(var, b)} for b in var.bitfields],
        "mappable": var.pdo_mappable, "size": dt.bit_length(var.data_type),
        "help": explain(var, low, high),
    }


def curves(od):
    result = []

    def add(id, name, group, index, pairs, x_label, y_label, *, percent=False, selector=None):
        keys = {key_of(v) for v in od.variables()}
        coords = [{"x": f"{index:04X}:{a:02X}", "y": f"{index:04X}:{b:02X}"} for a, b in pairs]
        if all(p[axis] in keys for p in coords for axis in ("x", "y")):
            result.append({"id": id, "name": name, "group": group, "points": coords,
                           "xLabel": x_label, "yLabel": y_label, "percent": percent,
                           "selector": f"{index:04X}:{selector:02X}" if selector else None})

    add("throttle", "Throttle response", "pedals", 0x2910, [(11, 12), (13, 14), (15, 16)], "Pedal travel", "Requested output", percent=True, selector=2)
    add("brake", "Footbrake response", "pedals", 0x2911, [(8, 9), (10, 11), (12, 13)], "Brake travel", "Braking request", percent=True, selector=3)
    for index, name, group, count, reverse, x, y in [
        (0x2C31, "Battery charge map", "battery", 5, False, "Battery voltage / V", "Remaining charge / %"),
        (0x4611, "Torque limit by speed", "motor", 9, True, "Motor speed / rpm", "Maximum torque / Nm"),
        (0x4615, "Secondary torque limit", "motor", 9, True, "Motor speed / rpm", "Maximum torque / Nm"),
        (0x4612, "Voltage torque cutback", "motor", 9, False, "Battery voltage / V", "Torque factor"),
        (0x461E, "Temperature cutback", "motor", 6, False, "Motor temperature / °C", "Torque factor"),
        (0x461F, "Thermistor calibration", "motor", 8, False, "Resistance / Ω", "Temperature / °C"),
    ]:
        add(f"map-{index:X}", name, group, index,
            [(2*i+2, 2*i+1) if reverse else (2*i+1, 2*i+2) for i in range(count)], x, y)
    add("steer-outer", "Outer wheel steering cutback", "aux", 0x2913, [(4,5),(6,7),(8,9),(10,11)], "Steering angle", "Speed factor")
    add("steer-inner", "Inner wheel steering cutback", "aux", 0x2913, [(12,13),(14,15),(16,17),(18,19)], "Steering angle", "Speed factor")
    for index in (0x2A10, 0x2A11):
        add(f"pump-{index:X}", f"Pump throttle {index-0x2A10+1} response", "aux", index, [(7,8),(9,10),(11,12)], "Pedal travel", "Pump request", percent=True, selector=2)
    return result


def build_catalog(od, node=0x20):
    settings = [metadata(v, node) for v in od.variables()]
    return {"settings": settings, "groups": GROUPS, "curves": curves(od), "access_levels": ACCESS_LEVELS,
            "source": od.source, "count": len(settings)}

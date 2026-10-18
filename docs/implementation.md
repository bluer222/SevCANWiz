# Implementation notes

The application imports the existing `sevcon_can` package. It does not copy
its CANopen implementation, dictionary, or generated fault tables.

`library.py` resolves an installed package, an explicit checkout, the sibling
checkout, or `~/Documents/GitHub/SevconCAN`. `runtime.py` dispatches native UI
requests into a dedicated asyncio thread. `service.py` owns
one controller, the simulator when used, connection identity, background jobs,
serialized writes, and the activity log. `catalog.py` turns EDS variables into
interface controls and actual curve-coordinate pairs. `helptext.py` contains
authored explanations plus firmware metadata. `desktop.py` owns the Qt main
monitoring window, menus, toolbar, docks, files, and workflow dialogs.
`desktop_windows.py` owns separate nonmodal configuration windows, each with
its own contextual explanation panel. `desktop_state.py`
bridges asynchronous results into Qt signals and holds session-bound drafts.
Task pages use native tables, forms, and QPainter plots. No HTTP or web assets
are shipped.

## Sources used

- SevconCAN's `README.md`, `docs/IMPLEMENTATION_STATUS.md`, `docs/ADAPTERS.md`,
  `src/sevcon_can/device.py`, `configuration.py`, `od.py`, `simulator.py`,
  `descriptions.py`, `datatypes.py`, and generated fault catalog.
- The checked-out Gen4 V3.4 product manual, notably throttle, footbrake,
  driveability, steering, battery protection, motor, I/O, and CANopen sections.
- The actual bundled EDS names, labels, limits, physical scaling, bitfield
  definitions, EEPROM tags, write levels, and pre-operational restrictions.

Help distinguishes documented metadata and authored operational explanations
from firmware details not established by those sources. Some proprietary DSP
flags have only a name and label in the public dictionary. Their help gives
the known function context, complete field encoding, permissions, and the
limit of the available documentation. It does not invent a tuning equation.

## Access levels

| Level | Role |
| --- | --- |
| 0 | Logged out |
| 1 | User |
| 2 | Dealer |
| 3 | Production |
| 4 | Engineering |
| 5 | Sevcon |

The UI compares each writable object's declared minimum with the level read
from the connected controller. Fields with no declared minimum are labeled
accordingly. A dedicated-procedure object can meet the login requirement while
remaining unavailable in the generic setting editor. Read-only values remain
readable regardless of their write metadata. The controller can still reject
a write for a firmware or application rule beyond the supplied EDS.

Live access uses SevconCAN's `access_level(cached=False)`. A failed fresh read
clears the library's cached grant and propagates the error, so the UI displays
unknown access. Apply refreshes access before preflight. Save enforces the
store object's metadata.

## Configuration guarantees and limits

Generic Apply preflights all values before the first write, requires explicit
pre-operational state, compares original bytes, and reads every write back.
Writes remain sequential. It does not silently roll back partial writes,
switch the network state, or persist parameters.

Cross-setting validation covers increasing curve coordinates, normalized pedal
range and monotonicity, the User defined selector, battery protection threshold
order, and the configured gear-ratio denominator. Firmware validates other
vehicle-specific relationships. Maps with unused zero-filled points require
editing into a valid ordered table before Apply; the app does not guess which
point is active.

SevconCAN's PDO configuration API supplies the standard disable/clear/map/
enable sequence. The UI also compares the entire read-back with the selected
mapping, identifier, transmission type, and enable state.
SevconCAN's `configure_pdo` also preflights and writes TPDO timing while the
PDO is disabled, then restores the requested enable state. The UI verifies
the returned timing values as part of read-back verification.
Extended identifiers,
RPDO drive-demand transmission, and timed host heartbeat/SYNC producers are
outside this configuration application's current scope.

Backups read parameters individually so monitoring can continue and exports
can be cancelled. They are not atomic captures of the entire controller;
avoid configuration changes from other clients while capturing one. An import
uses SevconCAN's strict snapshot identity and dictionary checks and then stages
only explicitly selected, supported writable parameter differences.

Polling shares serialized SDO access and can slow down when unsupported reads
time out. Failed samples are absent from recorded values and break traces.
Disconnect or reconnect waits for an in-progress Apply instead of interrupting
it mid-write. The app retains twelve completed operation results and 250
activity events. Desktop recordings are bounded at 50,000 samples.

## Hardware validation

No physical controller or USB adapter was used for this implementation.
The underlying library already documents its own unverified physical and
proprietary-service claims. The app does not broaden those claims.

Since then, the app made two read-only value dumps of the target controller
on 16 October 2026. On 17 October SevconCAN enumerated its dictionary and
logged in and out over a Candlelight SocketCAN adapter at 500 kbit/s, node 1.
Parameter writes, PDO remapping, and drive control remain untested on hardware.

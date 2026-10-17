"""Authored setting help, completed with the selected firmware's EDS metadata.

Mechanical limits, undocumented bit meanings, and proprietary commissioning
procedures are deliberately not inferred from a parameter name.
"""

from sevcon_can.descriptions import OBJECT_DESCRIPTIONS

TOPICS = {
    "connection": {
        "title": "Connect to a controller",
        "what": "The adapter carries CAN frames between this computer and the controller. Choose the backend that matches the adapter firmware. SocketCAN uses a Linux CAN interface, direct Candlelight uses gs_usb, and SLCAN uses a serial port. An adapter brand alone does not identify its protocol.",
        "adjust": "Use the node number and CAN bitrate already configured on the controller. The documented Gen4 default bitrate is 1 Mbit/s. SocketCAN must be brought up at that rate before connecting; this app does not reconfigure Linux interfaces. Direct USB and serial backends need the optional python-can dependencies.",
        "interactions": "Connecting reads identity and status. It does not log in, change network state, enable drive, or write settings. Simulation is a separate, clearly labeled CANopen test device. Select a firmware-specific EDS or DCF when available.",
    },
    "node": {
        "title": "Controller node",
        "what": "A CANopen node number identifies one controller on the bus. Valid controller numbers run from 1 to 127. The default example, 32, is not a discovery result.",
        "adjust": "Enter the number assigned to your controller; the target controller uses node 1. Devices on the same bus must have distinct node numbers. Changing this field selects a different destination for the next connection; it does not change a controller's node number.",
        "interactions": "A wrong node number commonly causes an SDO timeout. Check heartbeat traffic, the configured bitrate, wiring, and controller power before assuming a controller fault.",
    },
    "bitrate": {
        "title": "CAN bus bitrate",
        "what": "Bitrate sets how quickly bits travel on the CAN bus. Every device on that bus must use the same rate. CAN bitrate is separate from a SLCAN adapter's serial baudrate.",
        "adjust": "Match the existing vehicle network. Gen4 documentation lists 1 Mbit/s as the default, but the installed controller may have a different saved setting; the target controller uses 500 kbit/s. The selected rate configures direct USB and SLCAN backends only.",
        "interactions": "For SocketCAN, configure the operating system's CAN interface first. This app exposes the controller's physical-layer settings for inspection, but does not offer a generic write that would sever the connection.",
    },
    "eds": {
        "title": "Controller dictionary",
        "what": "An EDS or DCF describes the firmware's parameter names, units, scaling, ranges, labels, and access rules. The interface is generated from the selected file, so custom firmware can expose a different set of settings.",
        "adjust": "Use the file supplied for the installed firmware. Enter a path on the computer running this app. The bundled dictionary's header declares a different product code from the target controller, but a full scan found the target's installed entries, data types, and access identical to it.",
        "interactions": "Identity comparison is shown after connection. Matching identity supports dictionary selection but cannot prove that every optional object exists. DCF values are not automatically written to real hardware.",
    },
    "login": {
        "title": "Controller access level",
        "what": "Sevcon controls write permissions through login levels. The controller returns the granted level after checking the password and user ID. Reads generally remain available without engineering access.",
        "adjust": "Use credentials assigned to your controller. Levels are 0 logged out, 1 user, 2 dealer, 3 production, 4 engineering, and 5 Sevcon. The simulator and the target controller accept 0x4BDF for user 0; other controllers can use different credentials.",
        "interactions": "Logging in does not apply any drafts. Settings still obey their range, access, and pre-operational rules. Credentials remain in this process and are never put into saved settings, exports, or the activity log.",
    },
    "preop": {
        "title": "Configuration state",
        "what": "Pre-operational is a CANopen network state intended for configuration. SDO parameter access remains available, while normal PDO exchange stops. Many Gen4 settings require this state before a write.",
        "adjust": "Put the vehicle in its documented service condition before entering configuration state. Use the state button to request pre-operational explicitly. Apply never changes network state for you.",
        "interactions": "Returning to operational permits the vehicle application and PDO traffic to resume. It does not send an enable-drive sequence. Application interlocks, the vehicle master, and other nodes still determine vehicle behavior.",
    },
    "apply": {
        "title": "Review and apply changes",
        "what": "A draft is a proposed value held in this application. Editing a number, switch, profile, or curve does not write to the controller. The review lists the live value read when editing and the proposed value.",
        "adjust": "Apply checks every selected setting's type, range, login permission, curve ordering, and live network state before the first write. It also rejects changes if a parameter has changed since the app read it.",
        "interactions": "Writes occur sequentially and each is read back as exact controller bytes. This is not an atomic transaction. If a write fails, the app reports the verified changes and the failed setting; inspect or re-read that setting before retrying. Apply does not save to nonvolatile memory.",
    },
    "store": {
        "title": "Save to controller memory",
        "what": "Save sends the CANopen store signature so the controller can retain its current parameters across a power cycle. Apply and Save are separate actions because a temporary tuning change need not be permanent.",
        "adjust": "Apply your drafts, check their read-back, and test the vehicle configuration before saving. The app blocks Save while this application still has pending changes. Follow the installed controller's service procedure for power and state requirements.",
        "interactions": "Saving affects the controller's current configuration, including changes made by another client. A successful store acknowledgement is not a power-cycle persistence test. The simulator accepts the command but does not model persistent EEPROM.",
    },
    "curve": {
        "title": "Pedal response curve",
        "what": "This curve converts normalized pedal travel into a normalized request. The fixed endpoints are 0% input to 0% output and 100% input to 100% output. Three movable intermediate points are the controller's user-defined characteristic, not extra points created by the app.",
        "adjust": "Drag a point or enter exact coordinates. Lower output near the start gives finer low-speed control; higher output gives a stronger initial response. Interior input positions must increase and remain between the endpoints. Output positions must stay between 0% and 100%.",
        "interactions": "Editing the points stages the User defined characteristic selector as well. Voltage calibration first maps the physical pedal signal into travel. Drive mode, maximum torque or speed, ramps, and interlocks determine what the resulting request does. Built-in Curved and Crawl formulas are not documented precisely enough to draw as exact curves; their stored user points are shown separately.",
    },
    "map": {
        "title": "Controller lookup map",
        "what": "Each point is a pair of actual firmware parameters. The horizontal coordinate is the measured input, and the vertical coordinate is the limit, factor, or converted output. The app joins points with straight lines to make the stored table readable; firmware-specific extrapolation and interpolation rules still apply.",
        "adjust": "Use the fitted motor, battery, or sensor data to set these points. Input coordinates must increase. Zero-filled unused points remain visible and need correction before editing that map. Exact coordinate fields complement the draggable graph.",
        "interactions": "A curve is a group of ordinary draft settings and uses the same Apply review and read-back. Physical units come from the selected dictionary. A gain of 1 is full output and 0 is zero output where the dictionary identifies a normalized cutback factor.",
    },
    "backup": {
        "title": "Configuration backups",
        "what": "A backup reads all readable EEPROM-backed parameters described by the selected dictionary, plus the live vendor, product, firmware revision, and serial identity. It stores exact wire bytes to avoid rounding losses. Failed reads are recorded in the file.",
        "adjust": "Export before tuning. To restore, import a snapshot, review the differences, select the parameters you want, and stage them. Importing alone performs no parameter writes. Export may take several minutes when a controller has unsupported objects or slow responses.",
        "interactions": "Restore requires matching live identity, including serial, and matching dictionary metadata. Communication settings and service commands are excluded. Selected values use the normal Apply preflight and read-back. Backups are parameter snapshots, not firmware images or proprietary DVT DCF exports.",
    },
    "pdo": {
        "title": "Process data messages",
        "what": "PDOs carry selected live signals in small CAN messages. Transmit PDOs send controller data; receive PDOs supply data to the controller. Gen4 provides up to five of each. A mapping packs named signals into a maximum of 64 bits.",
        "adjust": "Select signals by name, a message identifier, and a transmission type. Types 0 to 240 use SYNC behavior; 254 and 255 use asynchronous behavior. Check the installed network design before choosing identifiers. This app's mapping editor uses standard 11-bit identifiers.",
        "interactions": "The dedicated Apply PDO button disables the PDO, clears the mapping count, writes the mapping and selected transmit timing, and restores the requested enabled state. A failure can leave the PDO disabled. Apply requires configuration state and verifies read-back. Save to memory remains separate. TPDO periodic and minimum transmit intervals are displayed in milliseconds.",
    },
    "pdo-identifier": {
        "title": "PDO message identifier",
        "what": "The CAN message identifier identifies this PDO on the shared bus and determines arbitration priority. Lower numbers win arbitration when messages start together. This field edits the standard 11-bit identifier, from 1 to 2047, separately from the PDO enable flag.",
        "adjust": "Use the identifier allocated by the vehicle's network design. Avoid collisions with another producer or with heartbeat, SDO, emergency, and other CANopen services. Changing a receive PDO identifier changes which incoming message this controller accepts; changing a transmit PDO identifier changes the message sent by this controller.",
        "interactions": "Other nodes that consume or produce this PDO must agree on its identifier and payload. Review and Apply performs the remapping sequence and checks read-back. Extended identifiers remain inspectable but cannot be edited here. Save to memory remains a separate action.",
    },
    "pdo-transmission": {
        "title": "PDO transmission type",
        "what": "Transmission type defines the relationship between a PDO and CANopen SYNC. Type 0 is synchronous and acyclic. Types 1 through 240 specify a SYNC cycle count. Types 254 and 255 are asynchronous manufacturer-specific and device-profile modes.",
        "adjust": "Match the network master's timing design. Selecting a synchronous mode does not make this app produce SYNC messages. Asynchronous event triggers and timing depend on the controller firmware and its event/inhibit settings; choosing 255 alone does not establish a polling interval.",
        "interactions": "Transmit and receive handling differ under the CANopen profile. Check the device manual for supported modes. TPDO timing fields set the event timer and inhibit time. Review and Apply verifies the requested type, timing, mapping, and identifier. Normal PDO traffic resumes in operational state.",
    },
    "pdo-enable": {
        "title": "Enable process data exchange",
        "what": "The enable flag controls whether this PDO is valid for process data exchange. The remapping procedure temporarily disables it before changing the payload. This checkbox chooses its requested state after that procedure completes.",
        "adjust": "Enable only PDOs used by the installed network. Disabling a transmit PDO stops its messages. Disabling a receive PDO prevents its normal reception and can affect demands or supervision expected by the vehicle application.",
        "interactions": "Normal PDO traffic also depends on network state and controller application rules. A failed remapping sequence may leave the PDO disabled even if this box was checked. Inspect the read-back and activity log after a failure. This flag does not enable the motor drive.",
    },
    "pdo-event-timer": {
        "title": "TPDO periodic transmit interval",
        "what": "A transmit PDO can send its mapped values when an event timer expires. The timer is expressed in milliseconds. For example, 100 ms requests a periodic transmission about ten times per second when the controller is operational and the PDO is enabled. Zero disables this periodic trigger.",
        "adjust": "Select asynchronous transmission type 254 or 255 as supported by the installed firmware, add the named values to the payload, and choose an interval suitable for the bus load. Synchronous types use incoming SYNC instead. An event-driven TPDO may also send when a mapped value changes, so the event timer alone is not a maximum send rate.",
        "interactions": "Minimum transmit interval, also called inhibit time, limits the rate of transmissions. Normal PDO traffic requires operational state. Apply writes timing while the PDO is disabled, reads it back, and restores the requested enable state. Save separately to keep it across power cycles. These settings configure controller messages; the monitoring window uses separate SDO polling.",
    },
    "pdo-inhibit": {
        "title": "TPDO minimum transmit interval",
        "what": "Inhibit time sets a minimum gap between transmissions of this PDO. The interface displays milliseconds with 0.1 ms steps, corresponding to the CANopen wire unit of 100 microseconds. Zero disables the minimum-gap restriction.",
        "adjust": "Use this to limit bursts caused by changing mapped signals. For example, a 10 ms minimum interval restricts this message to at most about 100 transmissions per second. A minimum interval longer than the periodic timer can delay its requested transmissions. Choose both values with the vehicle network's timing and bus-load requirements in mind.",
        "interactions": "This applies to transmit PDOs, particularly asynchronous event-driven operation. It does not set a sampling rate or change the app's polling interval. Apply checks the dictionary range and access role before writing and writes timing while the PDO is disabled. A failed operation may leave it disabled; inspect read-back before returning to service.",
    },
    "pdo-signal": {
        "title": "PDO payload and signal order",
        "what": "Each mapped signal contributes its dictionary-defined number of bits to the CAN payload. Signals are packed in the listed order, with at most 64 bits and eight mapped entries. The selector includes dictionary objects marked PDO-mappable, using readable signals for transmit PDOs and writable signals for receive PDOs.",
        "adjust": "Add the required named signals in the exact order agreed with the other nodes. Remove a selected row to change the payload. Raw on-wire encoding and scaling follow the dictionary; physical-unit display in this application does not change the PDO encoding.",
        "interactions": "A receiving node must use the same sizes, order, and interpretation. Dictionary permission and firmware restrictions still apply during remapping. Review and Apply changes the entire mapping through the dedicated sequence. This app does not generate receive PDO drive demands.",
    },
    "serial-rate": {
        "title": "SLCAN serial baudrate",
        "what": "Serial baudrate controls the link between this computer and a serial SLCAN adapter. It is separate from the CAN bitrate between the adapter and controller. Both links must match their respective devices.",
        "adjust": "Use the baudrate supported and configured by the adapter firmware. The default offered here is 115200 baud. A mismatched serial rate prevents reliable SLCAN commands even when the CAN bitrate is correct.",
        "interactions": "This field applies only to the serial SLCAN backend. Select the correct serial port and CAN bitrate as well. Changing it configures the host connection and does not write the controller's CAN physical-layer settings.",
    },
    "usb-index": {
        "title": "Direct USB adapter index",
        "what": "The device index selects a direct gs_usb adapter when the backend finds more than one matching USB device. Zero selects its first device. It is a host adapter selection, not a controller node number or CAN message identifier.",
        "adjust": "Use discovery and the adapter driver's enumeration to identify the intended device. Enumeration may change after unplugging or adding adapters. USB access requires the optional driver dependencies and the platform's USB permissions.",
        "interactions": "This selection applies to the direct Candlelight USB backend. The chosen adapter can reach multiple CANopen nodes, so the node number must still identify the target controller. Other backends select their adapter through the interface or port field.",
    },
    "monitor": {
        "title": "Live measurements and recording",
        "what": "Meters and traces display typed SDO reads in the dictionary's physical units. You can select any readable numeric setting for a trace. The app polls rather than assuming a factory PDO layout.",
        "adjust": "Use the signal selector to inspect voltage, current, temperature, speed, torque, or inputs. Recording captures successful samples while the application remains open. Export CSV to keep the recording. Pausing stops live polling.",
        "interactions": "Polling is approximately twice per second and shares serialized SDO access with configuration. Slow or unsupported reads reduce that rate. Missing samples stay missing instead of appearing as zero. Simulation animates example measurements and does not model motor physics.",
    },
    "dump": {
        "title": "Export all readable values",
        "what": "This scan reads every readable entry in the selected dictionary, including live measurements, communication records, counters, and configuration. Each result carries a name, physical value, raw interpretation, exact bytes, and timestamp, or a read error. Write-only entries are identified and skipped.",
        "adjust": "Use a value dump to inspect or share a controller's state beyond EEPROM configuration. The scan can take several minutes if optional objects time out. Cancel stops the read operation and exports the values collected so far with a partial flag.",
        "interactions": "Values are read sequentially, so this is not a simultaneous capture. The file is diagnostic data and cannot be imported as a configuration backup. Use Export backup when you need an identity-checked parameter snapshot for selected restoration.",
    },
    "faults": {
        "title": "Faults and controller messages",
        "what": "Active faults come from the controller's fault list. The included SevconCAN fault catalog provides descriptions and severity when the fault ID is known. Incoming EMCY messages appear in the activity log as well.",
        "adjust": "Read the fault description and correct its cause before requesting a fault reset. Reset sends the CiA 402 fault-reset edge; it does not repair wiring, override an interlock, or guarantee every vehicle fault clears.",
        "interactions": "Fault list inspection writes only the controller's list selector as part of its read protocol. It does not change configuration. Network state, drive state, and battery protection can each inhibit operation independently.",
    },
}

FAMILY = {
    "pedals": (
        "Pedal inputs first turn a voltage into a normalized request, then apply the chosen input characteristic. In torque mode the request affects torque; in closed-loop speed mode it affects speed. The footbrake request also depends on braking priority and the active driveability profile.",
        "Change these settings when matching an installed pedal's measured range or tuning driver response. Calibrate the start and end voltages before changing the response curve. Configure input mapping, wire-off detection, and the required pedal interlocks alongside calibration."),
    "drive": (
        "The traction application combines driver requests, selected driveability profiles, direction, and interlocks. A profile controls drive and braking torque limits, speed limits, and the rate at which demands change. Other vehicle parameters govern contactor behavior, service indicators, and sequencing.",
        "Change this parameter to match the vehicle's documented behavior. Compare all selectable profiles because a switch can replace the baseline settings while driving. Mechanical braking, motor ratings, and the available battery current remain independent constraints."),
    "motor": (
        "Motor configuration defines electrical ratings, current and speed limits, torque maps, control-loop gains, temperature protection, and commutation feedback. Encoder settings determine how the controller interprets rotor position; motor measurements report the resulting electrical and mechanical state.",
        "Use the fitted motor's data and the controller-specific commissioning procedure. A dictionary default is not a measured calibration. Motor constants, sensor type, supply voltage, pole pairs, and encoder offset must describe the same installation."),
    "battery": (
        "Battery settings limit current and voltage stress and configure the battery discharge indicator. Protection can reduce available drive or regenerative braking before a hard limit is reached. The charge indicator estimates remaining charge from its configured battery characteristics.",
        "Use battery manufacturer limits and the vehicle's battery-management design. Controller protection does not replace a battery management system. Check regenerative charging voltage and current against the battery's ability to accept energy."),
    "io": (
        "Input and output configuration connects physical pins to vehicle functions. Digital inputs report switch states; analog inputs report measured voltages. Virtual mappings route those signals to application functions. Analog outputs can drive contactors with distinct pull-in and hold levels.",
        "Use the build-specific harness diagram and the installed component ratings. Mapping a signal does not establish that its wiring, polarity, range, or fault detection is correct. Check physical input meters before assigning a vehicle function."),
    "aux": (
        "Pump and steering applications have their own requests, switch priorities, ramps, profiles, and interlocks. Pump requests can combine switches and analog controls. Twin traction motors can use steering maps to change the relative wheel speeds.",
        "Change this setting only for an auxiliary application fitted to the vehicle. Match pump and steering motor limits and verify the priority of simultaneous requests. A steering signal needs the correct mapping and fault detection."),
    "can": (
        "CANopen communication connects the controller to a vehicle master and other nodes. SDOs provide parameter access, PDOs carry process values, heartbeat supervises nodes, SYNC coordinates synchronous messages, and EMCY reports faults.",
        "Use the vehicle's network design. Message identifiers must not collide, supervised nodes must exist, and timeouts must allow normal traffic jitter. PDO mappings and settings that change the active connection need their dedicated procedures."),
    "diagnostics": (
        "Diagnostics expose controller identity, faults, runtime counters, recorded events, and firmware service information. Monitoring values show state rather than desired configuration. Some logs use a selector to choose which stored record is read next.",
        "Use these values to investigate a specific condition and compare changes over time. A counter or log value can describe earlier operation rather than the current state. Firmware debug and memory services require the exact manufacturer's service documentation."),
}

OBJECTS = {
    0x2910: ("Throttle calibration sets the start and end voltage and output for each input. Input 2 can represent a second pedal sensor or a reverse characteristic depending on the application. User-defined characteristic points use normalized 0 to 1 coordinates, even though the dictionary calls their horizontal field Voltage. The interface displays those points as percentages.", "Set calibration from actual released and fully pressed pedal measurements. Do not use the curve to compensate for wiring faults. Dual throttle operation requires separately mapped inputs; the manual specifies that disagreeing demands can inhibit drive."),
    0x2911: ("Footbrake calibration turns the brake pedal voltage into a braking request. The characteristic controls how quickly that request grows with travel. Braking exit speed ends footbraking below its threshold. Priority determines the response when throttle and brake are active together.", "Match the brake pedal's measured voltages first. Set priority to the intended vehicle behavior, then check footbraking torque and ramp limits in every driveability profile. Regeneration may reduce near zero speed or at high battery voltage."),
    0x2912: ("The economy input can modify the traction application's output according to an analog control. Start and end values map measured voltages into the request used by that application.", "Change it when the vehicle has a mapped economy control. Check its input mapping and verify the resulting economy value before tuning traction limits."),
    0x2913: ("Steering calibration defines left, center, and right potentiometer voltage. Inner and outer wheel tables relate steering angle to speed cutback in twin drive-motor applications. The tables work with the installed steering geometry and motor arrangement.", "Measure the physical steering limits and center position. Use the vehicle designer's steering geometry rather than a generic curve. Confirm wire-off detection and the observed steer-angle value before changing the tables."),
    0x2914: ("FS1 is the pedal-associated switch that indicates a drive request. Its configuration affects when pedal voltage is accepted and which sequence is required after an interruption. Dual pedal systems may provide a virtual FS1 where supported.", "Match the actual pedal assembly and vehicle sequence requirements. Removing a recycle requirement changes what happens when a pedal stays pressed while another interlock returns."),
    0x2915: ("The motor-to-vehicle ratio converts motor rotation into the vehicle speed representation. Numerator and denominator must describe the fitted gearing and speed conversion, so changing them can affect displayed speeds and application limits.", "Use drivetrain data and a measured speed check. Keep the denominator nonzero. A motor RPM limit and a vehicle speed limit are different quantities."),
    0x290A: ("S-curve control shapes changes in the speed target to reduce abrupt changes in acceleration. In speed mode it acts on the target; in torque mode it can act on the speed limit. The named factors belong to the firmware's S-curve implementation.", "Use the controller manual's tuning procedure and compare the response with torque ramps. The app does not invent an exact time-domain preview for undocumented factor equations."),
    0x290E: ("Brake feathering reduces braking torque near zero speed to help avoid rollback and harsh stopping. Start and end speeds define the transition, with a final torque and entry or exit rates controlling its shape. The manual describes this feature for torque mode.", "Tune against the installed drivetrain and braking system. Check neutral braking and footbraking profiles because feathering modifies their requested torque near a stop."),
    0x2930: ("Controlled roll-off limits unintended movement using configured torque and speed limits where the vehicle application supports it. It acts alongside hill-hold and the mechanical brake rather than defining the normal pedal response.", "Use the vehicle's slope and brake requirements. Check the enable setting and the behavior of the installed interlocks before adjusting torque."),
    0x2931: ("Profile triggers choose when driveability-select profiles replace the baseline profile. Different trigger flags can respond to vehicle inputs or operating conditions.", "Review each selectable profile together with its trigger. A profile that is not active during testing can still become active later when the assigned input changes."),
    0x2870: ("Master battery-current limits constrain the application's drive and regenerative current requests. They can interact with individual motor current limits and protection thresholds, so a requested torque may be reduced even below the motor's own limit.", "Use pack and battery-management current ratings. Distinguish discharge current from regenerative charge current and verify polarity in the live current measurement."),
    0x2C00: ("Nominal battery voltage identifies the intended battery system for the application. It is a reference rating, not a live measurement and not the hard overvoltage trip level.", "Match the installed pack and supported controller voltage class. Review the separate under- and overvoltage thresholds rather than relying on this value alone."),
    0x2C01: ("Overvoltage protection has a start-of-cutback voltage and a limiting voltage. It reduces permitted operation as voltage rises, particularly when regenerative braking returns energy to the battery.", "Set the start-of-cutback level below the limiting level. Use the pack's allowed charging voltage and the controller's voltage rating. High battery voltage can reduce regenerative braking."),
    0x2C02: ("Undervoltage protection reduces permitted operation as battery voltage falls. The start-of-cutback threshold precedes the limiting threshold during a falling voltage.", "Set the limiting voltage below the start-of-cutback voltage. Allow for voltage sag under load while respecting the battery's discharge limits."),
    0x2C30: ("The battery discharge indicator estimates state of charge using reset and discharge thresholds, cell count, timing, and warning or cutout levels. These settings describe the selected battery chemistry and voltage response.", "Use the battery-specific setup procedure. A voltage-based estimate can be inaccurate under heavy load or for a flat-voltage lithium chemistry; compare it with the battery management system."),
    0x2C31: ("The charge map pairs battery voltage with remaining-charge percentage. It is an estimate used by the battery discharge indicator, not a measurement of amp-hours. Each point's voltage uses the dictionary's physical scaling.", "Use a discharge curve appropriate to the pack, temperature, and measurement conditions. Voltage points must increase and charge percentages must remain within 0 to 100."),
    0x2D00: ("Contactor outputs can use a high pull-in voltage for a set time and then a lower hold voltage. This lets the coil close reliably while reducing steady heating.", "Use the installed coil's pull-in, hold, and maximum ratings. Check voltage-control and reduction-enable settings for each output. A pull-in time that is too short may prevent reliable closure."),
    0x4611: ("The motor power-limit map pairs motor speed with maximum torque. It shapes the torque envelope over speed; it does not describe a pedal characteristic. The graph displays speed horizontally and torque vertically even though the underlying record stores torque first.", "Use the motor manufacturer's torque-speed envelope and drivetrain limits. Sort speeds strictly upward. Other current, voltage, thermal, and traction limits can reduce torque further."),
    0x4615: ("The secondary torque-speed map provides another envelope. A separate trigger setting selects when it applies. Its points describe maximum torque at each motor speed.", "Set both the points and the secondary-map trigger. Do not assume the baseline map remains active during braking or a selected driveability input."),
    0x4612: ("Voltage torque-cutback points pair battery voltage with a normalized torque factor. A factor near 1 permits full output; a factor near 0 removes the allowed output represented by this map.", "Place points in increasing voltage order and use the installed motor and controller requirements. This map works alongside application-level battery protection."),
    0x461E: ("The temperature cutback map pairs motor temperature with a normalized torque factor. It can progressively reduce torque as the motor warms instead of relying only on a hard temperature limit.", "Use the motor's thermal limits and a calibrated sensor. Keep temperatures ordered and review the maximum allowable motor temperature and the selected measurement method."),
    0x461F: ("The thermistor map converts sensor resistance into temperature. NTC and PTC sensors have different curve directions, so temperature need not increase with resistance. The graph requires increasing resistance coordinates only.", "Enter the sensor manufacturer's resistance-temperature data in the dictionary's units. A wrong map makes every temperature-based protection decision wrong even when the displayed value looks plausible."),
    0x4621: ("Motor temperature setup defines the allowed temperature and parameters used by temperature estimation or resistance-based correction. The current constant and discretization belong to the selected firmware's estimation model.", "Select settings using the fitted motor's thermal data and documented measurement method. Compare estimated temperature with an independent measurement before using it as the protection reference."),
    0x4624: ("Overspeed protection monitors motor speed against configured limits and delays. Its purpose is different from the normal driver-command speed limit.", "Use the motor and drivetrain's permitted maximum speed. Check encoder scaling first; an incorrect resolution changes the apparent speed."),
    0x4630: ("Encoder configuration selects the sensor, electrical supply, pull-up behavior, offset, Sin/Cos amplitude limits, and supported latency adjustments. Sin/Cos actual minimum and maximum readings let you compare signal amplitude with the configured limits.", "Use the installed sensor's supply rating and the motor-specific commutation procedure. The app exposes only subindices present in the EDS because manual numbering differs between revisions. It does not run automatic alignment."),
    0x4641: ("Motor plate data defines motor currents, pole pairs, inductance, voltage constant, and current-loop gains. These electrical values feed the controller's motor model and regulation. The commit field is a firmware service action, not an ordinary rating.", "Use manufacturer or verified commissioning data. Pole pairs are half the electrical pole count. Use the documented commit procedure if the installed firmware requires it; Apply does not invent a motor-identification sequence."),
    0x4651: ("Speed-loop gains control how torque responds to the difference between target and actual speed. Proportional gain reacts to the current error; integral gain accumulates persistent error. Additional gains may be selected at low speed or during rollback.", "Tune in the documented commissioning order after the motor model and current loop are correct. Excessive gain can cause oscillation, while too little gain can give slow response. Compare actual speed and torque traces."),
    0x4680: ("Digital input setup controls electrical input behavior such as pull-ups. Pull-ups affect an open input's voltage; polarity and function mapping separately decide whether that voltage means an active switch.", "Match the switch wiring and check the physical input state with the switch both open and closed. Do not use software polarity to conceal an electrical wiring fault."),
    0x4681: ("Wire-off detection identifies certain broken or disconnected digital input circuits. Each enabled channel must use wiring compatible with the controller's detection method.", "Enable detection for the channels required by the vehicle design, using the documented resistor or switch arrangement. A normal open-switch state and a broken wire must be distinguishable electrically."),
    0x4690: ("Analog input setup includes thresholds used to interpret input voltages and detect faults. Thresholds are electrical limits and are separate from the pedal's start and end calibration.", "Measure the normal range and allow documented tolerance. Configure limits so a disconnected sensor is detected instead of interpreted as a valid full-scale command."),
    0x6802: ("Digital input polarity determines whether a channel is active when its switch is open or closed. It changes the logical interpretation of the input rather than changing pin voltage.", "Match each channel's normally open or normally closed switch. Check the live physical state and the resulting mapped application state before relying on an interlock."),
    0x5800: ("Master/slave configuration defines this node's application role and other nodes it coordinates. Network configuration must agree with the vehicle's distributed motor and I/O design.", "Use unique node numbers and the correct slave list. A standalone controller and a traction master can interpret the same local signals differently."),
    0x5902: ("Receive-PDO timeout supervision detects missing process data and selects the controller's reaction. A timeout can inhibit drive when a master stops sending required demands.", "Choose a timeout longer than the expected message period and jitter, and the reaction required by the vehicle's safety design. This record is inspection-only here because it needs coordinated network configuration."),
}

INTERACTIONS = {
    "pedals": "Check the physical voltage, mapped input, normalized request, response characteristic, and active driveability limit together. An input can look correct electrically while its mapping or interpretation is wrong.",
    "drive": "The active profile and application state determine which limits apply. Compare the selected profile, direction, pedal request, and interlock states when actual behavior differs from the requested setting.",
    "motor": "Motor-model data, encoder scaling, current limits, thermal limits, and application demands work together. Check the corresponding live measurements to identify which part is limiting or misinterpreting the request.",
    "battery": "Check live pack voltage and current alongside the configured protection and charge estimate. A battery management limit can restrict operation independently of a controller threshold.",
    "io": "Compare the pin's measured state, its polarity or voltage thresholds, and the assigned application function. Output configuration also depends on the installed load and its electrical rating.",
    "aux": "Check request priority, input mapping, the active auxiliary profile, and any inhibit switch together. The traction and auxiliary applications can have separate limits and state machines.",
    "can": "Communication records must agree with peer nodes and the network master. Inspect identifier, enabled state, transmission timing, mapping, and timeout behavior as one network configuration.",
    "diagnostics": "Compare the observation with current controller state and recorded time or sequence where available. Reading a stored event does not establish that its cause is still active.",
}

BIT_HELP = {
    "Proportional Braking": "Makes the braking demand depend on the pedal characteristic where the traction application supports proportional braking. Compare its behavior with the direction-change and footbraking torque limits; selecting this flag does not increase the battery's ability to accept regenerative energy.",
    "Directional Throttle": "Lets the throttle input carry a direction request as well as magnitude. The calibrated neutral position separates forward from reverse demand. Match both voltage characteristics and verify the neutral region before using this mode.",
    "Speed Limit Mode": "Chooses how the throttle affects the speed limit in the traction application. A proportional throttle limit can restrict speed at partial pedal even in torque mode. Compare the choice with the maximum forward and reverse speed in the active profile.",
    "Braking Directional Throttle": "Allows a directional throttle to request braking according to its direction and the traction state. This changes the interpretation of the pedal, so it must agree with directional-throttle calibration and the intended vehicle sequence.",
    "Proportional Speed Limit in Braking": "Makes the braking state's permitted speed limit follow throttle position when enabled. With this disabled the application can use the full configured speed limit while braking. The manual describes this distinction for torque mode.",
    "Proportional Speed Limit in Drive": "Makes the drive state's speed limit follow throttle position when supported. A low pedal request can then impose a low speed ceiling as well as a low torque request. Check traction control mode and the active profile's maximum speed.",
    "Reverse Speed Limit Encoding": "Selects the firmware's representation of the reverse speed limit. Use the labels declared by the installed EDS and the matching controller manual. Do not infer a sign or scaling convention from the flag name alone.",
    "Handbrake Fault": "Enables the traction application's configured fault behavior for the handbrake input. It works with the mapped handbrake switch and its polarity. Disabling a fault response changes the interlock behavior rather than correcting a switch fault.",
    "Allow step change in steer angle": "Allows a sudden steering-angle change to pass through the application's steering interpretation. This can make twin-motor speed demands change abruptly. Use the vehicle steering geometry and sensor behavior when choosing it.",
    "Separate Seat Regen Braking settings": "Selects separate seat-related regenerative braking settings where the firmware provides them. Check the seat switch, its delay, and the seat-regen limits. A seat interruption can then use a different braking response from ordinary neutral braking.",
    "Slave Left Motor Speed Inversion": "Reverses the speed interpretation for the left traction slave in the application's supported twin-motor arrangement. Match the installed motor direction and mechanical mounting; this is different from reversing encoder wiring.",
    "Brake Light when Neutral Braking": "Requests brake-light activation during neutral braking where the application supports it. Map the brake-light output and check its electrical configuration. This flag governs an indication, not braking torque.",
    "Inching functionality": "Chooses the application's behavior for inching requests. Inching uses its own configured request, speed, and timeout parameters and can be triggered by mapped inch switches. Check those limits independently of ordinary pedal operation.",
    "Virtual FS1": "Allows the supported dual-throttle application to derive FS1 from the pedal sensors instead of a separate pedal switch. The inputs must be correctly mapped and plausibility-checked. Single-input systems do not gain dual-sensor fault coverage by selecting this flag.",
    "FS1 Recycle": "Requires the operator to release and reapply the pedal-associated FS1 signal after the relevant interruption. This prevents a held pedal from immediately requesting drive when another interlock returns. Match the vehicle's intended restart sequence.",
    "Drive/Footbrake Priority": "Decides which request takes precedence when throttle and footbrake are active together. Use the available labels from the EDS and check the footbrake priority timeout. Braking torque limits still determine the size of a permitted braking request.",
    "Idling Creep Torque/Footbrake Priority": "Controls the firmware's interaction between creep torque and a footbrake request. The bundled dictionary has no creep-torque setting and the target controller does not install 291Fh, so this choice's effect there is unconfirmed.",
    "BDI Map": "Selects use of the configured remaining-charge lookup map where supported. That map pairs battery voltage with an estimated charge percentage. It needs battery-specific points; enabling the flag does not calibrate the map automatically.",
    "BDI Inhibit": "Controls the battery discharge indicator's inhibit behavior. The associated warning and cutout levels determine when the application responds to low estimated charge. Compare the estimate with the battery management system before relying on it.",
    "BDI Deep Discharge activates profile": "Allows a deep-discharge condition reported by the battery discharge indicator to select this profile. Review the triggered profile's speed, torque, and ramp values, as well as the BDI cutout thresholds.",
    "Low BDI activates profile": "Allows a low estimated battery-charge condition to activate this driveability profile. Check the BDI warning threshold and both the baseline and selected profile so a low-battery transition gives the intended behavior.",
    "Battery Electrolyte Low activates profile": "Allows an electrolyte-low input or condition to select the profile in supported battery applications. It is relevant to installations that provide that signal. Check its mapping and the reduced-performance profile.",
    "Reverse switch activates profile": "Allows the reverse-switch state to select this profile. A direction input can therefore change torque, braking, or speed limits as well as direction. Review the selected profile alongside the baseline.",
    "Low speed activates profile": "Allows the configured low-speed condition to select the profile. Check the threshold and any hysteresis or release condition declared by the firmware to avoid an unexpected profile transition near the threshold.",
    "Drive Profile 3 switch activates profile": "Allows the mapped driveability-select 3 input to activate this profile. Check physical switch polarity, mapping, and the complete profile before using it as a driver mode selector.",
    "Service interval activates profile": "Allows a service-due condition to select the profile. The service interval and next-due settings determine when it triggers. Check that the selected profile still gives the intended service-limited vehicle behavior.",
    "Pump to stop on low battery": "Makes the supported pump application stop in response to its low-battery condition. Check battery indicator thresholds and the hydraulic system's required behavior. Traction and pump reactions can differ.",
    "Allow pump to regen": "Permits regenerative behavior in the supported pump application. A hydraulic load may drive the motor, returning energy to the electrical system. Check pump mechanics, battery charge limits, and motor control setup.",
    "Disable bridge when no pump demand": "Allows the power bridge to disable while no pump request is present. This can change motor holding and restart behavior. Verify the hydraulic system's requirements and the configured contactor sequence.",
    "Use power steer motor as 2nd pump motor": "Assigns the supported power-steer motor application to a second pump role. The motor mapping, limits, switches, and contactors must match that role. This flag alone does not rewire or commission the second motor.",
    "Use power steer speed as minimum pump speed": "Uses the supported power-steering request as a lower bound on pump speed. Check how steering assistance and ordinary pump requests combine so the pump remains available when steering needs it.",
    "Add Power Steer Speed to Pump Speed": "Adds the supported power-steering speed request to the pump speed request. The combined demand remains subject to motor and application limits. This differs from using steering demand only as a minimum.",
    "Encoder wire-off detection": "Enables the supported encoder-disconnection detection. Correct sensor supply, pull-up configuration, type, and signal amplitudes are prerequisites. Detection does not repair a missing or invalid rotor-position signal.",
    "SinCos MinMax Tracking": "Controls tracking of Sin/Cos signal extrema where supported. The actual sine and cosine minimum and maximum readings can be compared with their configured limits. Tracking is an observation aid, not automatic commutation alignment.",
    "SinCos full-scale 5V sensor support": "Selects firmware support for the corresponding full-scale 5 V Sin/Cos sensor behavior. Confirm the sensor's output amplitude and the selected encoder supply. A supply-voltage choice and signal full-scale handling are separate settings.",
    "Encoder fault ride-through": "Controls a firmware-specific response that can continue through certain encoder faults. Its allowed conditions and reaction depend on the motor and firmware. Use the manufacturer's fault ride-through procedure; do not treat it as a substitute for a working sensor.",
    "PWM Switching Frequency": "Selects the power-stage switching-frequency mode supported by this firmware. Frequency affects switching losses, acoustic behavior, and control-loop operation. Use the controller and motor commissioning guidance rather than choosing only by audible noise.",
    "Gain Scheduling": "Enables selection among control-loop gains according to supported operating conditions. Check the base and low-speed gains and their selection thresholds together. A stable base gain does not prove every scheduled gain is stable.",
    "Torque based on peak or power limit map": "Selects the firmware's torque reference convention for the supported control function. A percentage of peak torque and a percentage of a speed-dependent limit can yield different actual torque. Review the torque-speed map and peak-torque rating together.",
    "Scale max torque by power limit": "Allows the supported function to scale the permitted torque using the power-limit envelope. Available torque can then change with speed even at a fixed percentage request. Check the active primary or secondary torque map.",
}


def explain_bit(var, bit):
    from .catalog import group_of
    group = group_of(var)
    text = BIT_HELP.get(bit.name)
    if text is None:
        if "Polarity" in bit.name:
            text = "This channel's polarity chooses whether the logical input is active for an open or closed switch. Check the physical pin state with the switch in both positions and then check the mapped vehicle function. Polarity does not change the voltage on the pin."
        elif "Heartbeat time" in bit.name:
            text = "This is the timeout for the corresponding supervised CANopen node. It must exceed the peer's heartbeat production interval and expected jitter. Check the node-number field in the same record. A zero timeout disables supervision where the CANopen consumer record follows the standard encoding."
        elif "Node ID" in bit.name:
            text = "This field names the peer supervised by the heartbeat consumer record. It is not this controller's own node number. Use the peer's actual configured number and a corresponding timeout so the controller supervises the intended device."
        elif bit.name.startswith("Digital Input Wire-Off"):
            text = "This field controls disconnection detection for the named digital input channel. Match the controller's documented detection circuit and the installed harness. An open switch and a broken wire must be distinguishable electrically."
        elif "activates profile" in bit.name:
            text = "This trigger lets the named condition select the surrounding driveability profile. Review the condition's input or threshold and every limit in that profile. Selecting a trigger changes which profile becomes active; it does not edit the profile's values."
        elif "error" in bit.name.lower() or "fault" in bit.name.lower() or not var.writable:
            text = f"This field identifies the {bit.name} condition within {var.path}. Read it alongside controller state, the active fault list, and the associated signal. The EDS supplies its field encoding and labels; a set field does not by itself establish the underlying electrical cause."
        else:
            text = f"{bit.name} is an independently encoded part of {var.path}. The choices below are the values declared by the selected firmware dictionary. Use this field when configuring the named function; its supported conditions depend on the surrounding application. The public metadata does not define every firmware-specific transition, so the installed controller's manual remains the source for those details."
    maximum = bit.high if bit.high is not None else bit.mask >> bit.shift
    return {"title": bit.name, "what": text, "adjust": FAMILY[group][1],
            "interactions": INTERACTIONS[group] + " Editing this field preserves the unrelated fields in the same parameter. The complete parameter is checked and applied together.",
            "range": f"{bit.low or 0} to {maximum}",
            "choices": [{"value": k, "label": v} for k, v in bit.labels.items()],
            "access": "This field inherits the surrounding parameter's write permissions, network-state requirements, and Apply behavior.",
            "source": "Selected EDS bit-field metadata; Sevcon Gen4 configuration manual.",
            "address": f"{var.index:04X}:{var.subindex:02X}, mask 0x{bit.mask:X}, shift {bit.shift}"}


def explain(var, low, high):
    from .catalog import group_of, restricted, ACCESS_LEVELS
    group = group_of(var)
    what, adjust = OBJECTS.get(var.index, FAMILY[group])
    name = var.name.lower()
    notes = []
    if var.subindex == 0 and var.parent_name and "number" in name:
        what = "This count reports the entries or parameters in the surrounding record. It is metadata about the record, not a vehicle adjustment. The named entries are shown separately in their relevant pages."
        adjust = "Read this count to inspect record coverage. Do not treat a record's declared count as proof that every optional entry is implemented by the installed firmware."
    elif "user defined char" in name:
        notes.append("This coordinate is normalized from 0 to 1. Use the response editor to display and edit it as 0% to 100%. Points only affect the pedal when the User defined input characteristic is selected.")
    elif "start voltage" in name or "end voltage" in name:
        notes.append("Measure this voltage at the relevant pedal endpoint. A decreasing-voltage pedal can have an end voltage below its start voltage; the two endpoints must still be distinct.")
    elif "start value" in name or "end value" in name:
        notes.append("This is the normalized request at the calibrated voltage endpoint. A value of 1 represents full-scale positive request, 0 represents zero request, and negative values can represent reverse where the application supports them.")
    if "ramp" in name or "slope" in name or "acceleration" in name or "deceleration" in name:
        notes.append("A rate controls how fast a demand changes, rather than its final limit. For a value expressed in %/s, a larger number permits a quicker change and a smaller number gives a longer transition.")
    if "delay" in name or "timer" in name or "timeout" in name:
        notes.append("This timing setting uses the unit shown by the dictionary. A delay, debounce, and communication timeout serve different purposes; the controller manual determines whether zero disables this particular feature.")
    if "maximum" in name or "limit" in name:
        notes.append("This is one constraint in the surrounding function. A lower limit elsewhere, an active protection, or an interlock can reduce actual output below it. Do not exceed installed hardware ratings just because the dictionary accepts a larger number.")
    if "actual" in name or "measured" in name or not var.writable:
        notes.append("This value is read from the controller. Compare it with the relevant request and limit to distinguish a sensor reading from a command or a cutback.")
    if var.bitfields:
        notes.append("The field editor shows each bit group's named options while preserving unrelated bits. These groups can be set independently; they are not mutually exclusive choices for the entire parameter.")
    if var.labels:
        notes.append("The available choices below come from the selected firmware dictionary. Their exact application behavior depends on the surrounding function and vehicle configuration.")
    if var.index in OBJECT_DESCRIPTIONS and var.index not in OBJECTS:
        notes.append(OBJECT_DESCRIPTIONS[var.index])
    if group == "diagnostics" and var.writable and not var.eeprom:
        notes.append("This is a transient service or log-control field. Check whether it selects a record, resets a counter, or triggers a firmware action before applying a value.")
    access = "Read only. This value cannot be applied as a setting." if not var.writable else (
        "This setting is available for inspection. Use the dedicated service or network procedure to change it." if restricted(var) else
        "Edits remain drafts until Apply. The app reads the written bytes back and does not automatically save them to memory.")
    access += f" Required write access: {ACCESS_LEVELS.get(var.access_level, 'Custom')} at level {var.access_level}, or a higher level." if var.access_level is not None and var.writable else " No login restriction is declared in this dictionary." if var.writable else " Read visibility does not depend on this object's write access level."
    access += " The selected dictionary requires pre-operational state for writes." if var.preop_only else ""
    access += " This parameter is marked EEPROM-backed." if var.eeprom else " The dictionary does not mark this parameter as EEPROM-backed."
    unit = f" {var.units}" if var.units else ""
    range_text = f"{low:g}{unit} to {high:g}{unit}" if low is not None and high is not None else "No complete numeric range is declared."
    return {"title": var.name, "what": f"{var.path}. {what}", "adjust": adjust,
            "interactions": " ".join([INTERACTIONS[group], *notes]),
            "access": access, "range": range_text,
            "choices": [{"value": k, "label": v} for k, v in var.labels.items()],
            "source": "Selected EDS/DCF metadata; Sevcon Gen4 product manual, configuration and CANopen sections; SevconCAN descriptions.",
            "address": f"{var.index:04X}:{var.subindex:02X}"}

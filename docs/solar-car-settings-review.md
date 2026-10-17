# Solar car Sevcon settings

Updated 17 October 2026. The owner reports applying the reviewed changes. `edited.json` is a post-change snapshot from the same controller, with no read errors. It captures only part of the settings below. There is no `can0` interface available for this review, so current read-back and persistence have not been checked live.

## Applied changes

| Setting | Before | Applied value | Evidence / why |
| --- | --- | --- | --- |
| Motor sensor type `4620:05` | 0, User Defined | 1, KTY84 | Owner report and reviewed screenshot. Not in the snapshot. Check the reading against an independent temperature measurement. |
| Temperature estimate current constant `4621:01` | 120 | 0 | Confirmed in snapshot. Same-firmware ME0913 examples use zero, but that does not establish its exact effect on this motor. |
| Maximum allowable temperature `4621:03` | 120°C | 150°C | Confirmed in snapshot. The owner wants 150°C as the ceiling; do not raise it based on another motor-rating claim. |
| Motor cutback map `461E` | 95%, 90%, 80%, 50%, 25%, about 1% at 80, 90, 100, 120, 130, 140°C | First three gains raised to 100%, 95%, 85%; temperature coordinates retained | Owner report and screenshot. The map is absent from the snapshot. The final three gains are assumed unchanged until read back. |
| Battery discharge limit `2870:02` | 200 A | 100 A | Owner report and screenshot. Not in snapshot. Matches the linked battery's 100 A continuous rating. |
| Battery profile factors `2870:04`, `:05`, `:08` | 50%, 30%, 0% | 100%, 50%, 30% | Owner report and screenshot. With the 100 A baseline, intended limits are 100, 50, 30 A; verify `4623:02` in each selected profile. |
| Neutral braking `2920:03`, `2921:03`, `2936:03` | 10 | 0 | Confirmed in snapshot. Profile 2 was already zero. No demonstrated range gain from this alone. |
| Throttle upper fault threshold `46C0:02` | 143.996 V | 10 V | Confirmed in snapshot. A more useful target for the measured pedal is listed below. |
| Current-sensor autozero range `4654:00` | 0 A | 60 A | Owner report and screenshot. Not in snapshot. Matches the dictionary default and reference examples; its effect on the takeoff issue is unverified. |

The snapshot omits the motor map, sensor selection, master battery-current settings, effective current limit, autozero range, and ride-through settings. Their omission is not evidence that writes failed. It means this backup cannot verify them or their persistence.

## Remaining edits and checks

| Item | Current / last known | Target or action | Why |
| --- | --- | --- | --- |
| Throttle upper fault threshold `46C0:02` | 10 V | Approximately 5.6 V if the highest valid pedal voltage remains at or below 5.0 V. Otherwise allow at least 0.6 V above its measured valid maximum. Keep `46C0:01` at 0 V. | Ten volts remains high for a roughly 0–5 V signal. Verify fault inhibition and FS1 with drive disabled. A fault inside the valid signal range will not be detected by this threshold. |
| Final thermal gain `461E:0C` | About 0.00977 at 140°C if unchanged | Optional conservative correction: 0 at the existing 140°C point | Gives a zero torque-demand limit instead of retaining about 1%, with a 10°C gap to the owner's 150°C ceiling. It does not prove the sensor or thermal model is accurate. |
| Save and operating state | Snapshot has `2800:00 = 1`, forced pre-operational | Confirm Save to controller, persistence after a controlled power cycle, and Operational state before driving | Apply and Save are separate. The snapshot records configuration state, not readiness to drive. |
| Effective battery-current limits | Not in snapshot | Keep source `2870:01 = 3`, Follow Profiles. Read `2871:01` and `4623:02`; check the intended 100/50/30 A modes and actual battery current. | Verifies the current limit actually selected by the vehicle switches. Preserve the existing 20 A cutback range initially. |
| Temperature estimate and sensor | Current constant 0; sensor reportedly KTY84 | Check cold readings, sensor fault handling, then log measured temperature `4600:03`, estimate `4602:08`, cutback `4602:01`, heatsink temperature, and current during a controlled drive | Zero's exact effect is not documented. The estimate remains a suspect in the old cut-out; its cause was not captured during the event. |

With the temperature coordinates retained, the intended curve is:

| Temperature | Gain after the reported edits | Suggested final gain |
| --- | --- | --- |
| 80°C | 100% | Keep 100% |
| 90°C | 95% | Keep 95% |
| 100°C | 85% | Keep 85% |
| 120°C | About 50%, if unchanged | Keep about 50% |
| 130°C | About 25%, if unchanged | Keep about 25% |
| 140°C | About 1%, if unchanged | Optional 0% |

This is an early taper for the owner's conservative preference. Raising the separate maximum to 150°C does not move these map coordinates or provide full torque up to 150°C.

## Keep pending testing

- Brake priority `2911:01 = 1` already gives the footbrake priority over ordinary drive. The earlier change to 3 was conditional on a creep trial. `291F:00` is absent from the installed dictionary scan; that creep proposal is withdrawn. Verify FS1 and brake-input operation.
- Motor constants, pole pairs, encoder offset, current-loop gains, and the 275 A RMS peak phase-current setting. The ME0913 examples use a different motor and power stage.
- Fault ride-through `5840:01 = 287`, with 16 retries, until fault behavior is understood. Copying the example's disabled setting could change how drive faults interrupt operation.
- Estimate smoothing `4621:02 = 32740`.
- Undervoltage 42/40 V, forward speed limit 4,500 rpm, pedal map 0.5–4.7 V, and throttle flags `2910:01 = 244` during the initial tests.

Takeoff stutter is unresolved. After the autozero-range change, observe whether it improves. If it persists, record pedal voltage, demand, FS1, motor rpm, current, and fault activity before changing gains.

## Evidence and limits

- `edited.json` matches the original controller's vendor, product, revision, and serial. It contains 637 entries selected by the backup exporter, not every configuration parameter. Eight captured entries differ from `sevcon-values2.json`, including configuration state and an event-counter identifier.
- The reported cut-out stopped the motor while the display stayed powered, at a displayed motor temperature around 80°C. The old measured-temperature curve still allowed about 95% torque there. That makes another limiting path plausible; it does not establish the estimate as the cause.
- The Cursor chat reported live sensor resistance of 568 ohms at a motor-casing measurement of 21.3°C, plus old supply-critical, current-control, and overcurrent events. No thermal warning was recorded, which does not exclude an unlogged warning.
- Same-firmware references are `../SevconCAN/specs/od/Gen4-110V-300A-rev0x00010026-a.dcf` and `-b.dcf`. They support comparison, not wholesale transfer to this motor.
- The saved installed-dictionary scan lists 1,340 addresses and no `291F:00`. It does not provide human names, scaling, or bit-field meanings.

[Sevcon V3.4 manual](https://www.thunderstruck-ev.com/images/Gen4%20Product%20Manual%20V3%204.pdf) documents temperature protection, sensor wire-off behavior, and battery-current limiting. It says the estimate is always applied; it does not document current constant zero as an off switch. [LiTime's linked battery specifications](https://www.litime.com/products/like-new-litime-48v-100ah-golf-cart-metal-case-lithium-battery-200a-bms-real-time-monitoring) specify 100 A continuous discharge.

## Solar / Victron

Handled separately in `victron-handoff.txt`. The planned approximately 2,000 W array requires no Sevcon change with the same battery/DC-bus voltage.

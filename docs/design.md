# Desktop design brief

The operator is configuring or diagnosing a motor controller at a service
bench. They need to compare measured signals, proposed settings, permissions,
and controller state while keeping the vehicle's configuration in view.

The native Qt Widgets main window is a monitoring instrument with a menu bar,
controller commands, and a toolbar of labeled domain icons. Each configuration
icon opens an independent nonmodal window. Windows share the same controller
connection and draft set, and each has its own contextual help. Configuration
uses compact forms and named parameter tables. Curves lead the pedal/map
windows. Monitoring uses instrument readouts and a shared time plot.

## Domain and visual choices

- The domain includes CAN nodes, drive state, interlocks, engineering units,
  calibration endpoints, torque envelopes, EEPROM, access levels, and verified
  parameter changes.
- The visual references are test instruments and commissioning software:
  light gray enclosure surfaces, dark instrument labels, white edit fields,
  blue selected traces, amber warnings, and red faults.
- The characteristic interaction is comparing live controller values and
  unapplied drafts while the curve, current access level, configuration state,
  and verification result stay in view.
- Large headings, decorative metric cards, and long vertically stacked forms
  are replaced by a fixed workspace title, compact instrument strips, native
  splitters, tables, and dock panels.

## Component rules

Use the native platform font at 9 to 10 points. Primary instrument values use
16 to 20 points and tabular alignment. Editing controls are approximately
28 pixels high. Related controls use 4-pixel gaps; groups use 8 or 12 pixels.
Surfaces are neutral, with thin separators and small corner radii. Selected
items and plotted data use blue. Amber and red identify a warning or fault,
always accompanied by text. Permission locks include their required role and
level and the operator's current grant. Controls and table rows unavailable
because of authentication use gray text and gray fields. Help remains active.

Domain toolbar icons and the Windows menu open configuration windows. Tabs
represent pages within a window, such as throttle, footbrake, and pedal settings.
Each window provides read, access, state, Apply, and Save commands. The monitor
stays visible when another window opens. Help > Search menus locates commands
and windows, including synonyms such as TPDO and event timer. Ctrl+Shift+P
opens that search, Ctrl+F opens parameter search, F1 explains the selected
setting, and F5 re-reads the active window.

The user can resize or hide help docks and restore the monitor layout. Window
geometry and monitor dock placement persist. Configuration drafts stay in memory for
the exact active connection session and survive page navigation. Credentials never persist.
Closing with pending changes or a recording requires an explicit choice.

## References applied

- [Interface-design skill](https://github.com/Dammyjay93/interface-design/blob/main/.claude/skills/interface-design/SKILL.md), reviewed for task-based hierarchy, deliberate density, native controls, and visible states.
- [Rockwell Automation, Process HMI Style Guide](https://literature.rockwellautomation.com/idc/groups/literature/documents/wp/proces-wp023_-en-p.pdf), particularly neutral surfaces, context on graphical data, legible units, consistent status, and information hierarchy.
- [Microsoft desktop menu guidance](https://learn.microsoft.com/en-us/windows/win32/uxguide/cmd-menus) and [toolbar guidance](https://learn.microsoft.com/en-us/windows/win32/uxguide/cmd-toolbars), for command organization and predictable application navigation.
- [Microsoft property-window guidance](https://learn.microsoft.com/en-us/windows/win32/uxguide/win-property-win), for explicit Apply semantics and related groups of settings.
- [Qt main-window framework](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QMainWindow.html), for native menus, toolbars, central widgets, and docks.

These are design references, not a claim of compliance with an HMI standard.

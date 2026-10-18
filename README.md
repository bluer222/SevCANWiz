> Note: This project is primarily AI-generated code.

# SevCANWiz

A Python desktop app for configuring and diagnosing Sevcon Gen4 motor
controllers over CAN. It uses PySide6 and [SevconCAN](https://github.com/bluer222/SevconCAN)
for live monitoring, parameter editing, backups, and PDO configuration.

## Quick start

Requires Python 3.10 or newer and the latest SevconCAN checkout. Clone both
projects into the same directory, then run these commands from SevCANWiz:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -e ../SevconCAN -e .
sevcanwiz
```

The app starts with a simulator. Choose **Connect** to select a physical CAN
adapter and controller. Read settings, edit drafts, review **Apply changes**,
then use **Save to controller** separately to persist them. Hardware writes
and PDO remapping remain unverified on a physical controller.

## Documentation

- [Usage guide](docs/usage.md): installation, adapters, monitoring, configuration, and tests.
- [Implementation notes](docs/implementation.md): protocol coverage, access rules, and limits.
- [Desktop design](docs/design.md): windows, controls, and interaction choices.

## License

GNU Affero General Public License v3.0, `AGPL-3.0-only`. See [LICENCE](LICENCE).

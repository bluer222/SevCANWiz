import argparse
from .library import load_library


def main():
    parser = argparse.ArgumentParser(description="SevCANWiz native Sevcon commissioning application")
    parser.add_argument("--library", help="SevconCAN checkout; otherwise use installed or sibling library")
    parser.add_argument("--eds", help="Firmware-specific EDS/DCF")
    parser.add_argument("--disconnected", action="store_true", help="Start without the demo controller")
    args = parser.parse_args()
    load_library(args.library)
    try:
        from .desktop import run_desktop
    except ModuleNotFoundError as exc:
        if exc.name == "PySide6":
            parser.exit(1, "PySide6 is required. Run: pip install -e .\nOn NixOS: nix-shell --run 'python app.py'\n")
        raise
    return run_desktop(args.eds, args.disconnected)


if __name__ == "__main__":
    main()

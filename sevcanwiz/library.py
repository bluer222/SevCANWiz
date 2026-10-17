"""Use an installed SevconCAN, an explicit checkout, or the sibling checkout."""

import os
import sys
from pathlib import Path


def load_library(path=None):
    if path or os.environ.get("SEVCONCAN_PATH"):
        root = Path(path or os.environ["SEVCONCAN_PATH"]).expanduser().resolve()
        source = root / "src" if (root / "src/sevcon_can").is_dir() else root
        if not (source / "sevcon_can").is_dir():
            raise RuntimeError(f"No sevcon_can package in {root}")
        sys.path.insert(0, str(source))
    else:
        try:
            import sevcon_can
            return
        except ModuleNotFoundError:
            for root in (Path(__file__).resolve().parents[2] / "SevconCAN",
                         Path.home() / "Documents/GitHub/SevconCAN"):
                if (root / "src/sevcon_can").is_dir():
                    sys.path.insert(0, str(root / "src"))
                    break
    try:
        import sevcon_can
    except ModuleNotFoundError as error:
        raise RuntimeError("SevconCAN is required. Pass --library /path/to/SevconCAN or install that library.") from error

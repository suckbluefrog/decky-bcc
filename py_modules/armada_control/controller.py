import subprocess
from pathlib import Path

from .privileged import SOCKET, call

CONTROLLER_TYPE = "/usr/libexec/armada/controller-type"
DEFAULT_TYPE = "deck-uhid"
CONTROLLER_TYPES = {
    "deck-uhid": "Steam Deck",
    "xb360": "Xbox 360",
    "ds5": "DualSense",
}


def supported():
    return Path(SOCKET).exists() or Path(CONTROLLER_TYPE).is_file()


def controller_type():
    if not supported():
        return DEFAULT_TYPE
    try:
        value = str(call("get_controller_type").get("value") or "")
        if value in CONTROLLER_TYPES:
            return value
    except Exception:
        pass
    try:
        value = subprocess.check_output((CONTROLLER_TYPE, "get"), text=True, timeout=3).strip()
    except (OSError, subprocess.SubprocessError):
        return DEFAULT_TYPE
    return value if value in CONTROLLER_TYPES else DEFAULT_TYPE


def set_controller_type(value):
    if value not in CONTROLLER_TYPES:
        raise ValueError("invalid controller type")
    if not supported():
        raise RuntimeError("controller emulation switching is unavailable on this Batocera image")
    try:
        return str(call("set_controller_type", value=value).get("value") or controller_type())
    except Exception:
        try:
            subprocess.run((CONTROLLER_TYPE, "set", value), check=True, timeout=5)
        except (OSError, subprocess.SubprocessError) as exc:
            raise RuntimeError("failed to change controller emulation") from exc
        return controller_type()

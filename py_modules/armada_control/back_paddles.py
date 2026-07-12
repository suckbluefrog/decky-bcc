"""Back paddle binding config for Batocera Control."""

from __future__ import annotations

import json
import threading
from pathlib import Path

from .paddle_actions import ACTIONS, DEFAULT_BINDINGS, action_choices
from .system import atomically_write, run_cmd

CONFIG_PATH = Path("/userdata/system/configs/batocera-control/back-paddles.json")
GPIO_CHIP = Path("/dev/gpiochip8")
SERVICE = Path("/userdata/system/services/odin_backpaddles")
_LOCK = threading.RLock()
_VALID_ACTIONS = {key for key, _label in ACTIONS}
SLOTS = [
    ("m1", "M1 (tap)"),
    ("m2", "M2 (tap)"),
    ("m1_m2", "M1 + M2"),
    ("m1_start", "M1 + Start"),
    ("m1_back", "M1 + Back"),
    ("select_m2", "Select + M2"),
    ("home_m2", "Home + M2"),
]


def _normalize(data: dict | None, *, strict=False) -> dict:
    merged = dict(DEFAULT_BINDINGS)
    if not isinstance(data, dict):
        if strict:
            raise ValueError("back-paddle bindings must be an object")
        return merged
    for key, _label in SLOTS:
        value = str(data.get(key, merged.get(key, "none")) or "none")
        if value not in _VALID_ACTIONS:
            if strict:
                raise ValueError(f"invalid action for {key}: {value}")
            value = merged.get(key, "none")
        merged[key] = value
    return merged


def _extract_bindings(data: dict | None) -> dict | None:
    """Accept {bindings:{...}} from disk or flat {m1:...} from the Decky UI."""
    if not isinstance(data, dict):
        return None
    nested = data.get("bindings")
    if isinstance(nested, dict):
        return nested
    if any(key in data for key, _label in SLOTS):
        return data
    return None


def get_state() -> dict:
    reason = ""
    warning = ""
    if CONFIG_PATH.exists():
        try:
            payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            bindings = _normalize(_extract_bindings(payload))
        except (OSError, json.JSONDecodeError):
            bindings = dict(DEFAULT_BINDINGS)
            warning = "Bindings file is malformed; defaults are shown"
    else:
        bindings = dict(DEFAULT_BINDINGS)
    if not GPIO_CHIP.exists():
        reason = "GPIO paddle device was not detected"
    elif not SERVICE.is_file():
        reason = "Back-paddle service is not installed"
    return {
        "supported": not reason,
        "reason": reason,
        "warning": warning,
        "bindings": bindings,
        "slots": [{"data": key, "label": label} for key, label in SLOTS],
        "actions": action_choices(),
    }


def save_state(data: dict) -> dict:
    if not GPIO_CHIP.exists() or not SERVICE.is_file():
        raise RuntimeError("back-paddle support is not installed on this device")
    bindings = _normalize(_extract_bindings(data), strict=True)
    with _LOCK:
        atomically_write(
            CONFIG_PATH,
            json.dumps({"bindings": bindings}, indent=2, sort_keys=True) + "\n",
            0o644,
        )
        _restart_daemon()
    return get_state()


def _restart_daemon() -> None:
    run_cmd(["batocera-services", "restart", "odin_backpaddles"], timeout=15)
    active = run_cmd(["pgrep", "-f", "[/]userdata/system/scripts/odin-backpaddles.py"])
    if not active or active.returncode != 0:
        result = run_cmd([str(SERVICE), "start"], timeout=15)
        if not result or result.returncode != 0:
            raise RuntimeError("failed to start the back-paddle service")

"""Execute back-paddle shortcut actions on Batocera."""

from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path

from .system import settings_set

try:
    import evdev
    from evdev import UInput, ecodes
except ImportError:
    evdev = None
    ecodes = None
    UInput = None

BRIGHTNESS_STATE = Path("/var/run/odin-brightness-saved")
FAN_MODE_STATE = Path("/var/run/odin-fan-mode-state")

ACTIONS = [
    ("none", "None"),
    ("control_center", "Batocera Control Center (host app)"),
    ("mouse_toggle", "Toggle mouse mode (pauses gamepad navigation)"),
    ("mouse_left", "Left click"),
    ("mouse_right", "Right click"),
    ("mouse_middle", "Middle click"),
    ("mangohud_toggle", "Toggle MangoHud"),
    ("keyboard_toggle", "Toggle on-screen keyboard"),
    ("mute_toggle", "Toggle mute"),
    ("brightness_min_toggle", "Toggle minimum brightness"),
    ("led_toggle", "Toggle joystick LEDs"),
    ("wifi_toggle", "Toggle Wi-Fi"),
    ("bluetooth_toggle", "Toggle Bluetooth"),
    ("fan_mode_cycle", "Fan 100/50/0/auto"),
    ("power_profile_cycle", "Cycle power profile (eco/balanced/perf)"),
    ("screenshot", "Screenshot"),
    ("volume_up", "Volume up"),
    ("volume_down", "Volume down"),
    ("key_f1", "F1 key"),
    ("key_f2", "F2 key"),
    ("key_f3", "F3 key"),
    ("key_f4", "F4 key"),
    ("key_f5", "F5 key"),
    ("key_f6", "F6 key"),
    ("key_f7", "F7 key"),
    ("key_f8", "F8 key"),
    ("key_f9", "F9 key"),
    ("key_f10", "F10 key"),
    ("key_f11", "F11 key"),
    ("key_f12", "F12 key"),
    ("key_esc", "Esc key"),
    ("key_enter", "Enter key"),
    ("key_space", "Space key"),
    ("key_tab", "Tab key"),
]

DEFAULT_BINDINGS = {
    "m1": "none",
    "m2": "none",
    "m1_m2": "none",
    "m1_start": "none",
    "m1_back": "none",
    "select_m2": "none",
    "home_m2": "none",
}


def _run(cmd: list[str], timeout: int = 15) -> str:
    try:
        result = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=timeout)
        return (result.stdout or result.stderr or "").strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _settings_get(key: str) -> str:
    return _run(["batocera-settings-get", key])


def _settings_set(key: str, value: str) -> None:
    settings_set(key, value)


def _tap_key(code: int) -> None:
    if UInput is None or ecodes is None:
        _run(["python3", "/userdata/system/scripts/odin-key-send.py", str(code)])
        return
    try:
        ui = UInput(name="odin-paddle-keys", events={ecodes.EV_KEY: [code]})
        time.sleep(0.08)
        ui.write(ecodes.EV_KEY, code, 1)
        ui.syn()
        time.sleep(0.05)
        ui.write(ecodes.EV_KEY, code, 0)
        ui.syn()
        ui.close()
    except OSError:
        _run(["python3", "/userdata/system/scripts/odin-key-send.py", str(code)])


MOUSE_BUTTONS: dict[str, int] = {}


def _build_mouse_buttons() -> dict[str, int]:
    if ecodes is None:
        return {}
    mapping = {}
    for name, attr in (
        ("mouse_left", "BTN_LEFT"),
        ("mouse_right", "BTN_RIGHT"),
        ("mouse_middle", "BTN_MIDDLE"),
    ):
        code = getattr(ecodes, attr, None)
        if code is not None:
            mapping[name] = code
    return mapping


MOUSE_BUTTONS = _build_mouse_buttons()


KEY_ACTIONS: dict[str, int] = {}


def _build_key_actions() -> dict[str, int]:
    if ecodes is None:
        return {}
    mapping = {}
    for i in range(1, 13):
        code = getattr(ecodes, f"KEY_F{i}", None)
        if code is not None:
            mapping[f"key_f{i}"] = code
    extras = {
        "key_esc": ecodes.KEY_ESC,
        "key_enter": ecodes.KEY_ENTER,
        "key_space": ecodes.KEY_SPACE,
        "key_tab": ecodes.KEY_TAB,
    }
    mapping.update(extras)
    return mapping


KEY_ACTIONS = _build_key_actions()


def run_action(action: str) -> None:
    action = (action or "none").strip()
    if not action or action == "none":
        return
    if action not in {key for key, _label in ACTIONS}:
        return

    if action == "control_center":
        _run(["/usr/bin/batocera-controlcenter"])
        return

    if action == "mouse_toggle":
        _run(["/usr/bin/batocera-mouse-mode", "toggle"])
        return

    if action == "mangohud_toggle":
        _run(["python3", "/userdata/system/scripts/odin-mangohud-toggle.py"])
        return

    if action == "keyboard_toggle":
        out = _run(["/usr/bin/batocera-controlcenter", "keyboard"])
        if not out or "Usage" in out or "error" in out.lower():
            _run(["/usr/bin/batocera-controlcenter", "virtualkeyboard"])
        return

    if action == "mute_toggle":
        _run(["batocera-audio", "setSystemVolume", "mute-toggle"])
        return

    if action == "volume_up":
        vol = _run(["batocera-audio", "getSystemVolume"])
        match = re.search(r"(\d+)", vol)
        current = int(match.group(1)) if match else 50
        _run(["batocera-audio", "setSystemVolume", str(min(100, current + 10))])
        return

    if action == "volume_down":
        vol = _run(["batocera-audio", "getSystemVolume"])
        match = re.search(r"(\d+)", vol)
        current = int(match.group(1)) if match else 50
        _run(["batocera-audio", "setSystemVolume", str(max(0, current - 10))])
        return

    if action == "brightness_min_toggle":
        current = _run(["batocera-brightness"])
        match = re.search(r"(\d+)", current)
        pct = int(match.group(1)) if match else 70
        if BRIGHTNESS_STATE.exists():
            try:
                saved = int(BRIGHTNESS_STATE.read_text(encoding="utf-8").strip() or "70")
            except (OSError, ValueError):
                saved = 70
            saved = max(10, min(100, saved))
            _run(["batocera-brightness", str(saved)])
            BRIGHTNESS_STATE.unlink(missing_ok=True)
        else:
            BRIGHTNESS_STATE.write_text(str(max(10, min(100, pct))), encoding="utf-8")
            _run(["batocera-brightness", "10"])
        return

    if action == "led_toggle":
        # Accent-only toggle: never disable or zero the battery/status LED.
        from .joystick_led import toggle

        toggle()
        return

    if action == "wifi_toggle":
        if Path("/usr/bin/nmcli").exists():
            state = _run(["nmcli", "-t", "-f", "WIFI", "radio", "wifi"]).lower()
            _run(["nmcli", "radio", "wifi", "off" if state == "enabled" else "on"])
        else:
            enabled = _settings_get("wifi.enabled") == "1"
            _run(["batocera-wifi", "disable" if enabled else "enable"])
        return

    if action == "bluetooth_toggle":
        enabled = _settings_get("controllers.bluetooth.enabled") == "1"
        _run(["batocera-bluetooth", "disable" if enabled else "enable"])
        return

    if action == "fan_mode_cycle":
        order = ["255", "128", "0", "auto"]
        current = FAN_MODE_STATE.read_text(encoding="utf-8").strip() if FAN_MODE_STATE.exists() else "auto"
        try:
            idx = order.index(current)
        except ValueError:
            idx = -1
        nxt = order[(idx + 1) % len(order)]
        if nxt == "auto":
            FAN_MODE_STATE.unlink(missing_ok=True)
        else:
            FAN_MODE_STATE.write_text(nxt, encoding="utf-8")
        _run(["/userdata/system/scripts/odin-power", "fan", nxt])
        return

    if action == "power_profile_cycle":
        _run(["/userdata/system/scripts/odin-power", "profile", "cycle"])
        return

    if action == "screenshot":
        if Path("/usr/bin/batocera-screenshot").exists():
            _run(["/usr/bin/batocera-screenshot"])
        else:
            _run(["/usr/bin/batocera-record", "screenshot"])
        return

    if action in KEY_ACTIONS:
        _tap_key(KEY_ACTIONS[action])
        return

    if action in MOUSE_BUTTONS:
        _tap_key(MOUSE_BUTTONS[action])
        return


def action_choices() -> list[dict[str, str]]:
    return [{"data": key, "label": label} for key, label in ACTIONS]

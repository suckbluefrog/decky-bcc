"""Joystick ring LEDs via Batocera native batocera-led-handheld (batoled).

Uses the same batocera.conf keys as EmulationStation. Joystick rings (rgb:l*/r*)
are accent LEDs; power-led is a separate system battery/status LED and is never
owned or modified by this plugin.
"""

from __future__ import annotations

import json
import re
import subprocess
import threading
from pathlib import Path

from .system import atomically_write

CONFIG_PATH = Path("/userdata/system/configs/batocera-control/joystick-led.json")
LED_SYSFS = Path("/sys/class/leds")
_LOCK = threading.RLock()

MODES = [
    ("off", "Off"),
    ("solid", "Solid"),
    ("pulse", "Pulse"),
    ("rainbow", "Rainbow"),
]

NATIVE_MODE = {
    "solid": "static",
    "pulse": "pulse",
    "rainbow": "rainbow",
}

UI_FROM_NATIVE = {
    "static": "solid",
    "pulse": "pulse",
    "rainbow": "rainbow",
    "chroma": "rainbow",
}

COLOR_PRESETS = {
    "red": "#ff2020",
    "green": "#20ff40",
    "blue": "#2080ff",
    "cyan": "#20ffff",
    "magenta": "#ff40ff",
    "yellow": "#ffff40",
    "orange": "#ff9020",
    "purple": "#a040ff",
    "white": "#ffffff",
}

DEFAULT_BRIGHTNESS = 70
DEFAULT_COLOR = "#2080ff"
DEFAULT_SIDE = {"mode": "solid", "color": DEFAULT_COLOR, "brightness": DEFAULT_BRIGHTNESS}
DEFAULT_CONFIG = {
    "left": dict(DEFAULT_SIDE),
    "right": dict(DEFAULT_SIDE),
    "linked": True,
}


def _run(cmd: list[str]) -> str:
    try:
        result = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=15)
        return (result.stdout or "").strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _settings_get(key: str) -> str | None:
    value = _run(["batocera-settings-get", key])
    return value if value else None


def _settings_set(key: str, value: str) -> None:
    _run(["batocera-settings-set", key, value])


def _hex_to_rgb_dec(hex_color: str) -> tuple[int, int, int]:
    value = hex_color.strip().lstrip("#")
    if len(value) != 6:
        return 32, 128, 255
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def _rgb_dec_to_hex(r: int, g: int, b: int) -> str:
    return f"#{max(0, min(255, r)):02x}{max(0, min(255, g)):02x}{max(0, min(255, b)):02x}"


def _parse_colour_setting(raw: str | None) -> str:
    if not raw:
        return DEFAULT_COLOR
    parts = raw.replace(",", " ").split()
    if len(parts) >= 3:
        try:
            return _rgb_dec_to_hex(int(parts[0]), int(parts[1]), int(parts[2]))
        except ValueError:
            pass
    if len(raw.strip()) == 6:
        return f"#{raw.strip()}"
    return DEFAULT_COLOR


def _normalize_side(entry: dict, previous: dict | None = None) -> dict:
    prev = previous or {}
    side = dict(DEFAULT_SIDE)
    if isinstance(prev, dict):
        side.update({k: v for k, v in prev.items() if k in side})

    if not isinstance(entry, dict):
        return side

    mode = str(entry.get("mode", side["mode"]))
    if mode == "breath":
        mode = "pulse"
    if mode not in {m[0] for m in MODES}:
        mode = "solid"
    side["mode"] = mode

    color = str(entry.get("color", side["color"])).lower()
    if not color.startswith("#"):
        color = COLOR_PRESETS.get(color, side["color"])
    if not re.fullmatch(r"#[0-9a-f]{6}", color):
        color = str(side["color"])
    side["color"] = color

    try:
        brightness = int(entry.get("brightness", side["brightness"]))
    except (TypeError, ValueError):
        brightness = DEFAULT_BRIGHTNESS

    # Off is represented by a black accent colour, not brightness=0. Retaining
    # the last positive value makes the next enable deterministic.
    if mode == "off" and brightness < 1:
        try:
            brightness = int(prev.get("brightness", DEFAULT_BRIGHTNESS))
        except (TypeError, ValueError):
            brightness = DEFAULT_BRIGHTNESS
    side["brightness"] = max(1, min(100, brightness))

    return side


def _load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text())
            if isinstance(data, dict):
                merged = json.loads(json.dumps(DEFAULT_CONFIG))
                for side in ("left", "right"):
                    merged[side] = _normalize_side(data.get(side, {}))
                merged["linked"] = True
                merged["right"] = dict(merged["left"])
                return merged
        except (OSError, json.JSONDecodeError):
            pass
    return _config_from_batocera()


def _config_from_batocera() -> dict:
    enabled = _settings_get("led.enabled")
    mode_raw = (_settings_get("led.mode") or "static").lower()
    mode = "off" if enabled == "0" else UI_FROM_NATIVE.get(mode_raw, "solid")
    try:
        brightness = int(_settings_get("led.brightness") or DEFAULT_BRIGHTNESS)
    except ValueError:
        brightness = DEFAULT_BRIGHTNESS
    brightness = max(1, min(100, brightness))
    color = _parse_colour_setting(_settings_get("led.colour"))
    side = {"mode": mode, "color": color, "brightness": brightness}
    return {"left": dict(side), "right": dict(side), "linked": True}


def _save_config(data: dict) -> dict:
    payload = {
        "left": {k: data["left"][k] for k in ("mode", "color", "brightness")},
        "right": {k: data["left"][k] for k in ("mode", "color", "brightness")},
        "linked": True,
    }
    atomically_write(CONFIG_PATH, json.dumps(payload, indent=2) + "\n", 0o644)
    return payload


def _ensure_daemon() -> None:
    _settings_set("system.led-handheld", "1")
    if Path("/var/run/led-handheld.pid").exists():
        return
    init = Path("/etc/init.d/S51led-handheld")
    if init.exists():
        _run([str(init), "start"])


def _apply_native(side: dict) -> None:
    mode = str(side.get("mode", "solid"))
    _settings_set("system.led-handheld", "1")
    _ensure_daemon()
    _run(["batocera-led-handheld", "unblock_color_changes"])

    if mode == "off":
        # Keep led.enabled and the native daemon alive: they own the independent
        # battery/status LED. A black static colour blanks only accent/ring LEDs.
        _settings_set("led.enabled", "1")
        _settings_set("led.colour", "0 0 0")
        _settings_set("led.mode", "static")
        _run(["batocera-led-handheld", "set_color", "ESCOLOR"])
        return

    r, g, b = _hex_to_rgb_dec(str(side.get("color", DEFAULT_COLOR)))
    brightness = max(1, min(100, int(side.get("brightness", DEFAULT_BRIGHTNESS))))
    native = NATIVE_MODE.get(mode, "static")

    _settings_set("led.enabled", "1")
    _settings_set("led.colour", f"{r} {g} {b}")
    _settings_set("led.brightness", str(brightness))
    _settings_set("led.mode", native)

    if native == "static":
        _run(["batocera-led-handheld", "set_color", "ESCOLOR"])
    elif native == "pulse":
        _run(["batocera-led-handheld", "pulse"])
    elif native == "rainbow":
        _run(["batocera-led-handheld", "rainbow"])

def supported() -> bool:
    # PluginLoader runs under FEX: subprocess python3 checks fail; sysfs is reliable.
    try:
        return any(
            child.name != "power-led" and (child / "multi_intensity").exists()
            for child in LED_SYSFS.iterdir()
        )
    except OSError:
        return False


def get_state() -> dict:
    with _LOCK:
        cfg = _load_config()
    return {
        "supported": supported(),
        "native": True,
        "modes": [{"data": key, "label": label} for key, label in MODES],
        "colors": [{"data": key, "label": key.title()} for key in COLOR_PRESETS],
        "config": cfg,
    }


def save_state(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ValueError("joystick LED settings must be an object")
    with _LOCK:
        merged = _load_config()
        if isinstance(data.get("left"), dict):
            merged["left"] = _normalize_side(data["left"], merged.get("left", {}))
        merged["linked"] = True
        merged["right"] = dict(merged["left"])
        _save_config(merged)
        _apply_native(merged["left"])
    return get_state()


def toggle() -> dict:
    """Toggle accent LEDs without changing the system status-LED policy."""
    with _LOCK:
        merged = _load_config()
        side = dict(merged["left"])
        side["mode"] = "solid" if side.get("mode") == "off" else "off"
        merged["left"] = _normalize_side(side, merged["left"])
        merged["right"] = dict(merged["left"])
        _save_config(merged)
        _apply_native(merged["left"])
    return get_state()

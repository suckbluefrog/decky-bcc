"""Batocera-native LSFG-VK controls.

This module configures the LSFG layer already built into Batocera. It never
downloads a Vulkan layer or copies the proprietary Lossless.dll.
"""

from __future__ import annotations

import platform
import threading
from pathlib import Path

from .system import run_cmd

DEFAULT_DLL = Path("/userdata/system/wine/lossless-scaling/Lossless.dll")
NATIVE_LIBRARY = Path("/usr/lib/liblsfg-vk.so")
NATIVE_LAYER = Path("/usr/share/vulkan/explicit_layer.d/VkLayer_LS_frame_generation.json")
WINE_LIBRARY = Path("/usr/wine/lsfg-vk/x64/lib/liblsfg-vk.so")
WINE_LAYER = Path("/usr/wine/lsfg-vk/x64/share/vulkan/explicit_layer.d/VkLayer_LS_frame_generation.json")
LEGACY_PLUGIN = Path("/userdata/system/homebrew/plugins/decky-lsfg-vk")
LEGACY_CONFIG = Path("/userdata/system/.config/lsfg-vk/conf.toml")
LEGACY_SCRIPTS = (
    Path("/userdata/system/lsfg"),
    Path("/home/deck/lsfg"),
    Path("/root/lsfg"),
)

SETTINGS_GET = "/usr/bin/batocera-settings-get"
SETTINGS_SET = "/usr/bin/batocera-settings-set"
PREFIX = "steam"
_LOCK = threading.RLock()

MULTIPLIERS = {"2", "3", "4"}
FLOW_SCALES = {"1.0", "0.75", "0.5", "0.25"}
PRESENT_MODES = {"", "fifo", "vsync", "mailbox", "immediate"}


def _key(name: str) -> str:
    return f"{PREFIX}.{name}"


def _get(name: str) -> str:
    result = run_cmd([SETTINGS_GET, _key(name)])
    if not result or result.returncode != 0:
        return ""
    return result.stdout.strip()


def _set_many(values: list[tuple[str, str]]) -> None:
    if not values:
        return
    command = [SETTINGS_SET, "--validate"]
    for name, value in values:
        command.extend((_key(name), value))
    result = run_cmd(command, timeout=15)
    if not result or result.returncode != 0:
        names = ", ".join(_key(name) for name, _value in values)
        raise RuntimeError(f"failed to persist LSFG-VK settings ({names})")


def _is_arm() -> bool:
    # FEX can present an x86 personality to a process on ARM. The native layer
    # location is a reliable Batocera-side signal in that case.
    return platform.machine().lower() in {"aarch64", "arm64"} or NATIVE_LIBRARY.is_file()


def _bool(raw: str, default=False) -> bool:
    if not raw:
        return default
    return raw.strip().lower() in {"1", "true", "on", "enabled", "yes"}


def _layers() -> dict[str, bool]:
    return {
        "native": NATIVE_LIBRARY.is_file() and NATIVE_LAYER.is_file(),
        "x64": WINE_LIBRARY.is_file() and WINE_LAYER.is_file(),
    }


def _config() -> dict[str, object]:
    multiplier = _get("lsfg_vk_multiplier") or "2"
    flow_scale = _get("lsfg_vk_flow_scale") or ("0.75" if _is_arm() else "1.0")
    present_mode = _get("lsfg_vk_present_mode")
    return {
        "enabled": _bool(_get("lsfg_vk"), False),
        "multiplier": multiplier if multiplier in MULTIPLIERS else "2",
        "flowScale": flow_scale if flow_scale in FLOW_SCALES else ("0.75" if _is_arm() else "1.0"),
        "performanceMode": _bool(_get("lsfg_vk_performance"), _is_arm()),
        "hdrMode": _bool(_get("lsfg_vk_hdr"), False),
        "presentMode": present_mode if present_mode in PRESENT_MODES else "",
    }


def get_state() -> dict[str, object]:
    layers = _layers()
    dll_detected = DEFAULT_DLL.is_file()
    supported = layers["native"] or layers["x64"]
    reason = "" if supported else "The Batocera LSFG-VK Vulkan layer is not installed in this image"
    return {
        "supported": supported,
        "reason": reason,
        "ready": supported and dll_detected,
        "dllDetected": dll_detected,
        "dllPath": str(DEFAULT_DLL),
        "layers": layers,
        "config": _config(),
        "legacyPluginDetected": LEGACY_PLUGIN.is_dir(),
        "legacyConfigDetected": LEGACY_CONFIG.is_file(),
        "legacyLaunchScriptDetected": any(path.is_file() for path in LEGACY_SCRIPTS),
        "appliesOnNextSteamLaunch": True,
    }


def _sanitize(data: object) -> dict[str, object]:
    if not isinstance(data, dict):
        raise ValueError("LSFG-VK settings must be an object")
    multiplier = str(data.get("multiplier", "2"))
    flow_scale = str(data.get("flowScale", "0.75" if _is_arm() else "1.0"))
    present_mode = str(data.get("presentMode", ""))
    if multiplier not in MULTIPLIERS:
        raise ValueError("LSFG-VK multiplier must be 2x, 3x, or 4x")
    if flow_scale not in FLOW_SCALES:
        raise ValueError("LSFG-VK flow scale is invalid")
    if present_mode not in PRESENT_MODES:
        raise ValueError("LSFG-VK present mode is invalid")
    for name in ("enabled", "performanceMode", "hdrMode"):
        if name in data and not isinstance(data[name], bool):
            raise ValueError(f"LSFG-VK {name} must be a boolean")
    return {
        "enabled": bool(data.get("enabled", False)),
        "multiplier": multiplier,
        "flowScale": flow_scale,
        "performanceMode": bool(data.get("performanceMode", _is_arm())),
        "hdrMode": bool(data.get("hdrMode", False)),
        "presentMode": present_mode,
    }


def save_state(data: object) -> dict[str, object]:
    clean = _sanitize(data)
    with _LOCK:
        state = get_state()
        if clean["enabled"] and not state["supported"]:
            raise RuntimeError(str(state["reason"]))
        if clean["enabled"] and not state["dllDetected"]:
            raise RuntimeError(f"Lossless.dll was not found at {DEFAULT_DLL}")

        desired = {
            "lsfg_vk_dll": str(DEFAULT_DLL),
            "lsfg_vk_multiplier": str(clean["multiplier"]),
            "lsfg_vk_flow_scale": str(clean["flowScale"]),
            "lsfg_vk_performance": "1" if clean["performanceMode"] else "0",
            "lsfg_vk_hdr": "1" if clean["hdrMode"] else "0",
            "lsfg_vk_present_mode": str(clean["presentMode"]),
            # Enable last so a partially written configuration can never activate.
            "lsfg_vk": "1" if clean["enabled"] else "0",
        }
        previous: dict[str, str] = {}
        changed: list[tuple[str, str]] = []
        try:
            for name, value in desired.items():
                current = _get(name)
                previous[name] = current
                if current == value:
                    continue
                changed.append((name, value))
            # mini_settings accepts multiple key/value pairs and rewrites the
            # config once. This avoids seven independent batocera.conf writes.
            _set_many(changed)
        except Exception:
            try:
                _set_many([(name, previous[name]) for name, _value in changed])
            except Exception:
                pass
            raise

    return get_state()

"""Validated Decky bridge for Batocera's native adaptive power limiters."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from .system import run_cmd, settings_set_many

# Qualcomm handheld images use the frequency-cap limiter. Zen3/x86 handhelds
# use the sibling package-TDP limiter. Keep HELPER as the CPU helper name for
# compatibility with older plugin tests and downstream imports.
HELPER = Path("/usr/bin/batocera-cpu-limit")
TDP_HELPER = Path("/usr/bin/batocera-tdp-limit")

MODE_SETTING = "system.cpu.limit.mode"
GLOBAL_CAP_SETTING = "global.cpu_max_freq"
GLOBAL_TARGET_SETTING = "global.cpu_limit_target_fps"
TDP_MODE_SETTING = "global.tdp_mode"
TDP_TARGET_SETTING = "global.tdp_target_fps"

DEFAULT_MODES = ("off", "auto", "adaptive")
DEFAULT_CAPS = ("auto", "none", "95", "90", "85", "80", "75", "70", "65", "60", "55", "50")
DEFAULT_TARGETS = ("auto", "30", "50", "60", "90", "120")
TDP_MODES = ("off", "adaptive")
TDP_TARGETS = ("auto", "30", "60", "90", "120")

GAMESCOPE_STATS = "/var/run/batocera-cpu-limit/gamescope-stats.pipe"
TDP_GAMESCOPE_STATS = "/var/run/batocera-tdp-limit/gamescope-stats.pipe"
TDP_FPS_STATE = Path("/var/run/batocera-tdp-limit/fps.json")
_FPS_FRESH_SECONDS = 30
_LOCK = threading.RLock()


def _result(args: list[str], timeout: int = 10):
    return run_cmd([str(HELPER), *args], timeout=timeout)


def _tdp_result(args: list[str], timeout: int = 10):
    return run_cmd([str(TDP_HELPER), *args], timeout=timeout)


def _safe_number(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    return None


def _json_result(result) -> dict:
    try:
        raw = json.loads(result.stdout) if result and result.stdout else {}
    except (TypeError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _data_source(path_value: object, gamescope_path: str) -> str:
    path = str(path_value or "")
    if path == gamescope_path:
        return "Steam / Gamescope stats"
    if path:
        return "Emulator FPS sampler"
    return "Waiting for a game session"


def _unavailable(reason: str, kind: str = "cpu") -> dict:
    tdp = kind == "tdp"
    return {
        "supported": False,
        "reason": reason,
        "kind": kind,
        "mode": "off",
        "globalCap": "auto",
        "globalTargetFps": "auto",
        "running": False,
        "temperatureC": None,
        "fanPercent": None,
        "fps": None,
        "currentTdp": None,
        "minTdp": None,
        "maxTdp": None,
        "session": {},
        "dataSource": "Waiting for a game session",
        "modeOptions": list(TDP_MODES if tdp else DEFAULT_MODES),
        "capOptions": [] if tdp else list(DEFAULT_CAPS),
        "targetOptions": list(TDP_TARGETS if tdp else DEFAULT_TARGETS),
    }


def _cpu_state() -> dict:
    raw = _json_result(_result(["status"]))
    modes = list(DEFAULT_MODES)
    caps = list(DEFAULT_CAPS)
    targets = list(DEFAULT_TARGETS)
    session = raw.get("session") if isinstance(raw.get("session"), dict) else {}
    mode = str(raw.get("mode") or "off")
    cap = str(raw.get("global_cap") or "auto")
    target = str(raw.get("global_target_fps") or "auto")
    available = bool(raw.get("available"))

    return {
        "supported": available,
        "reason": "" if available else "CPU frequency policies are unavailable on this device",
        "kind": "cpu",
        "mode": mode if mode in modes else "off",
        "globalCap": cap if cap in caps else "auto",
        "globalTargetFps": target if target in targets else "auto",
        "running": bool(raw.get("running")),
        "temperatureC": _safe_number(raw.get("temp")),
        "fanPercent": _safe_number(raw.get("fan_percent")),
        "fps": _safe_number(raw.get("fps")),
        "currentTdp": None,
        "minTdp": None,
        "maxTdp": None,
        "session": session,
        "dataSource": _data_source(session.get("fps_path"), GAMESCOPE_STATS),
        "modeOptions": modes,
        "capOptions": caps,
        "targetOptions": targets,
    }


def _tdp_fps() -> float | int | None:
    try:
        data = json.loads(TDP_FPS_STATE.read_text(encoding="utf-8"))
    except (OSError, TypeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    fps = _safe_number(data.get("fps"))
    timestamp = _safe_number(data.get("timestamp"))
    if fps is None or timestamp is None or time.time() - timestamp > _FPS_FRESH_SECONDS:
        return None
    return fps


def _tdp_state() -> dict:
    raw = _json_result(_tdp_result(["json"]))
    modes = list(TDP_MODES)
    targets = list(TDP_TARGETS)
    mode = str(raw.get("saved_mode") or "off")
    target = str(raw.get("saved_target") or "auto")
    available = bool(raw.get("available"))
    session_keys = (
        "active_mode",
        "target",
        "target_fps",
        "base_tdp",
        "restore_tdp",
        "min_tdp",
        "max_tdp",
        "hardware_min",
        "hardware_max",
        "fps_source",
        "last_tdp",
    )
    session = {key: raw[key] for key in session_keys if key in raw}

    return {
        "supported": available,
        "reason": "" if available else "Adaptive package-TDP control is unavailable on this device",
        "kind": "tdp",
        "mode": mode if mode in modes else "off",
        "globalCap": "auto",
        "globalTargetFps": target if target in targets else "auto",
        "running": bool(raw.get("daemon_running")),
        "temperatureC": None,
        "fanPercent": None,
        "fps": _tdp_fps(),
        "currentTdp": _safe_number(raw.get("current_tdp")),
        "minTdp": _safe_number(raw.get("min_tdp")),
        "maxTdp": _safe_number(raw.get("max_tdp")),
        "session": session,
        "dataSource": _data_source(raw.get("fps_source"), TDP_GAMESCOPE_STATS),
        "modeOptions": modes,
        "capOptions": [],
        "targetOptions": targets,
    }


def get_state() -> dict:
    if HELPER.is_file():
        cpu = _cpu_state()
        # If a generic image happens to carry both helpers, prefer the one
        # which actually reports usable CPU policies.
        if cpu["supported"] or not TDP_HELPER.is_file():
            return cpu
    if TDP_HELPER.is_file():
        return _tdp_state()
    return _unavailable("Batocera's adaptive CPU/TDP limiter is not installed in this image")


def _save_cpu(data: dict) -> None:
    mode = str(data.get("mode") or "")
    cap = str(data.get("globalCap") or "")
    target = str(data.get("globalTargetFps") or "")
    if mode not in DEFAULT_MODES:
        raise ValueError("invalid adaptive CPU mode")
    if cap not in DEFAULT_CAPS:
        raise ValueError("invalid global CPU cap")
    if target not in DEFAULT_TARGETS:
        raise ValueError("invalid adaptive FPS target")

    settings_set_many(
        [
            (MODE_SETTING, mode),
            (GLOBAL_CAP_SETTING, cap),
            (GLOBAL_TARGET_SETTING, target),
        ]
    )
    result = _result(["apply-mode"], timeout=20)
    if not result or result.returncode != 0:
        raise RuntimeError("adaptive CPU settings were saved but the limiter did not apply them")


def _save_tdp(data: dict) -> None:
    mode = str(data.get("mode") or "")
    target = str(data.get("globalTargetFps") or "")
    if mode not in TDP_MODES:
        raise ValueError("invalid adaptive TDP mode")
    if target not in TDP_TARGETS:
        raise ValueError("invalid adaptive FPS target")

    settings_set_many([(TDP_MODE_SETTING, mode), (TDP_TARGET_SETTING, target)])
    # apply-mode intentionally keeps an existing session alive. Off therefore
    # needs game-stop so its worker exits and the pre-session TDP is restored.
    command = ["apply-mode"] if mode == "adaptive" else ["game-stop"]
    result = _tdp_result(command, timeout=20)
    if not result or result.returncode != 0:
        raise RuntimeError("adaptive TDP settings were saved but the limiter did not apply them")


def save_state(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ValueError("adaptive power settings must be an object")

    with _LOCK:
        # Batocera owns each runtime daemon. Batch persistent values through
        # the plugin's validated writer, then ask the selected helper to apply.
        if HELPER.is_file() and (_cpu_state()["supported"] or not TDP_HELPER.is_file()):
            _save_cpu(data)
        elif TDP_HELPER.is_file():
            _save_tdp(data)
        else:
            raise RuntimeError("Batocera's adaptive CPU/TDP limiter is not installed in this image")
    return get_state()

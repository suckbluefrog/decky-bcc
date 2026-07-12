"""Install the small, persistent Batocera helper used by Steam launch options."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from .system import atomically_write

BUNDLED_DIR = Path(__file__).resolve().parent.parent
BUNDLED_WRAPPER = BUNDLED_DIR / "batocera-control-game-launch"
BUNDLED_FEX_CONTRACT = BUNDLED_DIR / "fex-profiles.json"
RUNTIME_DIR = Path("/userdata/system/configs/batocera-control")
# /userdata/system/scripts is Batocera's game hook directory: every file there
# is executed on gameStart/gameStop. Keep this ordinary executable in bin.
STABLE_WRAPPER = Path("/userdata/system/bin/batocera-control-game-launch")
STABLE_FEX_CONTRACT = RUNTIME_DIR / "fex-profiles.json"
_LOCK = threading.Lock()


def _validated_contract_text() -> str:
    text = BUNDLED_FEX_CONTRACT.read_text(encoding="utf-8")
    contract = json.loads(text)
    if not isinstance(contract, dict):
        raise ValueError("bundled FEX profile contract is invalid")
    profiles = contract.get("profiles")
    if not isinstance(contract.get("defaults"), dict) or not isinstance(profiles, dict) or "default" not in profiles:
        raise ValueError("bundled FEX profile contract is invalid")
    for profile in profiles.values():
        if not isinstance(profile, dict) or not isinstance(profile.get("config"), dict):
            raise ValueError("bundled FEX profile contract is invalid")
    return json.dumps(contract, indent=2, sort_keys=True) + "\n"


def _write_if_changed(path: Path, text: str, mode: int) -> None:
    try:
        if path.read_text(encoding="utf-8") == text:
            if not (mode & 0o111) or os.access(path, os.X_OK):
                return
    except OSError:
        pass
    atomically_write(path, text, mode)


def ensure_runtime() -> dict[str, object]:
    """Install to userdata so existing Steam launch options survive plugin updates/removal."""
    with _LOCK:
        try:
            wrapper = BUNDLED_WRAPPER.read_text(encoding="utf-8")
            if "BATOCERA_CONTROL_GAME_LAUNCH" not in wrapper:
                raise ValueError("bundled Steam launch helper is invalid")
            contract = _validated_contract_text()
            _write_if_changed(STABLE_WRAPPER, wrapper, 0o755)
            _write_if_changed(STABLE_FEX_CONTRACT, contract, 0o644)
            if not os.access(STABLE_WRAPPER, os.X_OK):
                raise OSError(f"{STABLE_WRAPPER} is not executable")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            return {"supported": False, "path": "", "reason": str(exc)}
    return {"supported": True, "path": str(STABLE_WRAPPER), "reason": ""}

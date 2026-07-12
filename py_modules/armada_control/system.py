"""Batocera system helpers for Batocera Control plugin."""

from __future__ import annotations

import os
import re
import stat
import subprocess
import tempfile
from pathlib import Path


BATOCERA_SETTINGS_GET = "/usr/bin/batocera-settings-get"
BATOCERA_SETTINGS_SET = "/usr/bin/batocera-settings-set"
DROPBEAR_INIT = Path("/etc/init.d/S50dropbear")


def read_text(path, default=""):
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        return default


def atomically_write(path, text, mode=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if mode is None:
        try:
            mode = stat.S_IMODE(path.stat().st_mode)
        except OSError:
            mode = 0o644
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
        try:
            directory_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            pass
    finally:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass


def run_cmd(cmd, timeout=5, capture=True):
    try:
        return subprocess.run(
            cmd,
            check=False,
            text=True,
            stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def _settings_get(key: str) -> str:
    result = run_cmd([BATOCERA_SETTINGS_GET, key])
    return result.stdout.strip() if result and result.returncode == 0 else ""


def is_batocera() -> bool:
    return Path("/usr/share/batocera").is_dir() or Path(BATOCERA_SETTINGS_GET).exists()


def cpu_device_class():
    candidates = [
        read_text("/proc/device-tree/compatible").replace("\x00", " "),
        read_text("/sys/firmware/devicetree/base/compatible").replace("\x00", " "),
        read_text("/usr/share/batocera/batocera.arch"),
    ]
    for value in candidates:
        matches = re.findall(r"(?:qcom[,\-])?(sm\d{4}|qcs\d{4})", value, flags=re.IGNORECASE)
        if matches:
            return matches[0].upper()
    return "UNKNOWN"


def ssh_enabled():
    # Batocera uses Dropbear/OpenRC-style init scripts, not systemd's sshd unit.
    if is_batocera():
        active = run_cmd(["pgrep", "-x", "dropbear"])
        return bool(active and active.returncode == 0)
    active = run_cmd(["systemctl", "is-active", "sshd"])
    return bool(active and active.returncode == 0 and active.stdout.strip() == "active")


def os_version():
    try:
        return Path("/usr/share/batocera/batocera.version").read_text(encoding="utf-8").strip()
    except OSError:
        return "batocera"


def set_ssh_enabled(enabled):
    if is_batocera():
        setting = run_cmd([BATOCERA_SETTINGS_SET, "system.ssh.enabled", "1" if enabled else "0"])
        if not setting or setting.returncode != 0:
            raise RuntimeError("failed to persist Batocera SSH setting")
        if DROPBEAR_INIT.exists():
            action = "start" if enabled else "stop"
            result = run_cmd([str(DROPBEAR_INIT), action], timeout=30)
            if not result or result.returncode != 0:
                raise RuntimeError(f"failed to {action} Dropbear")
    else:
        command = ["systemctl", "enable", "--now", "sshd"] if enabled else ["systemctl", "disable", "--now", "sshd"]
        result = run_cmd(command, timeout=30)
        if not result or result.returncode != 0:
            raise RuntimeError("failed to update sshd")
    return ssh_enabled()

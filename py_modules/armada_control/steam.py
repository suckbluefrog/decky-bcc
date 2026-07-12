"""Installed Steam games — Batocera paths (not Armada /var/home/armada)."""

from __future__ import annotations

import os
from pathlib import Path


def _steam_roots() -> list[Path]:
    seen: set[Path] = set()
    roots: list[Path] = []
    for raw in (
        os.environ.get("STEAM_COMPAT_CLIENT_INSTALL_PATH", ""),
        os.environ.get("STEAM_ROOT", ""),
        "/userdata/system/.local/share/Steam",
        "/var/home/armada/.local/share/Steam",
    ):
        if not raw:
            continue
        path = Path(raw)
        if path in seen or not path.is_dir():
            continue
        seen.add(path)
        roots.append(path)
    return roots


def installed_games() -> list[dict[str, str]]:
    steamapps_dirs: set[Path] = set()
    for root in _steam_roots():
        steamapps_dirs.add(root / "steamapps")
        for library_file in (
            root / "steamapps/libraryfolders.vdf",
            root / "config/libraryfolders.vdf",
        ):
            try:
                lines = library_file.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for line in lines:
                parts = line.strip().split('"')
                if len(parts) >= 4 and parts[1] == "path":
                    steamapps_dirs.add(Path(parts[3]) / "steamapps")

    games: list[dict[str, str]] = []
    seen: set[str] = set()
    for steamapps_dir in sorted(steamapps_dirs):
        if not steamapps_dir.is_dir():
            continue
        for manifest in sorted(steamapps_dir.glob("appmanifest_*.acf")):
            values: dict[str, str] = {}
            try:
                lines = manifest.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for line in lines:
                parts = line.strip().split('"')
                if len(parts) >= 4 and parts[1] in ("appid", "name"):
                    values[parts[1]] = parts[3]
            appid = values.get("appid")
            name = values.get("name")
            if appid and name and appid not in seen and _is_playable_game(name):
                games.append({"appid": str(appid), "name": name})
                seen.add(appid)
    return sorted(games, key=lambda game: game["name"].casefold())


def _is_playable_game(name: str) -> bool:
    lower = name.lower()
    if lower.startswith("proton "):
        return False
    if "steam linux runtime" in lower:
        return False
    if lower.startswith("steamworks"):
        return False
    return True

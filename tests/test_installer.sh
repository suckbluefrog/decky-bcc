#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TEST_ROOT="$(mktemp -d)"
trap 'rm -rf "$TEST_ROOT"' EXIT INT TERM

mkdir -p "$TEST_ROOT/system/homebrew/services"
printf '#!/bin/sh\nexit 0\n' > "$TEST_ROOT/system/homebrew/services/PluginLoader"
chmod 0755 "$TEST_ROOT/system/homebrew/services/PluginLoader"
mkdir -p "$TEST_ROOT/system/homebrew/plugins/decky-lsfg-vk"
printf '{"name":"legacy"}\n' > "$TEST_ROOT/system/homebrew/plugins/decky-lsfg-vk/plugin.json"

BATOCERA_USERDATA="$TEST_ROOT" bash "$ROOT/install.sh" --no-restart
test -s "$TEST_ROOT/system/homebrew/plugins/armada-control/dist/index.js"
test -x "$TEST_ROOT/system/bin/batocera-control-game-launch"
test -x "$TEST_ROOT/system/bin/batocera-control-lsfg-launch"
test -s "$TEST_ROOT/system/configs/batocera-control/fex-profiles.json"
test "$(cat "$TEST_ROOT/system/homebrew/plugins/armada-control/VERSION")" = "$(cat "$ROOT/VERSION")"
test ! -e "$TEST_ROOT/system/homebrew/plugins/decky-lsfg-vk"
test -f "$TEST_ROOT/system/homebrew/disabled-plugins/decky-lsfg-vk-merged/plugin.json"

# A second install exercises atomic replacement and the previous-version backup.
mkdir -p "$TEST_ROOT/system/homebrew/plugins/.armada-control.previous"
printf '{"name":"legacy backup"}\n' > "$TEST_ROOT/system/homebrew/plugins/.armada-control.previous/plugin.json"
BATOCERA_USERDATA="$TEST_ROOT" bash "$ROOT/install.sh" --no-restart
test ! -e "$TEST_ROOT/system/homebrew/plugins/.armada-control.previous"
test -d "$TEST_ROOT/system/homebrew/disabled-plugins/armada-control-previous"

echo "Installer smoke test passed"

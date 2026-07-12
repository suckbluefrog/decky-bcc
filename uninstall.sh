#!/bin/bash
set -euo pipefail

TARGET=/userdata/system/homebrew/plugins/armada-control
BACKUP=/userdata/system/homebrew/plugins/.armada-control.previous

rm -rf "$TARGET" "$BACKUP"

echo "Batocera Control plugin removed."
echo "Settings and /userdata/system/bin/batocera-control-game-launch were retained."
echo "The helper must remain while any Steam game launch option references it."
echo "A migrated standalone LSFG plugin, if present, remains under homebrew/disabled-plugins."

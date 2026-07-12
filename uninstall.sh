#!/bin/bash
set -euo pipefail

TARGET=/userdata/system/homebrew/plugins/armada-control
BACKUP=/userdata/system/homebrew/plugins/.armada-control.previous

rm -rf "$TARGET" "$BACKUP"

echo "Batocera Control plugin removed."
echo "Settings and the Batocera Control game/LSFG launch helpers were retained."
echo "The helpers must remain while any Steam game launch option references them."
echo "A migrated standalone LSFG plugin, if present, remains under homebrew/disabled-plugins."

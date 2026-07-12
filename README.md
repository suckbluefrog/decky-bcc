# Batocera Control

Batocera-native Decky controls for AYN handhelds, derived from Armada Control.
This repository contains source, a prebuilt Decky frontend, the Python backend,
and a network-free installer suitable for Batocera Steam Tools.

## Why this fork exists

The former Odin 3 installer cloned Armada's moving `main` branch, overlaid an
older Batocera patch set, and ran npm on the handheld. That became
non-reproducible when upstream interfaces changed. It also allowed the plugin
to overwrite the battery LED policy and inject a Steam launch helper that did
not exist on Batocera.

Version 0.2.0 is pinned to the provenance recorded in `SOURCE.json`. It keeps
the system-owned status LED separate from the joystick rings and uses native
Batocera services for SSH and RSInput calibration.

## Install on Batocera

Extract a release and run as root:

```sh
bash install.sh
```

Decky's `PluginLoader` must already be installed (Steam Tools handles that
first). The installer verifies `PAYLOAD.sha256`, atomically replaces
`/userdata/system/homebrew/plugins/armada-control`, and never uses git, npm, or
the network. If Decky is running, it restarts it. Use `--no-restart` when
installing from an image migration or another service.

The FEX launch helper is installed at
`/userdata/system/bin/batocera-control-game-launch`. It intentionally lives
outside `/userdata/system/scripts`, because Batocera executes every file in
that directory as a game hook. The helper and FEX contract remain in userdata
if the plugin is removed so existing Steam launch options cannot become dead.

### LSFG-VK tab

The unified LSFG tab configures Batocera's system LSFG-VK integration for
Steam. It detects the native and x64/Wine layer files already supplied by the
image and requires the purchased DLL at:

```text
/userdata/system/wine/lossless-scaling/Lossless.dll
```

It does not download or bundle LSFG-VK or Lossless Scaling. Changes apply on
the next Steam/GamepadUI launch. The installer moves an old standalone
`decky-lsfg-vk` plugin to `homebrew/disabled-plugins` so only one control tab is
loaded, while retaining its config and `~/lsfg` script for rollback. Remove the
old `~/lsfg` prefix from per-game Steam launch options before enabling the
global Batocera layer.

## Develop and verify

```sh
npm ci
npm run build
npx tsc --noEmit
python3 -m unittest discover -s tests -v
npm audit
```

`dist/index.js` is committed deliberately. A Batocera target installs the
prebuilt output and does not need Node.js.

Create deterministic release archives with:

```sh
tools/make-release.sh
```

## Batocera integration

The plugin is distributed independently from the Batocera image:

1. A version tag builds and tests the frontend in GitHub Actions.
2. The workflow publishes versioned `.tar.gz` and `.zip` files plus
   `SHA256SUMS` in the GitHub release.
3. Steam Tools installs/updates Decky, downloads this artifact, verifies its
   hash, and runs `install.sh`.

The `swy8750` main branch and 8550 branch only need the release URL/update logic
in Steam Tools. No Node.js build, branch clone, or plugin Buildroot package is
needed on the target. The release is architecture-independent; hardware tabs
feature-detect the services and sysfs interfaces provided by each image.

## Persistence and removal

Plugin settings live under `/userdata/system/configs/batocera-control` (OLED
care retains its existing dedicated config directory). `uninstall.sh` removes
the Decky plugin but keeps settings and the fail-open launch helper. This is
deliberate: removing a helper still referenced by Steam launch options would
make games fail to start.

## License and provenance

GPL-2.0-or-later. See `LICENSE.md`, `THIRD_PARTY_NOTICES.md`, and `SOURCE.json`.

- Armada upstream: <https://github.com/virtudude/armada>
- Odin 3 Batocera integration: <https://github.com/darkplace/batocera-odin3-patches>
- Decky LSFG-VK UI reference: <https://github.com/xXJSONDeruloXx/decky-lsfg-vk>
- LSFG-VK system layer: <https://github.com/PancakeTAS/lsfg-vk>

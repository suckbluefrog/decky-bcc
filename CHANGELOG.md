# Changelog

## 0.2.0 - 2026-07-12

- Prevent joystick LED controls and paddle shortcuts from changing the
  independent battery/status power LED or replacing `leds.conf`.
- Preserve the last joystick-ring brightness across Off/On and serialize UI
  saves to prevent stale slider requests winning races.
- Use Batocera's Dropbear service and persistent SSH setting instead of a
  nonexistent systemd `sshd` unit.
- Save controller calibration in Batocera's native RSInput key/value format,
  apply it live, validate full-range captures, and work without InputPlumber.
- Hide unsupported Armada controller emulation and unavailable power, OLED,
  and paddle services instead of reporting false success.
- Validate paddle bindings, repair Wi-Fi/Bluetooth toggles, and tolerate a
  corrupt saved brightness value.
- Restore the latest upstream compatibility-state RPC integration that the old
  Batocera overlay omitted.
- Install a persistent, fail-open Batocera FEX launch helper before adding it
  to Steam launch options; migrate the old nonexistent Armada helper path.
- Use atomic, durable writes for persistent plugin settings.
- Add bounded privileged-socket responses, per-subsystem config fallbacks,
  source provenance, tests, and reproducible release tooling.
- Merge LSFG-VK controls into a feature-detected tab that configures
  Batocera's built-in native/x64 layers and the standard user-provided
  `/userdata/system/wine/lossless-scaling/Lossless.dll`, without downloading a
  second LSFG runtime.

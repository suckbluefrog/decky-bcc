from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT / "py_modules"))

from armada_control import back_paddles, calibration, joystick_led, lsfg, paddle_actions, power, runtime  # noqa: E402


class JoystickLedTests(unittest.TestCase):
    def test_off_blanks_accents_without_disabling_status_service(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = root / "joystick-led.json"
            config.write_text(
                json.dumps(
                    {
                        "left": {"mode": "solid", "color": "#2080ff", "brightness": 70},
                        "right": {"mode": "solid", "color": "#2080ff", "brightness": 70},
                        "linked": True,
                    }
                ),
                encoding="utf-8",
            )
            led_root = root / "leds"
            accent = led_root / "rgb:l1"
            accent.mkdir(parents=True)
            (accent / "multi_intensity").write_text("1 2 3", encoding="utf-8")
            settings = []
            commands = []
            with (
                mock.patch.object(joystick_led, "CONFIG_PATH", config),
                mock.patch.object(joystick_led, "LED_SYSFS", led_root),
                mock.patch.object(joystick_led, "_settings_set", side_effect=lambda key, value: settings.append((key, value))),
                mock.patch.object(joystick_led, "_run", side_effect=lambda command: commands.append(command) or ""),
            ):
                state = joystick_led.save_state(
                    {"left": {"mode": "off", "color": "#2080ff", "brightness": 0}}
                )

            self.assertEqual(state["config"]["left"]["mode"], "off")
            self.assertEqual(state["config"]["left"]["brightness"], 70)
            self.assertIn(("led.enabled", "1"), settings)
            self.assertIn(("led.colour", "0 0 0"), settings)
            self.assertNotIn(("led.enabled", "0"), settings)
            self.assertFalse(any("stop" in command for command in commands))
            self.assertFalse(any("power-led" in " ".join(command) for command in commands))


class CalibrationTests(unittest.TestCase):
    @staticmethod
    def valid_capture():
        capture = {}
        for name in ("left_x", "left_y", "right_x", "right_y"):
            capture[name] = {"center": 0, "min": -900, "max": 900, "range": 2048}
        for name in ("left_trigger", "right_trigger"):
            capture[name] = {"center": 0, "min": 0, "max": 1500, "range": 1552}
        return capture

    def test_rejects_incomplete_capture(self):
        capture = self.valid_capture()
        capture["right_x"] = {"center": 0, "min": -2, "max": 3, "range": 2048}
        with self.assertRaisesRegex(ValueError, "right_x"):
            calibration.validate_capture(capture)

    def test_reset_writes_native_batocera_format_and_applies_live(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            params = root / "parameters"
            params.mkdir()
            for name in (*calibration.CALIBRATION_PARAMS, "update_params"):
                (params / name).write_text("0", encoding="utf-8")
            target = root / "rsinput-calibration.conf"
            with (
                mock.patch.object(calibration, "RSINPUT_PARAMETERS", params),
                mock.patch.object(calibration, "INPUT_CALIBRATION_CONFIG", target),
                mock.patch.object(calibration, "BATOCERA_CALIBRATION_INIT", root / "missing-init"),
                mock.patch.object(
                    calibration,
                    "controller_state",
                    return_value={"supported": True, "controls": {}, "event": {}, "canApply": True},
                ),
            ):
                state = calibration.reset_calibration_params()

            text = target.read_text(encoding="utf-8")
            self.assertIn("axis_leftx_min=-1024", text)
            self.assertIn("trigger_right_max=1552", text)
            self.assertIn("update_params=1", text)
            self.assertFalse(text.lstrip().startswith("{"))
            self.assertEqual((params / "axis_leftx_min").read_text(encoding="utf-8"), "-1024")
            self.assertEqual((params / "update_params").read_text(encoding="utf-8"), "1")
            self.assertTrue(state["saved"])


class BackPaddleTests(unittest.TestCase):
    def test_rejects_unknown_actions_and_writes_atomically(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            gpio = root / "gpiochip8"
            service = root / "odin_backpaddles"
            gpio.touch()
            service.touch()
            config = root / "back-paddles.json"
            with (
                mock.patch.object(back_paddles, "GPIO_CHIP", gpio),
                mock.patch.object(back_paddles, "SERVICE", service),
                mock.patch.object(back_paddles, "CONFIG_PATH", config),
                mock.patch.object(back_paddles, "_restart_daemon"),
            ):
                with self.assertRaisesRegex(ValueError, "invalid action"):
                    back_paddles.save_state({"m1": "shell:rm -rf /"})
                self.assertFalse(config.exists())
                result = back_paddles.save_state({"m1": "screenshot", "m2": "mouse_left"})

            self.assertEqual(result["bindings"]["m1"], "screenshot")
            self.assertEqual(stat.S_IMODE(config.stat().st_mode), 0o644)


class PaddleActionTests(unittest.TestCase):
    def test_batocera_wifi_and_bluetooth_toggle_both_directions(self):
        commands = []

        def setting(key):
            return {"wifi.enabled": "0", "controllers.bluetooth.enabled": "1"}.get(key, "")

        with (
            mock.patch.object(paddle_actions, "_settings_get", side_effect=setting),
            mock.patch.object(paddle_actions, "_run", side_effect=lambda command: commands.append(command) or ""),
            mock.patch("pathlib.Path.exists", return_value=False),
        ):
            paddle_actions.run_action("wifi_toggle")
            paddle_actions.run_action("bluetooth_toggle")

        self.assertIn(["batocera-wifi", "enable"], commands)
        self.assertIn(["batocera-bluetooth", "disable"], commands)

    def test_corrupt_saved_brightness_does_not_crash(self):
        with tempfile.TemporaryDirectory() as temp:
            saved = Path(temp) / "brightness"
            saved.write_text("not-a-number", encoding="utf-8")
            commands = []
            with (
                mock.patch.object(paddle_actions, "BRIGHTNESS_STATE", saved),
                mock.patch.object(paddle_actions, "_run", side_effect=lambda command: commands.append(command) or "70"),
            ):
                paddle_actions.run_action("brightness_min_toggle")
            self.assertIn(["batocera-brightness", "70"], commands)
            self.assertFalse(saved.exists())


class PersistentRuntimeTests(unittest.TestCase):
    def test_arm_host_survives_fex_x86_personality(self):
        with (
            mock.patch.object(runtime.platform, "machine", return_value="x86_64"),
            mock.patch.object(runtime.Path, "read_bytes", return_value=b"qcom,sm8550 ayn,thor"),
        ):
            self.assertTrue(runtime._arm_host())

    def test_installs_versioned_helper_to_stable_userdata_path(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            wrapper = root / "scripts" / "batocera-control-game-launch"
            contract = root / "config" / "fex-profiles.json"
            with (
                mock.patch.object(runtime, "STABLE_WRAPPER", wrapper),
                mock.patch.object(runtime, "STABLE_FEX_CONTRACT", contract),
                mock.patch.object(runtime, "_arm_host", return_value=True),
            ):
                state = runtime.ensure_runtime()
                second = runtime.ensure_runtime()
            self.assertTrue(state["supported"])
            self.assertTrue(second["supported"])
            self.assertEqual(stat.S_IMODE(wrapper.stat().st_mode), 0o755)
            self.assertIn("default", json.loads(contract.read_text(encoding="utf-8"))["profiles"])

    def test_x86_does_not_offer_or_install_fex_wrapper(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            wrapper = root / "bin" / "batocera-control-game-launch"
            contract = root / "config" / "fex-profiles.json"
            with (
                mock.patch.object(runtime, "STABLE_WRAPPER", wrapper),
                mock.patch.object(runtime, "STABLE_FEX_CONTRACT", contract),
                mock.patch.object(runtime, "_arm_host", return_value=False),
            ):
                state = runtime.ensure_runtime()

            self.assertFalse(state["supported"])
            self.assertEqual(state["path"], "")
            self.assertIn("ARM64", state["reason"])
            self.assertFalse(wrapper.exists())
            self.assertFalse(contract.exists())

    def test_launch_helper_fails_open_when_fex_config_is_missing(self):
        helper = PLUGIN_ROOT / "py_modules" / "batocera-control-game-launch"
        result = subprocess.run(
            [sys.executable, str(helper), "/bin/echo", "game-started"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
            env={**os.environ, "STEAM_COMPAT_APP_ID": "1234"},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "game-started")


class PowerDetectionTests(unittest.TestCase):
    def test_generic_amd_tool_does_not_mislabel_arm_host(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            amd_tdp = root / "batocera-amd-tdp"
            device_tree = root / "compatible"
            amd_tdp.touch()
            device_tree.touch()
            with (
                mock.patch.object(power, "POWER_SCRIPT", root / "missing-odin-power"),
                mock.patch.object(power, "AMD_TDP", amd_tdp),
                mock.patch.object(power, "DEVICE_TREE_COMPAT", device_tree),
                mock.patch.object(power, "SIMPLE_DECKY_TDP", root / "missing-plugin"),
            ):
                self.assertEqual(power.unsupported_reason(), "Odin power service is not installed")

    def test_x86_defers_to_simple_decky_tdp(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            amd_tdp = root / "batocera-amd-tdp"
            plugin = root / "SimpleDeckyTDP" / "plugin.json"
            amd_tdp.touch()
            plugin.parent.mkdir()
            plugin.touch()
            with (
                mock.patch.object(power, "POWER_SCRIPT", root / "missing-odin-power"),
                mock.patch.object(power, "AMD_TDP", amd_tdp),
                mock.patch.object(power, "DEVICE_TREE_COMPAT", root / "missing-device-tree"),
                mock.patch.object(power, "SIMPLE_DECKY_TDP", plugin),
            ):
                self.assertIn("SimpleDeckyTDP", power.unsupported_reason())


class LsfgTests(unittest.TestCase):
    def test_uses_system_layers_and_persists_steam_scope(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            native_lib = root / "usr/lib/liblsfg-vk.so"
            native_layer = root / "usr/share/vulkan/explicit_layer.d/VkLayer_LS_frame_generation.json"
            dll = root / "userdata/system/wine/lossless-scaling/Lossless.dll"
            for path in (native_lib, native_layer, dll):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            store = {}
            writes = []

            def command(args, **_kwargs):
                if args[0] == lsfg.SETTINGS_GET:
                    return subprocess.CompletedProcess(args, 0, store.get(args[1], ""), "")
                if args[0] == lsfg.SETTINGS_SET:
                    self.assertEqual(args[1], "--validate")
                    pairs = args[2:]
                    self.assertEqual(len(pairs) % 2, 0)
                    writes.append(pairs)
                    for index in range(0, len(pairs), 2):
                        store[pairs[index]] = pairs[index + 1]
                    return subprocess.CompletedProcess(args, 0, "", "")
                raise AssertionError(args)

            with (
                mock.patch.object(lsfg, "DEFAULT_DLL", dll),
                mock.patch.object(lsfg, "NATIVE_LIBRARY", native_lib),
                mock.patch.object(lsfg, "NATIVE_LAYER", native_layer),
                mock.patch.object(lsfg, "WINE_LIBRARY", root / "missing-x64-lib"),
                mock.patch.object(lsfg, "WINE_LAYER", root / "missing-x64-layer"),
                mock.patch.object(lsfg, "LEGACY_PLUGIN", root / "missing-plugin"),
                mock.patch.object(lsfg, "LEGACY_CONFIG", root / "missing-config"),
                mock.patch.object(lsfg, "LEGACY_SCRIPTS", (root / "missing-script",)),
                mock.patch.object(lsfg.platform, "machine", return_value="aarch64"),
                mock.patch.object(lsfg, "run_cmd", side_effect=command),
            ):
                initial = lsfg.get_state()
                saved = lsfg.save_state(
                    {
                        "enabled": True,
                        "multiplier": "3",
                        "flowScale": "0.5",
                        "performanceMode": True,
                        "hdrMode": False,
                        "presentMode": "mailbox",
                    }
                )

            self.assertTrue(initial["ready"])
            self.assertEqual(initial["config"]["flowScale"], "0.75")
            self.assertEqual(store["steam.lsfg_vk"], "1")
            self.assertEqual(store["steam.lsfg_vk_dll"], str(dll))
            self.assertEqual(store["steam.lsfg_vk_multiplier"], "3")
            self.assertEqual(store["steam.lsfg_vk_flow_scale"], "0.5")
            self.assertEqual(store["steam.lsfg_vk_present_mode"], "mailbox")
            self.assertEqual(len(writes), 1)
            self.assertEqual(writes[0][-2:], ["steam.lsfg_vk", "1"])
            self.assertTrue(saved["config"]["enabled"])
            self.assertNotIn("download", " ".join(store))

    def test_refuses_enable_without_purchased_dll(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            native_lib = root / "liblsfg-vk.so"
            native_layer = root / "VkLayer_LS_frame_generation.json"
            native_lib.touch()
            native_layer.touch()

            def command(args, **_kwargs):
                return subprocess.CompletedProcess(args, 0, "", "")

            with (
                mock.patch.object(lsfg, "DEFAULT_DLL", root / "missing-Lossless.dll"),
                mock.patch.object(lsfg, "NATIVE_LIBRARY", native_lib),
                mock.patch.object(lsfg, "NATIVE_LAYER", native_layer),
                mock.patch.object(lsfg, "WINE_LIBRARY", root / "missing-x64-lib"),
                mock.patch.object(lsfg, "WINE_LAYER", root / "missing-x64-layer"),
                mock.patch.object(lsfg, "LEGACY_PLUGIN", root / "missing-plugin"),
                mock.patch.object(lsfg, "LEGACY_CONFIG", root / "missing-config"),
                mock.patch.object(lsfg, "LEGACY_SCRIPTS", (root / "missing-script",)),
                mock.patch.object(lsfg, "run_cmd", side_effect=command),
            ):
                with self.assertRaisesRegex(RuntimeError, "Lossless.dll"):
                    lsfg.save_state({"enabled": True, "multiplier": "2", "flowScale": "0.75"})
                with self.assertRaisesRegex(ValueError, "boolean"):
                    lsfg.save_state({"enabled": "true", "multiplier": "2", "flowScale": "0.75"})


if __name__ == "__main__":
    unittest.main()

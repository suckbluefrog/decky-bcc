"""Non-grabbing rsinput listener for AYN rear-paddle shortcuts."""

from __future__ import annotations

import json
import os
import queue
import select
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Callable

from .back_paddles import (
    CONFIG_PATH,
    RSINPUT_M1_CODE,
    RSINPUT_M2_CODE,
    load_bindings,
    open_rsinput_device,
)
from .paddle_actions import run_action

try:
    from evdev import ecodes
except ImportError:
    ecodes = None

LOG_TAG = "batocera-control-paddles"
DEBOUNCE_SECONDS = 0.25

BTN_START = 315
BTN_BACK = 278
BTN_SELECT = 314
BTN_HOME = 316

_PADDLE_TAPS = {
    RSINPUT_M1_CODE: "m1",
    RSINPUT_M2_CODE: "m2",
}
_CHORDS = (
    ("m1_m2", frozenset((RSINPUT_M1_CODE, RSINPUT_M2_CODE))),
    ("m1_start", frozenset((RSINPUT_M1_CODE, BTN_START))),
    ("m1_back", frozenset((RSINPUT_M1_CODE, BTN_BACK))),
    ("select_m2", frozenset((BTN_SELECT, RSINPUT_M2_CODE))),
    ("home_m2", frozenset((BTN_HOME, RSINPUT_M2_CODE))),
)


def log(message: str) -> None:
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    print(f"{stamp} {LOG_TAG}: {message}", flush=True)


class PaddleInterpreter:
    """Convert key transitions into one tap or chord slot per paddle hold."""

    def __init__(self, fire: Callable[[str], None]):
        self._fire = fire
        self._held: set[int] = set()
        self._combo_done = False

    def reset(self) -> None:
        self._held.clear()
        self._combo_done = False

    def handle(self, code: int, value: int) -> None:
        # Ignore autorepeat; rsinput buttons normally emit only 0/1.
        if value not in (0, 1):
            return

        if value == 1:
            self._held.add(code)
            if self._combo_done:
                return
            for slot, chord in _CHORDS:
                if code in chord and chord.issubset(self._held):
                    self._combo_done = True
                    self._fire(slot)
                    return

            # Home is Batocera's normal joystick-hotkey modifier. Suppress a
            # direct paddle tap for Home+M1 too, even though BCC has no separate
            # action slot for that chord, so the in-game mapping never double
            # fires with the Decky tap action.
            if BTN_HOME in self._held and any(paddle in self._held for paddle in _PADDLE_TAPS):
                self._combo_done = True
            return

        was_held = code in self._held
        self._held.discard(code)
        tap_slot = _PADDLE_TAPS.get(code)
        if tap_slot is not None and was_held and not self._combo_done:
            self._fire(tap_slot)
        if not any(paddle in self._held for paddle in _PADDLE_TAPS):
            self._combo_done = False


class ActionDispatcher:
    """Reload bindings and execute actions without blocking the input reader."""

    def __init__(self):
        self._bindings = load_bindings()
        self._config_mtime = self._mtime()
        self._last_action: dict[str, float] = {}
        self._queue: queue.Queue[tuple[str, str] | None] = queue.Queue(maxsize=32)
        self._worker = threading.Thread(target=self._run, name="paddle-actions", daemon=True)
        self._worker.start()

    @staticmethod
    def _mtime() -> int:
        try:
            return CONFIG_PATH.stat().st_mtime_ns
        except OSError:
            return 0

    def reload_if_changed(self) -> None:
        mtime = self._mtime()
        if mtime == self._config_mtime:
            return
        self._config_mtime = mtime
        self._bindings = load_bindings()
        log("bindings reloaded")

    def fire(self, slot: str) -> None:
        self.reload_if_changed()
        action = str(self._bindings.get(slot, "none") or "none")
        if action == "none":
            return
        now = time.monotonic()
        if now - self._last_action.get(slot, 0.0) < DEBOUNCE_SECONDS:
            return
        self._last_action[slot] = now
        try:
            self._queue.put_nowait((slot, action))
        except queue.Full:
            log(f"action queue full; dropped {slot}")

    def close(self) -> None:
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass
        self._worker.join(timeout=2)

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                return
            slot, action = item
            try:
                run_action(action)
                log(f"{slot} -> {action}")
            except Exception as exc:  # keep the listener alive after one failed action
                log(f"{slot} action failed: {exc}")


def run() -> int:
    if ecodes is None:
        log("python-evdev is unavailable")
        return 1

    stopping = threading.Event()

    def stop(_signum=None, _frame=None) -> None:
        stopping.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    dispatcher = ActionDispatcher()
    interpreter = PaddleInterpreter(dispatcher.fire)
    last_missing_log = 0.0
    try:
        while not stopping.is_set():
            device = open_rsinput_device()
            if device is None:
                now = time.monotonic()
                if now - last_missing_log >= 30:
                    log("waiting for an AYN rsinput paddle device")
                    last_missing_log = now
                stopping.wait(1.0)
                continue

            interpreter.reset()
            name = str(getattr(device, "name", "AYN gamepad") or "AYN gamepad")
            path = str(getattr(device, "path", "") or "")
            log(f"listening on {name} ({path}) without grabbing it")
            try:
                # Older Batocera python-evdev releases do not expose
                # InputDevice.set_nonblocking(), although the fd itself can be
                # switched portably through the standard library.
                os.set_blocking(device.fileno(), False)
                while not stopping.is_set():
                    dispatcher.reload_if_changed()
                    try:
                        readable, _, _ = select.select([device.fileno()], [], [], 0.5)
                    except (OSError, ValueError):
                        break
                    if not readable:
                        continue
                    try:
                        events = device.read()
                    except BlockingIOError:
                        continue
                    except OSError:
                        break
                    for event in events:
                        if event.type == ecodes.EV_KEY:
                            interpreter.handle(int(event.code), int(event.value))
            finally:
                device.close()
                interpreter.reset()
            if not stopping.is_set():
                log("input device disconnected; rescanning")
                stopping.wait(0.5)
    finally:
        dispatcher.close()
    return 0


def probe() -> int:
    # Installation must validate that native python-evdev can actually open
    # the device, not merely that the architecture-neutral sysfs probe sees it.
    device = open_rsinput_device()
    if device is None:
        return 1
    try:
        info = {
            "name": str(getattr(device, "name", "") or "AYN gamepad"),
            "path": str(getattr(device, "path", "") or ""),
            "m1Code": RSINPUT_M1_CODE,
            "m2Code": RSINPUT_M2_CODE,
        }
        print(json.dumps(info, sort_keys=True))
    finally:
        device.close()
    return 0


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--probe":
        raise SystemExit(probe())
    if len(sys.argv) != 1:
        print("usage: python3 -m armada_control.paddle_daemon [--probe]", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(run())

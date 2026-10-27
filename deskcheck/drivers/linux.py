"""Linux driver via xdotool + scrot (both optional, stdlib subprocess only).

If either tool is missing, construction raises DriverUnavailable with a
clear message instead of failing mid-run. Coordinates are primary-monitor
pixels, matching the PyAutoGUI convention; the runner records the
resolution with every screenshot (in the JSONL log's screenshot entry
via the driver's resolution, surfaced in the report).
"""
from __future__ import annotations

import shutil
import subprocess
import time

from .base import Driver
from ..errors import DriverUnavailable


def _run(args, timeout=30):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)


class LinuxDriver(Driver):
    name = "linux"

    def __init__(self):
        if not shutil.which("xdotool"):
            raise DriverUnavailable("linux driver unavailable: 'xdotool' not found")
        if not shutil.which("scrot"):
            raise DriverUnavailable("linux driver unavailable: 'scrot' not found")
        self._focused = None

    def launch(self, app_name, command=None):
        if command:
            subprocess.Popen(command, shell=True)  # noqa: S602 - command comes
            # from the operator-written allowlist config, never from a test file
        self._focused = app_name

    def foreground_window(self):
        out = _run(["xdotool", "getactivewindow", "getwindowname"])
        name = out.stdout.strip()
        return name or self._focused

    def click(self, x, y):
        _run(["xdotool", "mousemove", str(x), str(y), "click", "1"])

    def type_text(self, text):
        _run(["xdotool", "type", "--", text])

    def press_key(self, key):
        _run(["xdotool", "key", key])

    def screenshot(self, path):
        _run(["scrot", path])
        return path

    def wait_window(self, window, timeout_ms):
        deadline = time.time() + timeout_ms / 1000.0
        while time.time() < deadline:
            if window in (self.foreground_window() or ""):
                return True
            time.sleep(0.25)
        return False

    def resolution(self):
        out = _run(["xdotool", "getdisplaygeometry"])
        try:
            w, h = out.stdout.strip().split()
            return (int(w), int(h))
        except Exception:
            return (0, 0)

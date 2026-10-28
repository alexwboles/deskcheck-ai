"""MockDriver: hermetic, deterministic driver for tests and demos.

Scripted windows: ``windows`` is the list of window names the mock
pretends exist. ``launch`` focuses a scripted window (or, for demo
flexibility, any app name when ``windows`` is empty — the demo config
passes an explicit list, and tests pass explicit lists too).
Screenshots are deterministic PNGs: the pixel colour is derived from
SHA-256 of (screenshot path basename + focused window), so the same
script always produces the same pixels, and a tampered baseline (a
different solid colour) always fails pixel-diff.
"""
from __future__ import annotations

import hashlib
import os

from .base import Driver
from ..errors import PermissionDenied
from ..pngutil import encode_png


class MockDriver(Driver):
    name = "mock"

    def __init__(self, windows=None, width=32, height=24):
        self._windows = list(windows or [])
        self._focused = None
        self._text = ""
        self.width = width
        self.height = height
        self.actions = []  # recorded for tests: list of tuples

    def launch(self, app_name, command=None):
        self.actions.append(("launch", app_name))
        if self._windows and app_name not in self._windows:
            # Still "launch" but no window appears: window-visible fails.
            self._focused = None
            return
        self._focused = app_name

    def foreground_window(self):
        return self._focused

    def check_input_target(self, app_name):
        # The simulated desktop has no OS windows or focus race. Do not copy
        # this title-only check into a native driver.
        if not app_name or self.foreground_window() != app_name:
            raise PermissionDenied("input denied: simulated focus left the launched app")

    def click(self, x, y):
        self.actions.append(("click", x, y))

    def type_text(self, text):
        self.actions.append(("type", text))
        self._text += text

    def read_text(self):
        return self._text

    def press_key(self, key):
        self.actions.append(("key", key))

    def screenshot(self, path):
        seed = hashlib.sha256(
            f"{os.path.basename(path)}|{self._focused or ''}".encode()).digest()
        rgb = (seed[0], seed[1], seed[2])
        # Vary a corner block by window so different windows differ.
        rows = []
        for r in range(self.height):
            row = []
            for c in range(self.width):
                if r < 4 and c < 4:
                    row.append(((seed[3] + r * 7) % 256,
                                (seed[4] + c * 11) % 256, seed[5]))
                else:
                    row.append(rgb)
            rows.append(row)
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(encode_png(self.width, self.height, rows))
        self.actions.append(("screenshot", path))
        return path

    def wait_window(self, window, timeout_ms):
        return self._focused == window

    def resolution(self):
        return (self.width, self.height)

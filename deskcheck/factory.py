"""Driver factory: pick a backend by name, fail clearly if unavailable."""
from __future__ import annotations

import platform

from .drivers.mock import MockDriver
from .errors import DriverUnavailable


def get_driver(name: str, mock_windows=None):
    name = (name or "auto").lower()
    if name == "mock":
        return MockDriver(windows=mock_windows)
    if name == "linux":
        from .drivers.linux import LinuxDriver
        return LinuxDriver()
    if name == "windows":
        from .drivers.windows import WindowsDriver
        return WindowsDriver()
    if name == "auto":
        raise DriverUnavailable("Choose --driver mock or --driver windows explicitly; auto never substitutes a simulated pass")
    raise DriverUnavailable(f"unknown driver '{name}' (mock|linux|windows|auto)")

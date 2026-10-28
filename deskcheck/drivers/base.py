"""Driver interface. A driver owns the real (or fake) desktop."""
from __future__ import annotations

from ..errors import PermissionDenied


class Driver:
    name = "base"

    def launch(self, app_name: str, command=None):
        raise NotImplementedError

    def foreground_window(self):
        """Return the title/name of the foreground window, or None."""
        raise NotImplementedError

    def check_input_target(self, app_name: str):
        """Fail closed unless the driver can verify and contain input.

        A cached launch name or matching window title is not process identity,
        and global coordinates can click outside that window. Native drivers
        must implement target identity, bounds and focus-race protection before
        overriding this guard. This method intentionally denies by default.
        """
        raise PermissionDenied(
            f"input denied: driver '{self.name}' has no verified input target; "
            "native input is disabled pending process/window isolation")

    def click(self, x: int, y: int):
        raise NotImplementedError

    def type_text(self, text: str):
        raise NotImplementedError

    def press_key(self, key: str):
        raise NotImplementedError

    def screenshot(self, path: str) -> str:
        """Capture the screen (or foreground window) to path; return path."""
        raise NotImplementedError

    def wait_window(self, window: str, timeout_ms: int) -> bool:
        raise NotImplementedError

    def resolution(self):
        return (0, 0)

    def read_text(self):
        raise PermissionDenied("Selected-control text is unsupported by this driver")

    def close(self):
        pass

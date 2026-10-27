"""Driver interface. A driver owns the real (or fake) desktop."""
from __future__ import annotations


class Driver:
    name = "base"

    def launch(self, app_name: str, command=None):
        raise NotImplementedError

    def foreground_window(self):
        """Return the title/name of the foreground window, or None."""
        raise NotImplementedError

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

    def close(self):
        pass

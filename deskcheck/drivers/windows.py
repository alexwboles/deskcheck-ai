"""Windows driver via PowerShell + .NET (no new dependencies).

Screenshots use System.Drawing (Graphics.CopyFromScreen) saved as PNG;
input uses System.Windows.Forms.SendKeys / mouse via user32 through
PowerShell Add-Type. This is a standalone reimplementation of the
well-known PowerShell/.NET approach; it shares no code with any other
project. On non-Windows hosts (or without PowerShell) construction
raises DriverUnavailable.
"""
from __future__ import annotations

import platform
import shutil
import subprocess
import time

from .base import Driver
from ..errors import DriverUnavailable

_PS_SCREENSHOT = r"""
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
$bmp = New-Object System.Drawing.Bitmap([System.Windows.Forms.Screen]::PrimaryScreen.Bounds.Width, [System.Windows.Forms.Screen]::PrimaryScreen.Bounds.Height)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen(0, 0, 0, 0, $bmp.Size)
$bmp.Save('{path}', [System.Drawing.Imaging.ImageFormat]::Png)
"""


class WindowsDriver(Driver):
    name = "windows"

    def __init__(self):
        if platform.system() != "Windows":
            raise DriverUnavailable("windows driver unavailable: not running on Windows")
        if not shutil.which("powershell"):
            raise DriverUnavailable("windows driver unavailable: 'powershell' not found")
        self._focused = None

    def _ps(self, script, timeout=30):
        return subprocess.run(["powershell", "-NoProfile", "-Command", script],
                              capture_output=True, text=True, timeout=timeout)

    def launch(self, app_name, command=None):
        if command:
            subprocess.Popen(["powershell", "-NoProfile", "-Command",
                              f"Start-Process {command}"])
        self._focused = app_name

    def foreground_window(self):
        out = self._ps(
            "Add-Type -AssemblyName System.Windows.Forms; "
            "(Get-Process | Where-Object { $_.MainWindowTitle } | "
            "Sort-Object StartTime -Descending | Select-Object -First 1).MainWindowTitle")
        return out.stdout.strip() or self._focused

    def click(self, x, y):
        self._ps(f"Add-Type -AssemblyName System.Windows.Forms; "
                 f"[System.Windows.Forms.Cursor]::Position = New-Object System.Drawing.Point({x},{y}); "
                 "Add-Type -MemberDefinition '[DllImport(\"user32.dll\")] public static extern void mouse_event(int f,int x,int y,int d,int e);' -Name Win32 -Namespace W; "
                 "[W.Win32]::mouse_event(2,0,0,0,0); [W.Win32]::mouse_event(4,0,0,0,0)")

    def type_text(self, text):
        esc = text.replace("'", "''")
        self._ps(f"Add-Type -AssemblyName System.Windows.Forms; "
                 f"[System.Windows.Forms.SendKeys]::SendWait('{esc}')")

    def press_key(self, key):
        self._ps(f"Add-Type -AssemblyName System.Windows.Forms; "
                 f"[System.Windows.Forms.SendKeys]::SendWait('{{{key}}}')")

    def screenshot(self, path):
        self._ps(_PS_SCREENSHOT.format(path=path.replace("'", "''")))
        return path

    def wait_window(self, window, timeout_ms):
        deadline = time.time() + timeout_ms / 1000.0
        while time.time() < deadline:
            if window in (self.foreground_window() or ""):
                return True
            time.sleep(0.25)
        return False

    def resolution(self):
        out = self._ps("[System.Windows.Forms.Screen]::PrimaryScreen.Bounds.Size")
        try:
            parts = out.stdout.replace("{Width=", "").replace("Height=", "") \
                .replace("}", "").strip().split(",")
            return (int(parts[0]), int(parts[1]))
        except Exception:
            return (0, 0)

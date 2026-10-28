"""Safety regressions use simulated desktops only; never inject OS input."""
import os
from pathlib import Path
import tempfile
import unittest
import uuid

from deskcheck.drivers.base import Driver
from deskcheck.drivers.mock import MockDriver
from deskcheck.drivers.linux import LinuxDriver
from deskcheck.drivers.windows import WindowsDriver
from deskcheck.errors import PermissionDenied
from deskcheck.mcp_server import MCPServer
from deskcheck.permissions import PermissionConfig
from deskcheck.runner import run_test


class FocusLostDriver(MockDriver):
    def launch(self, app_name, command=None):
        super().launch(app_name, command)
        self._focused = "not-allowlisted"


class UnverifiedDriver(Driver):
    """An apparently focused driver without verified target isolation."""
    name = "unverified-test"

    def __init__(self):
        self.actions = []

    def launch(self, app_name, command=None):
        self.actions.append(("launch", app_name))

    def foreground_window(self):
        return "demo-app"

    def click(self, x, y):
        self.actions.append(("click", x, y))


class TestInputSafety(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config = PermissionConfig.from_dict({"apps": {"demo-app": {}}})

    def run_steps(self, driver, steps):
        path = Path(self.tmp.name) / "test.yaml"
        path.write_text("version: 1\nname: guard\napp: demo-app\nsteps:\n"
                        "  - {type: launch, app: demo-app}\n" + steps,
                        encoding="utf-8")
        return run_test(str(path), self.config, driver,
                        os.path.join(self.tmp.name, "out-"+uuid.uuid4().hex))

    def test_runner_refuses_focus_drift_for_every_input(self):
        for step in ("{type: click, x: 1, y: 2}",
                     "{type: type, text: synthetic}",
                     "{type: key, key: Enter}"):
            with self.subTest(step=step):
                driver = FocusLostDriver()
                result = self.run_steps(driver, "  - " + step + "\n")
                self.assertEqual(result.status, "fail")
                self.assertEqual(driver.actions, [("launch", "demo-app")])

    def test_unverified_driver_cannot_inject_input(self):
        driver = UnverifiedDriver()
        result = self.run_steps(driver, "  - {type: click, x: 1, y: 2}\n")
        self.assertEqual(result.status, "fail")
        self.assertEqual(driver.actions, [("launch", "demo-app")])

    def test_mcp_refuses_focus_drift_for_every_input(self):
        for tool, arguments in (("click", {"x": 1, "y": 2}),
                                ("type_text", {"text": "synthetic"}),
                                ("press_key", {"key": "Enter"})):
            with self.subTest(tool=tool):
                server = MCPServer(self.config)
                server.shot_dir = os.path.join(self.tmp.name, "screenshots")
                server.driver = FocusLostDriver()
                self.assertFalse(server.call_tool("launch_app", {"app": "demo-app"})["isError"])
                self.assertTrue(server.call_tool(tool, arguments)["isError"])
                self.assertEqual(server.driver.actions, [("launch", "demo-app")])

    def test_mcp_unverified_driver_returns_tool_error(self):
        server = MCPServer(self.config)
        server.driver = UnverifiedDriver()
        server.call_tool("launch_app", {"app": "demo-app"})
        result = server.call_tool("click", {"x": 1, "y": 2})
        self.assertTrue(result["isError"])
        self.assertEqual(server.driver.actions, [("launch", "demo-app")])

    def test_base_driver_denies_even_allowlisted_title(self):
        with self.assertRaises(PermissionDenied):
            UnverifiedDriver().check_input_target("demo-app")

    def test_native_drivers_inherit_default_deny_without_os_calls(self):
        # Bypass constructors: no PowerShell, xdotool, window or OS API calls.
        for driver_class in (WindowsDriver, LinuxDriver):
            with self.subTest(driver=driver_class.name):
                driver = object.__new__(driver_class)
                with self.assertRaises(PermissionDenied):
                    driver.check_input_target("demo-app")

    def test_mock_allows_matching_target(self):
        driver = MockDriver()
        result = self.run_steps(driver, "  - {type: click, x: 1, y: 2}\n")
        self.assertEqual(result.status, "pass")
        self.assertIn(("click", 1, 2), driver.actions)


if __name__ == "__main__":
    unittest.main()

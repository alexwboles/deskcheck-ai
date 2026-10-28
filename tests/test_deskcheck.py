"""Unit + e2e tests for deskcheck-ai (unittest, stdlib only, no network)."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from deskcheck.assertions import assert_pixel_diff, pixel_diff
from deskcheck.drivers.mock import MockDriver
from deskcheck.errors import AssertionFailed, ParseError, PermissionDenied
from deskcheck.parser import parse_test
from deskcheck.permissions import PermissionConfig
from deskcheck.pngutil import decode_png, solid_png
from deskcheck.runner import run_test
from deskcheck.mcp_server import MCPServer

ROOT = os.path.join(os.path.dirname(__file__), "..")


def cfg():
    return PermissionConfig.from_dict({"apps": {
        "demo-app": {"command": "demo-app", "category": "app"},
        "vault": {"category": "password-manager"},
        "keychain": {"category": "credential-store"},
        "settings": {"category": "system-settings"},
        "browser-plain": {"category": "browser"},
        "browser-throw": {"category": "browser", "throwaway_profile": True},
    }})


def write(tmp, name, text):
    path = os.path.join(tmp, name)
    with open(path, "w") as fh:
        fh.write(text)
    return path


DEMO = """version: 1
name: demo
app: demo-app
steps:
  - {type: launch, app: demo-app}
  - {type: screenshot, name: main}
  - {type: assert, kind: window-visible, window: demo-app}
  - {type: assert, kind: screenshot-saved, screenshot: main}
"""


class TestParser(unittest.TestCase):
    def test_valid(self):
        t = parse_test(DEMO)
        self.assertEqual(t["app"], "demo-app")
        self.assertEqual(len(t["steps"]), 4)

    def test_unknown_step_rejected(self):
        with self.assertRaises(ParseError) as cm:
            parse_test(DEMO.replace("screenshot", "shell", 1))
        self.assertIn("unknown step type", str(cm.exception))

    def test_exec_key_rejected(self):
        bad = DEMO + ""  # steps are data, never code
        bad = bad.replace("{type: screenshot, name: main}",
                          "{type: screenshot, name: main, exec: 'rm -rf /'}")
        with self.assertRaises(ParseError):
            parse_test(bad)

    def test_forbidden_top_level_key(self):
        with self.assertRaises(ParseError):
            parse_test("version: 1\nname: x\napp: demo-app\n"
                       "steps: []\ncommand: ls\n")

    def test_unknown_key_in_step(self):
        with self.assertRaises(ParseError):
            parse_test(DEMO.replace("name: main", "name: main, shell: true"))

    def test_non_list_steps(self):
        with self.assertRaises(ParseError):
            parse_test("version: 1\nname: x\napp: demo-app\nsteps: nope\n")

    def test_bad_assert_kind(self):
        with self.assertRaises(ParseError):
            parse_test(DEMO.replace("window-visible", "is-magic"))

    def test_missing_top_key(self):
        with self.assertRaises(ParseError):
            parse_test("version: 1\nname: x\nsteps: []\n")


class TestPermissions(unittest.TestCase):
    def test_allow(self):
        self.assertEqual(cfg().check_launch("demo-app").name, "demo-app")

    def test_default_deny_unknown(self):
        with self.assertRaises(PermissionDenied):
            cfg().check_launch("not-listed")

    def test_denied_categories(self):
        for name in ("vault", "keychain", "settings"):
            with self.assertRaises(PermissionDenied, msg=name):
                cfg().check_launch(name)

    def test_browser_needs_throwaway(self):
        with self.assertRaises(PermissionDenied):
            cfg().check_launch("browser-plain")
        self.assertEqual(cfg().check_launch("browser-throw").name, "browser-throw")

    def test_input_needs_focused_allowed_app(self):
        with self.assertRaises(PermissionDenied):
            cfg().check_input(None)
        with self.assertRaises(PermissionDenied):
            cfg().check_input("vault")


class TestAssertions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def _png(self, name, rgb):
        path = os.path.join(self.tmp, name)
        with open(path, "wb") as fh:
            fh.write(solid_png(4, 4, rgb))
        return path

    def test_pixel_diff_identical_passes(self):
        a = self._png("a.png", (10, 20, 30))
        b = self._png("b.png", (10, 20, 30))
        r = pixel_diff(a, b)
        self.assertTrue(r.passed)
        self.assertEqual(r.ratio, 0.0)

    def test_pixel_diff_total_mismatch_fails(self):
        a = self._png("a.png", (10, 20, 30))
        b = self._png("b.png", (200, 20, 30))
        with self.assertRaises(AssertionFailed):
            assert_pixel_diff(a, b)

    def test_tolerance_edge(self):
        # Gap exactly at tolerance passes (differs only when gap > thresh).
        a = self._png("a.png", (10, 20, 30))
        b = self._png("b.png", (10 + 25, 20, 30))  # gap 25
        r = pixel_diff(a, b, tolerance=25 / 255.0, max_diff_ratio=1.0)
        self.assertTrue(r.passed)
        r2 = pixel_diff(a, b, tolerance=24 / 255.0, max_diff_ratio=0.0)
        self.assertFalse(r2.passed)

    def test_max_diff_ratio_edge(self):
        # 4x4 = 16 px; one row (4 px) differs -> ratio 0.25.
        from deskcheck.pngutil import encode_png
        rows_a = [[(0, 0, 0)] * 4 for _ in range(4)]
        rows_b = [[(255, 0, 0)] * 4] + [[(0, 0, 0)] * 4 for _ in range(3)]
        pa, pb = os.path.join(self.tmp, "a.png"), os.path.join(self.tmp, "b.png")
        for p, rows in ((pa, rows_a), (pb, rows_b)):
            with open(p, "wb") as fh:
                fh.write(encode_png(4, 4, rows))
        self.assertTrue(pixel_diff(pa, pb, max_diff_ratio=0.25).passed)
        self.assertFalse(pixel_diff(pa, pb, max_diff_ratio=0.24).passed)

    def test_missing_baseline_message(self):
        a = self._png("a.png", (0, 0, 0))
        with self.assertRaises(AssertionFailed) as cm:
            pixel_diff(a, os.path.join(self.tmp, "nope.png"))
        self.assertIn("baseline missing", str(cm.exception))

    def test_png_roundtrip(self):
        path = self._png("x.png", (1, 2, 3))
        w, h, rows = decode_png(Path(path).read_bytes())
        self.assertEqual((w, h), (4, 4))
        self.assertEqual(rows[0][0][:3], (1, 2, 3))


class TestRunnerE2E(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def _run(self, text, **kw):
        test = write(self.tmp, "t.yaml", text)
        out = os.path.join(self.tmp, "out")
        kw.setdefault("config", cfg())
        kw.setdefault("driver", MockDriver(windows=["demo-app"]))
        return run_test(test, out_dir=out, **kw), out

    def test_full_pass_loop(self):
        result, out = self._run(DEMO)
        self.assertEqual(result.status, "pass")
        self.assertTrue(os.path.isfile(os.path.join(out, "report.md")))
        self.assertTrue(os.path.isfile(os.path.join(out, "report.html")))
        entries = [json.loads(l) for l in Path(out,"actions.jsonl").read_text().splitlines()]
        self.assertEqual(len(entries), 4)
        self.assertTrue(all("timestamp" in e and "outcome" in e for e in entries))
        self.assertTrue(os.path.isfile(
            os.path.join(out, "screenshots", "main.png")))

    def test_denied_app_blocked_and_logged(self):
        result, out = self._run(
            "version: 1\nname: denied\napp: vault\n"
            "steps:\n  - {type: launch, app: vault}\n")
        self.assertEqual(result.status, "fail")
        log = Path(out,"actions.jsonl").read_text()
        self.assertIn("denied", log)

    def test_tampered_baseline_fails(self):
        # Accept a baseline, then replace it with a different colour.
        text = ("version: 1\nname: pd\napp: demo-app\nsteps:\n"
                "  - {type: launch, app: demo-app}\n"
                "  - {type: screenshot, name: main}\n"
                "  - {type: assert, kind: pixel-diff, screenshot: main, "
                "baseline: main.png}\n")
        test = write(self.tmp, "pd.yaml", text)
        run_test(test, config=cfg(), driver=MockDriver(windows=["demo-app"]),
                 out_dir=os.path.join(self.tmp, "o1"), update_baselines=True)
        base = os.path.join(self.tmp, "baselines", "main.png")
        self.assertTrue(os.path.isfile(base))
        with open(base, "wb") as fh:
            fh.write(solid_png(32, 24, (255, 0, 0)))  # tampered: solid red
        result = run_test(test, config=cfg(),
                          driver=MockDriver(windows=["demo-app"]),
                          out_dir=os.path.join(self.tmp, "o2"))
        self.assertEqual(result.status, "fail")
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, "o2",
                                                    "diff-main.png")))

    def test_timeout_fails(self):
        result, _ = self._run(
            "version: 1\nname: to\napp: demo-app\nsteps:\n"
            "  - {type: launch, app: demo-app}\n"
            "  - {type: wait, ms: 999999}\n",
            timeout_ms=1000)
        self.assertEqual(result.status, "fail")
        self.assertIn("timeout", result.failures[0].lower())

    def test_max_steps_fails(self):
        steps = "\n".join(f"  - {{type: wait, ms: 1}}" for _ in range(5))
        result, _ = self._run(
            f"version: 1\nname: ms\napp: demo-app\nsteps:\n"
            f"  - {{type: launch, app: demo-app}}\n{steps}\n", max_steps=3)
        self.assertEqual(result.status, "fail")
        self.assertIn("max-steps", result.failures[0])

    def test_html_no_rounded_no_gradient(self):
        result, out = self._run(DEMO)
        page = Path(out,"report.html").read_text(encoding="utf-8")
        self.assertNotIn("linear-gradient", page)
        self.assertNotIn("border-radius:8", page)
        self.assertIn("border-radius:0", page)


class TestMCP(unittest.TestCase):
    def test_handshake_and_tools_list(self):
        srv = MCPServer(config=cfg(), driver_name="mock")
        init = srv.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                           "params": {"protocolVersion": "2024-11-05"}})
        self.assertEqual(init["result"]["serverInfo"]["name"], "deskcheck")
        lst = srv.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = [t["name"] for t in lst["result"]["tools"]]
        self.assertEqual(names, ["launch_app", "click", "type_text",
                                 "press_key", "screenshot", "assert_window",
                                 "run_test"])

    def test_tool_failure_is_isError_not_transport_error(self):
        srv = MCPServer(config=cfg(), driver_name="mock")
        resp = srv.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                           "params": {"name": "launch_app",
                                      "arguments": {"app": "vault"}}})
        self.assertNotIn("error", resp)
        self.assertTrue(resp["result"]["isError"])
        self.assertIn("denied", resp["result"]["content"][0]["text"])

    def test_ping(self):
        srv = MCPServer(config=cfg(), driver_name="mock")
        self.assertEqual(srv.handle({"jsonrpc": "2.0", "id": 9,
                                     "method": "ping"})["result"], {})


class TestCLI(unittest.TestCase):
    def test_cli_pass_and_fail_exit_codes(self):
        demo = write(tempfile.mkdtemp(), "d.yaml", DEMO)
        cfg_path = os.path.join(ROOT, "examples", "config.yaml")
        ok = subprocess.run([sys.executable, "-m", "deskcheck", "run", demo,
                             "--config", cfg_path, "--driver", "mock",
                             "--mock-windows", "demo-app"],
                            cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(ok.returncode, 0, ok.stderr)
        denied = os.path.join(ROOT, "examples", "denied-app.yaml")
        bad = subprocess.run([sys.executable, "-m", "deskcheck", "run", denied,
                              "--config", cfg_path, "--driver", "mock"],
                             cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(bad.returncode, 1)


if __name__ == "__main__":
    unittest.main()

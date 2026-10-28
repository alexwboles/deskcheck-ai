import json
import os
from pathlib import Path
import signal
import struct
import tempfile
import threading
import unittest
from unittest.mock import patch
import uuid
import zlib

from deskcheck.drivers.mock import MockDriver
from deskcheck.errors import DeskcheckError, ParseError, PermissionDenied
from deskcheck.factory import get_driver
from deskcheck.mcp_server import MCPServer
from deskcheck.parser import parse_test
from deskcheck.permissions import PermissionConfig
from deskcheck.pngutil import decode_png, solid_png
from deskcheck.runner import run_test
from deskcheck.safety import contained, load_yaml


class TestReleaseSafety(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.config = PermissionConfig.from_dict({"apps":{"demo-app":{}}})

    def write_case(self,steps,app="demo-app"):
        path = self.root/(uuid.uuid4().hex+".yaml")
        path.write_text(f"version: 1\nname: test\napp: {app}\nsteps:\n"+steps,encoding="utf-8")
        return path

    def run_case(self,steps,driver=None,**kwargs):
        path = self.write_case(steps)
        result = run_test(str(path),self.config,driver or MockDriver(),str(self.root/uuid.uuid4().hex),**kwargs)
        return result,Path(result.out_dir)

    def test_no_silent_mock_auto_fallback(self):
        with self.assertRaises(DeskcheckError):
            get_driver("auto")

    def test_mock_reports_cannot_be_mistaken_for_native_evidence(self):
        result,out = self.run_case("  - {type: launch, app: demo-app}\n")
        self.assertEqual(result.driver,"mock")
        self.assertEqual(json.loads((out/"result.json").read_text())["driver"],"mock")
        self.assertIn("MOCK SIMULATION",(out/"report.html").read_text(encoding="utf-8"))

    def test_reject_duplicate_yaml_keys_and_aliases(self):
        for text in ("apps: {}\napps: {}", "a: &ref [1]\nb: *ref", "a: &ref [*ref]"):
            with self.subTest(text=text),self.assertRaises(ParseError):
                load_yaml(text)

    def test_empty_and_oversize_yaml_rejected(self):
        with self.assertRaises(ParseError):
            parse_test("version: 1\nname: x\napp: demo-app\nsteps: []")
        with self.assertRaises(ParseError):
            load_yaml("x"*(1024*1024+1))

    def test_bool_and_container_step_types_rejected(self):
        for fragment in ("{type: [click]}","{type: assert, kind: [pixel-diff]}","{type: click, x: true, y: 1}"):
            with self.subTest(fragment=fragment),self.assertRaises(ParseError):
                parse_test(self.write_case("  - "+fragment+"\n").read_text())

    def test_invalid_keys_and_literal_controls_rejected(self):
        for fragment in ("{type: key, key: 'Win+R'}", "{type: key, key: \"Enter');bad\"}",
                         '{type: type, text: "hello\\nworld"}'):
            with self.subTest(fragment=fragment),self.assertRaises(ParseError):
                parse_test(self.write_case("  - "+fragment+"\n").read_text())

    def test_config_is_strict(self):
        for data in ([],{"unknown":{}},{"apps":[]},{"apps":{"x":{"category":[]}}},{"apps":{"x":{"throwaway_profile":"false"}}},
                     {"apps":{"x":{"category":"made-up"}}},{"apps":{"x":{"unknown":1}}},
                     {"apps":{"x":"shell string"}}):
            with self.subTest(data=data),self.assertRaises((ValueError,ParseError)):
                PermissionConfig.from_dict(data)

    def test_tolerance_overflow_is_parse_error(self):
        path = self.write_case("  - {type: assert, kind: pixel-diff, screenshot: x, baseline: x.png, tolerance: "+"9"*500+"}\n")
        with self.assertRaises(ParseError):
            parse_test(path.read_text())

    def test_progress_failure_cannot_write_pass_report(self):
        def broken_progress(*args):
            raise ValueError("synthetic progress error")
        result,out = self.run_case("  - {type: launch, app: demo-app}\n",progress=broken_progress)
        self.assertEqual(result.status,"error")
        self.assertEqual(json.loads((out/"result.json").read_text())["status"],"error")

    def test_paths_cannot_escape_or_use_ntfs_streams(self):
        for value in ("../outside.png","x/../../outside.png","C:\\outside.png","\\\\server\\path","/abs","x:secret","x\\..\\y"):
            with self.subTest(value=value),self.assertRaises(PermissionDenied):
                contained(self.root,value)

    def test_output_preserved_when_reused(self):
        out = self.root/"out"
        out.mkdir()
        original = out/"report.html"
        original.write_bytes(b"previous report")
        with self.assertRaises(PermissionDenied):
            run_test(str(self.write_case("  - {type: launch, app: demo-app}\n")),self.config,MockDriver(),str(out))
        self.assertEqual(original.read_bytes(),b"previous report")

    def test_linked_root_is_refused(self):
        actual = self.root/"actual"
        actual.mkdir()
        alias = self.root/"linked"
        try:
            alias.symlink_to(actual,target_is_directory=True)
        except (OSError,NotImplementedError):
            self.skipTest("Creating symlinks requires OS privileges here")
        with self.assertRaises(PermissionDenied):
            contained(alias,"report.html")

    @unittest.skipUnless(os.name == "nt","Windows short-path acceptance")
    def test_windows_short_path_spelling_is_not_a_symlink(self):
        import ctypes
        base = self.root/"long-directory-for-short-path-check"
        base.mkdir()
        buffer = ctypes.create_unicode_buffer(32768)
        size = ctypes.windll.kernel32.GetShortPathNameW(str(base),buffer,len(buffer))
        self.assertGreater(size,0)
        self.assertEqual(contained(buffer.value,"new.json"),base.resolve()/"new.json")

    def test_typed_secrets_redacted_from_all_reports(self):
        secret = "SYNTHETIC_PRIVATE_TEXT_946"
        result,out = self.run_case("  - {type: launch, app: demo-app}\n  - {type: type, text: "+secret+"}\n")
        self.assertTrue(result.passed)
        for file in out.iterdir():
            if file.is_file():
                self.assertNotIn(secret,file.read_text(encoding="utf-8"))

    def test_type_driver_exception_does_not_leak_secret(self):
        class Broken(MockDriver):
            def type_text(self,text):
                raise ValueError(text)
        result,out = self.run_case("  - {type: launch, app: demo-app}\n  - {type: type, text: SYNTHETIC_SECRET}\n",Broken())
        self.assertFalse(result.passed)
        self.assertNotIn("SYNTHETIC_SECRET",(out/"actions.jsonl").read_text())

    def test_stale_screenshot_cannot_pass(self):
        result,_ = self.run_case("  - {type: assert, kind: screenshot-saved, screenshot: old}\n")
        self.assertFalse(result.passed)

    def test_control_text_assertion_matches_and_redacts(self):
        result,out = self.run_case("  - {type: launch, app: demo-app}\n  - {type: type, text: SYNTHETIC_ASSERT_SECRET}\n  - {type: assert, kind: control-text, text: SYNTHETIC_ASSERT_SECRET}\n")
        self.assertTrue(result.passed)
        self.assertNotIn("SYNTHETIC_ASSERT_SECRET",(out/"report.html").read_text())

    def test_control_text_mismatch_fails_without_values(self):
        result,out = self.run_case("  - {type: launch, app: demo-app}\n  - {type: assert, kind: control-text, text: SYNTHETIC_ASSERT_SECRET}\n")
        self.assertFalse(result.passed)
        self.assertNotIn("SYNTHETIC_ASSERT_SECRET",(out/"actions.jsonl").read_text())

    def test_duplicate_screenshot_refused(self):
        result,_ = self.run_case("  - {type: launch, app: demo-app}\n  - {type: screenshot, name: x}\n  - {type: screenshot, name: x}\n")
        self.assertFalse(result.passed)

    def test_baseline_traversal_does_not_write(self):
        result,_ = self.run_case("  - {type: launch, app: demo-app}\n  - {type: screenshot, name: x}\n  - {type: assert, kind: pixel-diff, screenshot: x, baseline: ../victim.png}\n",update_baselines=True)
        self.assertFalse(result.passed)
        self.assertFalse((self.root/"victim.png").exists())

    def test_signal_restored_on_setup_failure(self):
        old = signal.getsignal(signal.SIGINT)
        path = self.write_case("  - {type: launch, app: unknown}\n",app="unknown")
        result = run_test(str(path),self.config,MockDriver(),str(self.root/"denied"))
        self.assertFalse(result.passed)
        self.assertIs(signal.getsignal(signal.SIGINT),old)

    def test_cancel_and_driver_interrupt_recorded(self):
        event = threading.Event()
        event.set()
        result,out = self.run_case("  - {type: launch, app: demo-app}\n",cancel_event=event)
        self.assertEqual(result.status,"interrupted")
        self.assertEqual(json.loads((out/"result.json").read_text())["status"],"interrupted")
        class Interrupt(MockDriver):
            def click(self,*args):
                raise KeyboardInterrupt
        result,_ = self.run_case("  - {type: launch, app: demo-app}\n  - {type: click, x: 1, y: 2}\n",Interrupt())
        self.assertEqual(result.status,"interrupted")

    def test_driver_errors_write_failure_report(self):
        class Broken(MockDriver):
            def screenshot(self,path):
                raise OSError("synthetic")
        result,out = self.run_case("  - {type: launch, app: demo-app}\n  - {type: screenshot, name: x}\n",Broken())
        self.assertFalse(result.passed)
        self.assertTrue((out/"report.html").is_file())

    def test_invalid_limits_fail_before_launch(self):
        for kwargs in ({"max_steps":0},{"timeout_ms":0},{"max_steps":True},{"timeout_ms":200000}):
            driver = MockDriver()
            with self.subTest(kwargs=kwargs),self.assertRaises(DeskcheckError):
                self.run_case("  - {type: launch, app: demo-app}\n",driver,**kwargs)
            self.assertEqual(driver.actions,[])

    def test_mcp_rejects_bad_arguments_and_unsafe_paths(self):
        server = MCPServer(self.config,workspace=self.root)
        for name,args in (("click",{"x":True,"y":0}),("click",{"x":0,"y":0,"shell":"bad"}),
                          ("type_text",["bad"]),("press_key",{"key":"Win+R"}),
                          ("screenshot",{"name":"../outside"}),("run_test",{"test":"../outside.yaml"}),
                          ("run_test",{"test":"test.yaml","update_baselines":True})):
            with self.subTest(name=name,args=args):
                self.assertTrue(server.call_tool(name,args)["isError"])
        self.assertEqual(server.driver.actions,[])

    def test_mcp_failed_run_returns_is_error(self):
        path = self.write_case("  - {type: launch, app: denied}\n",app="denied")
        server = MCPServer(self.config,workspace=self.root)
        result = server.call_tool("run_test",{"test":path.name})
        self.assertTrue(result["isError"])
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"],"fail")
        self.assertTrue(Path(payload["report"]).is_file())

    def test_mcp_never_executes_notifications_and_survives_invalid_request(self):
        server = MCPServer(self.config,workspace=self.root)
        for req in ([],None,{"method":"ping"},{"jsonrpc":"2.0","id":True,"method":"ping"}):
            self.assertIn("error",server.handle(req))
        self.assertIsNone(server.handle({"jsonrpc":"2.0","method":"tools/call","params":{"name":"launch_app","arguments":{"app":"demo-app"}}}))
        self.assertEqual(server.driver.actions,[])
        self.assertEqual(server.handle({"jsonrpc":"2.0","id":1,"method":"ping"})["result"],{})

    def test_png_crc_truncation_and_bomb_rejected(self):
        original = solid_png(4,4,(1,2,3))
        for bad in (original[:20],original[:30]+b"x"+original[31:]):
            with self.subTest(bad=bad[:20]),self.assertRaises(ValueError):
                decode_png(bad)
        data = bytearray(original)
        data[16:24] = struct.pack(">II",50000,50000)
        data[29:33] = struct.pack(">I",zlib.crc32(data[12:29])&0xffffffff)
        with self.assertRaises(ValueError):
            decode_png(bytes(data))

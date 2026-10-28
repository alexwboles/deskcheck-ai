"""Own-widget regression checks; no interaction with other desktop apps."""
import json
import os
from pathlib import Path
import tempfile
import time
import unittest

try:
    import tkinter as tk
    from deskcheck.desktop import Desktop
    HAS_TK = True
except ImportError:
    HAS_TK = False


@unittest.skipUnless(HAS_TK and (os.name == "nt" or os.environ.get("DISPLAY")),"Tk display unavailable; native Windows CI covers desktop widgets")
class TestDesktop(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = tk.Tk()
        self.root.withdraw()
        self.app = Desktop(self.root,Path(self.tmp.name))

    def tearDown(self):
        if self.app.running:
            self.app.cancel.set()
            self.finish()
        self.app.close()

    def finish(self):
        end = time.monotonic()+10
        while self.app.running and time.monotonic()<end:
            self.root.update()
            time.sleep(.01)
        self.assertFalse(self.app.running,"UI worker did not finish")

    def test_sample_run_and_report_reset(self):
        self.app.load_sample()
        self.app.start()
        self.assertTrue(self.app.running)
        self.assertTrue(self.app.run.instate(["disabled"]))
        self.finish()
        self.assertIn("PASS",self.app.status.get())
        self.assertTrue(self.app.report.is_file())
        old = self.app.report
        self.app.load_sample()
        self.assertIsNone(self.app.report)
        self.assertTrue(self.app.view.instate(["disabled"]))
        self.assertTrue(old.is_file(),"Old report must remain on disk")

    def test_stop_interrupts_wait_and_reenables_controls(self):
        self.app.load_sample()
        path = Path(self.app.test.get())
        test = json.loads(path.read_text())
        test["steps"] = [{"type":"launch","app":"demo-app"},{"type":"wait","ms":10000}]
        path.write_text(json.dumps(test))
        self.app.start()
        self.app.stop.invoke()
        self.finish()
        self.assertIn("INTERRUPTED",self.app.status.get())
        self.assertFalse(self.app.run.instate(["disabled"]))

    def test_setup_error_does_not_get_stuck_or_claim_pass(self):
        self.app.load_sample()
        self.app.config.set(str(Path(self.tmp.name)/"missing.yaml"))
        self.app.start()
        self.finish()
        self.assertIn("SETUP ERROR",self.app.status.get())
        self.assertIsNone(self.app.report)
        self.assertFalse(self.app.run.instate(["disabled"]))

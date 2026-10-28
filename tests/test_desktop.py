"""Own-widget regression checks; no interaction with other desktop apps."""
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

try:
    import tkinter as tk
    from deskcheck.desktop import Desktop
    HAS_TK = True
except ImportError:
    HAS_TK = False


@unittest.skipUnless(HAS_TK and (os.name == "nt" or os.environ.get("DISPLAY")),"Tk display unavailable; native Windows CI covers desktop widgets")
class TestDesktop(unittest.TestCase):
    def setUp(self):
        self.confirm = patch('deskcheck.desktop.messagebox.askyesno', return_value=True)
        self.confirm.start()
        self.addCleanup(self.confirm.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = tk.Tk()
        self.root.withdraw()
        self.app = Desktop(self.root,Path(self.tmp.name))
        self.root.update_idletasks()

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

    def test_edit_save_reopen_and_result_invalidated(self):
        self.app.load_sample()
        self.app.start()
        self.finish()
        old_report = self.app.report
        self.app.goto(1)
        self.app.selected = 1
        self.app.render_step()
        self.app.fields['text'].set('new synthetic note')
        self.app.apply_step()
        self.assertIsNone(self.app.result)
        self.assertIsNone(self.app.report)
        self.assertTrue(old_report.exists())
        self.assertTrue(self.app.save_check())
        items, errors = self.app.library.list_checks()
        saved, config = self.app.library.read(items[0])
        self.assertEqual(saved['steps'][1]['text'],'new synthetic note')
        self.assertEqual(errors,[])

    def test_capture_is_not_a_test_and_coordinates_use_image_scale(self):
        self.root.deiconify()
        self.app.load_sample()
        self.app.capture_app()
        self.finish()
        self.assertIsNone(self.app.result)
        self.assertIn('SIMULATION',self.app.capture_note.get())
        self.app.goto(1)
        self.app.selected = 1
        self.app.draft['steps'][1] = {'type':'click','x':0,'y':0}
        self.app.render()
        self.root.update()
        x,y,w,h,sw,sh = self.app.preview_bounds
        from types import SimpleNamespace
        self.app.pick_point(SimpleNamespace(x=x+w//2,y=y+h//2))
        step = self.app.draft['steps'][1]
        self.assertLess(abs(step['x']-sw//2),2)
        self.assertLess(abs(step['y']-sh//2),2)
        self.assertIn('No click was sent',self.app.status.get())

    def test_add_reorder_remove_and_stage_navigation(self):
        self.app.load_sample()
        self.app.goto(1)
        self.app.add_step()
        self.assertEqual(len(self.app.draft['steps']),5)
        self.assertEqual(self.app.draft['steps'][1]['type'],'click')
        self.app.move_step(1)
        self.assertEqual(self.app.selected,2)
        self.app.remove_step()
        self.assertEqual(len(self.app.draft['steps']),4)
        self.app.goto(2)
        self.assertEqual(self.app.stage,2)
        self.assertEqual(self.app.draft['steps'][self.app.selected]['type'],'assert')
        self.app.goto(3)
        self.assertEqual(self.app.stage,3)
        self.assertIsNone(self.app.result)
        self.app.goto(0)
        self.assertEqual(self.app.stage,0)

    def test_failed_check_has_real_failure_evidence_and_private_comparison(self):
        self.app.load_sample()
        self.app.draft['steps'][-1] = {'type':'assert','kind':'control-text','text':'different synthetic text'}
        self.app.mark_dirty()
        self.app.start()
        self.finish()
        self.assertEqual(self.app.result.status,'fail')
        self.assertTrue(self.app.result.observations)
        data = json.loads((Path(self.app.result.out_dir)/'result.json').read_text())
        self.assertIn('failed-step',data['screenshots'])
        for name in ('result.json','report.html','report.md','actions.jsonl'):
            content = (Path(self.app.result.out_dir)/name).read_text()
            self.assertNotIn('different synthetic text',content)
            self.assertNotIn('Synthetic demo only',content)

    def test_running_disables_navigation_and_duplicate_capture(self):
        self.app.load_sample()
        self.app.draft['steps'].insert(1,{'type':'wait','ms':500})
        self.app.mark_dirty()
        self.app.start()
        stage = self.app.stage
        self.app.goto(0)
        self.assertEqual(stage,self.app.stage)
        self.assertTrue(self.app.capture.instate(['disabled']))
        self.assertEqual(str(self.app.checks['state']),'disabled')
        self.app.stop.invoke()
        self.finish()
        self.assertIn('INTERRUPTED',self.app.status.get())

    def test_invalid_editor_does_not_replace_saved_check(self):
        self.app.load_sample()
        original = Path(self.app.test.get()).read_bytes()
        self.app.goto(1)
        self.app.selected = 1
        self.app.draft['steps'][1] = {'type':'click','x':5,'y':5}
        self.app.render_step()
        self.app.fields['x'].set('-5')
        with patch('deskcheck.desktop.messagebox.showerror'):
            self.assertFalse(self.app.save_check())
        self.assertEqual(Path(self.app.test.get()).read_bytes(),original)

    def test_setup_error_does_not_get_stuck_or_claim_pass(self):
        self.app.load_sample()
        self.app.config.set(str(Path(self.tmp.name)/"missing.yaml"))
        self.app.start()
        self.finish()
        self.assertIn("SETUP ERROR",self.app.status.get())
        self.assertIsNone(self.app.report)
        self.assertFalse(self.app.run.instate(["disabled"]))

    def test_unsaved_field_changes_are_detected_before_apply(self):
        self.app.load_sample()
        self.app.goto(1)
        self.app.selected = 1
        self.app.render_step()
        self.assertFalse(self.app.dirty)
        for widget in self.app.editor.winfo_children():
            if widget.winfo_class() in ('TEntry','TCombobox'):
                self.assertIn('-16',str(widget.cget('font')))
        self.app.fields['text'].set('edited but not applied yet')
        self.assertTrue(self.app.dirty)
        with patch('deskcheck.desktop.messagebox.askyesno',return_value=False):
            self.assertFalse(self.app.confirm_discard())

    def test_closing_advanced_does_not_change_the_active_execution_plan(self):
        self.app.load_sample()
        before = self.app.test.get(),self.app.config.get(),self.app.mode.get()
        self.app.advanced()
        self.app.backend.set('windows')
        self.app.advanced_window.destroy()
        self.app.advanced_window = None
        self.assertEqual((self.app.test.get(),self.app.config.get(),self.app.mode.get()),before)

import copy
import json
from pathlib import Path
import tempfile
import unittest

from deskcheck.workspace import CheckLibrary
from deskcheck.pngutil import encode_png

TEST = {'version':1,'name':'check','app':'demo','steps':[{'type':'launch','app':'demo'},
    {'type':'type','text':'synthetic'},{'type':'assert','kind':'control-text','text':'synthetic'}]}
CONFIG = {'apps':{'demo':{}}}


class TestLibrary(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.lib = CheckLibrary(self.root)

    def test_save_reopen_and_immutable_revisions(self):
        first = self.lib.save('My check',TEST,CONFIG,'mock')
        second = self.lib.save('My renamed check',TEST,CONFIG,'mock',first['id'])
        self.assertNotEqual(first['test'],second['test'])
        self.assertTrue(first['test'].is_file())
        items, errors = CheckLibrary(self.root).list_checks()
        self.assertEqual(errors,[])
        self.assertEqual(len(items),1)
        self.assertEqual(items[0]['title'],'My renamed check')
        self.assertEqual(self.lib.read(items[0]),(TEST,CONFIG))

    def test_validation_before_writes(self):
        for mode,title,key in [('shell','Name',None),('mock','',None),('mock','Name','../escape')]:
            with self.assertRaises(Exception):
                self.lib.save(title,TEST,CONFIG,mode,key)
        self.assertEqual(list(self.lib.root.iterdir()),[])

    def test_corrupt_metadata_does_not_hide_other_checks(self):
        self.lib.save('Good',TEST,CONFIG,'mock')
        bad = self.lib.root/'bad'
        bad.mkdir()
        (bad/'check.json').write_text('{invalid')
        items,errors = self.lib.list_checks()
        self.assertEqual(len(items),1)
        self.assertEqual(errors,['bad'])

    def test_baselines_carried_between_revisions(self):
        test = copy.deepcopy(TEST)
        test['steps'] = [{'type':'launch','app':'demo'}, {'type':'screenshot','name':'app'},
            {'type':'assert','kind':'pixel-diff','screenshot':'app','baseline':'nested/app.png'}]
        source = self.root/'imported'
        (source/'nested').mkdir(parents=True)
        image = encode_png(2,2,[[(0,0,0,255)]*2 for _ in range(2)])
        (source/'nested/app.png').write_bytes(image)
        first = self.lib.save('Baseline',test,CONFIG,'mock',baselines_from=source)
        second = self.lib.save('Baseline',test,CONFIG,'mock',first['id'],first['test'].parent/'baselines')
        self.assertEqual((second['test'].parent/'baselines/nested/app.png').read_bytes(),image)
        self.assertEqual((source/'nested/app.png').read_bytes(),image)

    def test_baseline_traversal_denied(self):
        test = copy.deepcopy(TEST)
        test['steps'][-1] = {'type':'assert','kind':'pixel-diff','screenshot':'app','baseline':'../escape.png'}
        with self.assertRaises(Exception):
            self.lib.save('Bad',test,CONFIG,'mock',baselines_from=self.root)

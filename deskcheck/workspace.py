"""Local check library. Imports are copied, never edited or executed on load."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import uuid

from .parser import parse_test, load_test
from .permissions import PermissionConfig
from .safety import atomic_bytes, checked_root, contained, load_yaml, safe_name


def step_title(step):
    kind = step['type']
    return {'launch': 'Open app', 'click': 'Click a control', 'type': 'Enter text',
            'key': 'Press a key', 'wait': 'Wait', 'screenshot': 'Capture app'}.get(
        kind, {'control-text': 'Verify saved text', 'window-visible': 'Verify app is open',
               'screenshot-saved': 'Verify capture', 'pixel-diff': 'Compare baseline'}.get(
                   step.get('kind'), 'Check result'))


class CheckLibrary:
    def __init__(self, workspace):
        self.root = contained(checked_root(workspace), 'checks')
        self.root.mkdir(parents=True, exist_ok=True)

    def list_checks(self):
        items, errors = [], []
        for folder in sorted(self.root.iterdir()):
            if not folder.is_dir():
                continue
            try:
                key = safe_name(folder.name)
                base = contained(self.root, key)
                with contained(base, 'check.json').open(encoding='utf-8') as fh:
                    meta = load_yaml(fh.read(1024*1024+1))
                if not isinstance(meta, dict) or not isinstance(meta.get('title'), str):
                    raise ValueError('Invalid check metadata')
                if not 1 <= len(meta['title']) <= 100 or any(ord(c)<32 for c in meta['title']):
                    raise ValueError('Invalid check title')
                if meta.get('mode') not in ('mock', 'windows'):
                    raise ValueError('Invalid check mode')
                # Immutable revision files plus one atomically replaced pointer.
                rev = safe_name(meta['revision'])
                items.append(dict(meta, id=key, test=contained(base, rev+'/test.json'),
                                  config=contained(base, rev+'/config.json')))
            except Exception:
                errors.append(folder.name)
        return items, errors

    def save(self, title, test, config, mode, key=None, baselines_from=None):
        title = title.strip()
        if not title or len(title) > 100 or any(ord(c) < 32 for c in title):
            raise ValueError('Give this check a name of 1–100 printable characters.')
        if mode not in ('mock', 'windows'):
            raise ValueError('Choose simulation or Windows.')
        test = parse_test(json.dumps(test))
        PermissionConfig.from_dict(config).check_launch(test['app'])
        key = safe_name(key) if key else uuid.uuid4().hex
        base = contained(self.root, key)
        revision = uuid.uuid4().hex
        # Baselines are per-revision, so editing does not lose comparison
        # images or mutate an imported project's baseline directory.
        if baselines_from is not None:
            from .pngutil import decode_png
            for step in test['steps']:
                if step['type'] == 'assert' and step['kind'] == 'pixel-diff':
                    source = contained(baselines_from, step['baseline'])
                    destination = contained(base, revision+'/baselines/'+step['baseline'])
                    if source.is_file() and not destination.exists():
                        if source.stat().st_size > 32*1024*1024:
                            raise ValueError('Baseline image is too large')
                        data = source.read_bytes()
                        decode_png(data)
                        atomic_bytes(destination, data)
        for name, value in (('test', test), ('config', config)):
            path = contained(base, revision+'/'+name+'.json')
            atomic_bytes(path, json.dumps(value, indent=2).encode('utf-8'))
        meta = {'title': title, 'mode': mode, 'revision': revision}
        atomic_bytes(contained(base, 'check.json'), json.dumps(meta).encode(), replace=True)
        return dict(meta, id=key, test=contained(base, revision+'/test.json'),
                    config=contained(base, revision+'/config.json'))

    @staticmethod
    def read(item):
        test = load_test(item['test'])
        with Path(item['config']).open(encoding='utf-8') as fh:
            config = load_yaml(fh.read(1024*1024+1))
        PermissionConfig.from_dict(config)
        return copy.deepcopy(test), config

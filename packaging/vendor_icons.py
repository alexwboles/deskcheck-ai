"""Development-only: render pinned MIT Feather SVGs to offline Tk PNG assets.

Requires free resvg-py in the builder environment, not in the product runtime.
"""
from pathlib import Path
from urllib.request import urlopen
import resvg_py

root = Path(__file__).resolve().parents[1]/'deskcheck'/'assets'
root.mkdir(exist_ok=True)
base = 'https://raw.githubusercontent.com/feathericons/feather/v4.29.2/'
license_text = urlopen(base+'LICENSE', timeout=20).read()
(root/'Feather-LICENSE.txt').write_bytes(license_text)
for name in ('check-circle', 'circle', 'alert-circle', 'play', 'stop-circle',
             'file-text', 'monitor', 'plus', 'settings', 'save', 'edit-2',
             'folder', 'arrow-left', 'arrow-right', 'check-square'):
    svg = urlopen(base+'icons/'+name+'.svg', timeout=20).read().decode()
    for color, value in (('navy', '#193449'), ('white', '#e9f0f7'),
                         ('teal', '#008c87'), ('red', '#bd3c2b')):
        png = resvg_py.svg_to_bytes(svg_string=svg.replace('currentColor', value),
                                   width=24, height=24)
        (root/(name+'-'+color+'.png')).write_bytes(png)
print('Vendored Feather 4.29.2 icons and MIT license; runtime remains offline.')

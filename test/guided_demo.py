"""Synthetic visual-QA harness; never used as the product entry point.

Starts only our bundled fixture, with no user app/config or paid API involved.
"""
from pathlib import Path
import json
import os
import sys
import tkinter as tk
import uuid

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from deskcheck.desktop import Desktop


def main():
    root = tk.Tk()
    workspace = Path(__file__).resolve().parents[1]/'.qa-output'/('guided-design-'+uuid.uuid4().hex[:8])
    app = Desktop(root,workspace)
    root.title('DeskCheck — Synthetic design QA')
    root.maxsize(4000,3000)
    root.geometry('1440x1024+0+0')
    if '--small' in sys.argv:
        root.geometry('1050x680+0+0')
    app.load_windows_sample()
    if '--failure' in sys.argv:
        app.config_data['apps']['sample-app']['command'].append('mismatch')
        app.mark_dirty()
    # Explicitly limited to this synthetic fixture in this dev-only harness.
    app.native_consent = lambda:True
    def begin():
        app.start()
    root.after(250,begin)
    if '--snapshot' in sys.argv:
        def snapshot_when_done():
            if app.running or app.result is None:
                root.after(100,snapshot_when_done)
                return
            # Render our own synthetic test UI, inside its own process. This
            # does not capture the desktop, inspect or automate another app.
            app.comparison_visible = True
            app.render()
            root.update_idletasks()
            from deskcheck.drivers.windows import WindowsDriver
            driver = WindowsDriver()
            hwnd = int(root.wm_frame(),16)
            import ctypes as C
            from ctypes import wintypes as W
            process = driver.k.OpenProcess(0x1000,False,os.getpid())
            try:
                size = W.DWORD(32768)
                exe = C.create_unicode_buffer(size.value)
                if not driver.k.QueryFullProcessImageNameW(process,0,exe,C.byref(size)):
                    raise RuntimeError('Cannot identify this QA process')
                image = os.path.normcase(os.path.realpath(exe.value))
            finally:
                driver.k.CloseHandle(process)
            # Tk does not paint child controls outside the physical monitor.
            # Tile this SAME synthetic window at a fixed size/state, capturing
            # only its own client pixels, then stitch the visible regions.
            from PIL import Image
            import io
            width,height = root.winfo_width(),root.winfo_height()
            stitched = Image.new('RGB',(width,height),'white')
            for left in (0,min(0,root.winfo_screenwidth()-width-48)):
                for top in (0,min(0,root.winfo_screenheight()-height-64)):
                    root.geometry(f'{width}x{height}+{left}+{top}')
                    root.update()
                    png = driver._capture_bound(hwnd,os.getpid(),image)
                    with Image.open(io.BytesIO(png)) as tile:
                        rx,ry = root.winfo_rootx(),root.winfo_rooty()
                        box = (max(0,-rx),max(0,-ry),min(width,root.winfo_screenwidth()-rx),min(height,root.winfo_screenheight()-ry))
                        stitched.paste(tile.crop(box),box[:2])
            stitched.save(workspace/'workspace.png')
            (workspace/'ui-state.json').write_text(json.dumps({
                'result':app.result.status,'viewport':[root.winfo_width(),root.winfo_height()],
                'runVisible':app.run.winfo_viewable(),'navigationVisible':app.new.winfo_viewable(),
                'evidence':str(app.report),'screenshot':str(workspace/'workspace.png')}))
            print(str(workspace/'workspace.png'),flush=True)
            root.after_cancel(app.timer)
            root.destroy()
        root.after(500,snapshot_when_done)
    root.mainloop()


if __name__=='__main__':
    main()

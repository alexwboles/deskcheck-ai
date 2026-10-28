"""Offline guided check workspace. UI thread owns Tk, workers own test apps."""
from __future__ import annotations
import copy
import json
import os
from pathlib import Path
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import uuid
import webbrowser

from . import __version__
from .factory import get_driver
from .parser import parse_test, load_test
from .permissions import PermissionConfig
from .safety import checked_root, contained, load_yaml
from .workspace import CheckLibrary, step_title

BG, INK, MUTED, NAVY, TEAL, LINE, PALE = '#ffffff', '#173247', '#577087', '#183247', '#008b89', '#e0e7ed', '#edf4f8'
STAGES = ('Choose app', 'Add actions', 'Expected result', 'Review results')
KINDS = ('Open app', 'Click a control', 'Enter text', 'Press a key', 'Wait',
         'Capture app', 'Verify saved text', 'Verify app is open', 'Verify capture')


class Desktop:
    def __init__(self, root, workspace=None):
        self.root = root
        self.workspace = checked_root(workspace or os.environ.get('DESKCHECK_WORKSPACE', Path.home()/'Documents'/'DeskCheck'))
        self.library = CheckLibrary(self.workspace)
        self.messages, self.cancel = queue.Queue(), threading.Event()
        self.running, self.dirty = False, False
        self.report = self.result = self.current = self.draft = self.config_data = None
        self.preview_source = self.preview_photo = self.preview_bounds = None
        self.entries, self.fields, self.stage, self.selected = [], {}, 0, 0
        self.advanced_window = None
        self.test, self.config = tk.StringVar(), tk.StringVar()
        self.mode, self.accept = tk.StringVar(value='mock'), tk.BooleanVar(value=False)
        self.title = tk.StringVar(value='Create your first check')
        self.saved = tk.StringVar(value='Choose a sample or a trusted test app to begin.')
        self.status = tk.StringVar(value='Ready — nothing runs until you choose Run check.')
        self.detail, self.capture_note = tk.StringVar(), tk.StringVar(value='No capture yet')
        self.icons = {}
        for file in (Path(__file__).parent/'assets').glob('*.png'):
            self.icons[file.stem] = tk.PhotoImage(master=root, file=str(file))
        root.title('DeskCheck — Guided check workspace')
        root.geometry(f'{min(1440,root.winfo_screenwidth()-50)}x{min(1024,root.winfo_screenheight()-80)}')
        root.minsize(1050, 680)
        root.configure(bg=BG)
        self.styles()
        self.build()
        self.refresh_library()
        self.render()
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.bind('<Control-s>', lambda _e:self.save_check())
        self.timer = root.after(80, self.poll)

    def icon(self, name, color='navy'):
        return self.icons.get(name+'-'+color, '')

    def styles(self):
        s = ttk.Style(self.root)
        s.theme_use('clam')
        s.configure('.', font=('Segoe UI', -16), background=BG, foreground=INK)
        s.configure('TFrame', background=BG)
        s.configure('TLabel', background=BG, foreground=INK)
        s.configure('Muted.TLabel', foreground=MUTED, font=('Segoe UI', -15))
        s.configure('Title.TLabel', font=('Segoe UI', -40, 'bold'))
        s.configure('Heading.TLabel', font=('Segoe UI', -22, 'bold'))
        s.configure('TButton', padding=(12, 9), background=BG, bordercolor=LINE, focuscolor=TEAL)
        s.map('TButton', background=[('active', PALE)], foreground=[('disabled', '#909da8')])
        s.configure('Primary.TButton', background=TEAL, foreground='white', borderwidth=0, font=('Segoe UI', -15, 'bold'))
        s.map('Primary.TButton', background=[('disabled', '#dce7eb'), ('active', '#00716f')], foreground=[('disabled', '#718491')])
        s.configure('Quiet.TButton', borderwidth=0, foreground=TEAL, padding=(6, 8))
        s.configure('Stage.TButton', borderwidth=0, padding=(6, 10), foreground=MUTED)
        s.configure('Active.Stage.TButton', foreground=TEAL, font=('Segoe UI', -15, 'bold'))
        s.configure('TEntry', padding=9, fieldbackground=BG, bordercolor=LINE)
        s.configure('TCombobox', padding=8, fieldbackground=BG, bordercolor=LINE)
        s.configure('Treeview', rowheight=42, fieldbackground=BG, background=BG, borderwidth=0)
        s.map('Treeview', background=[('selected', '#e8f4f3')], foreground=[('selected', INK)])
        s.configure('Horizontal.TProgressbar', background=TEAL, troughcolor=PALE, borderwidth=0, thickness=5)

    def button(self, parent, text, command, icon=None, style='TButton', pack=False):
        b = ttk.Button(parent, text=text, command=command, style=style,
            image=self.icon(icon, 'white' if style=='Primary.TButton' else 'navy') if icon else '', compound='left')
        if pack:
            b.pack(fill='x', pady=5)
        return b

    @staticmethod
    def clear(frame):
        for child in frame.winfo_children():
            child.destroy()

    def build(self):
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(0, weight=1)
        side = tk.Frame(self.root, bg=NAVY, width=226)
        side.grid(row=0, column=0, sticky='nsew')
        side.grid_propagate(False)
        side.rowconfigure(3, weight=1)
        side.columnconfigure(0, weight=1)
        tk.Label(side, text='  DeskCheck', bg=NAVY, fg='white', font=('Segoe UI', -26, 'bold'),
                 image=self.icon('check-square', 'white'), compound='left', padx=22, pady=26).grid(row=0, sticky='ew')
        tk.Label(side, text='YOUR CHECKS', bg=NAVY, fg='#a8bfd0', anchor='w',
                 font=('Segoe UI', -12, 'bold'), padx=24).grid(row=1, sticky='ew', pady=(18, 12))
        self.new = tk.Button(side, text='  New check', image=self.icon('plus', 'white'), compound='left',
            bg=NAVY, fg='white', activebackground='#284c68', activeforeground='white', relief='flat',
            anchor='w', padx=22, pady=14, font=('Segoe UI', -16), command=self.new_check)
        self.new.grid(row=2, sticky='ew')
        self.checks = tk.Listbox(side, bg=NAVY, fg='#e7eff6', selectbackground='#2b506f', selectforeground='white',
            font=('Segoe UI', -16), relief='flat', highlightthickness=0, exportselection=False, activestyle='none')
        self.checks.grid(row=3, sticky='nsew', padx=16, pady=10)
        self.checks.bind('<<ListboxSelect>>', self.select_check)
        self.advanced_button = tk.Button(side, text='  Advanced', image=self.icon('settings', 'white'), compound='left',
            command=self.advanced, relief='flat', bg=NAVY, fg='white', activebackground='#284c68',
            activeforeground='white', anchor='w', padx=22, pady=18, font=('Segoe UI', -15))
        self.advanced_button.grid(row=4, sticky='ew', pady=(10, 8))
        main = ttk.Frame(self.root, padding=(28, 22, 24, 12))
        main.grid(row=0, column=1, sticky='nsew')
        main.columnconfigure(0, weight=1)
        main.rowconfigure(3, weight=1)
        self.breadcrumb = ttk.Label(main, text='Workspace / New check', style='Muted.TLabel')
        self.breadcrumb.grid(row=0, sticky='w', pady=(0, 14))
        header = ttk.Frame(main)
        header.grid(row=1, sticky='ew')
        header.columnconfigure(0, weight=1)
        self.title_label = ttk.Label(header, textvariable=self.title, style='Title.TLabel', wraplength=450)
        self.title_label.grid(row=0, column=0, sticky='w')
        header.bind('<Configure>', lambda e:self.title_label.configure(wraplength=max(180,e.width-320)))
        ttk.Label(header, textvariable=self.saved, style='Muted.TLabel', wraplength=450).grid(row=1, column=0, sticky='w', pady=(4, 0))
        self.run = self.button(header, 'Run check', self.start, 'play', 'Primary.TButton')
        self.run.grid(row=0, column=1, rowspan=2, padx=(12, 8))
        self.save = self.button(header, 'Save', self.save_check, 'save')
        self.save.grid(row=0, column=2, rowspan=2)
        flow = ttk.Frame(main)
        flow.grid(row=2, sticky='ew', pady=(22, 16))
        self.stage_buttons = []
        for n, title in enumerate(STAGES):
            flow.columnconfigure(n, weight=1)
            b = self.button(flow, title, lambda n=n:self.goto(n), 'circle', 'Stage.TButton')
            b.grid(row=0, column=n, sticky='ew', padx=(0, 6))
            self.stage_buttons.append(b)
        body = ttk.Frame(main)
        body.grid(row=3, sticky='nsew')
        body.columnconfigure(0, weight=3, minsize=350,uniform='workspace')
        body.columnconfigure(1, weight=2, minsize=260,uniform='workspace')
        body.rowconfigure(0, weight=1)
        preview = ttk.Frame(body)
        preview.grid(row=0, column=0, sticky='nsew', padx=(0, 18))
        preview.grid_propagate(False)
        preview.columnconfigure(0, weight=1)
        preview.rowconfigure(1, weight=1)
        row = ttk.Frame(preview, padding=(12, 10))
        row.grid(row=0, sticky='ew')
        ttk.Label(row, text='App preview', style='Heading.TLabel').pack(side='left')
        ttk.Label(row, textvariable=self.capture_note, style='Muted.TLabel').pack(side='right', padx=(8, 0))
        self.canvas = tk.Canvas(preview, bg=PALE, highlightthickness=0)
        self.canvas.grid(row=1, sticky='nsew')
        self.canvas.bind('<Configure>', lambda _e:self.draw_preview())
        self.canvas.bind('<Button-1>', self.pick_point)
        self.capture = self.button(preview, 'Capture app', self.capture_app, 'monitor', 'Quiet.TButton')
        self.capture.grid(row=2, sticky='w', pady=(6, 0))
        self.zoom = self.button(preview,'View full size',self.zoom_preview,style='Quiet.TButton')
        self.zoom.grid(row=2,sticky='e',pady=(6,0))
        self.inspector_canvas = tk.Canvas(body, bg=BG, highlightthickness=0, width=300)
        self.inspector_canvas.grid(row=0, column=1, sticky='nsew')
        bar = ttk.Scrollbar(body, orient='vertical', command=self.inspector_canvas.yview)
        bar.grid(row=0, column=2, sticky='ns')
        self.inspector_canvas.configure(yscrollcommand=bar.set)
        self.inspector = ttk.Frame(self.inspector_canvas, padding=(0, 4, 10, 0))
        self.inspector_id = self.inspector_canvas.create_window((0, 0), anchor='nw', window=self.inspector)
        self.inspector.bind('<Configure>', lambda _e:self.inspector_canvas.configure(scrollregion=self.inspector_canvas.bbox('all')))
        self.inspector_canvas.bind('<Configure>', lambda e:self.inspector_canvas.itemconfigure(self.inspector_id, width=e.width))
        self.inspector_canvas.bind('<Enter>', lambda _e:self.inspector_canvas.focus_set())
        self.inspector_canvas.bind('<MouseWheel>', lambda e:self.inspector_canvas.yview_scroll(-int(e.delta/120), 'units'))
        progress_frame = ttk.Frame(main,height=5)
        progress_frame.grid(row=4,sticky='ew',pady=(16,0))
        self.progress = ttk.Progressbar(progress_frame, mode='determinate')
        self.progress.place(x=0,y=0,relwidth=1,height=5)
        footer = ttk.Frame(main, padding=(2, 12, 0, 6))
        footer.grid(row=5, sticky='ew')
        footer.columnconfigure(0, weight=1)
        self.status_label = ttk.Label(footer, textvariable=self.status, wraplength=450)
        self.status_label.grid(row=0, column=0, sticky='w')
        self.detail_label = ttk.Label(footer, textvariable=self.detail, style='Muted.TLabel', wraplength=450)
        self.detail_label.grid(row=1, column=0, sticky='w')
        self.stop = self.button(footer, 'Stop', self.cancel.set, 'stop-circle')
        self.stop.grid(row=0, column=1, rowspan=2, padx=6)
        self.stop.state(['disabled'])
        self.view = self.button(footer, 'View evidence', self.open_report, 'folder', 'Quiet.TButton')
        self.view.grid(row=0, column=2, rowspan=2)
        self.view.state(['disabled'])
        self.next = self.button(footer, 'Next', self.next_stage, 'arrow-right', 'Primary.TButton')
        self.next.grid(row=0,column=3,rowspan=2,padx=(8,0))
        footer.bind('<Configure>', lambda e:(self.status_label.configure(wraplength=max(200,e.width-400)),
                                            self.detail_label.configure(wraplength=max(200,e.width-400))))
        ttk.Label(main, text='Offline • No API charges • Use synthetic data. Captures may contain app data.',
                  style='Muted.TLabel').grid(row=6, sticky='e', pady=(6, 0))
        self.log = tk.Text(self.root, height=6, state='disabled')
        self.inputs = []

    def refresh_library(self):
        self.items, errors = self.library.list_checks()
        self.checks.delete(0, 'end')
        for i, item in enumerate(self.items):
            self.checks.insert('end', '  '+item['title'])
            if item['id'] == self.current:
                self.checks.selection_set(i)
        if errors:
            self.status.set(f'{len(errors)} saved check(s) could not be read. Other checks are unchanged.')

    def confirm_discard(self):
        return not self.dirty or messagebox.askyesno('Unsaved changes',
            'Leave this check without saving? The last saved version is kept.')

    def new_check(self):
        if self.running or not self.confirm_discard():
            return
        self.current = self.draft = self.config_data = None
        self.dirty, self.stage = False, 0
        self.title.set('Create a check')
        self.saved.set('Start with a sample or a trusted test app.')
        self.test.set('')
        self.config.set('')
        self.reset_sample()
        self.render()

    def select_check(self, _event=None):
        indices = self.checks.curselection()
        if self.running or not indices:
            return
        item = self.items[indices[0]]
        if item['id'] == self.current:
            return
        if not self.confirm_discard():
            self.refresh_library()
            return
        try:
            test, config = self.library.read(item)
            self.adopt(test, config, item['mode'], item['title'], item['id'])
            self.test.set(str(item['test']))
            self.config.set(str(item['config']))
        except Exception as exc:
            self.error(exc)

    def adopt(self, test, config, mode, title, key=None):
        self.reset_sample()
        self.current, self.draft, self.config_data = key, copy.deepcopy(test), copy.deepcopy(config)
        self.mode.set(mode)
        self.accept.set(False)
        self.title.set(title)
        self.dirty = key is None
        self.saved.set('Unsaved check' if self.dirty else 'Saved on this computer')
        self.selected, self.stage = 0, 0
        self.render()

    def save_check(self, apply_editor=True):
        if self.running or self.draft is None:
            return False
        try:
            if apply_editor and self.stage in (1, 2):
                self.read_step()
            if self.stage == 0 and 'title' in self.fields:
                self.title.set(self.fields['title'].get().strip())
            source = Path(self.test.get()).parent/'baselines' if self.test.get() else None
            item = self.library.save(self.title.get(), self.draft, self.config_data, self.mode.get(), self.current, source)
            self.current = item['id']
            self.test.set(str(item['test']))
            self.config.set(str(item['config']))
            self.dirty = False
            self.saved.set('Saved on this computer')
            self.refresh_library()
            return True
        except Exception as exc:
            self.error(exc)
            return False

    def mark_dirty(self):
        self.dirty = True
        self.saved.set('Unsaved changes • Save to keep them')
        self.invalidate_result()

    def invalidate_result(self):
        self.comparison_visible = False
        self.result, self.entries, self.report = None, [], None
        self.view.state(['disabled'])
        self.progress.configure(value=0)
        self.detail.set('')
        self.run.configure(text='Run check')
        self.status.set('Check changed — run it to verify these changes.')
        self.status_label.configure(foreground=INK,font=('Segoe UI',-16))

    def goto(self, stage):
        if self.running:
            return
        try:
            if self.draft and self.stage in (1, 2):
                self.read_step()
            if self.draft is None and stage:
                self.status.set('Choose a sample or app first.')
                return
            self.stage = stage
            if stage == 2:
                choices = [i for i, s in enumerate(self.draft['steps']) if s['type']=='assert']
                if choices:
                    self.selected = choices[0]
            self.render()
        except Exception as exc:
            self.error(exc)

    def render(self):
        if self.stage==3:
            self.next.grid_remove()
        else:
            self.next.grid()
            self.next.configure(text=('Next: actions','Next: expected','Review & run')[self.stage])
            self.next.configure(state='normal' if self.draft else 'disabled')
        for i, b in enumerate(self.stage_buttons):
            b.configure(style='Active.Stage.TButton' if i==self.stage else 'Stage.TButton',
                image=self.icon('check-circle' if i<self.stage else 'circle', 'teal' if i<=self.stage else 'navy'))
        self.breadcrumb.configure(text=('Simulation' if self.mode.get()=='mock' else 'Windows app')+' / '+
                                  ('New check' if self.draft is None else self.draft['app']))
        self.clear(self.inspector)
        self.fields, self.steps_view = {}, None
        self.inspector_canvas.yview_moveto(0)
        if self.stage == 0:
            self.render_app()
        elif self.stage in (1, 2):
            self.render_builder()
        else:
            self.render_results()
        self.draw_preview()

    def label(self, text, heading=False, parent=None):
        label = ttk.Label(parent or self.inspector, text=text, style='Heading.TLabel' if heading else 'Muted.TLabel',
                          wraplength=315, justify='left')
        label.pack(fill='x', pady=(0, 12), anchor='w')
        label.bind('<Configure>',lambda e:label.configure(wraplength=max(180,e.width-8)))
        return label

    def field(self, parent, label, value, key, choices=None):
        ttk.Label(parent, text=label,wraplength=260).pack(anchor='w', pady=(12, 5))
        var = tk.StringVar(value=str(value))
        widget = ttk.Combobox(parent, textvariable=var, values=choices, state='readonly') if choices else ttk.Entry(parent, textvariable=var)
        widget.pack(fill='x', pady=(0, 3))
        self.fields[key] = var
        var.trace_add('write',lambda *_:self.mark_dirty())
        return widget

    def render_app(self):
        if self.draft:
            self.label('App selected', True)
            self.label(self.draft['app'].replace('-', ' ').capitalize())
            self.field(self.inspector, 'Check name', self.title.get(), 'title')
            self.label('SIMULATION — no real app is tested' if self.mode.get()=='mock' else 'Windows standard-control app')
            self.button(self.inspector, 'Choose a different app…', self.choose_app, 'folder', 'Quiet.TButton', pack=True)
        else:
            self.label('Choose your app', True)
            self.label('Try the included sample or a disposable Windows test app. Nothing launches yet.')
            self.native_sample = self.button(self.inspector, 'Try Windows sample', self.load_windows_sample, 'monitor', pack=True)
            self.sample = self.button(self.inspector, 'Try simulation', self.load_sample, 'file-text', pack=True)
            self.button(self.inspector, 'Choose Windows app…', self.choose_app, 'folder', pack=True)
        self.label('Only compatible Windows standard controls are supported. Browsers and custom-rendered apps are not supported.')

    def title_next(self):
        if 'title' in self.fields:
            if self.title.get() != self.fields['title'].get().strip():
                self.title.set(self.fields['title'].get().strip())
                self.mark_dirty()
        self.goto(1)

    def next_stage(self):
        if self.stage==0:
            self.title_next()
        else:
            self.goto(self.stage+1)

    def choose_app(self):
        if self.running or not self.confirm_discard():
            return
        path = filedialog.askopenfilename(title='Choose a trusted disposable Windows test app', filetypes=[('Windows application','*.exe')])
        if not path:
            return
        from .drivers.windows import BLOCKED_EXES
        if Path(path).suffix.lower()!='.exe' or Path(path).name.lower() in BLOCKED_EXES:
            messagebox.showerror('Unsupported app', 'Choose a compatible test executable, not a browser, shell or system tool.')
            return
        test = {'version':1,'name':'new-check','app':'test-app','steps':[
            {'type':'launch','app':'test-app'}, {'type':'screenshot','name':'app'},
            {'type':'assert','kind':'window-visible','window':'test-app'}]}
        self.adopt(test, {'apps':{'test-app':{'command':[str(Path(path).resolve())],'category':'app'}}},
                   'windows', Path(path).stem+' check')

    def render_builder(self):
        self.label('Your check' if self.stage==1 else 'What should happen?', True)
        self.label('Select a step to edit it. Pick click locations on an app capture.' if self.stage==1 else
                   'For text checks, click the result control before verifying its text.')
        self.steps_view = ttk.Treeview(self.inspector, show='tree', selectmode='browse', height=4)
        self.steps_view.pack(fill='x', pady=(0, 6))
        for i, step in enumerate(self.draft['steps']):
            self.steps_view.insert('', 'end', iid=str(i), text='  '+step_title(step), image=self.icon('circle'))
        self.selected = min(self.selected, len(self.draft['steps'])-1)
        self.steps_view.selection_set(str(self.selected))
        self.steps_view.see(str(self.selected))
        self.steps_view.bind('<<TreeviewSelect>>', self.select_step)
        row = ttk.Frame(self.inspector)
        row.pack(fill='x', pady=(4, 8))
        for text, command in (('Add',self.add_step),('Up',lambda:self.move_step(-1)),
                              ('Down',lambda:self.move_step(1)),('Remove',self.remove_step)):
            self.button(row, text, command, style='Quiet.TButton').pack(side='left')
        self.editor = ttk.Frame(self.inspector)
        self.editor.pack(fill='x')
        self.render_step()
        self.button(self.inspector, 'Apply step', self.apply_step, 'save', 'Quiet.TButton', pack=True)

    def select_step(self, _event=None):
        selected = self.steps_view.selection() if self.steps_view else ()
        if self.running or not selected or int(selected[0])==self.selected:
            return
        old = self.selected
        try:
            self.read_step()
            self.selected = int(selected[0])
            self.render_step()
        except Exception as exc:
            self.steps_view.selection_set(str(old))
            self.error(exc)

    def render_step(self):
        self.clear(self.editor)
        self.fields = {}
        step = self.draft['steps'][self.selected]
        combo = self.field(self.editor, 'Action', step_title(step), 'action', KINDS)
        combo.bind('<<ComboboxSelected>>', self.change_kind)
        kind = step['type']
        if kind=='click':
            self.field(self.editor, 'App X position', step['x'], 'x')
            self.field(self.editor, 'App Y position', step['y'], 'y')
            self.label('Pick on the capture or enter client-area pixels.', parent=self.editor)
        elif kind=='type' or kind=='assert' and step['kind']=='control-text':
            self.field(self.editor, 'Text to enter' if kind=='type' else 'Expected text', step['text'], 'text')
            self.label('Use synthetic data. Text is saved locally in the check, not action logs.', parent=self.editor)
        elif kind=='key':
            from .safety import KEYS
            self.field(self.editor, 'Single key', step['key'], 'key', sorted(KEYS))
        elif kind=='wait':
            self.field(self.editor, 'Wait (milliseconds, up to 30000)', step.get('ms',0), 'ms')
        elif kind=='screenshot':
            self.field(self.editor, 'Capture name', step['name'], 'name')
        elif kind=='assert' and step['kind']=='screenshot-saved':
            self.field(self.editor, 'Capture to verify', step['screenshot'], 'screenshot')
        else:
            self.label('Uses this check’s app. Imported baseline comparisons retain their full settings.', parent=self.editor)

    def read_step(self):
        if 'action' not in self.fields:
            return
        before = self.draft['steps'][self.selected]
        step = copy.deepcopy(before)
        for key, var in self.fields.items():
            if key=='action':
                continue
            value = var.get()
            if key in ('x','y','ms'):
                try:
                    value = int(value)
                except ValueError:
                    raise ValueError('Positions and wait time must be whole numbers.')
                if key=='ms' and not 0<=value<=30000:
                    raise ValueError('Wait must be between 0 and 30000 milliseconds.')
            step[key] = value
        candidate = copy.deepcopy(self.draft)
        candidate['steps'][self.selected] = step
        parse_test(json.dumps(candidate))
        if step!=before:
            self.draft = candidate
            self.mark_dirty()

    def apply_step(self):
        try:
            self.read_step()
            self.status.set('Step updated. Save your check or run it to verify.')
        except Exception as exc:
            self.error(exc)

    def default_step(self, title):
        app = self.draft['app']
        return {'Open app':{'type':'launch','app':app}, 'Click a control':{'type':'click','x':0,'y':0},
            'Enter text':{'type':'type','text':''}, 'Press a key':{'type':'key','key':'Tab'},
            'Wait':{'type':'wait','ms':250}, 'Capture app':{'type':'screenshot','name':'capture-'+uuid.uuid4().hex[:5]},
            'Verify saved text':{'type':'assert','kind':'control-text','text':''},
            'Verify app is open':{'type':'assert','kind':'window-visible','window':app},
            'Verify capture':{'type':'assert','kind':'screenshot-saved','screenshot':next(
                (s['name'] for s in self.draft['steps'] if s['type']=='screenshot'), 'app')}}[title]

    def change_kind(self, _event=None):
        if not self.running:
            self.draft['steps'][self.selected] = self.default_step(self.fields['action'].get())
            self.mark_dirty()
            self.render()

    def add_step(self):
        if self.running:
            return
        try:
            self.read_step()
            if len(self.draft['steps'])>=100:
                raise ValueError('The visual builder supports up to 100 steps per check.')
            self.selected += 1
            self.draft['steps'].insert(self.selected, self.default_step('Verify saved text' if self.stage==2 else 'Click a control'))
            self.mark_dirty()
            self.render()
        except Exception as exc:
            self.error(exc)

    def move_step(self, delta):
        if self.running:
            return
        try:
            self.read_step()
            target = self.selected+delta
            if 0<=target<len(self.draft['steps']):
                steps = self.draft['steps']
                steps[self.selected], steps[target] = steps[target], steps[self.selected]
                self.selected = target
                self.mark_dirty()
                self.render()
        except Exception as exc:
            self.error(exc)

    def remove_step(self):
        if not self.running and len(self.draft['steps'])>1:
            del self.draft['steps'][self.selected]
            self.selected = max(0, self.selected-1)
            self.mark_dirty()
            self.render()

    def render_results(self):
        compact = self.root.winfo_height()<850
        if not compact:
            self.label('Your check', True)
        if self.result is None:
            self.label('Ready to try this check. Run it to see results here. Editing clears the previous result, not its saved evidence.')
        else:
            self.label({'pass':'All steps passed','fail':'Needs attention','error':'Run error','interrupted':'Stopped — not a pass'}[self.result.status], True)
            if self.result.driver=='mock':
                self.label('SIMULATION — no real app was tested.')
        self.result_details = ttk.Frame(self.inspector)
        if compact:
            self.result_details.pack(fill='x',pady=(0,8))
        tree = ttk.Treeview(self.inspector,show='tree',selectmode='browse',height=3 if compact else 4)
        tree.pack(fill='x',pady=(0,12))
        failure_index = None
        for i, step in enumerate(self.draft['steps'] if self.draft else []):
            outcome = next((e['outcome'] for e in self.entries if e['step']==i), None)
            icon = 'check-circle' if outcome=='ok' else 'alert-circle' if outcome=='fail' else 'circle'
            color = 'teal' if outcome=='ok' else 'red' if outcome=='fail' else 'navy'
            tree.insert('', 'end', iid=str(i), text='  '+step_title(step),image=self.icon(icon,color))
            if outcome=='fail':
                failure_index = i
        if not compact:
            self.result_details.pack(fill='x')
        def detail(_event=None):
            selection = tree.selection()
            if selection:
                self.show_result_detail(int(selection[0]))
        tree.bind('<<TreeviewSelect>>',detail)
        if self.draft:
            selected = failure_index if failure_index is not None else len(self.draft['steps'])-1
            tree.selection_set(str(selected))
            tree.see(str(selected))
            self.show_result_detail(selected)
        self.button(self.inspector, 'Edit expected result', lambda:self.goto(2), 'edit-2', 'Quiet.TButton', pack=True)

    def show_result_detail(self, index):
        self.clear(self.result_details)
        if not self.result:
            self.label('No result yet. Run the check when you’re ready.',parent=self.result_details)
            return
        entry = next((e for e in self.entries if e['step']==index),None)
        self.label('Step '+str(index+1)+' • '+('Passed' if entry and entry['outcome']=='ok' else
                   'Needs attention' if entry and entry['outcome']=='fail' else 'Not completed'),
                   self.root.winfo_height()>=850,parent=self.result_details)
        observation = getattr(self.result,'observations',{}).get(index)
        if observation:
            self.label('The selected control’s text did not match.',parent=self.result_details)
            if getattr(self,'comparison_visible',False):
                self.label('Expected',parent=self.result_details)
                self.comparison_value(observation['expected'],False)
                self.label('Actual',parent=self.result_details)
                self.comparison_value(observation['actual'],True)
            else:
                self.label('Expected and actual text are hidden for privacy. Reveal them only on this screen.',parent=self.result_details)
                self.button(self.result_details,'Reveal text comparison',lambda:self.reveal_comparison(index),
                            style='Quiet.TButton',pack=True)
        elif entry and entry.get('error'):
            self.label(entry['error'],parent=self.result_details)
        elif self.result.failures and not entry:
            self.label(self.result.failures[0],parent=self.result_details)

    def reveal_comparison(self, index):
        if messagebox.askyesno('Show app text locally?', 'App text may be private. Show expected and observed text on screen only? It is never added to reports.'):
            self.comparison_visible = True
            self.show_result_detail(index)

    def comparison_value(self, text, failed):
        value = tk.Label(self.result_details,text=text,justify='left',anchor='w',
            bg='#fff0ed' if failed else PALE,fg='#b93827' if failed else INK,
            font=('Segoe UI',-16,'bold'),padx=10,pady=10,wraplength=300)
        value.pack(fill='x',pady=(0,12))
        value.bind('<Configure>',lambda e:value.configure(wraplength=max(180,e.width-20)))

    def set_preview(self, path, simulation=False):
        from .pngutil import decode_png
        from PIL import Image
        path = checked_root(path)
        decode_png(path.read_bytes())
        with Image.open(path) as image:
            self.preview_source = image.convert('RGBA')
        self.capture_note.set('SIMULATION • not a real app' if simulation else 'Last captured • not live')
        self.draw_preview()

    def draw_preview(self):
        self.canvas.delete('all')
        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        self.preview_bounds = None
        if self.preview_source is None:
            self.canvas.create_text(w/2,max(80,h/2-18),text='Your app will appear here',fill=MUTED,
                font=('Segoe UI',-21,'bold'),width=max(200,w-60))
            self.canvas.create_text(w/2,max(120,h/2+24),text='Choose an app, then capture it or run a check.\nCaptures are not live windows.',
                fill=MUTED,font=('Segoe UI',-15),justify='center',width=max(200,w-60))
            return
        from PIL import Image, ImageTk
        sw, sh = self.preview_source.size
        ratio = min(1,max(1,w-36)/sw,max(1,h-36)/sh)
        resized = self.preview_source.resize((max(1,int(sw*ratio)),max(1,int(sh*ratio))),Image.Resampling.LANCZOS)
        self.preview_photo = ImageTk.PhotoImage(resized, master=self.root)
        dw, dh = self.preview_photo.width(), self.preview_photo.height()
        x, y = (w-dw)//2,(h-dh)//2
        self.canvas.create_image(x,y,anchor='nw',image=self.preview_photo)
        self.preview_bounds = x,y,dw,dh,sw,sh

    def zoom_preview(self):
        if self.preview_source is None:
            self.status.set('Capture an app or run a check first.')
            return
        from PIL import ImageTk
        win = tk.Toplevel(self.root)
        win.title('DeskCheck — Full-size capture (not live)')
        win.geometry(f'{min(900,self.root.winfo_screenwidth()-80)}x{min(600,self.root.winfo_screenheight()-100)}')
        win.rowconfigure(0,weight=1)
        win.columnconfigure(0,weight=1)
        canvas = tk.Canvas(win,bg=PALE,highlightthickness=0)
        canvas.grid(row=0,column=0,sticky='nsew')
        photo = ImageTk.PhotoImage(self.preview_source,master=win)
        canvas.image = photo
        canvas.create_image(0,0,image=photo,anchor='nw')
        canvas.configure(scrollregion=(0,0,photo.width(),photo.height()))
        for orient,row,col,command in (('vertical',0,1,canvas.yview),('horizontal',1,0,canvas.xview)):
            bar = ttk.Scrollbar(win,orient=orient,command=command)
            bar.grid(row=row,column=col,sticky='ns' if orient=='vertical' else 'ew')
            canvas.configure(**{('yscrollcommand' if orient=='vertical' else 'xscrollcommand'):bar.set})
        win.bind('<Escape>',lambda _e:win.destroy())

    def pick_point(self, event):
        if self.running or self.stage not in (1,2) or not self.preview_bounds:
            return
        if self.draft['steps'][self.selected]['type']!='click':
            self.status.set('Select or add a “Click a control” step, then pick on the capture.')
            return
        x,y,w,h,sw,sh = self.preview_bounds
        if x<=event.x<x+w and y<=event.y<y+h:
            px,py = min(sw-1,int((event.x-x)*sw/w)),min(sh-1,int((event.y-y)*sh/h))
            self.fields['x'].set(px)
            self.fields['y'].set(py)
            self.apply_step()
            self.status.set(f'Picked app position {px}, {py}. No click was sent to the app.')

    def native_consent(self):
        return self.mode.get()!='windows' or messagebox.askyesno('Launch the selected test app?',
            'DeskCheck will launch the selected executable and close that new process afterward. Use only trusted disposable apps '
            'and synthetic data. This is NOT a filesystem/network sandbox. Continue?')

    def prepare(self):
        if self.draft is None:
            return bool(self.test.get() and self.config.get())
        if self.stage in (1,2):
            self.read_step()
        if self.stage==0 and 'title' in self.fields and self.title.get()!=self.fields['title'].get().strip():
            self.title.set(self.fields['title'].get().strip())
            self.mark_dirty()
        return self.save_check(False) if self.dirty or not self.test.get() else True

    def busy(self, value):
        self.running = value
        if value:
            self.cancel.clear()
        state = 'disabled' if value else 'normal'
        for widget in (self.run,self.save,self.new,self.advanced_button,self.capture,self.next,*self.stage_buttons):
            widget.configure(state=state)
        self.checks.configure(state=state)
        self.stop.configure(state='normal' if value else 'disabled')
        self.view.configure(state='normal' if not value and self.report else 'disabled')
        def toggle(parent):
            for widget in parent.winfo_children():
                if isinstance(widget,(ttk.Button,ttk.Entry,ttk.Combobox,ttk.Treeview)):
                    widget.state(['disabled'] if value else ['!disabled'])
                toggle(widget)
        toggle(self.inspector)

    def capture_app(self):
        if self.running:
            return
        try:
            if not self.prepare() or not self.native_consent():
                return
            test = load_test(self.test.get())
            entry = PermissionConfig.from_file(self.config.get()).check_launch(test['app'])
            mode = self.mode.get()
            if mode != 'mock' and entry.category == 'browser':
                raise ValueError('Native browser captures are unsupported; choose a compatible test app.')
        except Exception as exc:
            self.error(exc)
            return
        self.invalidate_result()
        self.preview_source = self.preview_photo = None
        self.capture_note.set('Capturing…')
        self.render()
        self.busy(True)
        self.status.set('Opening the test app for a capture…')
        def work():
            driver, message = None, None
            try:
                driver = get_driver(mode)
                driver.cancel_event,driver.operation_deadline = self.cancel,time.monotonic()+30
                driver.launch(test['app'],entry.command)
                driver.check_input_target(test['app'])
                path = contained(self.workspace,'captures/'+uuid.uuid4().hex+'.png')
                path.parent.mkdir(parents=True,exist_ok=True)
                driver.screenshot(str(path))
                message = ('capture',str(path),mode)
            except KeyboardInterrupt:
                message = ('error','Capture stopped — not a test result.')
            except Exception as exc:
                message = ('error',type(exc).__name__+': capture failed. The app may be unsupported.')
            finally:
                if driver:
                    try:
                        driver.close()
                    except Exception:
                        message = ('error','App cleanup failed; inspect the disposable test app before retrying.')
                self.messages.put(message)
        threading.Thread(target=work,daemon=True).start()

    def start(self):
        if self.running:
            return
        try:
            if not self.prepare():
                messagebox.showinfo('Choose an app','Choose a sample or a test app first.')
                return
        except Exception as exc:
            self.error(exc)
            return
        if self.accept.get() and not messagebox.askyesno('Replace baselines?',
                'This replaces matching baseline images. Accept only a deliberate, reviewed app change.'):
            return
        if not self.native_consent():
            return
        test,config,mode,accept = self.test.get(),self.config.get(),self.mode.get(),self.accept.get()
        try:
            self.draft = load_test(test)
        except Exception as exc:
            self.error(exc)
            return
        self.result,self.entries,self.report = None,[],None
        self.comparison_visible = False
        self.preview_source = self.preview_photo = None
        self.capture_note.set('Waiting for this run')
        self.stage = 3
        self.render()
        self.busy(True)
        self.status.set('Starting check…')
        self.progress.configure(value=0)
        self.detail.set('Preparing the selected test app')
        def work():
            driver,message = None,None
            try:
                from .runner import run_test
                permissions = PermissionConfig.from_file(config)
                driver = get_driver(mode)
                result = run_test(test,permissions,driver,str(contained(self.workspace,'runs/'+uuid.uuid4().hex)),
                    update_baselines=accept,cancel_event=self.cancel,
                    progress=lambda n,total,kind:self.messages.put(('progress',n,total,kind)))
                message = ('done',result)
            except Exception as exc:
                message = ('error',type(exc).__name__+': check setup failed. Review Advanced files and app compatibility.')
            finally:
                if driver:
                    try:
                        driver.close()
                    except Exception:
                        message = ('error','App cleanup failed; do not treat this run as passed.')
                self.messages.put(message)
        threading.Thread(target=work,daemon=True).start()

    def poll(self):
        try:
            while True:
                msg = self.messages.get_nowait()
                if msg[0]=='progress':
                    _,n,total,kind = msg
                    self.progress.configure(maximum=total,value=max(0,n-1))
                    self.status.set(f'Running step {n} of {total}')
                    self.detail.set({'launch':'Opening app','click':'Clicking control','type':'Entering test text',
                        'key':'Pressing key','wait':'Waiting','screenshot':'Capturing app','assert':'Verifying result'}.get(kind,kind))
                    self.append(f'{n}/{total} {kind}')
                    continue
                self.busy(False)
                if msg[0]=='capture':
                    self.set_preview(msg[1],msg[2]=='mock')
                    self.status.set('Capture ready. Select a click step and pick a location.')
                    self.detail.set('The newly launched app was closed. The image is not live.')
                elif msg[0]=='done':
                    self.result = msg[1]
                    self.report = Path(self.result.out_dir)/'report.html'
                    self.entries = [json.loads(line) for line in (Path(self.result.out_dir)/'actions.jsonl').read_text().splitlines()]
                    data = json.loads((Path(self.result.out_dir)/'result.json').read_text())
                    shots = list(data.get('screenshots',{}).values())
                    if shots:
                        self.set_preview(contained(self.result.out_dir,shots[-1]),self.result.driver=='mock')
                    self.status.set(self.result.status.upper()+(' • SIMULATION — no real app tested' if self.result.driver=='mock' else ' • Windows check'))
                    self.status_label.configure(foreground='#16846b' if self.result.passed else '#b93827',
                                                font=('Segoe UI',-18,'bold'))
                    ok = sum(e['outcome']=='ok' for e in self.entries)
                    total = len(self.draft['steps']) if self.draft else len(self.entries)
                    self.progress.configure(maximum=max(1,total),value=min(ok,total))
                    self.detail.set(f'{ok} of {total} actions passed. '+('View captured evidence.' if self.result.passed else 'Review the highlighted step.'))
                    self.view.state(['!disabled'])
                    self.run.configure(text='Run again')
                    self.append(self.status.get())
                    self.render()
                else:
                    self.result,self.report = None,None
                    self.view.state(['disabled'])
                    self.status.set('SETUP ERROR — '+msg[1])
                    self.detail.set('No successful result. Fix setup and try again.')
                    self.append(self.status.get())
        except queue.Empty:
            pass
        except Exception as exc:
            self.busy(False)
            self.result,self.report = None,None
            self.view.state(['disabled'])
            self.status.set('RESULT ERROR — could not display evidence: '+type(exc).__name__)
        self.timer = self.root.after(80,self.poll)

    def reset_sample(self):
        self.invalidate_result()
        self.preview_source = self.preview_photo = None
        self.capture_note.set('No capture yet')
        self.log.configure(state='normal')
        self.log.delete('1.0','end')
        self.log.configure(state='disabled')

    def load_sample(self):
        if self.running or not self.confirm_discard():
            return
        test = {'version':1,'name':'sample','app':'demo-app','steps':[
            {'type':'launch','app':'demo-app'},{'type':'type','text':'Synthetic demo only'},
            {'type':'screenshot','name':'main'},{'type':'assert','kind':'screenshot-saved','screenshot':'main'}]}
        self.adopt(test,{'apps':{'demo-app':{}}},'mock','Simulation sample')
        self.save_check(False)
        self.status.set('Simulation sample loaded. It does not interact with a real app.')

    def load_windows_sample(self):
        if self.running or not self.confirm_discard():
            return
        base = Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[1]/'.qa-output'
        exe = base/'DeskCheckSample.exe'
        if not exe.is_file():
            messagebox.showinfo('Windows sample unavailable','The portable package includes the sample. Source developers can compile test/Fixture.cs as .qa-output/DeskCheckSample.exe.')
            return
        state = contained(self.workspace,'sample-state/'+uuid.uuid4().hex+'.json')
        state.parent.mkdir(parents=True,exist_ok=True)
        test = {'version':1,'name':'save-a-note','app':'sample-app','steps':[
            {'type':'launch','app':'sample-app'},{'type':'click','x':80,'y':100},
            {'type':'type','text':'Synthetic acceptance check'},{'type':'click','x':100,'y':165},
            {'type':'click','x':80,'y':225},{'type':'assert','kind':'control-text','text':'Saved: Synthetic acceptance check'},
            {'type':'screenshot','name':'completed'},{'type':'assert','kind':'window-visible','window':'sample-app'}]}
        self.adopt(test,{'apps':{'sample-app':{'command':[str(exe),str(state)],'category':'app'}}},'windows','Save a note')
        self.save_check(False)
        self.status.set('Sample loaded. Capture or Run asks before launching it.')

    def import_files(self, test_path=None, config_path=None, mode=None):
        try:
            if not self.confirm_discard():
                return
            test_path,config_path = test_path or self.test.get(),config_path or self.config.get()
            test = load_test(test_path)
            with Path(config_path).open(encoding='utf-8') as fh:
                config = load_yaml(fh.read(1024*1024+1))
            PermissionConfig.from_dict(config).check_launch(test['app'])
            self.adopt(test,config,mode or self.mode.get(),test['name'].replace('-',' ').capitalize())
            self.test.set(str(test_path))
            self.config.set(str(config_path))
            self.save_check(False)
            if self.advanced_window:
                self.advanced_window.destroy()
                self.advanced_window = None
        except Exception as exc:
            self.error(exc)

    def advanced(self):
        if self.running:
            return
        if self.advanced_window and self.advanced_window.winfo_exists():
            self.advanced_window.lift()
            return
        win = self.advanced_window = tk.Toplevel(self.root)
        win.title('DeskCheck — Advanced')
        win.geometry('760x560')
        win.transient(self.root)
        win.grab_set()
        frame = ttk.Frame(win,padding=22)
        frame.pack(fill='both',expand=True)
        ttk.Label(frame,text='Import an existing check',style='Heading.TLabel').pack(anchor='w')
        ttk.Label(frame,text='Imports are copies. Original files are never edited.',style='Muted.TLabel').pack(anchor='w',pady=(8,16))
        import_test = tk.StringVar(value=self.test.get())
        import_config = tk.StringVar(value=self.config.get())
        import_mode = tk.StringVar(value=self.mode.get())
        for label,var in (('Test YAML / JSON',import_test),('Allowlist YAML / JSON',import_config)):
            ttk.Label(frame,text=label).pack(anchor='w')
            row = ttk.Frame(frame)
            row.pack(fill='x',pady=(4,12))
            ttk.Entry(row,textvariable=var).pack(side='left',fill='x',expand=True)
            self.button(row,'Browse…',lambda v=var:self.browse(v)).pack(side='right',padx=(8,0))
        ttk.Label(frame,text='Backend (simulation never proves a real app works)').pack(anchor='w')
        self.backend = ttk.Combobox(frame,textvariable=import_mode,values=('mock','windows'),state='readonly')
        self.backend.pack(anchor='w',pady=8)
        self.baseline = ttk.Checkbutton(frame,text='Accept screenshots as baselines (asks before replacement)',variable=self.accept)
        self.baseline.pack(anchor='w',pady=8)
        self.button(frame,'Import copy into library',lambda:self.import_files(import_test.get(),import_config.get(),import_mode.get()),'folder').pack(anchor='w',pady=8)
        ttk.Label(frame,text=f'Version {__version__} • Workspace: {self.workspace}',style='Muted.TLabel',wraplength=700).pack(anchor='w',pady=8)
        log = tk.Text(frame,height=5,wrap='word',font=('Consolas',-13),bg=PALE,fg=INK,relief='flat')
        log.pack(fill='both',expand=True)
        log.insert('end',self.log.get('1.0','end'))
        log.configure(state='disabled')

    def browse(self, var):
        path = filedialog.askopenfilename(title='Choose check file',filetypes=[('YAML or JSON','*.yaml *.yml *.json')])
        if path:
            var.set(path)

    def append(self, text):
        self.log.configure(state='normal')
        self.log.insert('end',text+'\n')
        self.log.configure(state='disabled')

    def error(self, exc):
        self.status.set('Needs attention — '+str(exc))
        messagebox.showerror('Check needs attention',str(exc))

    def open_report(self):
        if self.report and self.report.is_file():
            webbrowser.open(self.report.resolve().as_uri())

    def close(self):
        if self.running:
            self.cancel.set()
            self.status.set('Stopping safely… wait for the test app to close, then close DeskCheck.')
            return
        if not self.confirm_discard():
            return
        self.root.after_cancel(self.timer)
        self.root.destroy()


def main():
    root = tk.Tk()
    Desktop(root)
    root.mainloop()


if __name__=='__main__':
    main()

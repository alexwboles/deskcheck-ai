"""Small offline desktop runner; Tk stays on the UI thread, tests in a worker."""
from __future__ import annotations
import json
import os
from pathlib import Path
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import uuid
import webbrowser

from . import __version__
from .factory import get_driver
from .permissions import PermissionConfig
from .runner import run_test


class Desktop:
    def __init__(self,root,workspace=None):
        self.root = root
        self.workspace = Path(workspace or os.environ.get("DESKCHECK_WORKSPACE",Path.home()/"Documents"/"DeskCheck"))
        self.messages = queue.Queue()
        self.cancel = threading.Event()
        self.running = False
        self.report = None
        root.title("DeskCheck — Desktop test runner")
        root.geometry("960x740")
        root.minsize(740,650)
        root.configure(bg="#f3f6fa")
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TFrame",background="#f3f6fa")
        style.configure("TLabel",background="#f3f6fa",foreground="#203542",font=("Segoe UI",11))
        style.configure("Title.TLabel",font=("Segoe UI",24,"bold"))
        style.configure("TButton",font=("Segoe UI",11),padding=(14,9))
        style.configure("TEntry",padding=8)
        frame = ttk.Frame(root,padding=28)
        frame.pack(fill="both",expand=True)
        frame.columnconfigure(1,weight=1)
        ttk.Label(frame,text="DeskCheck",style="Title.TLabel").grid(row=0,column=0,columnspan=3,sticky="w")
        ttk.Label(frame,text="Run a repeatable test. Inspect the evidence. Know what passed.").grid(row=1,column=0,columnspan=3,sticky="w",pady=(4,20))
        self.test = tk.StringVar()
        self.config = tk.StringVar()
        self.mode = tk.StringVar(value="mock")
        self.accept = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="Ready — load the sample to try an offline test.")
        self.inputs = []
        for row,label,var,kind in ((2,"Test YAML",self.test,"test"),(3,"Allowlist YAML",self.config,"config")):
            ttk.Label(frame,text=label).grid(row=row,column=0,sticky="w",padx=(0,16),pady=8)
            entry = ttk.Entry(frame,textvariable=var)
            entry.grid(row=row,column=1,sticky="ew",pady=8)
            button = ttk.Button(frame,text="Browse…",command=lambda v=var:self.browse(v))
            button.grid(row=row,column=2,padx=(10,0))
            self.inputs.extend((entry,button))
        ttk.Label(frame,text="Backend").grid(row=4,column=0,sticky="w",pady=10)
        self.backend = ttk.Combobox(frame,textvariable=self.mode,values=("mock","windows"),state="readonly",width=20)
        self.backend.grid(row=4,column=1,sticky="w")
        ttk.Label(frame,text="Mock = simulated. Windows = new standard-control test app only.",wraplength=750).grid(row=5,column=0,columnspan=3,sticky="w",pady=(0,12))
        self.baseline = ttk.Checkbutton(frame,text="Accept these screenshots as baselines (replaces matching baselines)",variable=self.accept)
        self.baseline.grid(row=6,column=0,columnspan=3,sticky="w")
        toolbar = ttk.Frame(frame)
        toolbar.grid(row=7,column=0,columnspan=3,sticky="ew",pady=20)
        self.sample = ttk.Button(toolbar,text="Load sample",command=self.load_sample)
        self.sample.pack(side="left")
        self.native_sample = ttk.Button(toolbar,text="Windows sample",command=self.load_windows_sample)
        self.native_sample.pack(side="left",padx=(8,0))
        self.run = ttk.Button(toolbar,text="Run test",command=self.start)
        self.run.pack(side="left",padx=10)
        self.stop = ttk.Button(toolbar,text="Stop",command=self.cancel.set,state="disabled")
        self.stop.pack(side="left")
        self.view = ttk.Button(toolbar,text="View report",command=self.open_report,state="disabled")
        self.view.pack(side="right")
        self.progress = ttk.Progressbar(frame,mode="determinate")
        self.progress.grid(row=8,column=0,columnspan=3,sticky="ew")
        ttk.Label(frame,textvariable=self.status,wraplength=840).grid(row=9,column=0,columnspan=3,sticky="w",pady=12)
        self.log = tk.Text(frame,height=9,wrap="word",font=("Consolas",10),bg="white",fg="#203542",relief="flat",padx=14,pady=12,state="disabled")
        self.log.grid(row=10,column=0,columnspan=3,sticky="nsew")
        frame.rowconfigure(10,weight=1)
        ttk.Label(frame,text="Offline • No AI/API charges • Typed text redacted from logs\nScreenshots can contain app data. Use synthetic data and review before sharing.",wraplength=840).grid(row=11,column=0,columnspan=3,sticky="w",pady=(14,0))
        ttk.Label(frame,text=f"Version {__version__}  |  Outputs: {self.workspace}",wraplength=840,font=("Segoe UI",9)).grid(row=12,column=0,columnspan=3,sticky="w",pady=(8,0))
        root.protocol("WM_DELETE_WINDOW",self.close)
        root.after(100,self.poll)

    def browse(self,var):
        path = filedialog.askopenfilename(title="Choose YAML",filetypes=[("YAML","*.yaml *.yml")])
        if path:
            var.set(path)

    def load_sample(self):
        sample = self.workspace/("sample-"+uuid.uuid4().hex[:8])
        sample.mkdir(parents=True)
        test = {"version":1,"name":"sample","app":"demo-app","steps":[
            {"type":"launch","app":"demo-app"},
            {"type":"type","text":"Synthetic demo only"},
            {"type":"screenshot","name":"main"},
            {"type":"assert","kind":"screenshot-saved","screenshot":"main"}]}
        # JSON is valid YAML and avoids dependency/format surprises in the sample.
        (sample/"test.yaml").write_text(json.dumps(test,indent=2),encoding="utf-8")
        (sample/"config.yaml").write_text(json.dumps({"apps":{"demo-app":{}}},indent=2),encoding="utf-8")
        self.test.set(str(sample/"test.yaml"))
        self.config.set(str(sample/"config.yaml"))
        self.mode.set("mock")
        self.accept.set(False)
        self.status.set("Sample loaded. Click Run test; this uses no real desktop or network.")

    def append(self,text):
        self.log.configure(state="normal")
        self.log.insert("end",text+"\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def load_windows_sample(self):
        base = Path(sys.executable).parent if getattr(sys,"frozen",False) else Path(__file__).resolve().parents[1]/".qa-output"
        exe = base/"DeskCheckSample.exe"
        if not exe.is_file():
            messagebox.showinfo("Portable Windows sample","The prebuilt Windows sample is included in the portable package. Source developers can compile test/Fixture.cs as .qa-output/DeskCheckSample.exe.")
            return
        sample = self.workspace/("windows-sample-"+uuid.uuid4().hex[:8])
        sample.mkdir(parents=True)
        test = {"version":1,"name":"windows-sample","app":"sample-app","steps":[
            {"type":"launch","app":"sample-app"},
            {"type":"click","x":80,"y":100},
            {"type":"type","text":"Synthetic acceptance check"},
            {"type":"click","x":100,"y":165},
            {"type":"screenshot","name":"completed"},
            {"type":"assert","kind":"window-visible","window":"sample-app"}]}
        (sample/"test.yaml").write_text(json.dumps(test,indent=2),encoding="utf-8")
        (sample/"config.yaml").write_text(json.dumps({"apps":{"sample-app":{"command":[str(exe),str(sample/"state.json")],"category":"app"}}},indent=2),encoding="utf-8")
        self.test.set(str(sample/"test.yaml"))
        self.config.set(str(sample/"config.yaml"))
        self.mode.set("windows")
        self.accept.set(False)
        self.status.set("Windows sample loaded. Run test will ask before launching the bundled offline sample app.")

    def start(self):
        if self.running:
            return
        if not self.test.get() or not self.config.get():
            messagebox.showinfo("Choose files","Load the sample or select a test and allowlist first.")
            return
        if self.accept.get() and not messagebox.askyesno("Replace baselines?","This accepts the current screenshots and replaces matching baseline files. Only do this after reviewing the intended change."):
            return
        test,config,mode,accept = self.test.get(),self.config.get(),self.mode.get(),self.accept.get()
        if mode == "windows" and not messagebox.askyesno("Run the allowlisted test app?","DeskCheck will launch the executable in your allowlist and close that newly launched process when the test ends. Use only a trusted disposable test app and synthetic data. It is not an OS/filesystem/network sandbox. Continue?"):
            return
        self.running = True
        self.cancel.clear()
        self.report = None
        self.status.set("Starting test…")
        self.progress.configure(value=0)
        for widget in self.inputs+[self.run,self.sample,self.native_sample,self.backend,self.baseline]:
            widget.configure(state="disabled")
        self.stop.configure(state="normal")
        self.view.configure(state="disabled")
        def work():
            driver = None
            try:
                permissions = PermissionConfig.from_file(config)
                driver = get_driver(mode)
                out = self.workspace/"runs"/uuid.uuid4().hex
                result = run_test(test,permissions,driver,str(out),update_baselines=accept,
                    cancel_event=self.cancel,progress=lambda n,total,kind:self.messages.put(("progress",n,total,kind)))
                message = ("done",result)
            except Exception as exc:
                message = ("error",f"{type(exc).__name__}: {exc}")
            finally:
                if driver:
                    driver.close()
            self.messages.put(message)
        threading.Thread(target=work,daemon=True).start()

    def poll(self):
        try:
            while True:
                message = self.messages.get_nowait()
                if message[0] == "progress":
                    _,n,total,kind = message
                    self.progress.configure(maximum=total,value=n)
                    self.status.set(f"Running {n}/{total} — {kind}")
                    self.append(f"{n}/{total}  {kind}")
                else:
                    self.running = False
                    for widget in self.inputs+[self.run,self.sample,self.native_sample,self.baseline]:
                        widget.configure(state="normal")
                    self.backend.configure(state="readonly")
                    self.stop.configure(state="disabled")
                    if message[0] == "done":
                        result = message[1]
                        self.report = Path(result.out_dir)/"report.html"
                        self.status.set(f"{result.status.upper()} — {result.steps_run} logged actions. View the report for evidence.")
                        self.append(self.status.get())
                        for failure in result.failures:
                            self.append(failure)
                        self.view.configure(state="normal")
                    else:
                        self.status.set("SETUP ERROR — "+message[1])
                        self.append(self.status.get())
        except queue.Empty:
            pass
        self.root.after(100,self.poll)

    def open_report(self):
        if self.report and self.report.is_file():
            webbrowser.open(self.report.resolve().as_uri())

    def close(self):
        if self.running:
            self.cancel.set()
            self.status.set("Stopping safely… wait for the run to finish before closing.")
            return
        self.root.destroy()


def main():
    root = tk.Tk()
    Desktop(root)
    root.mainloop()


if __name__ == "__main__":
    main()

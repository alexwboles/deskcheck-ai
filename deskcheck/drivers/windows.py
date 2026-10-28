"""Windows standard-control backend: pinned PID/HWND, no global input.

Coordinates are client-area pixels. Messages go only to windows owned by the
process this driver launched. No SendInput, SendKeys, shells, clipboard, screen
copy or attachment to an existing process. Unsupported/custom-rendered apps
must use another test framework; this is not an OS sandbox.
"""
from __future__ import annotations

import ctypes as C
from ctypes import wintypes as W
import os
from pathlib import Path
import subprocess
import time
import multiprocessing

from .base import Driver
from ..errors import DeskcheckError, DriverUnavailable, PermissionDenied
from ..pngutil import encode_png
from ..safety import KEYS, literal_text, named_key

BLOCKED_EXES = {"cmd.exe", "powershell.exe", "pwsh.exe", "wt.exe", "conhost.exe",
                "regedit.exe", "control.exe", "rundll32.exe", "mshta.exe",
                "wscript.exe", "cscript.exe", "explorer.exe", "msedge.exe",
                "chrome.exe", "firefox.exe", "brave.exe", "opera.exe",
                "1password.exe", "keepass.exe", "keepassxc.exe", "bitwarden.exe",
                "credentialuibroker.exe", "systemsettings.exe"}
VKEYS = {"Enter":13, "Return":13, "Tab":9, "Escape":27, "Backspace":8,
         "Delete":46, "Left":37, "Up":38, "Right":39, "Down":40,
         "Home":36, "End":35, "PageUp":33, "PageDown":34, "Space":32}
VKEYS.update({f"F{i}":111+i for i in range(1,13)})


class BitmapInfoHeader(C.Structure):
    _fields_ = [("size",W.DWORD),("width",W.LONG),("height",W.LONG),
                ("planes",W.WORD),("bits",W.WORD),("compression",W.DWORD),
                ("image_size",W.DWORD),("xppm",W.LONG),("yppm",W.LONG),
                ("used",W.DWORD),("important",W.DWORD)]


class WindowsDriver(Driver):
    name = "windows"

    def __init__(self):
        if os.name != "nt":
            raise DriverUnavailable("Windows standard-control driver requires Windows")
        self.u = C.WinDLL("user32", use_last_error=True)
        self.g = C.WinDLL("gdi32", use_last_error=True)
        self.k = C.WinDLL("kernel32", use_last_error=True)
        self._process = None
        self._hwnd = self._input_hwnd = None
        self._app = None
        self.timeout_ms = 30000
        self.cancel_event = None
        self.operation_deadline = None
        self._signatures()

    def _signatures(self):
        def sig(lib, name, args, result):
            fn = getattr(lib, name)
            fn.argtypes, fn.restype = args, result
        H = W.HANDLE
        self.callback_type = C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
        sig(self.u,"EnumWindows",[self.callback_type,W.LPARAM],W.BOOL)
        sig(self.u,"GetWindowThreadProcessId",[W.HWND,C.POINTER(W.DWORD)],W.DWORD)
        sig(self.u,"IsWindow",[W.HWND],W.BOOL)
        sig(self.u,"IsWindowVisible",[W.HWND],W.BOOL)
        sig(self.u,"IsWindowEnabled",[W.HWND],W.BOOL)
        sig(self.u,"GetWindow",[W.HWND,W.UINT],W.HWND)
        sig(self.u,"IsChild",[W.HWND,W.HWND],W.BOOL)
        sig(self.u,"GetClientRect",[W.HWND,C.POINTER(W.RECT)],W.BOOL)
        sig(self.u,"MapWindowPoints",[W.HWND,W.HWND,C.POINTER(W.POINT),W.UINT],C.c_int)
        sig(self.u,"ChildWindowFromPointEx",[W.HWND,W.POINT,W.UINT],W.HWND)
        sig(self.u,"GetNextDlgTabItem",[W.HWND,W.HWND,W.BOOL],W.HWND)
        sig(self.u,"GetClassNameW",[W.HWND,W.LPWSTR,C.c_int],C.c_int)
        sig(self.u,"GetWindowLongW",[W.HWND,C.c_int],W.LONG)
        sig(self.u,"SendMessageTimeoutW",[W.HWND,W.UINT,W.WPARAM,W.LPARAM,W.UINT,W.UINT,C.POINTER(C.c_size_t)],C.c_ssize_t)
        sig(self.u,"GetDC",[W.HWND],H)
        sig(self.u,"PrintWindow",[W.HWND,H,W.UINT],W.BOOL)
        sig(self.u,"ReleaseDC",[W.HWND,H],C.c_int)
        sig(self.g,"CreateCompatibleDC",[H],H)
        sig(self.g,"CreateCompatibleBitmap",[H,C.c_int,C.c_int],H)
        sig(self.g,"SelectObject",[H,H],H)
        sig(self.g,"DeleteObject",[H],W.BOOL)
        sig(self.g,"DeleteDC",[H],W.BOOL)
        sig(self.g,"GetDIBits",[H,H,W.UINT,W.UINT,C.c_void_p,C.POINTER(BitmapInfoHeader),W.UINT],C.c_int)
        sig(self.k,"QueryFullProcessImageNameW",[H,W.DWORD,W.LPWSTR,C.POINTER(W.DWORD)],W.BOOL)
        sig(self.k,"OpenProcess",[W.DWORD,W.BOOL,W.DWORD],H)
        sig(self.k,"CloseHandle",[H],W.BOOL)

    def _remaining(self):
        if self.cancel_event is not None and self.cancel_event.is_set():
            raise KeyboardInterrupt
        remaining = self.timeout_ms
        if self.operation_deadline:
            remaining = min(remaining, int((self.operation_deadline-time.monotonic())*1000))
        if remaining <= 0:
            raise DeskcheckError("Native operation timed out")
        return max(1, min(remaining, 5000))

    def _owned(self, hwnd):
        if not self._process or self._process.poll() is not None or not hwnd or not self.u.IsWindow(hwnd):
            raise PermissionDenied("Launched app/window is no longer available")
        pid = W.DWORD()
        self.u.GetWindowThreadProcessId(hwnd, C.byref(pid))
        if pid.value != self._process.pid:
            raise PermissionDenied("Window belongs to a different process")
        length = W.DWORD(32768)
        name = C.create_unicode_buffer(length.value)
        if not self.k.QueryFullProcessImageNameW(int(self._process._handle),0,name,C.byref(length)):
            raise PermissionDenied("Cannot verify launched executable identity")
        if os.path.normcase(os.path.realpath(name.value)) != self._exe:
            raise PermissionDenied("Executable identity changed")
        if self._hwnd and hwnd != self._hwnd and not self.u.IsChild(self._hwnd, hwnd):
            raise PermissionDenied("Control lies outside the bound app window")
        return hwnd

    def _send(self, hwnd, message, wparam=0, lparam=0):
        self._owned(hwnd)
        result = C.c_size_t()
        if not self.u.SendMessageTimeoutW(hwnd,message,wparam,lparam,0x02|0x20,self._remaining(),C.byref(result)):
            raise DeskcheckError("App did not acknowledge targeted window message")
        self._owned(hwnd)
        return result.value

    def launch(self, app_name, command=None):
        if self._process is not None:
            raise PermissionDenied("One launched app per driver; close it before another launch")
        if not isinstance(command,list) or not command or not all(isinstance(a,str) and '\x00' not in a for a in command):
            raise PermissionDenied("Native command must be an argv list, not a shell string")
        exe = Path(command[0])
        if not exe.is_absolute() or not exe.is_file() or exe.suffix.lower() != ".exe":
            raise PermissionDenied("Native executable must be an existing absolute .exe path")
        if exe.name.lower() in BLOCKED_EXES:
            raise PermissionDenied("Shells, browsers, settings and credential apps are unsupported")
        self._exe = os.path.normcase(os.path.realpath(exe))
        try:
            self._process = subprocess.Popen(command, shell=False, cwd=str(exe.parent),
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self._app = app_name
            deadline = time.monotonic() + self.timeout_ms/1000
            while time.monotonic() < deadline:
                self._remaining()
                if self._process.poll() is not None:
                    raise DeskcheckError("App exited before exposing a window")
                windows = []
                @self.callback_type
                def collect(hwnd, _):
                    pid = W.DWORD()
                    self.u.GetWindowThreadProcessId(hwnd,C.byref(pid))
                    if pid.value == self._process.pid and self.u.IsWindowVisible(hwnd) and not self.u.GetWindow(hwnd,4):
                        windows.append(hwnd)
                    return True
                self.u.EnumWindows(collect,0)
                if len(windows) > 1:
                    raise PermissionDenied("App exposed multiple root windows; cannot select safely")
                if len(windows) == 1:
                    self._hwnd = windows[0]
                    self._owned(self._hwnd)
                    return
                time.sleep(.025)
            raise DeskcheckError("App window launch timed out")
        except BaseException:
            self.close()
            raise

    def check_input_target(self, app_name):
        if not getattr(self,"_process",None) or app_name != self._app:
            raise PermissionDenied("No verified launched app is bound")
        self._owned(self._hwnd)
        if not self.u.IsWindowVisible(self._hwnd) or not self.u.IsWindowEnabled(self._hwnd):
            raise PermissionDenied("Bound window is hidden, disabled or blocked by a modal")

    def foreground_window(self):
        # The assertion means bound-window-visible, not global OS foreground.
        try:
            self.check_input_target(self._app)
            return self._app
        except (PermissionDenied, AttributeError):
            return None

    def click(self,x,y):
        self.check_input_target(self._app)
        w,h = self.resolution()
        if type(x) is not int or type(y) is not int or not 0 <= x < w or not 0 <= y < h:
            raise PermissionDenied("Click is outside the bound client area")
        target, point = self._hwnd, W.POINT(x,y)
        for _ in range(32):
            child = self.u.ChildWindowFromPointEx(target,point,1|2|4)
            if not child or child == target:
                break
            self._owned(child)
            self.u.MapWindowPoints(target,child,C.byref(point),1)
            target = child
        self._input_hwnd = self._owned(target)
        cls = C.create_unicode_buffer(256)
        self.u.GetClassNameW(target,cls,256)
        if "button" in cls.value.lower():
            self._send(target,0xf5)  # BM_CLICK: standard-button activation.
            return
        coords = (point.y & 0xffff) << 16 | (point.x & 0xffff)
        self._send(target,0x201,1,coords)
        self._send(target,0x202,0,coords)

    def type_text(self,text):
        literal_text(text)
        self.check_input_target(self._app)
        target = self._owned(self._input_hwnd)
        cls = C.create_unicode_buffer(256)
        self.u.GetClassNameW(target,cls,256)
        if "edit" not in cls.value.lower():
            raise PermissionDenied("Click a standard edit control before typing")
        if self.u.GetWindowLongW(target,-16) & 0x20:
            raise PermissionDenied("Password edit controls are not supported")
        # UTF-16 code units; no SendKeys expansion, shell interpolation or clipboard.
        raw = text.encode("utf-16-le")
        for i in range(0,len(raw),2):
            self._send(target,0x102,int.from_bytes(raw[i:i+2],"little"),1)

    def press_key(self,key):
        named_key(key)
        self.check_input_target(self._app)
        target = self._owned(self._input_hwnd or self._hwnd)
        cls = C.create_unicode_buffer(256)
        self.u.GetClassNameW(target,cls,256)
        if key == "Tab":
            next_control = self.u.GetNextDlgTabItem(self._hwnd,target,False)
            self._input_hwnd = self._owned(next_control)
            self._send(self._hwnd,0x28,next_control,1)
        elif key in ("Enter","Return","Space") and "button" in cls.value.lower():
            self._send(target,0xf5)
        elif key in ("Enter","Return","Backspace","Space"):
            self._send(target,0x102,VKEYS[key],1)
        else:
            self._send(target,0x100,VKEYS[key],1)
            self._send(target,0x101,VKEYS[key],0xc0000001)

    def read_text(self):
        self.check_input_target(self._app)
        target = self._owned(self._input_hwnd)
        cls = C.create_unicode_buffer(256)
        self.u.GetClassNameW(target,cls,256)
        if "edit" in cls.value.lower() and self.u.GetWindowLongW(target,-16) & 0x20:
            raise PermissionDenied("Password edit controls are not supported")
        length = self._send(target,0x0e)
        if length > 10000:
            raise DeskcheckError("Selected control text exceeds 10000 characters")
        value = C.create_unicode_buffer(length+1)
        self._send(target,0x0d,len(value),C.addressof(value))
        return value.value

    def screenshot(self,path):
        self.check_input_target(self._app)
        # PrintWindow may hang in an unresponsive app. Run capture in an isolated
        # worker and bound its lifetime, without killing the app on capture timeout.
        context = multiprocessing.get_context("spawn")
        receiver,sender = context.Pipe(duplex=False)
        worker = context.Process(target=_capture_worker,
            args=(sender,self._hwnd,self._process.pid,self._exe))
        try:
            worker.start()
            sender.close()
            deadline = time.monotonic()+self._remaining()/1000
            while not receiver.poll(.025):
                self._remaining()
                if time.monotonic() >= deadline or not worker.is_alive():
                    raise DeskcheckError("Bound app capture timed out or worker exited")
            payload = receiver.recv_bytes(32*1024*1024)
            if not payload.startswith(b"\x89PNG\r\n\x1a\n"):
                raise DeskcheckError("App capture unavailable; custom-rendered windows may be unsupported")
            self._owned(self._hwnd)
            with open(path,"xb") as fh:
                fh.write(payload)
            return path
        finally:
            receiver.close()
            sender.close()
            if worker.pid:
                worker.join(timeout=.2)
                if worker.is_alive():
                    worker.terminate()
                    worker.join(timeout=1)

    def _capture_bound(self,hwnd,pid,exe):
        # Worker does not attach input or send keys. Verify the supplied target
        # before asking only its client area to render offscreen.
        actual = W.DWORD()
        self.u.GetWindowThreadProcessId(hwnd,C.byref(actual))
        if actual.value != pid:
            raise PermissionDenied("Capture PID mismatch")
        handle = self.k.OpenProcess(0x1000,False,pid)
        if not handle:
            raise PermissionDenied("Capture process unavailable")
        try:
            size = W.DWORD(32768)
            name = C.create_unicode_buffer(size.value)
            if not self.k.QueryFullProcessImageNameW(handle,0,name,C.byref(size)) or os.path.normcase(os.path.realpath(name.value)) != exe:
                raise PermissionDenied("Capture executable mismatch")
        finally:
            self.k.CloseHandle(handle)
        self._hwnd = hwnd
        rect = W.RECT()
        if not self.u.GetClientRect(hwnd,C.byref(rect)):
            raise DeskcheckError("Capture bounds unavailable")
        w,h = rect.right-rect.left,rect.bottom-rect.top
        if not w or not h or w*h > 4000000:
            raise DeskcheckError("Capture must be a nonempty client area of at most 4 million pixels")
        dc = self.u.GetDC(self._hwnd)
        mem = self.g.CreateCompatibleDC(dc)
        bmp = self.g.CreateCompatibleBitmap(dc,w,h)
        old = self.g.SelectObject(mem,bmp)
        try:
            if not dc or not mem or not bmp:
                raise DeskcheckError("Unable to allocate app capture")
            # Ask only the bound root and its children to draw; NEVER copy desktop pixels.
            if not self.u.PrintWindow(hwnd,mem,1):
                raise DeskcheckError("App refused client capture")
            self.g.SelectObject(mem,old)
            info = BitmapInfoHeader(C.sizeof(BitmapInfoHeader),w,-h,1,32,0,0,0,0,0,0)
            pixels = (C.c_ubyte*(w*h*4))()
            if self.g.GetDIBits(mem,bmp,0,h,pixels,C.byref(info),0) != h:
                raise DeskcheckError("Bound app did not provide a readable capture")
            rows = [[(pixels[(y*w+x)*4+2],pixels[(y*w+x)*4+1],pixels[(y*w+x)*4]) for x in range(w)] for y in range(h)]
            if not any(any(rgb) for row in rows for rgb in row):
                raise DeskcheckError("App returned a blank capture; custom-rendered windows are unsupported")
            return encode_png(w,h,rows)
        finally:
            self.g.SelectObject(mem,old)
            self.g.DeleteObject(bmp)
            self.g.DeleteDC(mem)
            self.u.ReleaseDC(self._hwnd,dc)

    def wait_window(self,window,timeout_ms):
        end = time.monotonic()+timeout_ms/1000
        while time.monotonic() < end:
            self._remaining()
            if self.foreground_window() == window:
                return True
            time.sleep(.025)
        return False

    def resolution(self):
        self._owned(self._hwnd)
        rect = W.RECT()
        if not self.u.GetClientRect(self._hwnd,C.byref(rect)):
            raise DeskcheckError("Cannot read bound client bounds")
        return rect.right-rect.left,rect.bottom-rect.top

    def close(self):
        process = getattr(self,"_process",None)
        if process and process.poll() is None:
            # Only a newly launched test process, never an attached existing app.
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                pass
        self._process = None
        self._hwnd = self._input_hwnd = None


def _capture_worker(connection,hwnd,pid,exe):
    try:
        image = WindowsDriver()._capture_bound(hwnd,pid,exe)
        connection.send_bytes(image)
    except Exception:
        connection.send_bytes(b"capture failed")
    finally:
        connection.close()

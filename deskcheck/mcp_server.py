"""Local newline-delimited JSON-RPC MCP; strict args, scoped files, real failures."""
from __future__ import annotations
import json
import os
from pathlib import Path
import sys
import uuid
import time

from . import __version__
from .assertions import assert_screenshot_saved, assert_window_visible
from .errors import DeskcheckError, PermissionDenied, ParseError
from .factory import get_driver
from .permissions import PermissionConfig
from .runner import run_test
from .safety import contained, literal_text, named_key, safe_name


def tool(name, description, properties, required):
    return {"name":name,"description":description,"inputSchema":{
        "type":"object","properties":properties,"required":required,
        "additionalProperties":False}}


TOOLS = [
    tool("launch_app","Launch a new allowlisted app; never attach to existing apps.",{"app":{"type":"string"}},["app"]),
    tool("click","Click within the bound app client area, in client pixels.",{"x":{"type":"integer"},"y":{"type":"integer"}},["x","y"]),
    tool("type_text","Send literal printable text to the selected standard edit control.",{"text":{"type":"string"}},["text"]),
    tool("press_key","Send a supported single named key; no OS shortcuts or chords.",{"key":{"type":"string"}},["key"]),
    tool("screenshot","Capture only the bound app to a new named PNG.",{"name":{"type":"string"}},["name"]),
    tool("assert_window","Assert the verified bound app window is visible.",{"window":{"type":"string"}},["window"]),
    tool("run_test","Run a YAML test below the operator-selected workspace, returning result and report path.",{"test":{"type":"string"},"update_baselines":{"type":"boolean"}},["test"]),
]


class MCPServer:
    def __init__(self,config=None,driver_name="mock",workspace=None,allow_baseline_updates=False):
        self.config = config or PermissionConfig.empty()
        self.driver_name = driver_name
        self.driver = get_driver(driver_name)
        self.current_app = None
        self.workspace = Path(workspace or os.getcwd()).resolve()
        self.allow_baseline_updates = allow_baseline_updates
        self.output = contained(self.workspace,f"deskcheck-mcp-output/session-{uuid.uuid4().hex}")
        self.shot_dir = str(self.output / "screenshots")
        self.output.mkdir(parents=True,exist_ok=False)

    def _ok(self,text):
        return {"content":[{"type":"text","text":text}],"isError":False}

    def _err(self,text):
        return {"content":[{"type":"text","text":text}],"isError":True}

    def _validate(self,name,args):
        spec = next((s for s in TOOLS if s["name"] == name),None)
        if spec is None:
            raise ParseError("Unknown tool")
        schema = spec["inputSchema"]
        if not isinstance(args,dict) or set(args)-set(schema["properties"]) or set(schema["required"])-set(args):
            raise ParseError("Missing or unknown tool arguments")
        for key,value in args.items():
            kind = schema["properties"][key]["type"]
            if kind == "string" and not isinstance(value,str) or kind == "integer" and type(value) is not int or kind == "boolean" and type(value) is not bool:
                raise ParseError("Tool argument has wrong type")
        if name in ("launch_app","screenshot"):
            safe_name(args["app"] if name == "launch_app" else args["name"])
        if name == "type_text":
            literal_text(args["text"])
        if name == "press_key":
            named_key(args["key"])
        if name == "click" and not all(0 <= args[k] <= 32767 for k in ("x","y")):
            raise ParseError("Coordinates must be integers from 0 to 32767")

    def call_tool(self,name,args):
        try:
            self._validate(name,args)
            if name == "launch_app":
                entry = self.config.check_launch(args["app"])
                if entry.category == "browser" and self.driver.name != "mock":
                    raise PermissionDenied("Native browsers are unsupported; profile isolation is unverified")
                self.driver.timeout_ms = 30000
                self.driver.operation_deadline = time.monotonic()+30
                self.driver.launch(args["app"],entry.command)
                self.current_app = args["app"]
                return self._ok("Launched " + self.current_app)
            if name in ("click","type_text","press_key","screenshot"):
                self.config.check_input(self.current_app)
                self.driver.operation_deadline = time.monotonic()+30
                self.driver.check_input_target(self.current_app)
                if name == "click":
                    self.driver.click(args["x"],args["y"])
                elif name == "type_text":
                    self.driver.type_text(args["text"])
                elif name == "press_key":
                    self.driver.press_key(args["key"])
                else:
                    path = contained(self.shot_dir,args["name"]+".png")
                    path.parent.mkdir(parents=True,exist_ok=True)
                    if path.exists():
                        raise PermissionDenied("Screenshot already exists; use a new name")
                    self.driver.screenshot(str(path))
                    assert_screenshot_saved(str(path))
                    return self._ok(str(path))
                return self._ok(name+" completed; content not logged")
            if name == "assert_window":
                assert_window_visible(self.driver,args["window"])
                return self._ok("Bound app window is visible")
            if name == "run_test":
                if args.get("update_baselines",False) and not self.allow_baseline_updates:
                    raise PermissionDenied("Baseline replacement requires operator --allow-baseline-updates")
                path = contained(self.workspace,args["test"])
                driver = get_driver(self.driver_name)
                try:
                    result = run_test(str(path),self.config,driver,
                        contained(self.output,"run-"+uuid.uuid4().hex),
                        update_baselines=args.get("update_baselines",False))
                finally:
                    driver.close()
                payload = json.dumps({"status":result.status,"name":result.name,"driver":result.driver,
                    "failures":result.failures,"report":str(Path(result.out_dir)/"report.html")})
                return (self._ok if result.passed else self._err)(payload)
            return self._err("Unknown tool")
        except KeyboardInterrupt:
            return self._err("Operation interrupted; completed actions are not rolled back")
        except Exception as exc:
            # Never echo a raw driver error that could contain a typed secret.
            safe = str(exc) if isinstance(exc,DeskcheckError) and name != "type_text" else type(exc).__name__+": tool failed"
            return self._err(safe)

    def handle(self,req):
        if not isinstance(req,dict) or req.get("jsonrpc") != "2.0" or not isinstance(req.get("method"),str):
            return {"jsonrpc":"2.0","id":None,"error":{"code":-32600,"message":"Invalid request"}}
        rid = req.get("id")
        if "id" not in req:
            return None  # Notifications must never trigger unacknowledged UI actions.
        if isinstance(rid,bool) or rid is not None and not isinstance(rid,(str,int)):
            return {"jsonrpc":"2.0","id":None,"error":{"code":-32600,"message":"Invalid id"}}
        params = req.get("params",{})
        if not isinstance(params,dict):
            return {"jsonrpc":"2.0","id":rid,"error":{"code":-32602,"message":"Invalid params"}}
        method = req["method"]
        if method == "initialize":
            result = {"protocolVersion":"2024-11-05","capabilities":{"tools":{}},
                      "serverInfo":{"name":"deskcheck","version":__version__}}
        elif method == "tools/list":
            result = {"tools":TOOLS}
        elif method == "tools/call":
            result = self.call_tool(params.get("name"),params.get("arguments",{}))
        elif method == "ping":
            result = {}
        else:
            return {"jsonrpc":"2.0","id":rid,"error":{"code":-32601,"message":"Method not found"}}
        return {"jsonrpc":"2.0","id":rid,"result":result}

    def close(self):
        self.driver.close()


def serve(config=None,driver_name="mock",workspace=None,allow_baseline_updates=False):
    server = MCPServer(config,driver_name,workspace,allow_baseline_updates)
    try:
        while True:
            line = sys.stdin.readline(262145)
            if not line:
                break
            if len(line) > 262144:
                while line and not line.endswith("\n"):
                    line = sys.stdin.readline(262145)
                resp = {"jsonrpc":"2.0","id":None,"error":{"code":-32600,"message":"Message exceeds 256 KiB"}}
            else:
                try:
                    resp = server.handle(json.loads(line))
                except (ValueError,RecursionError):
                    resp = {"jsonrpc":"2.0","id":None,"error":{"code":-32700,"message":"Parse error"}}
            if resp is not None:
                print(json.dumps(resp,ensure_ascii=True),flush=True)
    finally:
        server.close()

"""MCP server: stdio transport, JSON-RPC 2.0.

Methods: initialize, tools/list, tools/call, ping.
Tool failures return a normal result with ``isError: true`` (not a
transport error), per MCP convention, so the calling model can read the
reason and retry. Every tool enforces the same allowlist as the runner:
launch_app checks the config, and input tools re-check the focused app.
"""
from __future__ import annotations

import json
import os
import sys

from .assertions import assert_screenshot_saved, assert_window_visible
from .errors import DeskcheckError
from .factory import get_driver
from .permissions import PermissionConfig
from .runner import run_test

TOOLS = [
    {"name": "launch_app",
     "description": "Launch an allowlisted desktop app (default deny; denied apps fail).",
     "inputSchema": {"type": "object", "properties": {
         "app": {"type": "string"}}, "required": ["app"]}},
    {"name": "click",
     "description": "Click at primary-monitor pixel coordinates.",
     "inputSchema": {"type": "object", "properties": {
         "x": {"type": "integer"}, "y": {"type": "integer"}},
         "required": ["x", "y"]}},
    {"name": "type_text",
     "description": "Type text into the focused allowlisted app.",
     "inputSchema": {"type": "object", "properties": {
         "text": {"type": "string"}}, "required": ["text"]}},
    {"name": "press_key",
     "description": "Press a named key (e.g. Enter, Tab, Escape, F5) in the focused app.",
     "inputSchema": {"type": "object", "properties": {
         "key": {"type": "string"}}, "required": ["key"]}},
    {"name": "screenshot",
     "description": "Capture a screenshot to a named file; returns its path.",
     "inputSchema": {"type": "object", "properties": {
         "name": {"type": "string"}}, "required": ["name"]}},
    {"name": "assert_window",
     "description": "Assert a window is foreground.",
     "inputSchema": {"type": "object", "properties": {
         "window": {"type": "string"}}, "required": ["window"]}},
    {"name": "run_test",
     "description": "Run a deskcheck YAML test file and return its result + report path.",
     "inputSchema": {"type": "object", "properties": {
         "test": {"type": "string"},
         "update_baselines": {"type": "boolean"}},
         "required": ["test"]}},
]


class MCPServer:
    def __init__(self, config=None, driver_name="mock"):
        self.config = config or PermissionConfig.empty()
        self.driver = get_driver(driver_name)
        self.current_app = None
        self.shot_dir = os.path.join(os.getcwd(), "deskcheck-mcp-output",
                                     "screenshots")
        os.makedirs(self.shot_dir, exist_ok=True)

    def _ok(self, text):
        return {"content": [{"type": "text", "text": text}], "isError": False}

    def _err(self, text):
        return {"content": [{"type": "text", "text": text}], "isError": True}

    def call_tool(self, name, args):
        args = args or {}
        try:
            if name == "launch_app":
                entry = self.config.check_launch(args["app"])
                self.driver.launch(args["app"], entry.command)
                self.current_app = args["app"]
                return self._ok(f"launched '{args['app']}'")
            if name in ("click", "type_text", "press_key"):
                self.config.check_input(self.current_app)
                self.driver.check_input_target(self.current_app)
                if name == "click":
                    self.driver.click(args["x"], args["y"])
                    return self._ok(f"clicked {args['x']},{args['y']}")
                if name == "type_text":
                    self.driver.type_text(args["text"])
                    return self._ok(f"typed {len(args['text'])} chars")
                self.driver.press_key(args["key"])
                return self._ok(f"pressed {args['key']}")
            if name == "screenshot":
                path = os.path.join(self.shot_dir, args["name"] + ".png")
                self.driver.screenshot(path)
                assert_screenshot_saved(path)
                return self._ok(f"screenshot saved: {path}")
            if name == "assert_window":
                assert_window_visible(self.driver, args["window"])
                return self._ok(f"window '{args['window']}' is foreground")
            if name == "run_test":
                out_dir = os.path.join(os.getcwd(), "deskcheck-mcp-output",
                                       "runs")
                result = run_test(args["test"], self.config, self.driver,
                                  out_dir,
                                  update_baselines=bool(args.get("update_baselines")))
                return self._ok(f"run {result.status}: " +
                                "; ".join(result.failures) if result.failures
                                else f"run passed: {result.name}")
            return self._err(f"unknown tool '{name}'")
        except DeskcheckError as exc:
            return self._err(str(exc))
        except KeyError as exc:
            return self._err(f"missing argument: {exc}")
        except Exception as exc:  # keep the transport alive
            return self._err(f"{type(exc).__name__}: {exc}")

    def handle(self, req: dict):
        method, rid = req.get("method"), req.get("id")
        if method == "initialize":
            return {"jsonrpc": "2.0", "id": rid, "result": {
                "protocolVersion": req.get("params", {}).get("protocolVersion", "2024-11-05"),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "deskcheck", "version": "0.1.0"}}}
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}}
        if method == "tools/call":
            params = req.get("params", {})
            return {"jsonrpc": "2.0", "id": rid,
                    "result": self.call_tool(params.get("name"),
                                             params.get("arguments", {}))}
        if method == "ping":
            return {"jsonrpc": "2.0", "id": rid, "result": {}}
        if method and method.startswith("notifications/"):
            return None  # notifications get no response
        return {"jsonrpc": "2.0", "id": rid,
                "error": {"code": -32601, "message": f"method not found: {method}"}}


def serve(config=None, driver_name="mock"):
    server = MCPServer(config=config, driver_name=driver_name)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            print(json.dumps({"jsonrpc": "2.0", "id": None,
                              "error": {"code": -32700, "message": "parse error"}}),
                  flush=True)
            continue
        resp = server.handle(req)
        if resp is not None:
            print(json.dumps(resp), flush=True)

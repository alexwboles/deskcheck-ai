"""Bounded runs, private-by-default logs, immutable reports and honest outcomes."""
from __future__ import annotations

import datetime
import html
import json
import os
from pathlib import Path
import signal
import time
from urllib.parse import quote

from .assertions import assert_pixel_diff, assert_screenshot_saved, assert_window_visible
from .errors import DeskcheckError, PermissionDenied
from .parser import load_test
from .safety import atomic_bytes, contained, checked_root


class RunResult:
    def __init__(self, name, status, steps_run, failures, out_dir):
        self.name, self.status, self.steps_run = name, status, steps_run
        self.failures, self.out_dir = failures, str(out_dir)

    @property
    def passed(self):
        return self.status == "pass"


def run_test(test_path, config, driver, out_dir, update_baselines=False,
             max_steps=100, timeout_ms=30000, test_dir_baselines=None,
             cancel_event=None, progress=None):
    if type(max_steps) is not int or not 1 <= max_steps <= 1000:
        raise DeskcheckError("max-steps must be 1-1000")
    if type(timeout_ms) is not int or not 1 <= timeout_ms <= 120000:
        raise DeskcheckError("timeout-ms must be 1-120000")
    if type(update_baselines) is not bool:
        raise DeskcheckError("update_baselines must be a boolean")
    test = load_test(test_path)
    out = checked_root(out_dir)
    if out.exists() and any(out.iterdir()):
        raise PermissionDenied("Output directory is not empty; choose a new run directory")
    out.mkdir(parents=True, exist_ok=True)
    baseline_root = Path(test_dir_baselines or Path(test_path).resolve().parent / "baselines")
    entries, failures, shots = [], [], {}
    status, current_app, stopped = "pass", None, False
    old_handler = None

    def interrupted():
        return stopped or cancel_event is not None and cancel_event.is_set()

    def handler(_signal, _frame):
        nonlocal stopped
        stopped = True
        # Break out of a wait/driver call immediately. Always finalize below.
        raise KeyboardInterrupt

    def log(i, kind, target, outcome, shot=None, error=None):
        # Never log type content, raw step dictionaries, commands or payloads.
        item = {"timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "step": i, "type": kind, "target": target, "outcome": outcome,
                "screenshot": shot, "error": error}
        entries.append(item)
        with contained(out, "actions.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(item, ensure_ascii=True) + "\n")

    try:
        try:
            old_handler = signal.signal(signal.SIGINT, handler)
        except (ValueError, OSError):
            pass  # GUI worker/MCP non-main thread uses cancel_event.
        try:
            config.check_launch(test["app"])
            if len(test["steps"]) > max_steps:
                raise DeskcheckError(f"max-steps exceeded: {len(test['steps'])} > {max_steps}")
        except DeskcheckError as exc:
            status = "fail"
            failures.append(str(exc))
            log(-1, "setup", test["app"], "denied", error=str(exc))
        if status == "pass":
            for i, step in enumerate(test["steps"]):
                if interrupted():
                    raise KeyboardInterrupt
                kind = step["type"]
                start = time.monotonic()
                driver.timeout_ms = timeout_ms
                driver.operation_deadline = start + timeout_ms / 1000
                driver.cancel_event = cancel_event
                if progress:
                    progress(i + 1, len(test["steps"]), kind)
                try:
                    target = kind
                    shot = None
                    if kind == "launch":
                        entry = config.check_launch(step["app"])
                        if entry.category == "browser" and driver.name != "mock":
                            raise PermissionDenied("Native browsers are unsupported; a flag cannot prove profile isolation")
                        driver.launch(step["app"], entry.command)
                        current_app = step["app"]
                        target = current_app
                    elif kind == "wait":
                        ms = step.get("ms", 0)
                        if ms > timeout_ms:
                            raise DeskcheckError("wait exceeds the step timeout")
                        deadline = start + ms / 1000
                        while time.monotonic() < deadline:
                            if interrupted():
                                raise KeyboardInterrupt
                            time.sleep(min(.02, max(0, deadline - time.monotonic())))
                        if "window" in step:
                            remaining = max(1, timeout_ms - int((time.monotonic() - start) * 1000))
                            if not driver.wait_window(step["window"], remaining):
                                raise DeskcheckError("wait timed out: expected app window did not appear")
                        target = step.get("window", f"{ms}ms")
                    elif kind in ("click", "type", "key"):
                        config.check_input(current_app)
                        driver.check_input_target(current_app)
                        if kind == "click":
                            driver.click(step["x"], step["y"])
                            target = f"{step['x']},{step['y']}"
                        elif kind == "type":
                            driver.type_text(step["text"])
                            target = f"[redacted: {len(step['text'])} characters]"
                        else:
                            driver.press_key(step["key"])
                            target = step["key"]
                    elif kind == "screenshot":
                        config.check_input(current_app)
                        driver.check_input_target(current_app)
                        if step["name"] in shots:
                            raise DeskcheckError("Duplicate screenshot name")
                        path = contained(out, f"screenshots/{step['name']}.png")
                        path.parent.mkdir(parents=True, exist_ok=True)
                        driver.screenshot(str(path))
                        assert_screenshot_saved(str(path))
                        shots[step["name"]] = path
                        target, shot = step["name"], path.relative_to(out).as_posix()
                    elif kind == "assert":
                        assertion = step["kind"]
                        target = assertion
                        if assertion == "window-visible":
                            assert_window_visible(driver, step["window"])
                        else:
                            actual = shots.get(step["screenshot"])
                            if actual is None:
                                raise DeskcheckError("Screenshot was not captured in this run")
                            if assertion == "screenshot-saved":
                                assert_screenshot_saved(str(actual))
                            else:
                                baseline = contained(baseline_root, step["baseline"])
                                if update_baselines:
                                    atomic_bytes(baseline, actual.read_bytes(), replace=True)
                                    target = "pixel-diff (baseline accepted explicitly)"
                                else:
                                    assert_pixel_diff(str(actual), str(baseline),
                                        tolerance=step.get("tolerance", 0.0),
                                        max_diff_ratio=step.get("max_diff_ratio", .01),
                                        diff_path=str(contained(out, f"diff-{step['screenshot']}.png")))
                    if (time.monotonic() - start) * 1000 > timeout_ms:
                        raise DeskcheckError("Step exceeded its timeout; run failed (action may have completed)")
                    log(i, kind, target, "ok", shot=shot)
                except KeyboardInterrupt:
                    raise
                except Exception as exc:
                    # Driver messages can contain input content. Expose only known safe
                    # validation messages; never echo native errors for type steps.
                    error = str(exc) if isinstance(exc, DeskcheckError) and kind != "type" else f"{type(exc).__name__}: {kind} failed"
                    failures.append(f"step {i} ({kind}): {error}")
                    log(i, kind, "[redacted]" if kind == "type" else kind, "fail", error=error)
                    status = "fail"
                    break
            if interrupted():
                raise KeyboardInterrupt
    except KeyboardInterrupt:
        status = "interrupted"
        failures.append("run interrupted; completed actions are not rolled back")
        log(len(entries), "interrupt", None, "interrupted")
    except Exception as exc:
        status = "error"
        error = type(exc).__name__+": run setup/progress failed"
        failures.append(error)
        log(len(entries),"runtime",None,"error",error=error)
    finally:
        if old_handler is not None:
            signal.signal(signal.SIGINT, old_handler)
        _write_reports(test, entries, failures, status, out, shots)
    return RunResult(test["name"], status, len(entries), failures, out)


def _write_reports(test, entries, failures, status, out, shots):
    badge = status.upper()
    summary = {"name": test["name"], "app": test["app"], "status": status,
               "steps_run": len(entries), "failures": failures,
               "screenshots": {k: v.relative_to(out).as_posix() for k, v in shots.items()}}
    atomic_bytes(contained(out, "result.json"), json.dumps(summary, indent=2).encode())
    lines = [f"# deskcheck report: {test['name']}", "", f"Result: {badge}",
             f"App: {test['app']}", "", "## Failures"]
    lines += failures or ["None"]
    lines += ["", "## Steps"] + [f"{e['step']}: {e['type']} - {e['outcome']} - {e['target']}" for e in entries]
    atomic_bytes(contained(out, "report.md"), ("\n".join(lines) + "\n").encode())
    esc = lambda value: html.escape(str(value))
    rows = "".join(f"<tr><td>{e['step']}</td><td>{esc(e['type'])}</td><td>{esc(e['target'])}</td><td>{esc(e['outcome'])}</td></tr>" for e in entries)
    images = "".join(f'<figure><figcaption>{esc(k)}</figcaption><img alt="{esc(k)}" src="{quote(v.relative_to(out).as_posix())}"></figure>' for k, v in shots.items())
    failure_html = "".join(f"<li>{esc(f)}</li>" for f in failures)
    page = f'''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; base-uri 'none'">
<title>DeskCheck — {esc(test['name'])}</title>
<style>body{{font:16px system-ui;max-width:1050px;margin:40px auto;padding:0 20px;background:#f5f7fa;color:#172b36}}header,section{{background:white;padding:24px;margin-bottom:20px;border:1px solid #d8e1e7}}h1{{margin:0 0 12px}}.badge{{font-weight:700;color:{'#127349' if status == 'pass' else '#a52432'}}}table{{width:100%;border-collapse:collapse}}td,th{{text-align:left;padding:12px;border-bottom:1px solid #ddd;overflow-wrap:anywhere}}.table{{overflow:auto}}img{{max-width:100%;height:auto;border:1px solid #ddd}}button,input{{border-radius:0}}figure{{margin:20px 0}}</style>
<header><h1>{esc(test['name'])}</h1><span class="badge">{badge}</span> · {esc(test['app'])} · {len(entries)} logged actions<p>Typed content is redacted. Screenshots may contain app data; review before sharing.</p></header>
<section><h2>Failures</h2><ul>{failure_html or '<li>None</li>'}</ul></section>
<section><h2>Actions</h2><div class="table"><table><tr><th>#</th><th>Action</th><th>Target</th><th>Outcome</th></tr>{rows}</table></div></section>
<section><h2>Screenshots</h2>{images or '<p>No screenshots captured.</p>'}</section></html>'''
    atomic_bytes(contained(out, "report.html"), page.encode())

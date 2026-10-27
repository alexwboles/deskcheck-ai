"""Runner: executes a parsed test against a driver, logs, reports.

Exit contract (see CLI): 0 pass, 1 fail, 2 usage/parse/permission setup
error, 3 interrupted (Ctrl-C). A run marked interrupted still writes its
report and JSONL log.
"""
from __future__ import annotations

import datetime
import html
import json
import os
import shutil
import signal
import time

from .assertions import (assert_pixel_diff, assert_screenshot_saved,
                         assert_window_visible)
from .errors import (AssertionFailed, DeskcheckError, PermissionDenied)
from .parser import load_test
from .permissions import PermissionConfig


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class RunResult:
    def __init__(self, name, status, steps_run, failures, out_dir):
        self.name = name
        self.status = status  # pass | fail | interrupted | error
        self.steps_run = steps_run
        self.failures = failures
        self.out_dir = out_dir

    @property
    def passed(self):
        return self.status == "pass"


def _safe(name: str) -> str:
    return "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in name)


def run_test(test_path: str, config: PermissionConfig, driver,
             out_dir: str, update_baselines: bool = False,
             max_steps: int = 100, timeout_ms: int = 30000,
             test_dir_baselines: str | None = None) -> RunResult:
    test = load_test(test_path)
    test_dir = os.path.dirname(os.path.abspath(test_path))
    baseline_root = test_dir_baselines or os.path.join(test_dir, "baselines")
    shot_dir = os.path.join(out_dir, "screenshots")
    os.makedirs(shot_dir, exist_ok=True)
    log_path = os.path.join(out_dir, "actions.jsonl")
    steps = test["steps"]
    log_entries, failures = [], []
    status = "pass"
    shots = {}  # screenshot name -> path
    current_app = None
    interrupted = [False]

    def _log(step_i, stype, target, outcome, shot=None, error=None):
        entry = {"timestamp": _now(), "step": step_i, "type": stype,
                 "target": target, "outcome": outcome,
                 "screenshot": shot, "error": error}
        log_entries.append(entry)
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")

    def _handler(_signum, _frame):
        interrupted.append(True)
    old_handler = None
    try:
        old_handler = signal.signal(signal.SIGINT, _handler)
    except (ValueError, OSError):
        pass  # not main thread (e.g. inside MCP server): skip graceful hook

    # The test's own app must be allowlisted before anything runs.
    try:
        config.check_launch(test["app"])
    except PermissionDenied as exc:
        _log(-1, "launch", test["app"], "denied", error=str(exc))
        failures.append(str(exc))
        status = "fail"
        _write_reports(test, log_entries, failures, status, out_dir, shots)
        return RunResult(test["name"], status, 0, failures, out_dir)

    if len(steps) > max_steps:
        msg = (f"max-steps exceeded: test has {len(steps)} steps, "
               f"cap is {max_steps}")
        failures.append(msg)
        _log(-1, "limit", None, "fail", error=msg)
        _write_reports(test, log_entries, failures, "fail", out_dir, shots)
        return RunResult(test["name"], "fail", 0, failures, out_dir)

    for i, step in enumerate(steps):
        if interrupted[0]:
            status = "interrupted"
            failures.append("run interrupted (Ctrl-C)")
            break
        stype = step["type"]
        try:
            if stype == "launch":
                entry = config.check_launch(step["app"])
                driver.launch(step["app"], entry.command)
                current_app = step["app"]
                _log(i, stype, step["app"], "ok")
            elif stype == "wait":
                if "ms" in step and step["ms"] > timeout_ms:
                    raise DeskcheckError(
                        f"wait of {step['ms']}ms exceeds step timeout "
                        f"{timeout_ms}ms")
                if "ms" in step:
                    time.sleep(step["ms"] / 1000.0)
                if "window" in step:
                    if not driver.wait_window(step["window"], timeout_ms):
                        raise DeskcheckError(
                            f"wait timed out: window '{step['window']}' "
                            f"not visible within {timeout_ms}ms")
                _log(i, stype, step.get("window") or f"{step.get('ms')}ms", "ok")
            elif stype in ("click", "type", "key"):
                # Input steps re-check permission against the focused app.
                config.check_input(current_app)
                if stype == "click":
                    driver.click(step["x"], step["y"])
                    target = f"{step['x']},{step['y']}"
                elif stype == "type":
                    driver.type_text(step["text"])
                    target = step["text"][:40]
                else:
                    driver.press_key(step["key"])
                    target = step["key"]
                _log(i, stype, target, "ok")
            elif stype == "screenshot":
                path = os.path.join(shot_dir, _safe(step["name"]) + ".png")
                driver.screenshot(path)
                shots[step["name"]] = path
                _log(i, stype, step["name"], "ok", shot=path)
            elif stype == "assert":
                kind = step["kind"]
                if kind == "window-visible":
                    assert_window_visible(driver, step["window"])
                    _log(i, "assert", step["window"], "ok")
                elif kind == "screenshot-saved":
                    path = shots.get(step["screenshot"]) or os.path.join(
                        shot_dir, _safe(step["screenshot"]) + ".png")
                    assert_screenshot_saved(path)
                    _log(i, "assert", step["screenshot"], "ok", shot=path)
                else:
                    actual = shots.get(step["screenshot"]) or os.path.join(
                        shot_dir, _safe(step["screenshot"]) + ".png")
                    baseline = step["baseline"]
                    if not os.path.isabs(baseline):
                        baseline = os.path.join(baseline_root, baseline)
                    if update_baselines:
                        os.makedirs(os.path.dirname(baseline), exist_ok=True)
                        shutil.copyfile(actual, baseline)
                        _log(i, "assert", "pixel-diff (baseline updated)",
                             "ok", shot=actual)
                    else:
                        diff_path = os.path.join(
                            out_dir, "diff-" + _safe(step["screenshot"]) + ".png")
                        assert_pixel_diff(
                            actual, baseline,
                            tolerance=step.get("tolerance", 0.0),
                            max_diff_ratio=step.get("max_diff_ratio", 0.01),
                            diff_path=diff_path)
                        _log(i, "assert", "pixel-diff", "ok", shot=actual)
            else:  # pragma: no cover - parser already rejects this
                raise DeskcheckError(f"unknown step type {stype!r}")
        except (PermissionDenied, AssertionFailed, DeskcheckError) as exc:
            failures.append(f"step {i} ({stype}): {exc}")
            _log(i, stype, str(step), "fail", error=str(exc))
            status = "fail"
            break
    else:
        if status == "pass" and not interrupted[0]:
            status = "pass"
    if interrupted[0] and status != "interrupted":
        status = "interrupted"
    if old_handler is not None:
        try:
            signal.signal(signal.SIGINT, old_handler)
        except (ValueError, OSError):
            pass
    _write_reports(test, log_entries, failures, status, out_dir, shots)
    return RunResult(test["name"], status, len(log_entries), failures, out_dir)


def _write_reports(test, log_entries, failures, status, out_dir, shots):
    os.makedirs(out_dir, exist_ok=True)
    badge = {"pass": "PASS", "fail": "FAIL",
             "interrupted": "INTERRUPTED", "error": "ERROR"}[status]
    lines = [f"# deskcheck report: {test['name']}", "",
             f"**Result: {badge}**  |  App: `{test['app']}`  |  "
             f"Steps logged: {len(log_entries)}", ""]
    if failures:
        lines += ["## Failures", ""] + [f"- {f}" for f in failures] + [""]
    lines += ["## Steps", "", "| # | Type | Target | Outcome | Screenshot |",
              "|---|---|---|---|---|"]
    for e in log_entries:
        shot = os.path.basename(e["screenshot"]) if e["screenshot"] else ""
        lines.append(f"| {e['step']} | {e['type']} | {e['target']} | "
                     f"{e['outcome']} | {shot} |")
    if shots:
        lines += ["", "## Screenshots", ""] + \
            [f"- {k}: `{v}`" for k, v in shots.items()]
    with open(os.path.join(out_dir, "report.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    rows = "".join(
        f"<tr><td>{e['step']}</td><td>{html.escape(str(e['type']))}</td>"
        f"<td>{html.escape(str(e['target']))}</td>"
        f"<td>{html.escape(str(e['outcome']))}</td></tr>"
        for e in log_entries)
    fail_html = ("<h2>Failures</h2><ul>" +
                 "".join(f"<li>{html.escape(f)}</li>" for f in failures) +
                 "</ul>") if failures else ""
    # Sharp corners only, no gradients, no emoji chrome (standing design rule).
    page = f"""<!doctype html><html><head><meta charset="utf-8">
<title>deskcheck report: {html.escape(test['name'])}</title>
<style>body{{font-family:system-ui,sans-serif;max-width:900px;margin:2rem auto;
padding:0 1rem;color:#1a1a1a}}h1{{font-size:1.5rem}}table{{border-collapse:collapse;
width:100%}}th,td{{border:1px solid #ccc;padding:.4rem .6rem;text-align:left}}
.badge{{display:inline-block;padding:.2rem .6rem;border:2px solid #1a1a1a;
font-weight:700}}button,input{{border-radius:0}}</style></head><body>
<h1>deskcheck report: {html.escape(test['name'])}</h1>
<p><span class="badge">{badge}</span> App: {html.escape(test['app'])}</p>
{fail_html}<h2>Steps</h2><table><tr><th>#</th><th>Type</th><th>Target</th>
<th>Outcome</th></tr>{rows}</table></body></html>"""
    with open(os.path.join(out_dir, "report.html"), "w", encoding="utf-8") as fh:
        fh.write(page)

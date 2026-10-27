# deskcheck-ai

A free, open-source (MIT), deterministic desktop-test loop for open coding
agents. A coding agent (OpenCode, Codex CLI, Claude Code, etc.) calls
deskcheck to verify its own GUI/desktop work: launch a named app, perform
scripted GUI steps, screenshot, get pass/fail back into its build-fix loop.

It is a **test harness, not another agent brain**. It decides nothing about
what to do — it runs exactly the steps in a YAML test file and reports
whether they passed.

## Why this exists

Desktop agents that can click anywhere carry an obvious risk: an agent with
OS-wide control can touch mail, password managers, and signed-in browsers
(Cursor's Computer Use announcement, Oct 23, 2026, published no permission
model for exactly this). deskcheck's answer is the headline feature:
**a named-app allowlist with default deny**, enforced at launch *and* at
every input step, with whole categories (password managers, credential
stores, system-settings apps, browsers with existing profiles) denied
outright. See [docs/SECURITY.md](docs/SECURITY.md).

## Quickstart

```bash
pip install -e .
# 1. Write a test (steps are data, never code — no shell/exec step exists)
# 2. Run it against the mock driver (hermetic demo, no real desktop needed)
deskcheck run examples/demo-pass.yaml --config examples/config.yaml \
  --driver mock --mock-windows demo-app
# Exit 0 = pass, 1 = fail, 2 = setup/parse error, 3 = interrupted (Ctrl-C)
# Reports: <test-dir>/runs/<name>/report.md + report.html + actions.jsonl
#          + screenshots/<name>.png per screenshot step
```

On a real Linux desktop, use `--driver linux` (needs `xdotool` + `scrot`);
on Windows, `--driver windows` (PowerShell + .NET, no new dependencies).
If the driver is unavailable, deskcheck says so clearly instead of
failing mid-run.

## One full example test

```yaml
version: 1
name: demo-pass
app: demo-app
steps:
  - type: launch
    app: demo-app
  - type: wait
    ms: 10
  - type: click
    x: 100
    y: 200
  - type: type
    text: "hello"
  - type: key
    key: Enter
  - type: screenshot
    name: main
  - type: assert
    kind: window-visible
    window: demo-app
  - type: assert
    kind: screenshot-saved
    screenshot: main
```

Step types, and only these: `launch`, `wait` (ms, or window-visible),
`click` (x,y), `type` (text), `key` (named key), `screenshot` (named),
`assert` (`window-visible` | `screenshot-saved` | `pixel-diff` vs a
baseline, with tolerance + max-diff-ratio knobs). The parser rejects any
unknown step type or unknown key with a clear error, and rejects
shell/exec-style keys outright. Timeouts apply to every step; `--max-steps`
caps runaway tests; Ctrl-C stops gracefully and marks the run interrupted.

### Pixel-diff baselines (the Playwright-style accept flow)

First run with no baseline fails with a clear "baseline missing" message.
Accept the current screenshot as the baseline, then re-run:

```bash
deskcheck run examples/pixel-diff.yaml --config examples/config.yaml \
  --driver mock --mock-windows demo-app --update-baselines
deskcheck run examples/pixel-diff.yaml --config examples/config.yaml \
  --driver mock --mock-windows demo-app
```

On a pixel-diff failure, a red diff image is written next to the report
(`diff-<name>.png`). OCR is optional only: if `tesseract` is installed you
may add your own checks outside deskcheck; it is never in the default path
and never required.

## MCP setup (for coding agents)

deskcheck speaks MCP over stdio (JSON-RPC 2.0, `initialize` /
`tools/list` / `tools/call` / `ping`). Tools: `launch_app`, `click`,
`type_text`, `press_key`, `screenshot`, `assert_window`, `run_test`
(tool failures return `isError: true`, not a transport error, so the model
can read the reason and retry).

```json
{
  "mcpServers": {
    "deskcheck": {
      "command": "deskcheck",
      "args": ["mcp", "--config", "/path/to/config.yaml", "--driver", "linux"]
    }
  }
}
```

Drop-in agent instructions live in [AGENT-SKILL.md](AGENT-SKILL.md):
write test → run → read report → fix → re-run.

## How deskcheck differs from HQ's Holo4

Holo4 (in the HQ system) is a **model-driven autonomous desktop agent**:
it decides what to do next on the desktop. deskcheck is the opposite side
of that loop: it **verifies** — it runs only the steps a test file spells
out, against an allowlist, and returns pass/fail. Interop is documented
here only; there is no code coupling to HQ, and deskcheck never modifies
HQ files. In a combined workflow, Holo4 (or any agent) builds, deskcheck
checks, the agent fixes, deskcheck re-checks.

## Docs

- [docs/SECURITY.md](docs/SECURITY.md) — permission model + threat model
- [docs/RESEARCH.md](docs/RESEARCH.md) — what was borrowed from Cursor,
  Playwright, PyAutoGUI, and MCP conventions
- [AGENT-SKILL.md](AGENT-SKILL.md) — drop-in instructions for coding agents

## Tests

```bash
sh test/smoke.sh   # unit + e2e (MockDriver) + CLI + MCP handshake
```

No network calls in tests. Dependencies: PyYAML only; everything else
(including the PNG decoder used for pixel-diff) is stdlib.

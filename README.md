# DeskCheck

An offline test runner for repeatable **Windows standard-control app tests**
and cross-platform **simulated tests**. Use its desktop interface, CLI or MCP
server to run YAML steps and inspect HTML reports, screenshots and pixel diffs.
There is no AI model, subscription, telemetry or paid API dependency.

Version 0.2.0 is being verified on the `qa/input-target-guard` review branch.
See [release status](docs/RELEASE-STATUS.md) for evidence and remaining gates.
Do not confuse a mock pass with testing a real application.

## Start without Python — Windows portable package

1. Extract the **entire** provided DeskCheck ZIP into a writable folder.
2. Double-click **DeskCheck Desktop.exe**. Keep `DeskCheck.exe` and `_internal`
   beside it; no administrator installation or registry changes are required.
3. Click **Try Windows sample** for a real check of our disposable sample,
   or **Try simulation** for a clearly labelled simulated example.
4. Follow **Choose app → Add actions → Expected result → Review results**.
   The large app capture stays visible. **Run check** executes your saved steps.
5. **View evidence** opens the report. **Save** keeps a versioned local check;
   select it in the left sidebar next time. No YAML is needed for basic checks.
   The runner asks before launching it and closes that new process afterward.

Packages are unsigned. Do not bypass antivirus, organization policies or Windows
security warnings. There is no public binary release until Alex approves one.

## Developer quickstart

Requires Python 3.10+, PyYAML 6+, and Pillow 10+. The desktop UI also requires Tk.

```sh
python -m pip install .
deskcheck run examples/demo-pass.yaml --config examples/config.yaml --driver mock
deskcheck gui
```

Output: a new run directory containing `report.html`, `report.md`,
`result.json`, `actions.jsonl` and captured PNGs. Explicit `--out-dir` must be
empty; existing reports are never silently overwritten. Each default run uses
a unique directory. Open the HTML report locally; it has no external resources.

Exit codes: **0 passed**, **1 failed**, **2 setup/input error**, **3 interrupted**.
Interrupted/failed actions are not rolled back; the report never claims a pass.

## Real Windows app test

Supported: a **newly launched, non-elevated Win32/.NET standard-control app**
with one root window; standard edit controls and buttons. Uses PID/HWND-bound
messages, literal UTF-16 text, bounded client coordinates and app-only capture.
It does not move the user's mouse or type into the global foreground window.

Not supported: existing app attachment, browsers, credential/settings apps,
terminals, elevated apps, Linux native control, games, Electron/custom GPU
interfaces, arbitrary key chords, multi-process app trees or multi-root apps.
Unsupported operations must fail, not fall back to mock or global input.

Operator-written allowlist (replace with your actual absolute executable path):

```yaml
apps:
  sample-app:
    command: ["C:/TestApps/MySample.exe"]
    category: app
```

Only trusted disposable test apps belong here. A launch command is a literal
argv list, never a shell command. Windows closes the process it launched at
the end of a CLI/desktop run; never use it for unsaved production work.

```yaml
version: 1
name: save-note
app: sample-app
steps:
  - {type: launch, app: sample-app}
  - {type: click, x: 80, y: 100}
  - {type: type, text: "Synthetic note only"}
  - {type: click, x: 100, y: 165}
  - {type: click, x: 80, y: 225}
  - {type: assert, kind: control-text, text: "Saved: Synthetic note only"}
  - {type: screenshot, name: completed}
  - {type: assert, kind: window-visible, window: sample-app}
  - {type: assert, kind: screenshot-saved, screenshot: completed}
```

```sh
deskcheck run save-note.yaml --config allowlist.yaml --driver windows
```

Coordinates are **client-area pixels**, relative to the captured app image,
not desktop/screen pixels. Check DPI/layout and write tests for the actual app.
The visual builder can pick these positions from a captured image without
sending a click. **View full size** opens a readable, scrollable capture.
`window-visible` checks the bound app, not whichever unrelated app is foreground.

## Baselines

A missing baseline fails clearly. Review the intended screenshot, then
explicitly accept it with `--update-baselines` or the desktop checkbox.
This replaces matching baseline files, so do not accept regressions blindly.

```sh
deskcheck run examples/pixel-diff.yaml --config examples/config.yaml --driver mock --update-baselines
deskcheck run examples/pixel-diff.yaml --config examples/config.yaml --driver mock
```

Baseline names are relative to the test's `baselines/` folder. Traversal,
absolute/UNC paths, NTFS streams and linked output paths are rejected.

## MCP

Use an explicit workspace; agent-supplied test paths must stay below it.

```json
{
  "mcpServers": {
    "deskcheck": {
      "command": "C:/Tools/DeskCheck/DeskCheck.exe",
      "args": ["mcp", "--config", "C:/Tests/allowlist.yaml", "--workspace", "C:/Tests", "--driver", "windows"]
    }
  }
}
```

Tools: `launch_app`, `click`, `type_text`, `press_key`, `screenshot`,
`assert_window`, `run_test`. Failed/interrupted runs return `isError: true`
and a report path. Baseline replacement is denied unless the operator starts
MCP with `--allow-baseline-updates`. No network server/listening port is opened.

## Safety, delivery and verification

- Typed contents are redacted from action logs. Screenshots can still contain
  app data; use synthetic data and review artifacts before sharing.
- This is **not an OS, filesystem or network sandbox**. Trusted test apps retain
  their own capabilities. Config categories are operator declarations.
- No existing browser profiles, real credentials or customer records are used
  by the supplied examples/tests.
- See [user guide](docs/USER-GUIDE.md), [security boundary](docs/SECURITY.md),
  [release status](docs/RELEASE-STATUS.md), [agent usage](AGENT-SKILL.md).
- Source is MIT licensed; retain copyright/license notices. Optional commercial
  delivery/support terms must be separately agreed, not implied by this README.

## Tests and local build

```sh
python -W error::ResourceWarning -m unittest discover -s tests -q
```

`test/native_acceptance.py` is opt-in and runs **only our compiled synthetic
fixture**, including a covering decoy window. See the user guide for reproduction.
GitHub CI uses only standard public runners, with no artifact/cache uploads.

On Windows, install free PyInstaller 6 and run `python packaging/build_portable.py`.
This builds a local portable folder, GUI launcher and sample app. It never
publishes, signs, sends customer files or spends money.

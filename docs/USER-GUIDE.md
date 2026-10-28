# DeskCheck user guide

## First run

Extract the entire portable ZIP into a folder you own. Keep the `_internal`
runtime directory with the EXEs. Double-click `DeskCheck Desktop.exe`, choose
**Load sample**, **Run test**, then **View report**. The sample is simulated:
it proves runner/report installation, not a real app's behavior.

The desktop runner shows live step count and action type, disables duplicate
starts, and keeps the UI responsive. **Stop** requests cancellation; wait for
the interrupted result before closing. Existing output/notes are not removed.
Default workspace: your home `Documents/DeskCheck` folder; every sample/run
gets a unique directory. `DESKCHECK_WORKSPACE` can choose another local folder.

**Windows sample** creates an allowlist and test for the bundled synthetic
standard-control EXE. It asks for confirmation before launch; after the steps,
view the app-only screenshot. The test app is closed afterward. No browser,
mailbox or real customer data is involved.

## Test your own app

1. Read `SECURITY.md`. Use a trusted disposable standard-control app only.
2. Create an allowlist with an absolute executable argv list (README example).
3. Write YAML steps using client-area coordinates, with assertions for your
   actual workflow. Do not mistake a report screenshot for a complete test.
4. Browse to both YAML files in the desktop runner and select **windows**.
5. Run and inspect the outcome. Native failure never falls back to simulated
   execution. Do not use admin apps, real signed-in sessions or production files.

Steps: `launch`, `wait` (`ms` and/or bound `window`), `click` (`x`, `y`),
`type` (printable literal `text`), `key` (single named `key`), `screenshot`
(`name`), `assert` (`window-visible`, `screenshot-saved`, `pixel-diff`,
`control-text`). Click a standard control and use a `control-text` assertion
with `text` to verify its exact value without echoing it into the report.

Names: 1–80 ASCII letters/digits/underscore/hyphen, starting with a letter or
digit. Single keys: Enter/Return, Tab, Escape, Backspace, Delete, arrows,
Home/End, PageUp/PageDown, Space, F1–F12. No modifier chords. Native typing
requires first selecting a standard edit control. Unsupported widgets may not
react to messages; build functional assertions, and use the app's native test
framework if standard-control targeting cannot exercise it faithfully.

## Reports and privacy

Each run has HTML/Markdown/JSON results, JSONL actions and PNG screenshots.
Reports are self-contained apart from relative images inside the same folder.
They do not load CDNs/fonts/analytics. Keep the whole run folder together.
Typed text is redacted; screenshots and app names can still be private.
Delete only your chosen old run folders when no longer needed; no automatic
retention/deletion runs. DeskCheck does not upload reports.

Run failure is exit 1, setup/invalid input is 2, interruption is 3, pass is 0.
CLI flags include `--max-steps` (1–1000), `--timeout-ms` (1–120000), an empty
`--out-dir` and explicit `--update-baselines`. Capture uses a bounded helper
worker (at most five seconds per capture); input messages are also bounded.
An interruption/timeout may occur after an action took effect. No rollback
is promised. All newly launched test processes are closed at end of run.

## Troubleshooting

- **Missing DLL/runtime:** extract the full ZIP, not only the launcher EXE.
- **Windows policy/antivirus warning:** stop. Obtain an approved/signed build
  through your organization; never disable protections or bypass warnings.
- **No window / multiple windows / another process:** the app is unsupported
  or launch config is wrong. Do not weaken the identity checks.
- **Blank capture:** the app renderer does not support this capture method.
  There is intentionally no screenshot-of-the-whole-desktop fallback.
- **Cannot type:** click a standard edit control inside the bound app first.
- **Report folder exists:** select a new empty output folder.
- **Baseline missing:** inspect the screenshot, accept explicitly, then rerun.
- **Linux native unavailable:** only mock is supported outside Windows.
- **No Python command:** use the provided Windows portable package instead.
- **GUI error:** use `DeskCheck.exe gui` from an existing terminal to view the
  local error, without sharing logs containing personal paths unnecessarily.

## Verification from source (developers)

```sh
python -m pip install .
python -W error::ResourceWarning -m unittest discover -s tests -q
```

Windows native acceptance compiles only our fixture:

```powershell
New-Item -ItemType Directory -Force .qa-output | Out-Null
& "$env:WINDIR\Microsoft.NET\Framework64\v4.0.30319\csc.exe" /nologo /target:winexe /reference:System.Windows.Forms.dll /reference:System.Drawing.dll /reference:System.Web.Extensions.dll /out:.qa-output\DeskCheckFixture.exe test\Fixture.cs
python test/native_acceptance.py
```

This checks literal Unicode text, button activation, keyboard traversal,
offscreen app-only capture despite an overlapping decoy, foreign-process
rejection and coordinate bounds. It never attaches to existing user apps.

## Delivery/uninstall

The portable package makes no registry, startup, service or administrator
changes. Close DeskCheck, preserve any wanted reports, then remove only the
extracted program folder. Reports in `Documents/DeskCheck` remain separately.
The MIT source license and third-party license notices must travel with any
redistributed copy. Price/support/refund promises require an agreed offer;
there is no payment processor, paid subscription or licensing server built in.

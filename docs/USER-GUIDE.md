# DeskCheck user guide

## First run

Extract the entire portable ZIP into a folder you own. Keep the `_internal`
runtime directory with the EXEs. Double-click `DeskCheck Desktop.exe` and choose
**Try Windows sample** for the real bundled app, or **Try simulation** for a
labelled simulated example. Simulation does not test a real app.

## Guided workspace

1. **Choose app:** select a sample or a trusted disposable Windows `.exe`.
   Give the check a readable name. Nothing launches automatically.
2. **Add actions:** select steps, change their action/fields, add, reorder or
   remove them. Changes apply when you switch steps, continue, save or run.
   **Capture app** launches only the chosen test app, captures its client area,
   then closes it. Select a click step and click its location on that image.
   This only edits coordinates; it never clicks the app while you are editing.
3. **Expected result:** add/edit verification. For exact text, add a click on
   the result control before the text assertion. Use the app's real expected
   value, not an invented expected result just to get a pass.
4. **Review results:** Run check saves your current check and executes it.
   See passed, failed and not-completed actions; select any action for details.
   A text mismatch includes an app-only capture when supported. Text values
   stay hidden until you choose **Reveal text comparison** and confirm. They
   remain in local memory, not in HTML/JSON/action logs or MCP output.

The preview is a **capture, not a live app window**. **View full size** opens a
scrollable native-size image. Use **Next** in the fixed bottom toolbar to move
through setup, or use the stage buttons; navigation never disappears. A long
editor/results pane scrolls independently. On smaller windows the failure
explanation comes before the action list. Stop stays visible during a run.
The compact editor uses a step dropdown in place of the tall action list so
the selected step's fields remain the focus; Add/Up/Down/Remove stay grouped.

**Save** / Ctrl+S keeps the check in the left sidebar. Imports and edits create
immutable revision files; a single atomic metadata pointer selects the current
revision. Old reports and revisions remain. Switching/closing warns about
unsaved field edits. Editing invalidates the displayed test result; it never
silently relabels an old passing result as verification of new changes.

The desktop runner shows live step count and action type, disables duplicate
starts, and keeps the UI responsive. **Stop** requests cancellation; wait for
the interrupted result before closing. Existing output/notes are not removed.
Default workspace: your home `Documents/DeskCheck` folder; every sample/run
gets a unique directory. `DESKCHECK_WORKSPACE` can choose another local folder.

**Try Windows sample** creates an allowlist and test for the bundled synthetic
standard-control EXE. It asks for confirmation before launch; after the steps,
view the app-only screenshot. The test app is closed afterward. No browser,
mailbox or real customer data is involved.

## Test your own app

1. Read `SECURITY.md`. Use a trusted disposable standard-control app only.
2. Select **Choose Windows app**, then build actions using captures and fields.
   For apps requiring launch arguments, use an explicit literal argv list in
   an allowlist and import it via **Advanced** (README example).
3. Add assertions for your actual workflow. A capture alone is not a complete
   functional test. Checks with missing launch/input order fail, not pass.
4. Existing YAML/JSON checks: open **Advanced**, choose both files and mode,
   then **Import copy into library**. Originals are never edited. Referenced
   existing baseline images are copied safely into each saved revision.
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
Check definitions themselves contain the text you ask the app to type and
verify, and allowlists contain executable paths/arguments. The local library
is not encrypted: use synthetic data and appropriate local file permissions.
After a failed text check a failure capture can also contain private app text.
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

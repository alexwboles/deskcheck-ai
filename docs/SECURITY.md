# Trust boundary — version 0.2.0

DeskCheck is a local deterministic test harness, **not a security sandbox**.
No claims of universal desktop isolation or automatic app classification.

## What is checked

- Unknown app names are denied. Operator-declared credential-store,
  password-manager and system-settings categories are always denied.
- Native launch requires a literal argv list and an existing absolute `.exe`.
  Known shells, browsers and settings/credential executables are additionally
  refused. A renamed or malicious executable is not made safe by an allowlist.
- Only the new process launched by the driver is bound. Its live process handle,
  executable path, HWND PID and child-window ancestry are rechecked. No existing
  user app, browser session or child-process tree is attached.
- Native actions are targeted messages to that process's window/controls,
  not global mouse/keyboard injection. Client coordinates must be in bounds;
  controls from another process are denied. Target messages have timeouts.
- Literal text is sent as UTF-16 characters to a standard edit control, not
  expanded as SendKeys, a shell, hotkeys or clipboard data. Named keys are a
  small explicit allowlist; OS shortcuts/chords and control characters in text
  are rejected.
- Capture asks only the bound app's client window to render via PrintWindow.
  It never copies desktop pixels. A worker process bounds a hung capture.
  Blank/unavailable capture fails; there is no full-screen fallback.
- YAML size/steps, unique mapping keys, aliases, numeric limits, PNG sizes,
  decompressed dimensions, paths and MCP arguments are validated.
- Output directories must be new/empty. Agent-selected paths cannot escape
  operator-selected roots or use symlinks/junctions/alternate streams. Baseline
  replacement is an explicit CLI/GUI choice; MCP needs operator enablement.
- Typed text is redacted even on driver exceptions. Failed/interrupted runs
  do not return successful MCP results or reuse stale screenshots.

## What is NOT guaranteed

- An allowlisted executable can read/write files, access the network, launch
  other processes or perform actions through its own logic. Use trusted
  disposable apps and synthetic data only. The OS/configuration are trusted.
- This does not defend against an administrator, malicious OS, hostile
  same-user process racing filesystem/window identities, or direct Python
  callers bypassing orchestration. It is a bounded test tool, not a security
  product for executing untrusted applications.
- There is no browser profile automation, multi-process app-tree support,
  elevated input, Linux native backend, global shortcuts or GPU/game support.
- PrintWindow is app-rendered evidence and can be blank/unsupported on custom
  renderers; it is not proof of an unobstructed physical screen. Pixel diffs
  need stable DPI/fonts/theme/layout; they do not replace functional assertions.
- Closing a run terminates only the newly launched test process. Its actions
  are not undone. Do not test on a process carrying unsaved production work.
- Screenshots can contain private pixels from the test app itself. File/app
  names and errors can contain local paths. No automatic encryption or secure
  erasure is promised; keep outputs in a trusted local folder with OS access
  controls, retain only as needed and review before sharing.

## Operator checklist

1. Review the executable and YAML/config before running. Do not allowlist
   terminals, credential managers or production applications with real data.
2. Keep config outside the agent's change permissions when using MCP.
3. Choose a test workspace and new output folders. Never autoaccept baselines.
4. Use app-specific assertions; a screenshot-existing assertion alone does
   not prove that a business operation succeeded.
5. Review reports/screenshots before transmitting them. No telemetry/upload
   feature exists; opening a report uses your default local browser.
6. Stop on any Windows/antivirus/organization policy warning. Do not bypass
   security controls or disable protections to run an unsigned build.

The earlier 0.1.0 cached-focus and full-desktop-capture implementation remains
historical evidence in `QA-2026-10-28.md`; current release evidence is in
`RELEASE-STATUS.md`. No independent penetration-test certification is claimed.

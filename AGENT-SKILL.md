# Use DeskCheck in a build/test loop

These are optional instructions for a connected coding agent, not a grant of
permission to change the operator's allowlist or execute arbitrary apps.

1. Write a small YAML test with a named allowlisted app, synthetic input,
   client-relative coordinates and meaningful assertions.
2. Explicitly choose `mock` (simulated only) or `windows` (standard-control
   app only). Never present mock output as real-app verification.
3. Run with CLI or MCP. A nonzero CLI exit or `isError: true` is not success.
   Read `result.json`, `report.html`, logs and screenshots.
4. Fix the actual defect, then re-run into a new directory. Never delete or
   overwrite old evidence to hide failures.
5. Ask the operator before modifying the trusted config or accepting changed
   baselines. MCP baseline updates require explicit operator startup permission.

Do not use terminals, existing sessions, credentials, production data, global
hotkeys or unsupported renderers. Do not route around permission denials.
Capture is app-client-only; coordinates use that same client pixel space.
Logs redact typed text, but screenshots can reveal app data. Review before
sharing any artifact. There are no AI inference or paid API calls in DeskCheck.

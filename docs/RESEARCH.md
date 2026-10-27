# Research: what deskcheck borrowed, and from where

## Cursor Computer Use (announced Oct 23, 2026)

Agents click/type across *any* desktop app to test their own builds;
the headline demo drives the iOS Simulator after editing a hiking app.
It is invoked automatically when a task needs it, or via @-mention.
Its permission model was **not published** — and coverage flagged the
core risk: an agent with OS-wide control can touch mail, password
managers, and signed-in browsers.

**Borrowed:** the risk framing itself, inverted into a feature.
deskcheck's allowlist/default-deny permission model (docs/SECURITY.md)
is the direct answer to that unpublished model: named apps only, denied
categories enforced at launch and at every input step, browsers only
with a fresh throwaway profile. Related signals folded in: Codex asks
permission per app (with an Always-allow option); Claude Code frames
screen control as a last resort for things nothing else can reach.
deskcheck takes the stricter side in both cases: no per-run prompting
to widen access, and screen control only through pre-approved apps.

## Playwright's test loop (the web equivalent)

`expect(page).toHaveScreenshot()` compares against a committed baseline
with pixelmatch: per-pixel threshold default 0.2 (YIQ colour space),
plus `maxDiffPixels` and `maxDiffPixelRatio` (0.01 typical). The first
run creates the baseline; `--update-snapshots` regenerates it. Baselines
are per-browser/per-platform because rendering varies.

**Borrowed:** tolerance knobs (`tolerance`, `max_diff_ratio`, default
0.01), the baseline-accept workflow (`--update-baselines` here), and
diff artifacts in the report (`diff-<name>.png`, red where pixels
differ). Differences: deskcheck's tolerance is a normalised 0–1 channel
gap (not YIQ), its PNG decode is stdlib-only, and baselines are
per-driver/per-resolution in practice — the runner records the
resolution with every screenshot, so a baseline accepted on one
resolution failing on another is diagnosable rather than mysterious.

## PyAutoGUI driver patterns

`moveTo`/`click` (button, clicks), `typewrite` with interval,
`press`/`hotkey`, `screenshot` (full or region); fail-safe (corner =
abort); coordinates are primary-monitor pixels — record the resolution
with every screenshot.

**Borrowed:** the step vocabulary (`click`, `type`, `key`,
`screenshot`) and the coordinate convention, plus the fail-safe spirit:
deskcheck's clean stop is Ctrl-C → run marked interrupted, report still
written, never silently passed. Linux equivalents used by the Linux
driver: `xdotool` (window activation, key, mousemove/click) + `scrot`
(capture). Windows equivalents: PowerShell/.NET screenshots + input.

## MCP conventions

Stdio transport, JSON-RPC 2.0 framing, `initialize` handshake,
`tools/list` + `tools/call`; tool names snake_case; tool failures return
a successful response with `isError: true` (not transport errors) so
the model can read the reason and retry.

**Borrowed:** all of the above, verbatim, in `deskcheck/mcp_server.py`.
Tools: `launch_app`, `click`, `type_text`, `press_key`, `screenshot`,
`assert_window`, `run_test`, plus `ping`. The same allowlist enforced
by the runner is enforced by every MCP tool.

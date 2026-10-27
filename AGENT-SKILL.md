# AGENT-SKILL: using deskcheck-ai in your build-fix loop

Copy these instructions into your agent's skill/config. They assume the
deskcheck MCP server is connected (see README "MCP setup"), or that the
`deskcheck` CLI is available.

## The loop

1. **Write a test** (YAML, in the repo under `deskcheck-tests/`). Steps
   are data, never code — there is no shell/exec step, and the parser
   rejects unknown step types/keys. Allowed steps only:
   `launch`, `wait`, `click`, `type`, `key`, `screenshot`, `assert`.
2. **Run it**: `deskcheck run deskcheck-tests/<name>.yaml --config
   deskcheck-config.yaml` (or the `run_test` MCP tool).
3. **Read the report**: `report.md` (summary + step table + failures),
   `actions.jsonl` (one JSON line per action: timestamp, step, target,
   outcome, screenshot path), and any `diff-*.png` on pixel-diff failure.
4. **Fix the app** (not the test, unless the test itself is wrong —
   say which one you changed and why).
5. **Re-run** until the run passes (exit 0). Never declare GUI work done
   without a passing deskcheck run.

## Rules

- Only launch apps on the allowlist in `deskcheck-config.yaml`. If a
  launch is denied, do NOT work around it (no renaming, no launching via
  another app, no editing the config to add a denied category). Ask the
  human to change the config if the app genuinely belongs there.
- Browsers: only with a fresh throwaway profile (`throwaway_profile:
  true` in the config). Never point deskcheck at a browser carrying your
  real profile, mail, or signed-in sessions.
- Coordinates are primary-monitor pixels. Record the resolution with
  every screenshot (the driver does this; check `actions.jsonl`).
- Pixel-diff: a missing baseline is not a failure of the app — run with
  `--update-baselines` once, eyeball the screenshot yourself, then
  re-run. Only accept a baseline you have actually looked at.
- If a run is interrupted (Ctrl-C), it is marked interrupted, not passed.
  Re-run it.
- Keep tests small and deterministic: one behaviour per test, explicit
  waits, named screenshots. A flaky test is a bug in the test — fix it
  before blaming the app.

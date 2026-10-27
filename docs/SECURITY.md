# Security model: allowlist, default deny

## The model

deskcheck's headline feature is a permission model built for the risk
that desktop agents carry: an agent with OS-wide click/type control can
reach anything the user can — mail, password managers, signed-in
browsers, system settings. deskcheck narrows that to a named list.

- **Config file, named-app allowlist.** `apps:` maps a name to
  `{command, category, throwaway_profile}`. Anything not listed is
  **denied by default**.
- **Enforced twice.** Denials are checked at `launch` AND at every input
  step (`click`, `type`, `key`), which re-checks permission against the
  currently focused app. An allowlisted app cannot be used as a
  trampoline to drive a denied app.
- **Denied categories, even if listed.** These are refused no matter
  what the config says:
  - `password-manager` — password managers, vaults
  - `credential-store` — keychains, secret stores
  - `system-settings` — Settings, Control Panel, registry editors
- **Browsers: throwaway profile only.** A `browser` entry is denied
  unless it sets `throwaway_profile: true` — i.e. it must launch with a
  fresh, empty profile (e.g. `chromium --user-data-dir=/tmp/deskcheck-profile`),
  never an existing profile/session carrying mail, logins, or cookies.
  The flag is enforced on the entry, not just documented.
- **Steps are data, never code.** There is no shell/exec step; the
  parser rejects unknown step types, unknown keys, and shell/exec-style
  keys before anything runs. The only commands that ever execute are the
  `command:` strings in the operator-written allowlist config — never
  strings from a test file.
- **Denials fail loudly.** A denied attempt fails the run (exit 1),
  names the reason, and is written to `actions.jsonl` and the report.

## Threat model

What deskcheck protects against:

- An agent (or a prompt-injected test file) launching an app outside
  the allowlist, or smuggling a shell command into a test.
- An agent reaching a password manager, credential store, or settings
  app through the desktop, directly or via a trampoline app.
- An agent driving a browser that carries the user's real sessions.

What deskcheck does NOT protect against (be honest about the boundary):

- A malicious or careless allowlist entry. If the operator allowlists a
  dangerous app, or points a `command:` at a dangerous program,
  deskcheck will run it — the config is trusted, test files are not.
  Review the config like you would a sudoers file.
- Anything outside the desktop session: deskcheck does not sandbox the
  OS, the network, or the filesystem. An allowlisted app with its own
  file/network access keeps that access.
- A compromised driver or a second agent running alongside deskcheck
  with its own desktop access. deskcheck constrains *its own* steps only.
- Screenshots may contain sensitive pixels from the allowlisted app
  itself (e.g. a document it opens). Treat run output directories as
  sensitive and do not publish them unreviewed.

## Operator checklist

1. Start from `examples/config.yaml`; list only the apps the tests need.
2. Browsers: fresh throwaway profile, `throwaway_profile: true`, and a
   profile directory that is wiped between runs.
3. Never allowlist a password manager, credential store, or settings
   app — deskcheck will refuse it anyway, but do not try to route
   around that (e.g. via a launcher app).
4. Keep run outputs (`runs/`, `deskcheck-mcp-output/`) out of public
   repos; screenshots can leak what was on screen.

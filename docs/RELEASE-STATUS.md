# Version 0.2.0 release verification

Status: **verification in progress**, not a published or approved commercial release.

Completed locally on Windows, using synthetic data only:

- 80 unit/regression methods complete: 79 pass, one privilege-dependent
  Windows symlink test skips. Coverage includes the guided workspace and
  strict YAML/config/MCP boundaries,
  fail-closed permissions, path escapes, redaction, stale screenshots, report
  preservation, interrupted runs, bad PNGs and truthful MCP failures.
- Native standard-control fixture: Unicode/literal punctuation, button action,
  Tab/Enter/End navigation and client-boundary checks pass.
- A second synthetic foreground/covering app receives no text. App-only
  offscreen capture still shows the intended first app, not the covering decoy.
- Wrong-process control injection is rejected. No real private app controlled.
- Guided check library, immutable revisions, editor, captured coordinate picker,
  cancellation, result invalidation and local-only text comparison pass.
- Real app-only success/failure captures, 1440×1024 and 1050×680 desktop layouts
  and source/actual visual comparisons were checked; see `../design-qa.md`.
- Local portable package includes Python/Tk/Pillow and MIT Feather icons/notices.
  CLI mock/denied runs, real native app/capture worker and MCP native runs pass
  without depending on the user's Python installation.

Pending before claiming delivery readiness:

- Each new commit must pass fresh standard GitHub Windows/Linux checks (public
  repo only; no paid runners, caches, artifact upload or publishing). The Actions
  page is the source of truth for the current branch tip, not an older green run.
- The locally prepared portable build is unsigned; organizational acceptance
  and code signing are not claimed. Do not bypass security warnings.
- Explicit release approval. No marketing, payment collection or promises of
  support/delivery to a customer without Alex's specific approval.

Scope: Windows standard controls plus cross-platform mock. Linux native,
browsers, games and custom GPU/Electron interfaces are not supported and are
not a remaining claim to be silently made. See SECURITY.md for limitations.

No verified sale/payment/profit results from source/build/test completion.

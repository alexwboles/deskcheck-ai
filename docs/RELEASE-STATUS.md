# Version 0.2.0 release verification

Status: **verification in progress**, not a published or approved commercial release.

Completed locally on Windows, using synthetic data only:

- 57 unit/regression methods pass, including strict YAML/config/MCP boundaries,
  fail-closed permissions, path escapes, redaction, stale screenshots, report
  preservation, interrupted runs, bad PNGs and truthful MCP failures.
- Native standard-control fixture: Unicode/literal punctuation, button action,
  Tab/Enter/End navigation and client-boundary checks pass.
- A second synthetic foreground/covering app receives no text. App-only
  offscreen capture still shows the intended first app, not the covering decoy.
- Wrong-process control injection is rejected. No real private app controlled.

Pending before claiming delivery readiness:

- Final portable build with notices and sample, extracted-copy CLI/native tests,
  GUI user-side sample workflow, and packaged capture-worker verification.
- Fresh standard GitHub Windows/Linux runner checks (public repo only; no
  paid runners, caches, artifact upload or publishing).
- Explicit release approval. No marketing, payment collection or promises of
  support/delivery to a customer without Alex's specific approval.

Scope: Windows standard controls plus cross-platform mock. Linux native,
browsers, games and custom GPU/Electron interfaces are not supported and are
not a remaining claim to be silently made. See SECURITY.md for limitations.

No verified sale/payment/profit results from source/build/test completion.

# DeepVue W2-A — Delivery & Validation Receipt (2026-08-27)

Wave: W2-A (versioned workspace schema + lossless migration) of
`WS:DEEPVUE-INTELLIGENCE-WORKSPACE`, executed end-to-end under the explicit Sol
commission of 2026-08-26 by the Fable COO session. Skillpack pin
`7d160ff47df1bca0ac6312141e6e1134bbce6539` (re-pinned at pickup, identical to
Sol's dispatch pin; compatibility verified).

## Immutable identities

- Macro pickup `a0b92f9e01c0`; Terminal pickup `580de03e7a75` (the W1-C merge).
- **Macro PR #6473** — head `41f630183d22`, squash-merge `f507a25aee69`,
  verified ancestor of origin/main. Carries: architecture freeze +
  Amendments A1/A2/A3 + NB-F
  (`research/DEEPVUE_W2A_WORKSPACE_LAYOUT_CONTRACT_2026-08-26.md`),
  `contracts/intelligence_workspace/workspace_layout.v1.schema.json`,
  `engine/intelligence_workspace/workspace_layout.py`, 25 golden vectors +
  MANIFEST, `tests/test_intelligence_workspace_workspace_layout.py`
  (240 tests), CI registration, W2-A wave opened on the workstream.
- **Terminal PR #480** — head `49cc914f` (merge of master into the reviewed
  `085ea119` chain), squash-merge `b1b21a17f843`, verified ancestor of
  origin/master. Carries: TS contract mirror + strict/tolerant migration,
  CAS persistence over `chart_layouts`, `/api/layouts` ops, workspace renderer
  (chart primary + brain dock + unsupported tile), management UX per the
  committed spec `terminal/docs/W2A_WORKSPACE_UX_SPEC.md`, i18n, e2e + 20
  screenshots, ~250 new tests.
- **Final golden-vector digest** `3e7c1c50faf8b03b4fa2f3ad2c66db3ebf9ba3ebd93bbb15b228654c382ff339`
  — fixtures byte-identical in both repos, digest law identical, pinned as a
  literal in both test suites.
- Deployed: `terminal-build.sh` → `live = origin/master @ b1b21a17f843`,
  terminal.service restart 2026-08-27T06:11:20Z, healthy. Macro merge has no
  serving-path consequence (contract/validator/tests only).

## Architecture rulings that held

- **Zero DDL.** Optimistic concurrency via atomic conditional UPDATEs on
  `config->>'revision'` (+ the loaded-row-`id` ABA fence, + the two-attempt
  `IS NULL`/`<>` conversion guard). `chart_layouts` remains the single store;
  no second table, no migration ledger, no cache.
- **Migrate-on-write.** Legacy rows render via the tolerant read form
  (per-field no-claim with a surfaced `unclaimed`/`unsupportedWidgets`
  disclosure) and are rewritten only by the user's own save (strict,
  lossless-or-refuse). Original bytes remain exportable until then.
- **`mm.ws` unchanged** (device-local unnamed continuity only; tested).
- **Generic-graph proof pair**: `chart` (whole multi-pane surface, 1/2/4-pane
  + MTF preserved by construction) + `brain` (dock membership is real new
  capability; config `{}` — no state-ownership temptation). Default workspace
  = today's product byte-for-byte.
- **Name identity**: row column authoritative; stored `config.name` null;
  wire/export carries the name (wire-mode validation); normalize law unified
  at trim/collapse/≤60.

## Adversarial review (Phase 6) — three-round convergence

Macro (Opus reviewer, three passes): round 1 = 2 BLOCKER + 8 MAJOR + 5
NONBLOCKING (grammar rejected real Terminal values — `_lab`, dotted suite
keys, nested `_vis`, `line-markers`, composite/`^` symbols; silent field
drops; synthetic vectors; ensure_ascii digest split; export→import
impossibility; projection rewrite; three law-level defects: unrealizable
single-statement conversion guard, false-conflict retry, delete-recreate ABA).
All adjudicated into freeze **Amendments A2/A3 + NB-F** and repaired; final
verdict **PASS — mergeable**, every probe re-run CLOSED.

Terminal (Opus reviewer, three passes): round 1 = 3 BLOCKER + 5 MAJOR + 7
NONBLOCKING (tolerant read dead in product; `unclaimed` surfaced nowhere;
legacy POST could blind-clobber a workspace envelope past CAS; capture
silently dropped invalid fields; unknown widget type bricked the row; a real
W1-C regression — Brain entry points opening the singleton with dead
callbacks; missing isolation tests; name-law split). Round 2 = all fixed +
one new MAJOR (M5b: save silently destroying an unknown panel) → repaired as
warn-before-save with panel-specific disclosure. Final verdict **PASS —
mergeable** at `085ea119`; every probe re-run CLOSED.

## CI + flake adjudication

Macro: full ci.yml green on the merged head (packs + fences + authority).
Terminal: required contexts green; one red attempt of the full responsive
e2e suite was adjudicated environment (master green on the same base, failure
sets churned between attempts across specs W2-A never touched, the only
2/2-repeat passed 3/3 locally on the exact merged head); attempt 3 green.

## Production proof (guest boundary, 2026-08-27 ~06:15Z)

Real browser against `app.mastermind-x.com/terminal?symbol=AAOI` on the
deployed identity:

- Terminal loads; default workspace = chart + Brain dock (today's product);
  pane-grid + canvas live; no JS exceptions (only expected guest-lane
  401/403/404 resource responses).
- **Workspaces menu (new product noun, live)**: toolbar `Workspaces ▾` at
  1440; overflow drill `Workspaces›` at collapsed widths. Guest state exactly
  per spec: gate row "Create a free account to save workspaces", save input
  disabled ("Sign in to save workspaces"), assistant-dock toggle visible,
  `aria-checked=true`, guest-disabled; "Import from a file…" disabled; zero
  raw failure codes in the DOM. Clicking the gate opens the account-creation
  funnel (designed guest journey observed live).
- **W1-C regression proof**: `MM_BRAIN_CFG.getAiContext` live inside the
  workspace-gated mount returning well-formed `ai_context_client.v1`
  (origin, revision 1, active AAOI, ambient AAOI/3D); "INOD price" with AAOI
  active → context receipt strip **"INOD · From your question · overrode
  AAOI"**, run streamed, answer = the honest owner-unavailable plain-word
  disclosure for the quote at that hour (data-plane state, lawful null form).
- **Responsive**: 1440×900 full toolbar; 820×1180 tablet shell with Brain
  sheet + receipt strip, zero horizontal overflow; 390×844 mobile shell
  stacked, zero overflow, all cards reachable (canvas paint lags under
  emulated background throttling; CI `[mobile]` project covers chart
  interaction; the workspace menu has no phone entry point by existing
  product law — toolbar hidden ≤640px, pre-existing).

## Capability classification

- Versioned workspace contract + validator + vectors (both repos):
  **PROVEN_LIVE** (merged, deployed, digest-parity-pinned).
- Guest production surface (default workspace, menu guest states, W1-C
  context flow inside the renderer, responsive shell): **PROVEN_LIVE**.
- **Signed-in persisted-user path (create/save/reopen/rename/duplicate/
  export/import, stale-revision fork, cross-account isolation via real RLS):
  BUILT_NOT_PROVEN.** Fully CI-proven (unit + fixture-store + e2e incl. the
  live-DOM journeys) but the production proof requires an authorized
  signed-in production principal, which the fleet does not hold; account
  creation by the session is prohibited. No fixture was passed off as
  production proof. **External gate returned to Sol: provision/authorize a
  production principal (and ideally a second account for the cross-account
  half), then execute commission §22 items 2–14 as written.**

## Residuals (visible, not hidden)

- The RLS half of isolation gate §13.4 is unverifiable without the second
  production principal (application half fully tested).
- Import end-to-end through a real OS file picker: covered to the validation
  gates by tests/probes; a live signed-in import is part of the gated proof.
- M6(b) negative half (getAiContext undefined while dock excluded; the
  one-commit re-inclusion window) judged harmless (read at send time), untested.
- Full-suite responsive e2e on shared runners is variance-prone (documented
  in-repo); W2-A specs themselves were stable at `--workers=4`.
- The five phone-viewport menu screenshots are impossible until a phone entry
  point ships (existing product law; separate wave if ever commissioned).
- W1-B latency and deep-provider residuals untouched (out of scope).

## Non-goals honored

No W2-B propagation/link-group behavior (static schema vocabulary only), no
W2-C/screener/ratings/alerts, no second store/identity/registry, no DDL, no
quote-owner change, no `mm.ws` scope change, no Prophet/Fusion, no lexer
widening. W2-B remains parked pending a new explicit commission.

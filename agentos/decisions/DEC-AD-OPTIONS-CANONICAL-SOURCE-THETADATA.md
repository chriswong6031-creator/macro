---
key: AD-OPTIONS-CANONICAL-SOURCE-THETADATA
question: >
  Which vendor source is the canonical Mastermind options-data authority for the
  Advanced Data Options workstream — the Massive/Polygon options snapshot estate
  (whose chain entitlement regressed to HTTP 403 on 2026-08-13/14 and never
  returned), or the ThetaData estate (Terminal + T1 EOD/OI/Greeks store) that
  already serves the theta-m1 lanes?
answer: >
  ThetaData is the canonical Mastermind options-data source (Chairman source
  ruling, 2026-08-22). It covers EOD option chains, open interest, Greeks/IV,
  trade + NBBO, and the intraday options data used by Terminal. Massive/Polygon
  is a stock-data source and is NOT the canonical options source. Consequences:
  (1) the prior AD workstream blocker requiring restoration of the
  Massive/Polygon Options Snapshot entitlement is RETIRED, and the external
  options-entitlement blocker is not an AD dependency — the obsolete needs_ceo
  source gate is removed and NOT replaced with another rights gate; (2) any
  Massive/Polygon credential-security cleanup lives outside this Options
  workstream and must not block AD-1; (3) Terminal retains intraday options
  producer/classifier authority — AD originates no second intraday plane;
  (4) AD may consume the existing ThetaData EOD/T1 spine
  (engine/thetadata_store.py over the theta-m1 store) and existing Terminal
  summaries; (5) no duplicate intraday collector is authorized; (6) PRs #5974
  (AD-1C0 source-failure durability) and #6080 (AD-1C0.1 capture lease) remain
  merged evidence/hardening on the legacy estate but no longer gate AD-1;
  (7) DSC:AD-OPTIONS-CHAIN-ENTITLEMENT-REGRESSION becomes legacy-source context,
  not an AD blocker; (8) the current AD-1 scoring/authority architecture
  (intel_brief_heuristic/v1.2, DEC:AD1-DIRECTION-AUTHORITY-SEPARATES-SALIENCE-
  MECHANICS-AND-DIRECTION, Prophet zero-rank, Q_flow structurally absent)
  remains FROZEN — this is a source cutover, not a model revision.
rationale: >
  The workstream was carrying the wrong source authority: AD-1 production sat
  BLOCKED_EXTERNAL on a Massive/Polygon chain entitlement that vendor-side
  regressed on 2026-08-13/14 and did not return through two verified restoration
  claims, while the organization already operates a canonical ThetaData estate —
  a licensed Terminal (ONE-instance license, launchd com.macro.theta-terminal on
  the M1), a ~60GB T1 EOD/OI/Greeks store with a canonical fail-loud resolver
  (engine/thetadata_store.resolve_thetadata_store, WP-RESOLVER), theta-m1-pinned
  daily.yml consumers, and Terminal-side intraday options production. Waiting on
  a redundant entitlement for a non-canonical source was a category error. The
  prior "do not silently route AD-1 to ThetaData" prohibition guarded against a
  silent source swap by a coding agent; this ruling is the explicit
  Sol-commissioned source adjudication that prohibition reserved the decision
  for, so it is superseded, not violated.
alternatives:
  - option: Keep Massive/Polygon canonical and wait for entitlement restoration
    why_not: two restoration claims (2026-08-19, 2026-08-20) both re-probed 403 on both vendor domains; the blocker is vendor-external, unbounded in time, and gates a workstream whose data already exists in-house on the canonical ThetaData estate
  - option: Dual-source adjudication (Massive chains + ThetaData redundancy)
    why_not: maintains two options truth stores with conflicting identities and clocks; the Chairman ruling names ONE canonical source, and the Massive chain feed currently returns zero bytes anyway
  - option: Replace the AD-1 architecture while cutting the source over
    why_not: v1.2 scoring/authority semantics are frozen contract; widening a source cutover into a model revision would launder unreviewed semantic change through an infrastructure PR
affects:
  - "WS:ADVANCED-DATA-OPTIONS"
  - scripts/build_options_intel_brief.py
  - engine/thetadata_store.py
  - "DSC:AD-OPTIONS-CHAIN-ENTITLEMENT-REGRESSION (reclassified: legacy-source context, no longer an AD blocker)"
evidence:
  - "Chairman source ruling relayed via Sol directive AD-1T0, 2026-08-22"
  - "WS:ADVANCED-DATA-OPTIONS blocked_by/needs_ceo rows (pre-correction state this decision retires): chain 403 on both api.polygon.io and api.massive.com while stock/news 200, re-proven 2026-08-19T19:59:29Z and 2026-08-20T05:23:23Z"
  - "Live m1 probe 2026-08-22 (this session): store /Users/chriswong/theta-ops-wt/data/thetadata_eod content-bearing (eod/oi/greeks, 381 eod roots); Theta Terminal answering on :25503 (v3); launchd lanes com.macro.theta-terminal, com.macro.thetadata-backfill, com.macro.thetadata-r2sync, com.macro.theta-staleness present"
  - "daily.yml theta-m1 runner pin for ThetaData-consuming jobs (comment block at .github/workflows/daily.yml:1406-1644)"
confidence: high
reversibility: costly
decided_by: chairman-chris
decided_at: 2026-08-22
---

Chairman source-authority correction, recorded by coo-fable during wave AD-1T0.

ThetaData = canonical Mastermind options-data source (EOD chains, OI, Greeks/IV,
trade + NBBO, Terminal intraday). Massive/Polygon = stock-data source only.

Boundaries preserved by this ruling: Terminal keeps intraday options
producer/classifier authority; AD consumes the existing T1 spine through the
canonical resolver (never a second store path, never a repo copy of the ~60GB
store); no duplicate intraday collector; the legacy polygon_gex estate's merged
hardening (#5974, #6080) stays merged as evidence but does not gate AD-1;
AD-1 v1.2 scoring/authority stays frozen — Q_flow activation on ThetaData
trade+NBBO is a future model-version decision, not part of this cutover.

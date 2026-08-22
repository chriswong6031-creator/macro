---
key: THETADATA-T1-SPINE-DAILY-REFRESH-IS-48-ROOTS
claim: >
  The canonical ThetaData T1 store on the m1 host holds deep history (2013→)
  for ~381 roots, but its DAILY maintenance is a deliberate 48-root refresh
  list hard-coded in the launchd keepalive wrapper (22 ETF/index + 26 single
  names), of which 39 intersect the 375-name AD/gex universe — so AD-1's
  frozen SOURCE_COVERAGE_GATE (0.90) is structurally unreachable from today's
  store (39/375 = 0.104, uniform across the 20 most-recent sessions), ~333
  universe roots are frozen at their backfill dates (mostly 2026-07-02), and
  each nightly refresh re-pulls the whole current year per root at ~3 min/root
  (375 roots ≈ 19 h/night — infeasible under the existing design). Adjacent
  facts: thetadata-r2sync has failed nightly since ≥2026-08-08 (publish_r2's
  rglob does not descend the store's symlinked tier dirs), so no R2 projection
  exists for GitHub runners; and the store-bearing M1 is not a registered GH
  runner (theta-m1 label interim-carried by a non-store host; RE-PIN RULE in
  daily.yml comments) — every ThetaData-consuming nightly step self-skips.
kind: constraint
falsifier: >
  The m1 backfill.log shows a nightly pass whose per-pass universe exceeds the
  48-root REFRESH_ROOTS list (e.g. "Universe: 375 roots ... 375 succeeded"),
  or a post-2026-08 store session carries materially more than ~48 universe
  roots with same-session EOD+OI rows (per-session root counts on the live
  store), or an incremental-refresh backfill design lands that decouples
  nightly cost from whole-year re-pull.
so_what: >
  Do NOT try to reach 0.90 coverage by shrinking the universe, deriving it
  from the store, copying the ~60GB store between hosts, or launching a second
  Terminal/collector — the lawful path is a Sol-authorized spine-cadence wave
  (incremental refresh) plus a store-host topology decision (M1 runner re-pin
  or r2sync heal). Until then the honest production board state is
  INSUFFICIENT_COVERAGE, and the AD-1 producer self-skips off-host by design.
verified_at: 2026-08-22
verified_by: >
  Read-only m1 census 2026-08-22 (AD-1T0 wave): REFRESH_ROOTS in
  /Users/chriswong/theta-ops-wt/scripts/launchd/theta_backfill_keepalive.sh;
  backfill.log passes "Universe: 48 roots ... 48 succeeded" (~2.5 h each,
  13:10→15:40Z and 15:40→18:11Z on 2026-08-21); per-session universe coverage
  uniform at 39/372 across the 20 most-recent sessions (eod=oi=greeks=39);
  store tip 2026-08-20 with 08-21 absent as of 08-22; r2sync failure
  reproduced live (rglob sees 2 files, guard refuses); runner state from
  .github/runner-policy.yml:152-160 + daily.yml:1426-1440 unpin comment.
scope: [macro]
confidence: verified
---

Full census evidence and the cutover's disposition live in
`research/AD1T0_THETADATA_CUTOVER_SPEC_2026-08-22.md` (§H) and the
`ADVANCED-DATA-OPTIONS-2026-08-22` handoff. The r2sync defect is chipped as a
separate fix task; the spine-cadence decision is Sol's.

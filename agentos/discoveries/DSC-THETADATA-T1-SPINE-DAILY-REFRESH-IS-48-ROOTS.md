---
key: THETADATA-T1-SPINE-DAILY-REFRESH-IS-48-ROOTS
workstream: "WS:ADVANCED-DATA-OPTIONS"
falsifier: >
  The m1 backfill.log shows a nightly pass whose per-pass universe exceeds the
  48-root REFRESH_ROOTS list (e.g. "Universe: 375 roots ... 375 succeeded"), or
  a post-2026-08 store session carries >60 universe roots with same-session
  EOD+OI rows (measured via per-session root counts on the live store).
so_what: >
  AD-1's SOURCE_COVERAGE_GATE (0.90 vs the 375-name universe) is structurally
  unreachable from today's T1 store: only ~39 universe roots are daily-current
  (10.4%). Do NOT "fix" this by shrinking the universe, deriving it from the
  store, copying stores between hosts, or launching a second collector — the
  lawful path is a Sol-authorized spine-cadence wave (incremental refresh
  design: the current whole-year re-pull costs ~3 min/root/night, so 375 roots
  ≈ 19 h/night, infeasible under the existing design and Terminal budget).
  Until then the honest production board state is INSUFFICIENT_COVERAGE.
verified_by: >
  Read-only m1 census 2026-08-22 (session c9b9c5e2): REFRESH_ROOTS list in
  /Users/chriswong/theta-ops-wt/scripts/launchd/theta_backfill_keepalive.sh
  (22 ETF/index + 26 singles = 48); backfill.log passes "Universe: 48 roots ...
  48 succeeded" taking ~2.5 h each; per-session universe coverage uniform at
  39/372 across the 20 most-recent store sessions (eod=oi=greeks=39); ~333
  universe roots frozen at 2026-07-02-era dates; store tip 2026-08-20 while
  the 08-21 Friday session had not landed as of 08-22.
confidence: high
---

The ThetaData T1 store on the m1 host holds deep history (2013→) for ~381
roots, but its DAILY maintenance is a deliberate 48-root refresh list hard-coded
in the launchd keepalive wrapper — not a defect, an ops budget. 39 of the 48
intersect the 375-name AD/gex universe. Each nightly refresh re-pulls the whole
current year per root (self-healing for interior holes, ~3 min/root). Related:
the thetadata-r2sync lane has failed nightly since ≥2026-08-08 because
scripts/publish_r2.py's rglob does not descend the store's symlinked tier dirs
(chipped as a separate fix task), so no R2 projection of the store exists for
GitHub runners; and the store-bearing M1 is not currently a registered GH
runner (theta-m1 label interim-carried by a non-store host; RE-PIN RULE in
daily.yml comments). Every ThetaData-consuming nightly step therefore
self-skips today, and the AD-1 producer does the same off-host (resolver None
→ ::warning + exit 0 + bytes untouched).

---
key: THETADATA-19H-ESTIMATE-WAS-THE-WHOLE-YEAR-DESIGN
claim: >
  The ~19 h full-universe nightly estimate recorded during AD-1T0
  (DSC:THETADATA-T1-SPINE-DAILY-REFRESH-IS-48-ROOTS) is a property of the
  WRONG MAINTENANCE ALGORITHM, not of one-day ThetaData vendor throughput:
  the retiring launchd wrapper obtains freshness by unmarking the current
  year in _backfill_state.json and re-running the HISTORICAL BACKFILL
  primitive, which re-downloads the entire current year (~3 min/root). The
  bounded one-session request pattern the daily maintainer actually needs
  (EOD[S] + Greeks[S] + OI[D], one ≤7-day-window HTTP request per tier)
  measures at seconds per root on the live m1 Terminal — 2.5–9.1 s/root at
  worker=1 UNDER heavy concurrent backfill load (SPY 9.07 s dense-index
  worst case, NVDA 3.03 s, CBRS 2.54 s), i.e. a naive serial full-universe
  bound of ~16–56 min for 375 roots, two orders of magnitude under 19 h,
  before any root-level concurrency.
kind: constraint
falsifier: >
  The AD-1T1 quiet-window benchmark ladder (W=1/2/4/6, 24-root stratified
  sample, steady-state pattern on S=2026-08-19/D=2026-08-20) projects a
  full-universe steady-state runtime that does NOT fit the 16:10→18:30 ET
  envelope at any worker count ≤6, or production scheduled runs of the
  incremental daily mode take materially longer per root than the benchmark
  (e.g. vendor-side rate limiting that only binds at universe scale).
so_what: >
  Never cite the 19 h figure as evidence that full-universe daily ThetaData
  coverage is infeasible — it indicts the whole-year re-pull design only.
  The lawful cadence fix is the AD-1T1 one-session incremental maintainer
  (extend scripts/topup_thetadata_day.py; retire the current-year-unmark
  trick from DAILY maintenance; historical backfill stays an explicit
  resumable tool). Do not scale REFRESH_ROOTS to 375 names, and do not
  reach for DTE/strike filters or universe shrinkage to buy cadence.
verified_at: 2026-08-22
verified_by: >
  Sol AD-1T1 handoff §0/§4.1 (mechanism trace: current-year unmark in
  theta_backfill_keepalive.sh forces whole-year re-download); AD-1T1
  read-only benchmark smoke on m1 2026-08-22 ~21:5xZ (harness at
  m1:/tmp/ad1t1-bench, results smoke_UNDER_LOAD_SMOKE.json: SPY 9.07 s /
  NVDA 3.03 s / CBRS 2.54 s per root for the 3-tier one-day pattern,
  measured while the 48-root whole-year pass pid 38477 was actively
  consuming the Terminal); collectors/thetadata.py one-day request topology
  (≤7-day windows ⇒ one HTTP request per tier call).
scope: [macro]
confidence: verified
---

Benchmark ladder results (worker=1/2/4/6, quiet window) and the frozen
production concurrency land in `research/AD1T1_INCREMENTAL_CADENCE_SPEC_2026-08-22.md`
§F when measured. Supersedes the infeasibility IMPLICATION of
[[THETADATA-T1-SPINE-DAILY-REFRESH-IS-48-ROOTS]] (whose 48-root/whole-year
facts remain true of the retiring design).

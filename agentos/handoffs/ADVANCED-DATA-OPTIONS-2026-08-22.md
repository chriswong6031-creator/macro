---
workstream: "WS:ADVANCED-DATA-OPTIONS"
session_date: 2026-08-22
author: coo-fable
branch: claude/ad1t0-thetadata-source-cutover
---

# AD-1T0 — ThetaData canonical source cutover (Chairman ruling executed)

## What happened

Chairman source ruling recorded (`DEC:AD-OPTIONS-CANONICAL-SOURCE-THETADATA`):
ThetaData is canonical for options truth; Massive/Polygon is a stock source.
The entitlement blocker and needs_ceo gate are RETIRED. WS record corrected;
the AD-0 ledger's canonical-source answer superseded in place.

The AD-1 producer (`scripts/build_options_intel_brief.py`) was cut over from
`data/polygon_gex/chains` to the canonical T1 store via
`engine.thetadata_store.resolve_thetadata_store()`. Engine byte-unchanged
(verified `git diff <base> HEAD -- engine/ | wc -l` == 0 at every commit).
Frozen spec + identity ruling: `research/AD1T0_THETADATA_CUTOVER_SPEC_2026-08-22.md`.

Three adversarial review rounds (opus) on the implementation; every finding
closed and re-verified against its original reproduction (B1-B3 blockers:
absent-oi-baseline scored as zero / rung-2 spot unbound by receipt_id /
staleness anchor drift; N3/N4 second-order: per-contract coverage floor,
bounded S-role demotion; plus majors/minors). Final verdict SHIP.

Committed production artifact `site/options_intel_brief.json` built ON the m1
store-bearing host against the real store: S=2026-08-19, D=2026-08-20,
`receipt_id 637d0c60ec86...`, board honestly INSUFFICIENT_COVERAGE
(39/375 = 0.104), zero Polygon references, `_run` diagnostics present.

## Verified claims (command → result)

- Store live: `ssh m1 'ls /Users/chriswong/theta-ops-wt/data/thetadata_eod'` →
  eod/oi/greeks, 381 roots/tier (symlinked to /Volumes/STORAGE/macro-data/).
- Terminal live: `curl 127.0.0.1:25503/v3/option/list/symbols` on m1 → HTTP 200.
- Contract identity: tuple (root, expiration, strike, right) unique per
  (tier, session) across 9 sessions 2013→2026; 0 conflicting duplicates;
  0 nonstandard roots; strikes integral in thousandths (0/2,104,998).
- Daily-current coverage: 39/372 universe roots uniform across the last 20
  sessions (`DSC:THETADATA-T1-SPINE-DAILY-REFRESH-IS-48-ROOTS`).
- Producer on real store (m1, plane conda python 3.12/pandas 3.0.5):
  `python -m scripts.build_options_intel_brief` → header above, exit 0.
- Diagnostic scoring (reduced 39-name universe + ignore_staleness, NEVER
  production): 39/39 eligible, board OK, real top-six (AMZN/AVGO/PLTR/MSFT/
  SPY/GOOGL VOLATILITY), event=4, risk=4, no_signal_exemplar=QQQ — discharges
  the contract §8 feasibility debt (test_15 skip).
- Focused suites: `PYTHONHASHSEED={1,2,3} python3 -m pytest
  tests/test_options_intel_brief.py -q` → 143 passed, 1 skipped every seed.

## do_not_redo

- Do not re-run the contract-identity census — measured clean; ruling frozen in
  the spec §A. Do not invent an OCC grammar/identity registry: the adapter
  serializes the tuple into the engine's existing strike_ticker format.
- Do not re-derive the S/D pair law: committed-session predicate (plaus +
  capped S-role demotion + OI-only frontier X) is spec §C, reviewed and
  property-tested; select_settled_pair itself is frozen engine code.
- Do not try to reach 0.90 coverage by shrinking the universe, deriving it
  from the store, copying the 60GB store, or launching a second Terminal /
  collector — the spine is the blocker and it is a Sol decision.
- Do not treat the repo data/thetadata_eod stub as a store (resolver refuses
  it by design) and do not weaken the off-host self-skip (::warning + exit 0 +
  bytes untouched).
- Do not re-measure the oi/eod match-rate floor basis (organic min 0.825,
  floor 0.60) without new evidence — it is recorded in spec §A #7.

## danger_areas

- `engine/options_intel_brief.py` is FROZEN v1.2 — the whole wave was built
  around zero engine edits; any "small" engine change reopens Sol review.
- The oi tier's row dated t = positions at EOD t-1 (store law). Same-day OI
  in an S-feature is a lookahead bug; the ΔOI baseline is oi[S], next print
  oi[D]. Three review rounds defended this — read spec §B before touching.
- site/gex/*.json is legacy-Polygon provenance: hard-disabled in the producer
  (not date-gated). Re-enabling requires a ThetaData-backed P/mechanics wave.
- Q_flow stays structurally ABSENT (signing gate); activating ThetaData
  trade+NBBO direction is a future model-version decision.
- The m1 flow-ops-wt checkout is detached at a5f79c83 on a FORK remote
  (chriswong6031-creator/macro) — not a pusher to canonical main. Proof runs
  rsync the branch tree to /tmp/ad1t0-proof and run with the plane conda env.

## Open state for the next session

1. AD-1 = BUILT_NOT_PROVEN. Blockers to PROVEN_LIVE (all Sol-owned):
   (a) T1 spine daily refresh 48 roots vs 375-universe (the DSC);
   (b) store-bearing M1 not a GH runner (daily.yml RE-PIN RULE) and/or
   r2sync heal (publish_r2 symlink rglob — chip task_c138ddbd already spawned);
   until one lands, the nightly engine-job producer self-skips and the
   committed artifact serves as the honest board.
2. AD-2 stays CLOSED until AD-1 production acceptance.
3. Morning-cadence publication (S brief at ~06:30 ET on D) is a recorded
   future opportunity (spec §H), NOT authorized.

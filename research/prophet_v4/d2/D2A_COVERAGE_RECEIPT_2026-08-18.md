# V4-D2A COVERAGE RECEIPT — identity resolution, first bake (2026-08-18)

All numbers stamp **build pin `9ff7bad19126`** (origin/main, 2026-08-18) and the Data OS
master generation `generated_at 2026-08-14T16:45:46` / symbol-directory snapshot
`2026-08-10` (703 securities, 100% US, MICs XNYS/XNAS/XASE). Cohort populations here are
NOT the D1-pin populations — the underlying artifacts advanced between pins (e.g. C1 grew
1,508 → 2,936 as the candidate store advanced). Per house law, no percentage without its
stamp.

## 1. Baked sidecar census (the real resolver, committed artifact)

`data/theme_graph/identity_resolution.parquet`, first bake from the committed graph
(2,806 company-kind nodes) + committed master. Guard-printed census (strict, exit 0):

| resolution_state | rows |
|---|---|
| RESOLVED | 701 |
| NOT_IN_MASTER | 1,869 |
| UNSUPPORTED_MARKET | 233 |
| DEFERRED_IDENTITY_EXCEPTION | 2 (co:us:B, co:us:GOLD) |
| ENTITY_TYPE_CONFLICT | 1 (co:us:IBIT vs etf:IBIT) |
| **total** | **2,806** (== company nodes, set-equal) |

Same-security duplicate node-sets surfaced by the bridge (two topology nodes, one
security — the D2B/D3 signal): `SEC:US-XNAS-SATS` → {co:us:SATS, co:us:ECHO};
`SEC:US-XNAS-FISV` → {co:us:FI, co:us:FISV}.

## 2. Cross-check against the independent pre-bridge estimate (Scout D)

Scout D measured current-catalog master coverage naively (exact inception-code + active
alias membership) before the resolver existed: us-scope company nodes 699 exact + 4
alias-only = 703 matchable. The resolver's 701 RESOLVED reconciles exactly:
703 − GOLD (receipt exception, naive-exact but NOT issuer-safe) − IBIT (entity-kind
conflict, naive-exact but kind-contradicted) = 701. NOT_IN_MASTER 1,869 = 535 us-scope
unmatched + 1,335 cn/hk/ca nodes (master is US-only) − 1 (B, deferred). UNSUPPORTED_MARKET
233 = the intl-scope nodes. No unexplained residue.

## 3. D1-cohort identity coverage (pre-bridge, current-catalog approximation)

Measured at this pin by Scout D against the same master (exact = inception-code match;
alias = active alias row only; percentages of that row's total):

| population | total | exact | alias-only | unmatched |
|---|---|---|---|---|
| graph co:us:* company nodes | 1,238 | 699 (56.5%) | 4 (0.3%) | 535 (43.2%) |
| C0 (broad candidate store) | 3,227 | 688 (21.3%) | 4 (0.1%) | 2,535 (78.6%) |
| C1 (newest store stamp) | 2,936 | 685 (23.3%) | 4 (0.1%) | 2,247 (76.5%) |
| C2 (served Prophet plans) | 215 | 101 (47.0%) | 0 | 114 (53.0%) |
| C3 (TURN WATCH triggered) | 955 | 223 (23.4%) | 1 (0.1%) | 731 (76.5%) |
| C5 (standouts buy list) | 66 | 34 (51.5%) | 0 | 32 (48.5%) |

Structural noise (graph-tagged ETFs, config-receipted delisted) explains **under 2%** of
unmatched in every population; alias rows add ≤0.3% everywhere. The shortfall is genuine
narrow-master coverage (ordinary common-stock tickers), not junk tickers.

## 4. The D2B work queue (measured gap statement)

The Data OS master (703 rows, seeded from a 711-name universe) covers 21–57% of any V4
population. Closing the gap is **D2B's** charter — expand exact-identity coverage through
lawful canonical sources (never Prophet candidate outputs as identity authority), plus
correction lineage for the GOLD/B membership defect and the IBIT entity-kind treatment.
The bridge makes the queue precise: every NOT_IN_MASTER row in the committed sidecar is a
D2B work item with its receipts attached. D2A deliberately does NOT broaden the master
(handoff §5.4/§10) — the shortfall is published, not hidden.

## 5. Reproduction

Sidecar: `COLLECT_LANE=nightly python3 -m scripts.build_theme_graph` (writes
identity_resolution alongside capability; deterministic from the committed graph + master
inputs). Census: `python3 -m scripts.check_theme_graph_contracts --strict`. Cohort table:
Scout D's script at the session scratchpad `d2a_scout_d/census.py`, reusing
`research/prophet_v4/d1/build/_common.py::build_cohorts()` unchanged.

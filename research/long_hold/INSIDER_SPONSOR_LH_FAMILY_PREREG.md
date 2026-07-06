# Pre-registration — roster family F4: `long_hold.insider_sponsor_lh` (m = 3)

**Registered:** 2026-07-06 (operator + Fable). Criteria do not move after merge (OBJECTIVE §7 lock semantics).
**Family id:** `long_hold.insider_sponsor_lh` (sub-family of `fdr_family='long_hold'`).
**Mechanism claim:** insiders buying their own washed-out stock with open-market dollars are a sponsorship signal that separates durable holds from bounces. Construction inherits the only insider form that survived BH-FDR in its habitat (`net_usd_mcap`, sector-neutral, mid/small-cap; `research/INSIDER_FACTOR.md`).
**Coordination:** entry-ruler insider hypotheses (I1/I2/I3) belong to ESX Amendment 2 RUL-26 (`entry_stack` program). This family shares data lanes but registers claims ONLY at the long-hold ruler. No claim is double-counted across programs.
**Provenance:** `feature_provenance = {sec_insider_panel(2006q1→, filing_date PIT), fundamentals_panel(shares), label_panel_price_stores(mcap close)}`. No entry-selection variable is re-expressed.

## 1. Substrate

- Insider transactions: `data/sec_insider/panel/*.parquet` — open-market purchases/sales (`code ∈ {P, S}`, `direct` only), PIT by `filing_date ≤ fire_date`.
- Market cap at fire_date: close(fire_date) × shares from the most recent `fundamentals_panel` row with `asof_date ≤ fire_date`. Missing mcap → IS-1 missing (no raw-USD fallback).
- Sector-neutralization: sector map as expanded in LT-1 (fallback: market-wide percentile with `benchmark='market'` stamp).

## 2. Registered hypotheses (m = 3; expected signs frozen)

| id | Feature | Type | Definition (PIT as of fire_date) | Expected sign | Test |
|---|---|---|---|---|---|
| IS-1 | `insider_net_usd_mcap_6m_pct` | cont | Trailing 126-session net open-market insider dollars (ΣP − ΣS) / mcap, sector-neutral cross-sectional percentile | + | MWU / RBC |
| IS-2 | `cluster_buy_pre_fire` | bin | ≥2 distinct insider CIKs each with ≥$25,000 open-market P buys, filing_date within [fire_date − 63 sessions, fire_date] | + | Fisher |
| IS-3 | `officer_buy_flag` | bin | ≥1 `is_officer` open-market P buy ≥ $25,000 in the same window | + | Fisher |

Coverage rule: OBJECTIVE §5's 20% rule; drops stay in Σ.

## 3. Rulers, floors, stamps

Identical two-ruler structure, floors, stamps, era breakout, reshuffle null, and TrialLedger discipline as `EXPECT_DRIFT_FAMILY_PREREG.md` §3–§4, with `log_declared_budget(3, family='long_hold.insider_sponsor_lh')`. Ruler-P fires ≤ 2023-12-31 only; Ruler-H at the A2 trigger. This family also delivers the F1 `insider_cmp` coverage restoration (data lane shared; F1's hypothesis remains registered under F1's m=9).

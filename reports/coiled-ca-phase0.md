# COILED-CA — Durable-Bottom Detector on Canada · Phase-0

**Verdict: KILL. FAIL (powered wrong-sign). COILED is anti-predictive on Canada with adequate power — CA joins HK on the do-not-port list, with its own evidence.**

Battery COILED-CA of the HK/Canada program. `engine/coiled.py` is validated on US + CN and refuted on HK; **Canada was never tested until now**. This replicates the EXACT CN wave-3 gate (`m2d_s3d` trigger, COILED vs noncoiled_washout clean15 spread, split-half, per-name majority, name-clustered bootstrap) on the CA panel. Pre-registration: `research/COILED_CA_PREREG.md` (committed before this run; thresholds are the CN values verbatim). **Nothing is wired in this PR** (collision pact §8.1: china_alpha owns `engine/coiled.py`).

## Panel & power (honest)

- **Names panel:** `data/canada_search/closes.parquet` — 215 of 219 names clear the 800-bar floor (215 processed). Close-only → H4 volume + `low_stop5` skipped (same as CN/HK). EVAL_START 2022-09-01 (washout_ctx 308-bar + 126-fwd warmup); usable span ≈ 2.8y, **one macro cycle**.
- **Events:** 3114 total (1360 durable / 1754 trap).
- **`m2d_s3d` fires (eval):** 3106; **COILED 923** / noncoiled_washout 1021. Power floor n_COILED≥400: MET.
- **~7× thinner than CN** (10,784 COILED) and single-regime — the split-half is a within-cycle split, not a cross-regime replication. Stated on every number.

## Pre-registered G-CA gate (CN wave-3 thresholds, verbatim)

| # | gate | threshold | observed | pass |
|---|---|---|--:|:--:|
| 1 | Δclean15 lift | ≥ +3.0pp | -2.96pp | ❌ |
| 2 | Δstop5 (COILED not worse) | ≤ +1.0pp | 6.08pp | ❌ |
| 3 | n_COILED | ≥ 400 | 923 | ✅ |
| 4 | split-half both halves > 0 | both | h1 -1.76 / h2 -3.29 | ❌ |
| 5 | per-name majority | ≥ 55.0% | 45.8% (n=131) | ❌ |
| 6 | name-clustered bootstrap 90% LB | > 0 | -5.83pp | ❌ |
| R | robustness (clean10/20 sign + dead-money lower) | all | c10 -3.86 · c20 -2.66 · dm_lower True | ❌ |

**Gate reasons:** Δclean15 -2.96 < 3.0pp; Δstop5 6.08 > 1.0pp (COILED worse); split-half not both>0 (h1 -1.76 / h2 -3.29); per-name 45.8% < 55.0% (n=131); bootstrap 90% LB -5.83 ≤ 0; robustness: clean10 Δ -3.86, clean20 Δ -2.66, dm_lower=True.

## Strata (m2d_s3d, next-bar fill)

| stratum | n | clean15 | stop5 | dead_money |
|---|--:|--:|--:|--:|
| COILED | 923 | 34.45% | 48.0% | 5.96% |
| noncoiled_washout | 1021 | 37.41% | 41.92% | 7.54% |
| STAR (COILED∩div) | — | 41.0% | — | — |
| **Δ (COILED − NCW)** | | **-2.96pp** | **6.08pp** | |

Name-clustered bootstrap (unit = name, B=5000, seed 17): Δclean15 median -2.96pp, 5th pct -6.57pp, one-sided 90% LB **-5.83pp**, P(Δ>0) 0.102. Naive (unclustered, fire-level) Δ -2.96pp — the gap between naive and clustered is the correlated-fire haircut.

## Split-half (cut 2024-01-01, pre-registered)

| half | n_COILED | n_NCW | COILED clean15 | NCW clean15 | Δ |
|---|--:|--:|--:|--:|--:|
| pre-2024 | 458 | 440 | 31.88% | 33.64% | -1.76pp |
| post-2024 | 465 | 581 | 36.99% | 40.28% | -3.29pp |

## Deep TSX sector-ETF context (2001→, DIFFERENT cohort mechanic — NOT in the verdict)

**Pre-stated caveat:** an ETF *is* its sector, so there is no sector-peer cohort. This treats the 9 sector ETFs as ONE cross-ETF cohort (breadth-of-sector-washout) — a genuinely different object from the per-name mechanic. Context only; it cannot and does not change the G-CA verdict.

Inception: XEG 2001-03-23, XGD 2001-03-29, XFN 2001-03-29, XIT 2001-03-23, XRE 2002-10-22, XMA 2005-12-28, XBM 2012-01-24, XUT 2012-01-24, XST 2012-01-24. Total fires 789.

| stratum | n | clean15 | stop5 |
|---|--:|--:|--:|
| ALL | 789 | 26.49% | 40.56% |
| COILED (cross-ETF) | 140 | 25.0% | 52.14% |
| NCW (cross-ETF) | 190 | 34.21% | 44.21% |
| **Δ** | | **-9.21pp** | |

## Survivorship bound (not a stamp)
`canada_search/closes.parquet` is current-constituent (219 names on today's TSX); delisted losers are absent → durable-bottom liftoff rates are biased UP uniformly. The COILED-vs-NCW **spread** (both strata from the same survivor panel) is the object of interest and is far less sensitive to that level bias. Bound: a COILED-PASS here is an optimistic upper bound; a COILED-FAIL is conservative (survivorship only helps liftoff). No ex-US dead-name store → no worst-case delisted-imputation lower bound. The deep-ETF context is survivorship-clean.

## What this does NOT show
Only the COILED cohort-washout × bullish-divergence detector as a CA standout-board ranking bonus on the `m2d_s3d` trigger. It does NOT test other triggers, the wave-4 COILED-FIRE marker, theme-basket cohorts, volume/participation (no CA search-store volume), the deep-ETF cohort as a decision leg (context only, different mechanism), or any CA edge outside COILED (C1 commodity→sector, C-BANK, momentum — separate batteries, resolved in masterplan §6.1). A CA NO-GO/KILL is a verdict on THIS engine's portability to Canada, not on whether Canada has any tradable durable-bottom timing edge.

---
_Harness `research/entry_timing/wave3_ca.py` (fork of `wave3.py` close-only path; leak-free math reused verbatim). Pre-reg `research/COILED_CA_PREREG.md`. DSR family budget 40 via `TrialLedger.with_declared_budget`. No wiring._
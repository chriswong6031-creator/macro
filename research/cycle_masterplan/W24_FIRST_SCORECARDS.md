# W2.4 — The Three Promise-Graders: FIRST REAL SCORECARDS

**Wave:** Cycle Intelligence W2.4 · **Generated:** 2026-07-02T18:59:34.070871+00:00

This is the program's **first real self-measurement** — the first leak-free walk-forward track record for the numbers the platform already plots. Per the doctrine, **a bad number honestly measured is the product.** Turn truth is the INDEPENDENT realized-extrema oracle (`cycle_ontology.realized_extrema_turns`, ruling A6) — the ZigZag detector never grades itself. Sectors and countries are SEPARATE scorecards. BACKTEST (backfilled) and LIVE (prospective) cohorts never blend in one number.

## Headline — turn P/R · cone coverage · reliability (BACKTEST cohort)

| Engine | n stamps | Turn precision | Turn recall | Timing err (mo, median/IQR) | Cone cov vs 0.80 | Cone (fwd-only) | Overdue frac | Signal skill | Stance skill |
|---|---|---|---|---|---|---|---|---|---|
| **sector_cycles** | 1881 | 0.075 [0.05, 0.10] | 0.289 [0.21, 0.38] | -1.0 / 3.0 | 0.188 (n=442) | 0.266 (n=289) | 0.346 | -1.538 | -1.309 |
| **country_cycles** | 5738 | 0.109 [0.09, 0.13] | 0.255 [0.22, 0.29] | 1.0 / 3.0 | 0.283 (n=1235) | 0.347 (n=805) | 0.348 | -1.198 | -1.191 |
| **china_sector_cycles** | 4869 | 0.230 [0.20, 0.26] | 0.369 [0.33, 0.41] | 0.0 / 2.0 | 0.359 (n=856) | 0.414 (n=640) | 0.252 | -1.159 | — |

## Pre-registration gate verdicts (PREREGISTRATION.md §3)

Gates are FROZEN — this reports pass/fail/inconclusive, it does not move any criterion. FDR-BH applied within the `turn_pr` family at q=0.10.

| Gate | Claim | Bar | Result | Verdict |
|---|---|---|---|---|
| **CC-3** (sector_cycles) | turn P/R Wilson-lo > 0.5 on n_eff≥40, independent truth | prec-lo 0.05, rec-lo 0.21, n_eff 422.0 | FAIL | falsified |
| **CC-1** (sector_cycles) | cone coverage ≈ 0.80 (calibration, report-only) | empirical 0.188 vs 0.80, CI [0.15, 0.23] | MISCALIBRATED | too_tight |
| **CC-2** (sector_cycles/signal) | Brier skill vs base rate > 0, n≥30 | skill -1.538, hit 0.430 vs base 0.659, n 642 | FAIL | falsified |
| **CC-2** (sector_cycles/stance) | Brier skill vs base rate > 0, n≥30 | skill -1.309, hit 0.481 vs base 0.659, n 1257 | FAIL | falsified |
| **CC-3** (country_cycles) | turn P/R Wilson-lo > 0.5 on n_eff≥40, independent truth | prec-lo 0.09, rec-lo 0.22, n_eff 1191.0 | FAIL | falsified |
| **CC-1** (country_cycles) | cone coverage ≈ 0.80 (calibration, report-only) | empirical 0.283 vs 0.80, CI [0.26, 0.31] | MISCALIBRATED | too_tight |
| **CC-2** (country_cycles/signal) | Brier skill vs base rate > 0, n≥30 | skill -1.198, hit 0.460 vs base 0.565, n 2075 | FAIL | falsified |
| **CC-2** (country_cycles/stance) | Brier skill vs base rate > 0, n≥30 | skill -1.191, hit 0.462 vs base 0.565, n 3900 | FAIL | falsified |
| **CC-3** (china_sector_cycles) | turn P/R Wilson-lo > 0.5 on n_eff≥40, independent truth | prec-lo 0.20, rec-lo 0.33, n_eff 810.0 | FAIL | falsified |
| **CC-1** (china_sector_cycles) | cone coverage ≈ 0.80 (calibration, report-only) | empirical 0.359 vs 0.80, CI [0.33, 0.39] | MISCALIBRATED | too_tight |
| **CC-2** (china_sector_cycles/signal) | Brier skill vs base rate > 0, n≥30 | skill -1.159, hit 0.460 vs base 0.507, n 1677 | FAIL | falsified |
| **CC-2** (china_sector_cycles/stance) | Brier skill vs base rate > 0, n≥30 | skill —, hit — vs base —, n 0 | FAIL | None |

## Cone recalibration multipliers (ships to cone_recalibration.json)

The recalibration half-width = `quantile(|timing_err|, 0.80)` from the realized turn-timing distribution. This **replaces** the `lerp(1.5,13)` / `tilt(1.35,0.7)` hand constants (audit cycle-flagship-4).

| Engine | Headline mult (×) | Forward-only mult (×) | Interpretation |
|---|---|---|---|
| sector_cycles | 8.191 | 7.657 | cones far too tight |
| country_cycles | 3.567 | 3.291 | cones far too tight |
| china_sector_cycles | 3.118 | 2.949 | cones far too tight |

## Honest reading of the numbers

- **Turn precision is low and cone coverage is far below 0.80.** This is not a grader bug — it is the measurement doing its job. The dominant cause (surfaced by the `overdue_fraction` column) is that a large majority of stamped projections are **chronically overdue**: their `proj_central` points at a turn date in the PAST relative to the stamp. This is exactly the re-anchoring / `find_troughs` repaint the audit flagged (cycles-core-4).
- **The forward-only cone slice** isolates the cone's own calibration from the overdue-projection pathology; it is the number to watch once the projection engine is fixed downstream (D5).
- **Reliability skill is negative** for the directional labels vs the instrument base rate over 63d — the labels do not, on this backfill, beat an always-predict-the-majority-direction coin. Reported honestly, not hidden.
- **LIVE cohort** is small and prospective; its cells stay `ACCRUING` until n_eff≥40. Badge discipline (A6/A1): a BACKTEST number never promotes a user-facing MEASURED badge — only a matured LIVE cohort can.

_Artifacts: `data/<engine>/scorecards/promises_<epoch>.json`, `data/cycle_ontology/cone_recalibration.json`._

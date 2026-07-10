# Backtest Results V1 — NFP Revision-Direction Model (Track R)

**Run date:** 2026-07-10
**Spec:** research/release_forecast/PREREG_NFP_REVISION_V1.md (frozen before run)
**Target basis:** TRUE first→third revision (ALFRED output_type=2)
**Algorithm:** Ridge(λ=1.0, numpy closed-form), expanding window, MIN_TRAIN_OBS=60
**Kill rule:** Walk-forward hit-rate Wilson LB must exceed majority-class base rate (full non-covid window); non-directional steps (|y_hat| < 0.1) excluded

---

## Summary

| Item | Value |
|------|-------|
| Records available | 353 |
| Walk-forward steps | 291 |
| Target basis | first_to_third |
| Kill verdict | **KILL** |
| Hit rate (full non-covid) | 0.569 |
| Wilson 95% LB | 0.506 |
| Majority base rate | 0.547 |
| n directional steps | 239 |

---

## Kill Rule Detail

**Kill TRIGGERED** (model suppressed — lean='none'):

- Wilson LB: 0.5057
- Majority base rate: 0.547
- Kill condition (Wilson LB <= majority base rate): True

---

## Era-Split Results

Directional only (steps where |y_hat| >= strength_threshold); majority base rate = max(n_up, n_down) / n_total in each era.

| Era | n_dir | n_hits | Hit Rate | Wilson 95% CI | Majority Base Rate | FP-Baseline HR |
|-----|-------|--------|----------|---------------|--------------------|----------------|
| pre_2010 | 74 | 39 | 0.527 | [0.415, 0.637] | 0.516 | 0.474 |
| 2010_2020 | 108 | 61 | 0.565 | [0.471, 0.654] | 0.615 | 0.451 |
| covid | 3 | 2 | 0.667 | [0.208, 0.939] | 0.750 | 0.750 |
| 2020_recovery | 5 | 4 | 0.800 | [0.376, 0.964] | 0.667 | 0.333 |
| 2021_plus | 52 | 32 | 0.615 | [0.480, 0.735] | 0.547 | 0.484 |
| full_non_covid | 239 | 136 | 0.569 | [0.506, 0.630] | 0.547 | 0.463 |

**Note:** Pre-2010 directional n=74 (model has ≥60 training rows available before 2010 given data starting ~1997).
COVID rows (2020-03..2020-06) are excluded from the kill-rule evaluation per PREREG §3.2.
n_directional in the kill-rule evaluation (239) equals the full_non_covid directional count in the era table — any difference between this and prior runs reflects the PIT-compliance fix (look-ahead-corrected training windows can raise or lower the directional call rate at certain folds).

---

## Feature Presence

| Feature | n_present | pct_present |
|---------|-----------|-------------|
| fp_surprise_vs_AR1 | 353 | 100.0% |
| sin_month | 353 | 100.0% |
| cos_month | 353 | 100.0% |
| icsa_4m_survey_week_change | 198 | 56.1% |

---

## Provenance

- **Basis:** first_to_third
- **Multi-vintage store:** data/fred_vintage/payems_all_vintages.parquet (output_type=2)
- **Fallback store:** data/fred_vintage/vintages.parquet (output_type=4)
- **display_only:** true
- **authority:** false

---

## Interpretation

The kill rule is TRIGGERED. Per PREREG_NFP_REVISION_V1.md §4: walk-forward hit-rate Wilson LB does not exceed the majority-class base rate in the full non-covid window. The `revision_lean` field will display 'none' (suppressed). Attempt #1 of 2 is exhausted under this kill condition. A second attempt may be registered under program-level adjudication (per PREREG_NFP_REVISION_V1.md §12.3).

The LEVEL-bias annotation (expansions +216k / contractions -262k cumulative level revision) is a SEPARATE display field — descriptive, no model, always displayed regardless of kill outcome. MoM-change bias is NOT significant and must not be implied.

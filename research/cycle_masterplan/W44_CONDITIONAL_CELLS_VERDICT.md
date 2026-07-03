# W4.4 Conditional Cells Verdict
## Phase × Quad Forward-Return Cells — James-Stein Shrinkage, Month-Block Bootstrap

**Wave:** W4.4  
**Date:** 2026-07-03  
**Builder:** `scripts/build_conditional_cells.py`  
**Artifact:** `data/cycle_ontology/conditional_cells_20260703.json`  
**Ruling scope:** A2 (no n/h Wilson path), A7 (research surface only), P-D5-1 (revision-optimistic)

---

## 0. In plain English

We split 25 years of monthly cycle data into 60 cells (5 phases × 4 quads × 3 families) and asked: for each cell, do the 63-day and 126-day forward returns — and the vol-residualized max-drawdowns — differ from the phase average with a confidence interval that excludes zero?

**Finding:** 39 of 240 cell×outcome×horizon combinations (across 60 cells × 4 outcome-horizon pairs) show CIs excluding the phase-pooled baseline. The most prominent winner is `cn_sector | Peak | Q1 | 63d`: shrunk return +14.3%, CI [+7.3%, +19.3%], n_months=46. However, **all quad-conditioned cells carry `revision_optimistic=True`** because the quad labels come from revised macro data (no ALFRED vintages — P-D5-1). The apparent edge may shrink or reverse under PIT-correct quad labeling.

**Ruling A7 verdict:** these cells ship as a research surface on `measurement.html` only. The DL-2 gate (walk-forward conviction backtest) has not been run. No tilt into `sector_central` or any trading card is wired.

---

## 1. Methodology

### 1.1 Phase derivation
`phase_v2` is derived from `pos_osc` (the canonical position oscillator) and `direction` (the leg direction from the hazard panel) using `ZONE_EHI=68` and `ZONE_ELO=32` from `engine/cycle_ontology.py`:

| pos_osc | direction | phase_v2 |
|---------|-----------|----------|
| ≥ 68    | up        | Peak     |
| ≥ 68    | down      | Downturn |
| ≤ 32    | up        | Recovery |
| ≤ 32    | down      | Trough   |
| middle  | up        | Expansion|
| middle  | down      | Downturn |

MTF MACD votes are not available in the monthly panel; `direction` is the causal substitute, consistent with the D1 ontology. This is a simplification relative to the full `classify_phase()` function but PIT-pure.

### 1.2 Forward returns
63-day and 126-day forward log-returns computed from daily dividend-adjusted closes (`data/yahoo/*.parquet`, `data/china_sectors/*.parquet`). Resampled to month-end. Panel: 18,619 rows → 18,342 with non-null 63d return, 18,123 with non-null 126d return.

### 1.3 Vol-residualized max-DD (rdd)
Per W4.6 metric definition: `rdd = fwd_maxdd / trailing_63d_vol`. The raw max-DD is the worst close-to-close drawdown over the forward window (≤0). Trailing 63-day annualized realized vol clamped to ≥0.01 to prevent division by near-zero on illiquid series.

### 1.4 James-Stein shrinkage (D5 §2.2)
Shrinkage toward the phase-pooled mean (pooling over quads within each family×phase):
```
m_pooled = weighted mean by n_eff
tau2     = max(0, Var_c(m_c) - mean_c(s2_c / n_eff_c))   # between-cell variance
w_c      = tau2 / (tau2 + s2_c / n_eff_c)                  # shrink weight
shrunk   = w_c * m_c + (1 - w_c) * m_pooled
```
`n_eff = n_raw / h` (where h=3 for 63d, h=6 for 126d) is used **ONLY** for the shrinkage weight denominator. It is never used as a Wilson CI input (ruling A2).

Cells with `n_eff < 3.0` (floor) receive `w_c = 0` (full shrinkage to pooled).

### 1.5 Block-bootstrap CI (ruling A2)
All CIs are 95% intervals on the gap (cell mean − pooled mean) from `engine.grading_stats.block_bootstrap_ci` (800 draws, seed=7). This function resamples whole month-end **dates** so that cross-sectionally correlated rows on the same date move together. No Wilson CI path on n_eff exists anywhere in the code (grep-tested; see `tests/test_conditional_cells.py::test_no_wilson_on_neff_in_builder`).

### 1.6 Collapse discipline
Cells with `n_months < 12` → `collapsed=True`, `shrunk_mean = phase_pooled_mean`, `shrink_weight = 0`. In this dataset all 60 cells have ≥12 months (minimum n_months=14 for `us_sector|Downturn|Q3`). No cells collapsed.

---

## 2. Results by outcome × horizon

### 2.1 Forward return, 63d — 7/60 cells with CI excluding pooled mean

| Family | Phase | Quad | n_months | Shrunk mean | CI 95% | Direction |
|--------|-------|------|----------|-------------|--------|-----------|
| country | Trough | Q2 | 79 | +4.4% | [+0.3%, +5.9%] | above pooled |
| country | Expansion | Q3 | 40 | −0.3% | [−6.0%, −0.1%] | below pooled |
| country | Peak | Q4 | 53 | +3.3% | [+0.1%, +4.5%] | above pooled |
| cn_sector | Expansion | Q4 | 54 | −1.9% | [−6.3%, −1.2%] | below pooled |
| **cn_sector** | **Peak** | **Q1** | **46** | **+14.3%** | **[+7.3%, +19.3%]** | **above pooled** |
| cn_sector | Peak | Q2 | 82 | +5.1% | [+0.2%, +7.6%] | above pooled |
| cn_sector | Downturn | Q1 | 41 | −4.3% | [−14.9%, −0.5%] | below pooled |

All 7 cells: `revision_optimistic=True`.

### 2.2 Forward return, 126d — 11/60 cells with CI excluding pooled mean

Winners include `cn_sector|Peak|Q1` (shrunk +22.0%, CI [+8.9%, +34.7%]), `country|Peak|Q1` (shrunk +5.9%, CI [+1.1%, +6.7%]), and `country|Recovery|Q4` (shrunk +8.3%, CI [+1.1%, +9.5%]).

Notable: `us_sector|Recovery|Q1` (shrunk +3.1%, CI [−7.5%, −0.2%]) — shrunk mean is above pooled but CI is negative; this means the *gap* is below zero (the cell's returns are below the phase average) even after heavy shrinkage toward the positive pooled mean.

### 2.3 Vol-residualized max-DD, 63d — 10/60 cells with CI excluding pooled mean

rdd values are negative (drawdown). A positive CI gap = shallower drawdown than phase average. A negative CI gap = deeper drawdown than average.

Notable: `cn_sector|Trough|Q1` (rdd CI [−0.25, −0.06]) = meaningfully deeper drawdown than the Trough phase average when Q1 (Goldilocks). This is consistent with the hazard model finding that the trough hazard is not monotone in regime.

### 2.4 Vol-residualized max-DD, 126d — 11/60 cells with CI excluding pooled mean

`country|Expansion|Q3` shows a notably negative CI [−0.44, −0.05] = deeper drawdown at 126d in Expansion phase when Q3 (Stagflation). This is consistent with cross-asset logic.

---

## 3. Revision-optimistic caveat (P-D5-1)

**Every quad-conditioned cell is marked `revision_optimistic=True`.**

`regime_history.parquet` is built from revised macro series (`payrolls_trend`, `indpro_trend`) with no ALFRED vintages. At the time each observation was made in real time, the growth and inflation axes might have been classified differently. The quad assignments are therefore "hindsight" in the sense of using the most recent vintage of the data.

**Practical consequence:** the apparent edge in cells like `cn_sector|Peak|Q1` (fwd_ret +14% above pooled, CI [+7.3%, +19.3%]) should be understood as "this edge if you had known the correct quad in advance." The real-time edge is likely smaller and has not been measured.

This verdict does not attempt to correct for this; it discloses it. The correction belongs to the macro-regime pillar when ALFRED vintages become available.

---

## 4. DL-2 gate evaluation (pre-registered criterion)

From `PREREGISTRATION.md §6`:

> **DL-2**: the fitted `tilt_config.json` tilt improves sector_central walk-forward drawdown-adjusted conviction ordering vs the flat map, CI excluding 0.

**Status: NOT RUN.**

This wave (W4.4) delivers the cell estimates and their CIs on the backfill panel. The DL-2 gate requires a forward walk-forward conviction backtest — a separate wave not implemented here. Per ruling A7, this is the correct sequencing: produce the estimates first (research surface), run the decision-linkage test second before wiring any tilt.

**Prerequisite check:** the 7 cells with CI excluding zero in fwd_ret/63d are the candidates for a potential tilt map. The criterion requires that a tilt derived from these cells improves walk-forward drawdown-adjusted conviction ordering out-of-sample. Given the revision_optimistic caveat, this bar is likely to be difficult to clear.

---

## 5. Honest summary

| Criterion | Result |
|-----------|--------|
| Any cells with CI excluding pooled mean? | YES — 39 of 240 cell×outcome×horizon combos |
| Any cells without revision_optimistic caveat? | NO — all quad cells marked revision_optimistic |
| Collapse discipline maintained (n_months < 12 → collapsed)? | YES — no cells triggered (all ≥12 months) |
| Wilson CI on n_eff used anywhere? | NO — grep test confirms zero uses |
| DL-2 gate passed? | NO — not run; research surface only |
| Tilt wired into sector_central? | NO — ruling A7 prohibits until DL-2 passes |

**The honest verdict:** there ARE cells with non-zero gaps relative to the phase pooled mean, concentrated in China sectors at the Peak phase in Goldilocks (Q1) regime. But the revision-optimistic label is load-bearing — these results are built on quad labels that may differ from what was knowable in real time. The research surface displays these estimates with the caveat prominent.

---

## 6. Artifact provenance

- **Input panel:** `data/hazard/panel_price_c4414dcb.parquet` (18,619 rows, 73 instruments, 359 months)
- **Price data:** `data/yahoo/*.parquet` (TR adjusted close, US+country), `data/china_sectors/*.parquet` (CN)
- **Bootstrap:** 800 draws, seed=7, date-blocked (ruling A2)
- **Output artifact:** `data/cycle_ontology/conditional_cells_20260703.json`
- **Tests:** `tests/test_conditional_cells.py` (21 tests, all passing)
- **Measurement surface:** `site/measurement.html` §"Conditional Forward-Return Cells" (collapsible, research-only label)

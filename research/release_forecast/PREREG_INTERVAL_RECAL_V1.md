# Pre-Registration — MRI-R30 Interval Recalibration V1 (Vol-Scaled Residual Quantiles)

**Frozen:** 2026-07-10  
**Program:** Macro Release Intelligence (MRI), W11-F  
**Branch:** claude/mri-w11-interval-recal  
**Ruling:** MRI-R30 (§12.1 of research/MACRO_RELEASE_INTEL_MASTERPLAN_BY_FABLE.md)  
**Status:** FROZEN — spec committed before any coverage tables are computed

---

## 0. Purpose and Anti-Mining Commitment

Coverage falsifier triggered (§6, [70%,95%] gate): cpi_core p10–p90 64.1% and pce_core 67.7% in
2021+ (bands regime-blind, audit F4). This document pre-registers the ONE §6-sanctioned
recalibration spec — vol-scaled residual quantiles — BEFORE any coverage re-computation is run.
No per-target tuning. No iteration. If coverage is still outside [70%,95%] after 12 more forward
prints, quantile claims drop from the UI (existing §6 rule).

---

## 1. Spec (frozen)

### 1.1 Trailing realized-error sigma

For each step i in the walk-forward sequence:

```
sigma_i = std(residuals[max(0, i-W) : i], ddof=1)
```

Where:
- **W = 24** (frozen; no tuning)
- `residuals[j]` = `actual[j] - predicted[j]` for walk-forward step j
- `std(..., ddof=1)` is the sample standard deviation (numpy)
- If the number of available trailing residuals is less than **MIN_SIGMA_OBS = 12**, fall back
  to the current behavior: full-history unscaled quantiles (no vol-scaling)

### 1.2 Standardized residuals

Each residual `r_i` is standardized by its OWN trailing sigma at its time (no lookahead):

```
r_std_i = r_i / sigma_i     (only when sigma_i > 0 and available)
```

Standardized residuals are accumulated across the walk-forward sequence.

### 1.3 Band computation

At projection time (after all walk-forward steps), current sigma is:

```
sigma_now = std(residuals[-W:], ddof=1)   (last W residuals available at projection time)
```

Quantiles of the standardized residuals:

```
q_std[p] = quantile(r_std_array, p)   for p in {0.10, 0.25, 0.50, 0.75, 0.90}
```

Bands (re-scaled by sigma_now):

```
band[p] = point + q_std[p] * sigma_now
```

Fallback (when fewer than MIN_QUANTILE_OBS = 24 standardized residuals are available, or when
sigma_now = 0): current behavior (full-history unscaled quantiles on raw residuals).

### 1.4 Parameters (all frozen; no post-results tuning)

| Parameter | Value | Notes |
|---|---|---|
| W | 24 | Rolling window for sigma_i and sigma_now |
| MIN_SIGMA_OBS | 12 | Min trailing residuals to compute sigma_i; else fall back |
| MIN_QUANTILE_OBS | 24 | Min standardized residuals for quantile (unchanged) |

### 1.5 Application scope

ONE spec applied UNIFORMLY to every target — cpi_headline, cpi_core, nfp, pce_headline,
pce_core, ppi_finaldemand, and all challengers (v3_factor, mf_energy). The same
`_compute_quantiles_volscaled` function is called from:

- `engine/release_forecast.py` — `_compute_quantiles` (champion CPI and NFP)
- `engine/release_targets_v11.py` — direct call at quantile line
- `engine/release_forecast_v3.py` — via `compute_quantiles_fn` parameter
- `engine/release_mf_energy.py` — replaces `_compute_quantiles_mf`

The old `_compute_quantiles` signature (residuals, point, min_obs) is preserved as a
fallback-only path and remains callable for backward compatibility in tests.

### 1.6 Point identity requirement (§ spec)

POINTS ARE BYTE-IDENTICAL. The vol-scaling affects only the quantile bands (p10, p25, p50,
p75, p90). The model point estimate and all baseline values are completely unchanged.

---

## 2. No-lookahead guarantee

The sigma used to standardize residual at step i is computed from residuals strictly
BEFORE step i (indices 0 to i-1, at most W of them). sigma_now uses the residuals that
have accumulated UP TO the current projection step. No future residuals are used.

This is verified by the test suite (see tests/test_release_interval_recal.py).

---

## 3. Fallback conditions

The function returns full-history unscaled quantiles (current behavior) when:
1. Trailing residuals < MIN_SIGMA_OBS (not enough to estimate sigma_i reliably)
2. sigma_i == 0 for a given step (rare; treated as "step excluded from standardization")
3. Accumulated standardized residuals < MIN_QUANTILE_OBS (not enough for quantile)
4. sigma_now == 0 at projection time (degenerate; treated as fallback)

In all fallback cases, the band is computed on raw residuals identically to the pre-recal code.

---

## 4. Coverage reporting

After implementation, coverage tables are regenerated for all four engines:
- `research/release_forecast/RESULTS_V2.md` (cpi_headline, cpi_core)
- `research/release_forecast/RESULTS_NEW_TARGETS_V1.md` (pce_headline, pce_core, ppi_finaldemand)
- `research/release_forecast/RESULTS_V3_FACTOR.md` (v3_factor challenger)
- `research/release_forecast/RESULTS_MF_ENERGY_V1.md` (mf_energy)

Each results file gains a "MRI-R30 recalibration (2026-07-10)" section with:
- Per-era p10-p90 and p25-p75 coverage BEFORE vs AFTER
- Pinball loss before and after
- Honest report if coverage does not improve

---

## 5. Kill criteria (from §6, unchanged)

If coverage p10–p90 is still outside [70%, 95%] after 12 more forward prints per target,
quantile claims drop from the UI for that target. This is not a re-spec — it is the existing
§6 consequential rule. There is no attempt 2 for this recalibration.

# PREREG — combined_point v1 (forecast-combination layer, MRI-R40)

**Frozen:** 2026-07-14
**Attempt:** #1 of 1 for this construction (no re-tuning of the weight formula after results; a
different combination construction would require a new prereg).
**Charter:** research/MACRO_RELEASE_INTEL_MASTERPLAN_BY_FABLE.md Amendment 2026-07-14 (MRI-R40).
**Model id:** `combined_v1`

---

## 1. Motivation

Post-mortem of the June-2026 CPI print (defect_notices.json DN-001/DN-002; PR #2574):
the system carried five point estimates into the print (champion +0.0818, v3_factor +0.143,
cpi_bridge +0.028, mf_energy −0.206, Cleveland −0.061 vs actual −0.4) with no mechanism for
them to add up. The masterplan §7 graduation endpoint grants a badge and never changes the
displayed number; the only promotion concept was champion replacement. This prereg charters
the missing layer: a pre-registered forecast combination whose output becomes the DISPLAYED
point. Forecast combination under model uncertainty is the standard robust choice; equal
weights are the hard-to-beat baseline, so the weighting scheme below stays deliberately
simple and shrinks toward the pool.

Authority is unchanged: `display_only=true`, all authority booleans false. Inputs to a model
do not need gauntlets; outputs and authority do (input-tier doctrine, MRI-R40).

## 2. Model specification (frozen)

### 2.1 Scope

Releases: `cpi_headline`, `cpi_core`. Extension to other releases requires an amendment that
changes NOTHING in §2.2–§2.4 (release list only); any formula change = new prereg.

### 2.2 Inputs (per release, per asof night; only non-null values participate)

| Input id | Source (same-night, PIT) |
|----------|--------------------------|
| `champion` | v1 authority `projection` row `projection_point` |
| `v3_factor` | shadow row `projection_point` |
| `cpi_bridge` | shadow row `projection_point` (cpi_headline only) |
| `mf_energy` | shadow row `projection_point` (cpi_headline only) |
| `cleveland` | data/cleveland_nowcast/nowcast.parquet, series `cpi_mom` / `core_cpi_mom`, target_period == release period, latest row with `first_seen_asof` <= asof (PIT via vintage column) |

Minimum 2 non-null inputs, else `combined_point = null` for that night (display falls back to
champion). No other inputs may be added without a new prereg.

### 2.3 Weights — shrunk inverse-MAE on forward scored rows ONLY

For release r and input i, using ONLY scored forward-ledger rows for r (no backtest rows,
MRI-R8; each input's error is `actual − frozen input point`; the cleveland error uses the
frozen `benchmark_cleveland` on the champion's scored row):

```
MAE_shrunk_i = ( sum_over_scored |e_i| + k * MAE_pool ) / ( n_i + k ),   k = 3 (frozen)
MAE_pool     = pooled MAE over ALL inputs' scored errors for release r
w_i          = (1 / MAE_shrunk_i) / sum_j (1 / MAE_shrunk_j)
```

Cold start: if release r has zero scored errors across all inputs, all `MAE_shrunk_i` are
undefined → equal weights `w_i = 1/N`. An input with `n_i = 0` while others have history
receives `MAE_shrunk_i = MAE_pool` (pure prior) automatically.

```
combined_point = sum_i w_i * point_i
```

### 2.4 Interval — dispersion-aware (NEW construction)

```
Var_w          = sum_i w_i * (point_i − combined_point)^2
sigma_combined = sqrt( sigma_champion^2 + Var_w )      # sigma_champion = champion sigma_scale_pp
p10/p90 = combined_point ∓/± 1.2816 * sigma_combined
p25/p75 = combined_point ∓/± 0.6745 * sigma_combined
p50     = combined_point
```

This is a distinct construction from the champion's vol-scaled empirical quantiles and from
the executed one-shot interval recalibration (PREREG_INTERVAL_RECAL_V1, W11-F #2151); neither
is modified, re-run, or re-tuned by this prereg. Cross-model dispersion enters ONLY here.

## 3. PIT / provenance

- All input points are the same asof-night's ledger rows (frozen before the print).
- Cleveland input filtered by `first_seen_asof <= asof` (vintage-tracked store).
- Weights use only rows already scored as of the asof night (strictly past prints).
- No LLM involvement anywhere (pure arithmetic; LLM law trivially satisfied).

## 4. Output contract

1. Nightly ledger row: `row_type = "shadow_projection"`, `model = "combined_v1"`,
   `display_only = true`, `authority = false`, with `combined_components` dict:
   inputs used, each point, each weight, each `n_i`, each `MAE_shrunk_i`, `MAE_pool`,
   `sigma_champion`, `Var_w`. Scored by the standard shadow scoring path.
2. `latest.json` / `site/macrodata/release_forecast.json` gain a `combined` block per
   release (point, quantiles, inputs+weights receipt, n_scored basis).
3. Display: the release card's headline point sources the `combined` block when non-null,
   falling back to the champion point. Champion + all inputs demoted to the hover/receipt
   breakdown. Glance-tier copy uses plain words ("blend of N models" / 「N模型混合」);
   the word "consensus/共识" remains banned from all card strings (MRI-R5).
   Authority booleans and all disclosure lines unchanged.

## 5. Forward gates (pre-registered; forward ledger is the sole judge)

- **Success badge:** at n ≥ 12 scored prints for a release, MAE_combined ≤ MAE_champion.
- **Kill (construction-specific):** at n ≥ 24, MAE_combined > MAE_champion AND
  MAE_combined > min_i MAE_i → display reverts to champion point; row emission continues
  (accrual is never blocked); DO_NOT_REBUILD row appended for THIS construction only.
- **Promotion-review ticket:** at n ≥ 12, if any single input's MAE < MAE_combined, the
  scoreboard emits a `promotion_review` entry naming the input — a mandatory adjudication
  trigger, not an automatic change.
- **Interval honesty:** p10–p90 coverage outside [70%, 95%] at n ≥ 12 → coverage printed
  on the card (null-printed, not hidden); no re-tuning (attempt #1 of 1).

### 2.5 Clarification (2026-07-14, pre-accrual — resolves cases §2.4 left unspecified)

If `sigma_champion` is unavailable on a night (champion row missing `sigma_scale_pp`), it is
treated as 0 and the interval is dispersion-only (`sigma_combined = sqrt(Var_w)`); the receipt
records `sigma_champion = null`. This clarifies pre-registered silence; it does not alter any
formula. Recorded before the first combined row accrued to the forward ledger.

## 6. Anti-mining

k = 3 frozen; input list frozen (§2.2); normal-quantile multipliers frozen; no alternative
weighting schemes will be evaluated retroactively against the same forward window. Any
change = new prereg with a fresh forward window.

## 7. What is NOT changed

- Champion v1 model, its features, its quantiles: unchanged.
- Shadow models and their scoring: unchanged.
- Authority booleans: all false everywhere, unchanged.
- PREREG_INTERVAL_RECAL_V1 (one-shot, executed): untouched.
- Forward ledger schema for existing row types: unchanged (additive row model id only).

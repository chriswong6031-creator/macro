# Pre-Registration — CPI Component Bridge V1 (Track CB)

**Frozen:** 2026-07-08
**Program:** Macro Release Intelligence (MRI), Wave 10, Track CB
**Ruling:** MRI-R25 (component-bridge challenger charter)
**Branch:** claude/mri-w10-track-cb
**Status:** FROZEN — no model spec, block, weight, or method changes after this commit

---

## 0. Purpose and Anti-Mining Commitment

This document pre-registers the EXACT model specification for the BLS relative-importance CPI
component bridge BEFORE any backtest results are observed. Per MRI §6 anti-mining law: exactly
ONE spec is declared here and frozen. No block weighting, feature selection, or method iteration
after results are seen. Kill-rule verdict is printed regardless of direction.

This is the SECOND CHALLENGER (Track CB, parallel to Track M). The champion (frozen v2 ridge)
keeps the card; Track CB enters as a shadow-eligible challenger only.

---

## 1. Model Class

**Component bridge (not a regression).** Each block computes a MoM estimate from its PIT-safe
proxy series, multiplied by the BLS Dec-2025 relative-importance weight → contribution in
percentage-points. Headline estimate = sum of contributions + residual. The residual is the
unmodelled basket share (prior-only blocks at their prior MoM × their RI weight) — it is PRINTED,
never hidden (MRI-R19 / MRI-R25).

No sklearn, statsmodels, or scipy.stats. Pure numpy/pandas.

---

## 2. BLS Relative-Importance Weights (Dec-2025 basis, in effect Jan–Dec 2026)

Source: https://www.bls.gov/cpi/tables/relative-importance/2025.htm  
Basis: December 2025 (Table 1, 2024 expenditure weights), CPI-U U.S. City Average  
PIT rule: weights are FROZEN for the calendar year (January 2026 – December 2026); refresh each
January. Weights are not ALFRED-vintaged — treat as revision_optimistic for the weight leg.

All-items = 100.000 (denominator). Component weights listed in
`data/release_forecast/component_weights/cpi_relative_importance_2026.yml`.

---

## 3. Blocks and Per-Block MoM Method (frozen per MRI-R25)

### 3.1 Block 1 — Energy (modelled, confidence = 1.0)

**RI weight (CPI-U):**
- Gasoline (all types): 2.895
- Electricity (APU000072610): derived from Housing→Fuels and utilities→Electricity sub-item

**Gasoline sub-block:**
- Source: `data/fred/GASREGW.parquet` (weekly EIA price, unrevised)
- Method: reference-month average vs prior-month average MoM % (identical to champion gasoline_mom)
  - PIT: asof determines what weeks are knowable for the reference month M
  - `ref_month_avg = mean(GASREGW where date in [M_start, M_end ∩ asof])`
  - `prior_month_avg = mean(GASREGW where date in [M-1_start, M-1_end])`
  - `gasoline_mom = (ref_month_avg / prior_month_avg - 1) × 100`
- Declared `unrevised_legs` (administrative survey, unrevised in practice)

**Electricity sub-block:**
- Source: `data/fred/APU000072610.parquet` (BLS average electricity price, monthly, 1978-11+)
- Method: month-over-month % change of the most recent knowable print (non-vintaged → revision_optimistic)
  - PIT: electricity releases with the CPI; at decision date (day before target release), the last
    knowable electricity value is for month M-1 (same lag as shelter)
  - `elec_mom = (elec[M-1] / elec[M-2] - 1) × 100`
- Declared `revision_optimistic_legs`

**Energy contribution:** `(gasoline_mom × gasoline_weight + elec_mom × elec_weight) / (gasoline_weight + elec_weight) × energy_total_weight / 100`

More precisely:
```
energy_contribution_pp = (gasoline_mom/100) × gasoline_weight + (elec_mom/100) × elec_weight
```

### 3.2 Block 2 — Shelter (modelled, confidence = 0.6)

**RI weight (CPI-U):**
- Rent of primary residence: 7.840
- Owners' equivalent rent (OER): 26.204
- Total shelter: 35.625 (also includes lodging away from home: 1.289; OER + rent of primary = 34.044)

**Method:** existing `_compute_shelter_nowcast` from `engine/release_components_cpi.py`
(PREREG_V2.md §2, frozen k=0.35, ZORI lease-reset window M-12..M-6, divergence guard).
- PIT: ZORI +45-day lag; CPI shelter knowable through M-1 at decision date
- Sources: `data/zori/national.parquet` + `data/fred/CUSR0000SAH1.parquet`
- Declared `revision_optimistic_legs` (CUSR0000SAH1 not ALFRED-vintaged)

**Contribution:**
```
shelter_contribution_pp = (shelter_nowcast/100) × shelter_weight
```
where `shelter_weight = 35.625` (full shelter basket).

### 3.3 Block 3 — Food at Home (modelled, confidence = 0.4)

**RI weight:** 8.325

**Method:** PPI farm products (WPU01) as directional momentum signal applied to CUSR0000SAF11
prior MoM:
1. Compute `wpu01_mom` = WPU01 MoM % for most-recent PIT-knowable month (non-vintaged)
2. Compute `fah_prior_mom` = most-recent knowable CUSR0000SAF11 MoM %
3. Bridge estimate: blend prior with momentum signal
   - `sign_signal = sign(wpu01_mom)` if `abs(wpu01_mom) > 1.0`, else 0.0 (directional threshold)
   - `fah_mom_est = fah_prior_mom + 0.2 × sign_signal × abs(fah_prior_mom)`
   - Clamped to `max(fah_prior_mom × 0.5, min(fah_prior_mom × 1.5, fah_mom_est))`
   - If either source is missing, falls back to `fah_prior_mom` (pure prior)
   - If both missing, block falls to `prior_only = True`
- PIT: WPU01 releases typically 1-2 weeks before CPI; CUSR0000SAF11 is non-vintaged (revision_optimistic)
- Sources: `data/fred/WPU01.parquet` + `data/fred/CUSR0000SAF11.parquet`
- Declared `revision_optimistic_legs` for both series

**Contribution:**
```
food_at_home_contribution_pp = (fah_mom_est/100) × food_at_home_weight
```

**Confidence:** 0.4 (directional proxy — weaker than energy/shelter).

### 3.4 Block 4 — Core Goods Pipeline (modelled, confidence = 0.6)

**RI weight target:** "Commodities less food and energy" = 19.176 (covers new vehicles, used
vehicles, apparel, medical commodities, other core goods).

**Method:** PPIFIS (PPI Final Demand) and PPIFES (PPI Final Demand ex-food and energy)
momentum as in the champion pipeline leg.
- Source: vintages (`data/fred_vintage/vintages.parquet`) via `knowable_series`
- `ppifis_mom` = lag-1 MoM of PPIFIS (ALFRED-vintaged, PIT-safe)
- `ppifes_mom` = lag-1 MoM of PPIFES (ALFRED-vintaged, PIT-safe)
- Bridge estimate: `pipeline_mom_est = 0.5 × ppifis_mom + 0.5 × ppifes_mom` (equal weight)
  - If one missing, use the other; if both missing, block falls to prior_only

**Contribution:**
```
core_goods_contribution_pp = (pipeline_mom_est/100) × core_goods_weight
```

**Confidence:** 0.6 (ALFRED-vintaged proxy).

### 3.5 Block 5 — Core Services ex-Shelter (modelled, confidence = 0.4)

**RI weight target:** CUSR0000SASLE is "All items less energy, shelter, and food". Its RI
complement is derived as:
- `csxs_weight` ≈ All items less food and energy (79.919) − shelter (35.625) = 44.294
- However, core-services-ex-shelter is better scoped to services only, not including core goods.
- Use the BLS "Other services" aggregate: 9.845 (this is services less rent of shelter less
  transportation services; the broadest available services-ex-shelter-ex-medical aggregate)
- Note: CUSR0000SASLE tracks "All items less food, energy, shelter" (commodities + services),
  so RI weight is approximated as 44.294 (full complement) for the bridge estimate.
- Gap: this weight DOUBLE-COUNTS core goods. The bridge is conservative here — core-goods
  and core-services-ex-shelter are modelled with overlapping weights. The residual reconciles.

**Method:** Persistence — CUSR0000SASLE lag-1 MoM applied as estimate for upcoming month.
- Source: `data/fred/CUSR0000SASLE.parquet` (non-vintaged, revision_optimistic)
- `csxs_prior_mom` = most-recent knowable CUSR0000SASLE MoM %
- `csxs_mom_est = csxs_prior_mom` (pure persistence; confidence reflects this is weak)
- PIT: CUSR0000SASLE releases with CPI; last knowable = M-1

**Contribution:**
```
csxs_contribution_pp = (csxs_mom_est/100) × csxs_weight
```

**Confidence:** 0.4 (persistence-only, no forward proxy; series not ALFRED-vintaged).

---

## 4. Prior-Only Blocks (confidence = 0.0 per MRI-R25)

All blocks not modelled above → prior MoM × RI weight, confidence = 0.0, no proxy.
No free PIT proxy exists for these; modelling them would be false precision.

| Block | RI Weight (CPI-U) | Prior Series | Reason |
|---|---|---|---|
| Food away from home | 5.373 | Prior MoM | No free scanner/restaurant data |
| Alcoholic beverages | 0.840 | Prior MoM | No free PIT proxy |
| New vehicles | 3.838 | Prior MoM | Manheim auction is paid |
| Used vehicles | 2.759 | Prior MoM | Manheim is paid |
| Airline fares | 0.881 | Prior MoM | No free RT booking data |
| Lodging away from home | 1.289 | Prior MoM | STR data is paid |
| Medical care | 8.423 | Prior MoM | No free monthly proxy |
| Apparel | 2.368 | Prior MoM | No free RT proxy |
| Recreation | 5.137 | Prior MoM | No free RT proxy |
| Education & communication | 5.846 | Prior MoM | No free RT proxy |
| Other goods & services | 2.902 | Prior MoM | No free RT proxy |
| Motor vehicle insurance | 2.754 | Prior MoM | No free proxy |
| Other transportation | remaining | Prior MoM | No free proxy |

---

## 5. Bridge Math (frozen per MRI-R19 / MRI-R25)

```
headline_est = Σ_i contribution_pp[i]    (ALL blocks, modelled and prior)
residual = 0  (by construction when all blocks included)
```

For reconciliation tracking purposes:
```
modelled_sum = Σ_i contribution_pp[i] where block.prior_only == False
prior_sum = Σ_i contribution_pp[i] where block.prior_only == True
headline_est = modelled_sum + prior_sum
```

The "residual" reported in provenance is the difference caused by floating-point precision:
```
residual = headline_est - (modelled_sum + prior_sum)  # should be ≈ 0 within 1e-10
```

Core estimate uses the same blocks but excludes energy components (gasoline, electricity).
Weight reconciliation: Σ all block weights must equal approximately 100.0.

**weight_coverage** = sum of RI weights for modelled blocks / 100.0

---

## 6. Output Schema

Returns a dict matching the champion's `release_forecast.v2` schema, tagged:
- `model = 'cpi_bridge'`
- `display_only = True`
- `authority = False`
- `components`: list of `{block, contribution_pp, weight, confidence, prior_only}`
- `weight_coverage`: share of the CPI basket backed by modelled legs (float, 0–1)
- `residual_pp`: reconciliation residual (should be ~0)
- `revision_optimistic_legs`: list of non-ALFRED-vintaged series used

---

## 7. Kill Rule (frozen per MRI §11.1)

Same as champion:
- Model MAE ≥ naive_prior MAE in BOTH the full window AND the 2021+ slice → NOT SHADOWED
- Era splits: full (all periods) and 2021+ (2021-01 onward)
- COVID months (2020-03..2020-06) excluded from era stats (same as champion)
- Max 2 spec attempts (this is attempt 1; second attempt requires new adjudication)
- Comparison baselines: naive_prior (last own-series MoM), trailing_3m (3-month mean), champion ridge

---

## 8. PIT Provenance Declarations

| Series | Vintaged | Declaration |
|---|---|---|
| GASREGW | No (administrative, unrevised) | unrevised_legs |
| APU000072610 | No | revision_optimistic_legs |
| CUSR0000SAH1 | No | revision_optimistic_legs |
| ZORI national | No (+45d lag applied) | revision_optimistic_legs |
| CUSR0000SAF11 | No | revision_optimistic_legs |
| WPU01 | No | revision_optimistic_legs |
| CUSR0000SASLE | No | revision_optimistic_legs |
| PPIFIS | Yes (ALFRED) | PIT-safe via knowable_series |
| PPIFES | Yes (ALFRED) | PIT-safe via knowable_series |
| CPIAUCSL | Yes (ALFRED) | PIT-safe (for prior MoM target baseline) |
| CPILFESL | Yes (ALFRED) | PIT-safe (for prior MoM core baseline) |

---

## 9. What This Is NOT

- Not a regression. No trained coefficients. Weights come from BLS, not from data fitting.
- Not scored or authority-bearing. display_only=True, authority=False enforced in engine.
- Not the champion. The champion (v2 ridge) keeps the card. This is a shadow challenger.
- Not iterated. No block/weight/method changes after results are observed (this freeze).

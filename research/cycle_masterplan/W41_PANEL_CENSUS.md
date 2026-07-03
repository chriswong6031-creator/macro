# W4.1 Panel Census

**Built:** 2026-07-03 13:19 UTC
**Panel epoch:** `tr_4d5643ac`
**Engine fingerprint:** `1f313352836b`

## Overall

| Item | Value |
|------|-------|
| Total rows | 18,526 |
| Date range | 1996-08-31 → 2026-05-31 |
| Instruments | 73 |
| Months | 358 |
| Events y1 | 7,496 |
| Events y3 | 10,107 |
| Events y6 | 12,395 |
| Censored rows | 786 |
| Censoring rate | 4.2% |

## Events per direction × family

| Family | Direction | Rows | Events (y1) | Events (y3) | Events (y6) | Censored | Cens. rate |
|--------|-----------|------|------------|------------|------------|----------|------------|
| us_sector | up | 2,603 | 574 | 807 | 1,083 | 135 | 5.2% |
| us_sector | down | 471 | 350 | 428 | 459 | 0 | 0.0% |
| country | up | 6,730 | 2,207 | 3,096 | 3,991 | 443 | 6.6% |
| country | down | 2,201 | 1,411 | 1,853 | 2,085 | 7 | 0.3% |
| cn_sector | up | 4,080 | 1,749 | 2,279 | 2,771 | 168 | 4.1% |
| cn_sector | down | 2,441 | 1,205 | 1,644 | 2,006 | 33 | 1.4% |

## Feature missingness

| Feature | Missing rows | Miss. rate |
|---------|-------------|------------|
| pos_osc | 32 | 0.2% |
| osc_slope | 48 | 0.3% |
| trend_pass | 0 | 0.0% |
| mom_score | 17 | 0.1% |
| rs_63d | 721 | 3.9% |
| vol_pctile | 0 | 0.0% |
| amp_proxy | 0 | 0.0% |
| log_age_ratio | 11 | 0.1% |
| quad | 0 | 0.0% |
| liquidity | 0 | 0.0% |

## KM baselines (age-only median survival)

*Ruling A14: family-stratified baseline — the skill bar W4.2 must beat.*

| Family | Direction | Rows | Events y1 | Median survival (months) | Median survival (bucket) |
|--------|-----------|------|-----------|--------------------------|--------------------------|
| us_sector | up | 2,603 | 574 | None | b2 |
| us_sector | down | 471 | 350 | 6 | b1 |
| country | up | 6,730 | 2,207 | 24 | b2 |
| country | down | 2,201 | 1,411 | 6 | b1 |
| cn_sector | up | 4,080 | 1,749 | 16 | b2 |
| cn_sector | down | 2,441 | 1,205 | 12 | b1 |

## rho_hat (within-month cross-sectional correlation)

*Ruling A2: W4.2 MUST use rho_hat for n_eff computation, not raw row counts.*

| Direction | rho_y1 | avg_k | n_months | Implied n_eff |
|-----------|--------|-------|----------|---------------|
| up | -0.0074 | 37.6 | 357 | 357 |
| down | -0.0176 | 15.4 | 333 | 333 |

## Effective months and n_eff by family

| Family+Dir | rho_y1 | avg_k | n_months | n_eff |
|------------|--------|-------|----------|-------|
| us_sector_up | -0.0273 | 8.2 | 316 | 316 |
| us_sector_down | -0.0672 | 2.5 | 187 | 187 |
| country_up | -0.0142 | 18.9 | 357 | 357 |
| country_down | -0.0363 | 7.8 | 282 | 282 |
| cn_sector_up | -0.0168 | 14.3 | 285 | 285 |
| cn_sector_down | -0.0243 | 9.9 | 246 | 246 |

## Power note

*What Brier-gap is detectable at 80% power given rho_hat and event counts?*

Using a simple simulation: generate 10,000 panel datasets of size matching the actual panel, with null model (KM prior as the prediction), and measure the standard deviation of the paired Brier difference across month-block bootstrap samples. The MDE is 2.8σ for 80% power (two-sided 90% CI = 1.645 z).

| Model | Direction | n_months | rho_y1 | n_eff | Base rate | σ_Brier | MDE (80% power) |
|-------|-----------|----------|--------|-------|-----------|---------|-----------------|
| pooled | up | 357 | -0.0074 | 357 | 0.3377 | 0.01674 | 0.04164 |
| pooled | down | 333 | -0.0176 | 333 | 0.5801 | 0.01888 | 0.04695 |

**Interpretation:** The MDE is the minimum Brier-gap at which a model trained on this panel would be detectable at 80% power with a 90% CI month-block bootstrap test. If the MDE > 0.01 (1% Brier gap), the panel is likely underpowered for detection of small true skill; most cells will ship as PRIOR initially (masterplan §6 risk #2 / R1). This is expected — the KM prior is itself a large upgrade over the re-anchoring projection.

## Blocs inclusion note (ruling A14)

Ruling A14 drops blocs from the HAZARD PANEL? **No — A14 drops blocs from the LEAD-LAG screen (Stage A).** The hazard panel includes all 31 country-family instruments matching the backfill IDs (including EFA/EEM/AAXJ/VGK/VPL/VXUS/ILF). Per D5_PREDICTION.md §1.3 note on Q.3: blocs are kept in the hazard panel but EXCLUDED from the lead-lag Stage A pairs screen (W5.1).

## Universe per family

**us_sector** (11 instruments):
XLB, XLC, XLE, XLF, XLI, XLK, XLP, XLRE, XLU, XLV, XLY

**country** (31 instruments):
AAXJ, ECH, EEM, EFA, EIDO, EPOL, EWA, EWC, EWD, EWG, EWH, EWI, EWJ, EWL, EWN, EWP, EWQ, EWS, EWT, EWU, EWW, EWY, EWZ, EZA, FXI, ILF, INDA, TUR, VGK, VPL, VXUS

**cn_sector** (31 instruments):
801010, 801030, 801040, 801050, 801080, 801110, 801120, 801130, 801140, 801150, 801160, 801170, 801180, 801200, 801210, 801230, 801710, 801720, 801730, 801740, 801750, 801760, 801770, 801780, 801790, 801880, 801890, 801950, 801960, 801970, 801980


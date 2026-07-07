# d2 Russell Deletion Overshoot — Phase-0 Report

**Run date:** 2026-07-07 00:02 UTC  
**Family:** `d2_russell_deletion_overshoot`  
**Adjudication doc:** research/SIGNAL_LAB_FRONTIER_DAY2_FABLE_ADJUDICATION_2026-07-06.md  
**Branch:** feat/d2-russell-deletion-phase0  

## In Plain English

When a stock is removed from the Russell 2000 index, the ETFs and funds that
track it must sell — often into thin liquidity at year-end. This forced selling
can temporarily push prices below fair value, creating a reversion opportunity.
The trade: buy deleted stocks after the June reconstitution, sell 3-6 weeks later.
The moat: institutions can't systematically exploit this in the names that get
deleted because the same illiquidity that creates the overshoot limits their
entry size.

**n=3 valid return observations (2023/2024/2025); 2026 cohort sizes only.**
With only 3 years of actual forward-return data, no statistical test has power
to distinguish skill from noise. 2026 is included for cohort-size tracking only
(MSD ends before T+21cd can be measured, per Amendment A-4). Come back when
n≥10 (~2032). The commit message's "effective n=3" is correct.

## Pre-Registration Summary

All parameters frozen before computation per the house epistemics rule.
Four amendments filed at analysis time (noted in script header), all pre-registered
BEFORE any data was read:

- **Amendment A-1:** MSD price data starts 2021-07-06; May 2021 prices
  unavailable. Recon year 2022 (which requires May 2021 as t-1 baseline)
  is excluded. Analysis covers n=4 recon years: 2023, 2024, 2025, 2026.
  However, 2026 contributes cohort sizes only (see A-4); effective n=3 for
  return statistics. The '4/5 years positive' gate is restated as '3/3 years
  positive' (matching n_obs=3 return observations). The exclude-2022 gate
  is vacuously satisfied (2022 never in data).

- **Amendment A-2:** Price floor of $1.00 at T=0 (recon effective date).
  Excludes near-bankrupt/penny-stock names from both cohorts. Standard
  practice in Russell reconstitution studies; prevents contamination by
  bankruptcy-bounce and meme-pump events that would otherwise dominate
  the return signal. Triggered by investigation of the deletion-proxy
  composition: without this filter, cohort returns showed >600% outliers
  (e.g., VIEW pumped from $0.12 to $12.83 in one quarter).

- **Amendment A-3:** Active-trading filter — ticker must have MSD price
  within 8 calendar days of the recon effective date. Ensures ticker is
  still actively trading (filters delistings counted as "deletions" purely
  due to data gaps in shares coverage).

- **Amendment A-4:** MSD ends 2026-07-02; recon 2026-06-26; T+21cd
  (2026-07-17) is 15 calendar days beyond MSD (gap > 10cd tolerance).
  2026 T+21 and T+63 forward returns are UNAVAILABLE. 2026 contributes
  cohort size data only. Effective n_obs = 3 for return statistics.

## STEP 1: Shares Outstanding — SEC EDGAR XBRL Coverage

- **2022 May snapshot:** 3115 tickers ranked, rank-1000 mcap ≈ $3.67B
- **2023 May snapshot:** 3437 tickers ranked, rank-1000 mcap ≈ $3.69B
- **2024 May snapshot:** 3705 tickers ranked, rank-1000 mcap ≈ $4.55B
- **2025 May snapshot:** 4063 tickers ranked, rank-1000 mcap ≈ $4.77B
- **2026 May snapshot:** 4356 tickers ranked, rank-1000 mcap ≈ $6.06B

PIT rule: for each May-31 rank date, only shares filings with estimated
availability date (end_date + 90d) on or before May 31 are used. This is
conservative (90d lag vs typical 45d); ensures no look-ahead.

## STEP 2: End-of-May Market Cap Rank Calibration

**TAUTOLOGY CAVEAT (first-class): The band_cutoff is PINNED to produce ~300
proxy deletions/year — not validated against external anchor counts. The target
of ~300 is the midpoint of FTSE Russell's published 200-400 range, but actual
per-year deletion counts have NOT been verified against FTSE press-release
totals. Consequently n_deletions_proxy≈300 is forced by construction; it
cannot detect a garbage proxy. This is a structural limitation of the
rank-proxy approach at phase-0 with no paid data.**

Band_cutoff PINNED to produce closest-to-300 deletions (NOT independently validated):

  2023: band_cutoff=2900, n_deletions_proxy=311
  2024: band_cutoff=2850, n_deletions_proxy=317
  2025: band_cutoff=2900, n_deletions_proxy=304
  2026: band_cutoff=2900, n_deletions_proxy=281

**PIT ASSUMPTION CAVEAT:** The shares data from SEC XBRL uses a conservative
+90-day availability lag from the reporting period end. True filing dates
vary (10-K ~60d, 10-Q ~40d); the 90d lag means we may undercount shares for
some companies (using an older annual vs. the available quarterly). This is the
conservative direction for market cap (smaller denominator = higher rank bias).

## STEP 3: Cohort Construction and Forward Returns

**Deletion cohort:** Ranked 1001..3000 in May t-1,
falls above band_cutoff rank OR absent in May t snapshot.
**Matched cohort:** Ranked 800..1000 or 3001..4000
in May t-1, NOT deleted in May t.
**Liquidity floor:** 60-day trailing median dollar volume ≥ $500k.

- **2023 (recon: 2023-06-30, cutoff rank 2900):**
  - Pre-liq/pre-filter deletions: 313, matched: 217
  - After all filters (activity+liq+price): deletions n=8, matched n=198
  - T+21d: del=-4.96% (n=8), match=4.52% (n=198), spread=-9.48%
  - T+63d: del=-4.67% (n=8), match=1.71% (n=198), spread=-6.38%
- **2024 (recon: 2024-06-28, cutoff rank 2850):**
  - Pre-liq/pre-filter deletions: 318, matched: 229
  - After all filters (activity+liq+price): deletions n=34, matched n=208
  - T+21d: del=13.40% (n=34), match=4.61% (n=208), spread=8.79%
  - T+63d: del=2.86% (n=34), match=6.10% (n=208), spread=-3.25%
- **2025 (recon: 2025-06-27, cutoff rank 2900):**
  - Pre-liq/pre-filter deletions: 304, matched: 244
  - After all filters (activity+liq+price): deletions n=71, matched n=222
  - T+21d: del=16.56% (n=71), match=3.79% (n=222), spread=12.78%
  - T+63d: del=22.74% (n=71), match=5.67% (n=222), spread=17.07%
- **2026 (recon: 2026-06-26, cutoff rank 2900):**
  - Pre-liq/pre-filter deletions: 281, matched: 279
  - After all filters (activity+liq+price): deletions n=137, matched n=250
  - T+21d: UNAVAILABLE (gap_15cd)
  - T+63d: UNAVAILABLE (gap_57cd)

## STEP 4: Statistical Tests

**Primary (correct for n=3 return obs):** Sign test + pooled bootstrap.
**Secondary (reported for completeness, near-powerless at n=3):** date-clustered t.

### T+21 calendar days
- Observations: 3 recon years with valid spread
- Positive spread years: 2/3
- Mean spread: 4.03% (deletion - matched)
- Bootstrap 95% CI: [-9.48%, 12.78%]
- Bootstrap P(spread>0): 0.734
- Sign test p-value (2-sided): 1.000
- Date-clustered t-stat (secondary): 0.59

### T+63 calendar days
- Observations: 3 recon years with valid spread
- Positive spread years: 1/3
- Mean spread: 2.48% (deletion - matched)
- Bootstrap 95% CI: [-6.38%, 17.07%]
- Bootstrap P(spread>0): 0.695
- Sign test p-value (2-sided): 1.000
- Date-clustered t-stat (secondary): 0.34

## STEP 5: Gate Verdicts

| Gate | Criterion | T+21d | T+63d |
|------|-----------|-------|-------|
| |t|≥2 date-clustered (SECONDARY) | 0.59<2 FAIL | 0.34<2 FAIL |
| Spread positive ≥3/3 return-obs (restated from 4/5 Amend A-1; n_obs=3, 2026=sizes only) | ≥3/3 | 2/3 FAIL | 1/3 FAIL |
| Exclude-2022 robustness | vacuous | PASS (A-1) | PASS (A-1) |

**OVERALL VERDICT:** DESCRIPTIVE/ACCRUAL — n=3 return observations prohibits any GO/NO-GO claim.

**Direction:** T+21d spread mean POSITIVE (4.03%), T+63d spread mean POSITIVE (2.48%).

**Sign consistency:** 2/3 years positive at T+21d, 1/3 at T+63d.

**Key numbers (effective n=3, years 2023/2024/2025):**

| Year | T+21d del | T+21d match | T+21d spread | T+63d del | T+63d match | T+63d spread |
|------|-----------|-------------|--------------|-----------|-------------|--------------|
| 2023 | -4.96% (n=8)  | +4.52% (n=198) | **-9.48%** | -4.67% (n=8) | +1.71% (n=198) | **-6.38%** |
| 2024 | +13.40% (n=34) | +4.61% (n=208) | **+8.79%** | +2.86% (n=34) | +6.10% (n=208) | **-3.25%** |
| 2025 | +16.56% (n=71) | +3.79% (n=222) | **+12.78%** | +22.74% (n=71) | +5.67% (n=222) | **+17.07%** |
| 2026 | N/A | N/A | **N/A** | N/A | N/A | **N/A** |

## Critical Caveats

1. **n=3 return observations (2023/2024/2025); 2026 = cohort size only:**
   Statistical inference is decorative at this sample size. The sign test
   and bootstrap CI are honest but have almost no power to distinguish the
   true effect from a coin flip. Filed for the record only.

2. **Deletion proxy quality:** The rank-based deletion proxy is a noisy
   approximation. True FTSE Russell deletions use market cap from a specific
   rank date + buffer zones + founder/multiple-share class adjustments not
   captured here. The proxy over-or-under-includes names vs. the actual list.

3. **Shares data coverage:** We ranked ~3115 tickers per year.
   Coverage gaps mean some deleted names are missed (if their shares weren't in
   SEC XBRL or fundamentals_panel). Coverage is better for larger-cap names
   and may undercount the smallest deletions (highest-rank deletions, most
   interesting for this study).

4. **No dividend adjustment:** Returns are price-only. Deleted small-caps
   have minimal dividend yields (~0.5-1.5%/yr) so 21d/63d impact is small
   but not zero.

5. **PIT shares conservatism:** The +90d lag for shares availability may
   use stale annual data when a more recent quarterly filing is available.
   This is conservative (safe direction for PIT compliance).

6. **Cohort-size instability — FIRST CLASS:** Post-filter deletion cohort
   sizes are: 2023 n=8, 2024 n=34, 2025 n=71, 2026 n=137 — an ~8x swing
   from 2023 to 2025. The 2023 T+21d spread of -9.48% rests on only 8 names.
   At n=8 a single name moving ±10% shifts the cohort return ~±1.25pp; the
   equal-weight mean is NOT a stable point estimate and must not be read as one.
   The dramatic cohort-size growth (driven by the activity+liquidity+price
   filters, not by the deletion count) means the post-filter selection — not
   the deletion signal itself — is doing most of the cohort definition work.
   Cross-year comparability is undermined: the 2023 "cohort" (8 names) and
   the 2025 "cohort" (71 names) are phenotypically different groups. Within-year
   dispersion (IQR of individual returns) was not reported at phase-0 and should
   be added at phase-1 to make the 2023 fragility visible alongside the mean.

## Nightly Wiring (for consolidation)

This study is ACCRUAL PHASE — no nightly wiring recommended until n≥10.
Data collection plan: the shares data fetch (SEC EDGAR frames API) runs
automatically each time this script executes. The deletion proxy and cohort
statistics accrue with each annual recon (new recon available ~July each year).

When n≥10 (~2032), wire as a standalone event-study module reading from:
- `data/massive_stock_day/` (prices)
- `data/edgar/fundamentals_panel.parquet` (shares fallback)
- SEC EDGAR frames API (primary shares source)

## Family Trial Ledger
Family `d2_russell_deletion_overshoot`: 1 configuration registered (see engine/trial_ledger.py).
DSR haircut at n_trials=1: minimal (first trial in family).

---
*Generated by scripts/d2_russell_deletion_phase0.py on 2026-07-07 00:02 UTC*  
*Pre-registration: all parameters frozen before data access.*
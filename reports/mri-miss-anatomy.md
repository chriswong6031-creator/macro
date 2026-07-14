# MRI Miss Anatomy — Engine-Replay Diagnostic

**Generated:** 2026-07-14  |  **Status:** DISPLAY-TIER RESEARCH — not authority, not promotion-eligible

## Plain-Word Summary

This report replays the v1 MRI champion model release-by-release using the CORRECTED feature construction (fixing the double-derivative bug confirmed in the 2026-07-14 postmortem). The bug applied pct_change() to sticky/median/flex CPI and PPI series that are ALREADY monthly percent-rate values, producing economically meaningless values (e.g. sticky_mom_lag1 of -36 to +229 instead of 0.09 to 0.38). All published V1/V2/V3 backtest results are contaminated and may not be cited.

The corrected walk-forward diagnostic measures how close the model was (or would have been) on each release, clusters the largest misses by diagnosed cause, and maps each cluster to candidate measurable inputs for future MRI track amendments. **No promotion or kill claims are made.** This is context for the comeback track, not a verdict.

## Coverage Constraints

These constraints are printed first because they bound every table below.

| Series | Store Period | Constraint |
|--------|-------------|------------|
| CPIAUCSL / CPILFESL | 1997-01 to 2026-05 | 353 initial prints; 352 MoM targets |
| Sticky/Median/Flex CPI | 2014-02/03 vintage start | Full-feature era begins ~2015 |
| PPIFIS (PPI) | 2014-03 | Same as sticky |
| GASREGW | 1990-08 to 2026-07 | Full availability |
| ZORI national | 2015-01 to 2026-05 | Shelter leg available 2015+ |
| CUSR0000SAH1 (shelter) | 1953-01 to 2026-05 | Full availability |
| PAYEMS (NFP) | 1997-01 to 2026-05 | 354 prints; 353 diff targets |
| ICSA/CCSA claims | 2009-06 / 2009-09 | NFP claims era from 2010+ |
| withheld_taxes | 2023-02 to 2026-07 | YoY (12m needed) => 2024-02+ only |
| **June 2026 CPI actual** | **ABSENT** | **period 2026-06-01 not in store; actual from postmortem** |

Walk-forward burn-in: 60 observations. First prediction with full-feature set (sticky/median/flex/PPI all present): ~2015-04. Total walk-forward predictions for CPI headline: 292 (core: 292, NFP: 293).

## Bug Receipt — Independent Verification of Postmortem Claim

The following table shows buggy vs corrected sticky_mom_lag1 for 3 example releases. This is the report's first receipt: the postmortem claim that pct_change() was applied to an already-rate series is confirmed by direct inspection.

| Period | asof | sticky_mom_lag1 (BUGGY) | sticky_mom_lag1 (CORRECTED) | Actual MoM |
|--------|------|------------------------|----------------------------|------------|
| 2015-01-01 | 2015-02-25 | -49.1102 | 0.0969 | -0.6233 |
| 2019-01-01 | 2019-02-12 | 14.9079 | 0.2282 | -0.0237 |
| 2025-01-01 | 2025-02-11 | 13.9599 | 0.228 | 0.441 |

The buggy values are dimensionless second-derivatives (pct_change of a percent rate). The corrected values are in the economically meaningful range of roughly 0.09-0.40 %/month for sticky CPI. The magnitude difference (~100x) explains why the contaminated model over-weighted persistence signals.

## MAE Summary — Corrected Replay vs Naive Prior

**EXPLICIT CAVEAT (MRI-R8):** These are walk-forward replay statistics, not the MRI forward scoreboard record. The forward scoreboard started 2026-07-07 and has zero rows. This table is descriptive — a diagnostic of how the corrected model behaves historically. With the bug, ALL prior results were contaminated.

| Release | n predictions | Model MAE (corrected) | Naive MAE | Q75 abs error | Top-Q misses |
|---------|--------------|----------------------|-----------|---------------|--------------|
| CPI Headline | 292 | 0.157 | 0.261 | 0.2179 | 73 |
| CPI Core | 292 | 0.0925 | 0.0991 | 0.1253 | 73 |
| NFP | 293 | 308.1 | 359.6 | 219.5 | 74 |

## June 2026 CPI — Worked Example

The June 2026 print (CPI for period 2026-06-01, released 2026-07-11) is ABSENT from the vintage store as of 2026-07-14. The actual values are sourced from the postmortem.

| Item | Headline | Core |
|------|----------|------|
| Actual (postmortem) | -0.4 | -0.02 |
| Contaminated engine | +0.0818 | +0.2167 |
| Postmortem error | -0.4818 | -0.2367 |

Postmortem decomposition: ~-0.3 pp street-wide (gasoline/energy turning point, broad disinflation), ~-0.18 pp self-inflicted (double-derivative bug over-anchored model to prior-month persistence).

Headline features (corrected, as of 2026-07-10):

- **cpi_hl_mom_lag1**: 0.4729
- **cpi_hl_mom_lag2**: 0.64
- **cpi_hl_mom_lag3**: 0.8651
- **sticky_mom_lag1**: 0.2386
- **median_mom_lag1**: 3.6643
- **flex_mom_lag1**: 1.1076
- **ppi_mom_lag1**: 0.7431
- **gasoline_mom**: -9.592
- **shelter_nowcast**: 0.2613

Buggy sticky_mom_lag1 for this step: -36.6832 (corrected: 0.2386). The corrected model would have seen ~0.24 for sticky (plausible persistence signal) vs the buggy -36.6832 (noise, disrupts coefficient weighting throughout training).

## Miss Anatomy — Cluster Summary

Top-quartile misses (|error| >= Q75 of the replay distribution) are classified by dominant diagnosed cause. n=count within top-quartile misses.

Priority-order disclosure: each miss is assigned to a single cluster by fixed priority january_seasonal > energy_turning_point > persistence_overshoot > shelter_lag > unexplained; shares are order-dependent and not additive across overlapping causes.

### CPI Headline

| Cluster | n | Mean abs error | % of top-Q misses |
|---------|---|----------------|-------------------|
| energy_turning_point | 17 | 0.3393 | 23.3% |
| january_seasonal | 8 | 0.3281 | 11.0% |
| persistence_overshoot | 11 | 0.3782 | 15.1% |
| unexplained | 37 | 0.3361 | 50.7% |

### CPI Core

| Cluster | n | Mean abs error | % of top-Q misses |
|---------|---|----------------|-------------------|
| january_seasonal | 8 | 0.241 | 11.0% |
| persistence_overshoot | 5 | 0.2251 | 6.8% |
| unexplained | 60 | 0.2029 | 82.2% |

### NFP

Note: NFP cluster labels are magnitude buckets, not diagnosed mechanisms (no block decomposition exists for NFP). 'large_miss_uncharacterized' = |error| > 200k (above Q75=~220k); no mechanism evidence supports the label.

| Cluster | n | Mean abs error | % of top-Q misses |
|---------|---|----------------|-------------------|
| january_seasonal | 15 | 632.4 | 20.3% |
| covid_outlier | 4 | 8962.5 | 5.4% |
| large_miss_uncharacterized | 55 | 449.0 | 74.3% |

## Per-Release Table (Recent 24 CPI Headline Rows)

Full table in mri_miss_anatomy.json. Showing the most recent 24 headline releases to illustrate full-feature era behavior. signed_error = actual - corrected_projection. cluster = diagnosed cause category.

| Period | Release Date | Corrected Proj | Actual | Signed Error | Naive Error | Cluster |
|--------|-------------|---------------|--------|-------------|-------------|---------|
| 2024-05-01 | 2024-06-12 | 0.3517 | 0.0057 | -0.346 | -0.3072 | persistence_overshoot |
| 2024-06-01 | 2024-07-11 | 0.027 | -0.0562 | -0.0832 | -0.0619 | persistence_overshoot |
| 2024-07-01 | 2024-08-14 | 0.2166 | 0.1549 | -0.0617 | 0.2111 | unexplained |
| 2024-08-01 | 2024-09-11 | 0.078 | 0.1872 | 0.1092 | 0.0323 | energy_turning_point |
| 2024-09-01 | 2024-10-10 | -0.0042 | 0.1799 | 0.184 | -0.0074 | unexplained |
| 2024-10-01 | 2024-11-13 | 0.1569 | 0.2441 | 0.0872 | 0.0642 | unexplained |
| 2024-11-01 | 2024-12-11 | 0.1527 | 0.3129 | 0.1602 | 0.0688 | unexplained |
| 2024-12-01 | 2025-01-15 | 0.1467 | 0.3931 | 0.2464 | 0.0802 | unexplained |
| 2025-01-01 | 2025-02-12 | 0.2886 | 0.441 | 0.1524 | 0.0479 | january_seasonal |
| 2025-02-01 | 2025-03-12 | 0.4126 | 0.2159 | -0.1967 | -0.2251 | unexplained |
| 2025-03-01 | 2025-04-10 | 0.2173 | -0.05 | -0.2674 | -0.266 | unexplained |
| 2025-04-01 | 2025-05-13 | 0.2336 | 0.2209 | -0.0127 | 0.2709 | energy_turning_point |
| 2025-05-01 | 2025-06-11 | 0.242 | 0.0809 | -0.1611 | -0.14 | unexplained |
| 2025-06-01 | 2025-07-15 | 0.0916 | 0.287 | 0.1954 | 0.2061 | unexplained |
| 2025-07-01 | 2025-08-12 | 0.2696 | 0.1966 | -0.073 | -0.0904 | unexplained |
| 2025-08-01 | 2025-09-11 | 0.2486 | 0.3825 | 0.1338 | 0.1859 | unexplained |
| 2025-09-01 | 2025-10-24 | 0.3118 | 0.3105 | -0.0013 | -0.072 | unexplained |
| 2025-11-01 | 2025-12-18 | 0.1882 | 0.2044 | 0.0162 | -0.1061 | unexplained |
| 2025-12-01 | 2026-01-13 | -0.0239 | 0.3074 | 0.3313 | 0.103 | persistence_overshoot |
| 2026-01-01 | 2026-02-13 | 0.1961 | 0.1711 | -0.0249 | -0.1362 | january_seasonal |
| 2026-02-01 | 2026-03-11 | 0.3998 | 0.267 | -0.1328 | 0.0959 | energy_turning_point |
| 2026-03-01 | 2026-04-10 | 1.0436 | 0.8651 | -0.1785 | 0.5981 | unexplained |
| 2026-04-01 | 2026-05-12 | 0.6974 | 0.64 | -0.0573 | -0.2251 | unexplained |
| 2026-05-01 | 2026-06-10 | 0.6366 | 0.4729 | -0.1637 | -0.1671 | unexplained |

## Chartered Improvement Track Candidates

These are CANDIDATES for a future MRI §13 amendment PR. No decisions are made here. Every track listed requires its own pre-registration under MRI law before any result contact. Tracks mapping to existing C-tracks can be scoped within their current prereg framework.

### Energy Turning Point

**Cluster:** energy_turning_point  
**Evidence basis:** Sign-flip in gasoline_mom (GASREGW) vs prior month co-occurs with top-quartile CPI headline misses in replay. The model uses within-month average GASREGW for ref_month M which is knowable, but the sign of the MoM change amplifies or damps the energy block contribution.  
**Candidate measurable input:** GASREGW weekly observations through the release week (not just monthly avg). EIA weekly petroleum supply data (already in data/eia/). Sign of gasoline MoM known ~10 days before CPI print.  
**Already collected:** Yes  
**Maps to C-track:** new track candidate (needs MRI §13 amendment + own prereg under MRI law). NOTE: C-4 is PCE/PPI/retail-sales expansion (v1.1) — no energy component; the within-month energy-accumulator nowcast lives in Track T (mf_energy, §12.3), which is already chartered and shadow-scored. A sign-flip indicator for the energy block is a sub-feature of Track T, not a standalone C-track; coordinate with Track T prereg before filing separately.  
**Proposed gate:** Pre-register: does adding gasoline sign-flip indicator reduce energy-block error by >15% in 2015-2026 corrected walk-forward? Gate: corrected-replay energy-block MAE reduction, one-shot.  
**Status:** candidate (needs MRI §13 amendment + own prereg under MRI law)  

### Shelter Lag

**Cluster:** shelter_lag  
**Evidence basis:** HYPOTHESIS — n=0 observed releases assigned this cluster under the exclusive priority classifier (classifier returns 'shelter_lag' for zero of 292 replayed CPI releases). Supporting stats: 228 of 292 releases have nonzero shelter block contributions (max |contrib| 0.128pp, median 0.005pp); 14 of 73 top-quartile misses have shelter contrib >0.01pp but never achieve dominance under the exclusive classifier. Track candidacy rests on the June-2026 postmortem mechanism (ZORI lease-reset signal diverges from BLS momentum; double-derivative bug over-anchored model to prior-month persistence) rather than replay evidence. Shelter nowcast (ZORI blended with BLS CPI shelter) under-adjusts when this divergence occurs; the divergence guard (PREREG_V2.md §2.5) is hypothesized to fire too infrequently, but this is unconfirmed in replay.  
**Candidate measurable input:** Cleveland nowcast (data/cleveland_nowcast/nowcast.parquet, series=core_cpi_mom) is already collected and provides a second shelter-adjacent estimate. Its PIT structure: obs_date column gives the nowcast-as-of date; CAVEAT: first_seen_asof starts 2026-07-07, so historical backfill may not reflect real-time availability pre-collection.  
**Already collected:** Yes  
**Maps to C-track:** new track candidate (needs MRI §13 amendment + own prereg under MRI law). NOTE: C-10 is specifically the CPI bridge sub-index vintaging comeback (vintage the sub-index series, add to vintage_series, then decide whether to spend attempt #2 on a PIT-clean scope-fixed re-run — masterplan §12.1 MRI-R29). C-2 is the market-implied distribution adapter (Kalshi benchmark member) — no vintaging role. Neither C-track covers shelter nowcast augmentation; this requires its own prereg.  
**Proposed gate:** Pre-register: does adding Cleveland nowcast (obs_date <= D) as shelter supplement reduce shelter-block error by >10% in 2015-2026 replay? Gate: shelter-block MAE reduction with PIT-honest Cleveland obs_date filter. CAVEAT: collection-start limits genuine historical PIT to 2026-07-07+.  
**Status:** HYPOTHESIS — not an observed replay cluster (n=0 under exclusive classifier); track candidacy based on June-2026 postmortem mechanism. Requires MRI §13 amendment + own prereg before any result contact.  

### January Seasonal

**Cluster:** january_seasonal  
**Evidence basis:** January CPI releases carry weight-update and seasonal-factor-revision effects that are not captured by any current feature. January mis-prediction rate is structurally elevated across all walk-forward eras.  
**Candidate measurable input:** BLS weights published in December (before January CPI release). A January-indicator dummy (binary) is zero-cost to implement and would allow the model to reduce its persistence weight for Jan. SCE (data exists, maps to C-12) can also flag expectation shifts pre-Jan.  
**Already collected:** Yes  
**Maps to C-track:** C-12 (SCE); January indicator = new feature within existing prereg spec  
**Proposed gate:** Pre-register: add January dummy; gate = corrected-replay MAE for January releases improves vs holdout (2021+). One pre-registered gate attempt.  
**Status:** candidate (needs MRI §13 amendment + own prereg under MRI law)  

### Persistence Overshoot

**Cluster:** persistence_overshoot  
**Evidence basis:** When the trailing-3m momentum sign reverses (e.g. 3 months of 0.3% then a shock to -0.4%), the persistence/own-lag block contributes a large positive prediction that amplifies the miss. June 2026 is the prototypical case: sticky/median/flex were all anchored near 0.20-0.38 range, but the headline came in -0.40 due to broad energy disinflation.  
**Candidate measurable input:** Sticky-flex divergence (STICKCPIM157SFRBATL minus FLEXCPIM157SFRBATL): a widening gap signals regime turn more reliably than either alone. Both are already collected (2014-03+). Claims breadth (C-13): ICSA breadth across states could signal demand-side shock before CPI. SCE (C-12): consumer inflation expectations from NY Fed SCE.  
**Already collected:** Yes  
**Maps to C-track:** C-13 (claims breadth); C-12 (SCE); sticky-flex divergence = new derived feature within existing data.  
**Proposed gate:** Pre-register: does sticky-flex divergence as an additional feature reduce persistence-block error at regime turns by >15%? Gate: corrected-replay error on persistence_overshoot-classified misses. Also pre-register: test whether ICSA breadth (C-13) leads CPI regime turns.  
**Status:** candidate (needs MRI §13 amendment + own prereg under MRI law)  

### Unexplained

**Cluster:** unexplained  
**Evidence basis:** Residual misses with no dominant identifiable cause in the current feature set. May reflect true measurement noise, concurrent policy shocks, or features not yet collected.  
**Candidate measurable input:** No single candidate identified with high confidence. General candidates: sector-level PPI disaggregation (data/... check); import price index (not currently collected). These would require new collection before a prereg.  
**Already collected:** No — new collection needed  
**Maps to C-track:** new track candidate (needs MRI §13 amendment + its own prereg under MRI law)  
**Proposed gate:** TBD — data collection required before gate can be specified.  
**Status:** new track candidate (needs MRI §13 amendment + its own prereg under MRI law)  

## Self-Checks

1. Self-check 1 (row count): HL=292 predictions, CORE=292 predictions, NFP=293 predictions. CPIAUCSL store has 353 initial prints -> 352 MoM targets; burn-in=60 -> expect ~292 if all obs valid. Actual HL=292 (PASS).
2. Self-check 2 (corrected sticky lag range): n=146, min=-0.1414, max=0.6813, mean=0.2646. 100.0% of values in [-0.20, +0.80] monthly % range (PASS).
3. Self-check 3 (MAE vs naive, DESCRIPTIVE per MRI-R8 — NOT forward record): HL model MAE=0.1570 vs naive MAE=0.2610; CORE model MAE=0.0925 vs naive MAE=0.0991. EXPLICIT CAVEAT: these are walk-forward replay statistics from a corrected but still contaminated-era store. They indicate whether the corrected model reduces systematic error vs naive prior — they do NOT constitute the MRI forward scoreboard (which started 2026-07-07 and has zero rows).
4. Self-check 4 (PIT invariant): asserted in-code for all records (pd.Timestamp(asof) < pd.Timestamp(release_date)). Spot-check of 5 random HL rows: PASS (no violations found).

## Methodology Notes

Feature construction correction: sticky/median/flex CPI are already published as rate series (sticky and flex as monthly %, median as annualized %). The engine's _last_n_mom_lags function applied pct_change() to these series (computing the rate-of-change of a rate = second derivative), producing values 100-800x outside the economically meaningful range. This is corrected here by reading the last known rate value directly. PPIFIS (PPI Final Demand) is an INDEX LEVEL (~109-157), not a rate series; pct_change() on the index gives the correct MoM % change (~0.5-1.5%). The bug does NOT affect PPI. The engine's PPI treatment is correct; this script replicates that behavior for PPI.

Walk-forward: expanding-window Ridge regression (lambda=1.0, numpy only), z-scored features, complete-case training (missing features dropped per step). Minimum 60 training observations before first prediction (same as engine). Features unavailable before 2014-03 (sticky/median/flex/PPI) are dropped from the model for those steps via complete-case selection — the model uses only own CPI lags, gasoline, and shelter for pre-2014 steps.

Block contributions: computed via beta * z_feature from the ridge fit (same as PREREG_V2.md §4). Energy block = gasoline_mom. Shelter = shelter_nowcast. Core_persistence = own lags + sticky + median + flex. Pipeline = PPI.

NFP note: the NFP series (PAYEMS) is a level in thousands of jobs; the target is the first-difference (change). There is NO rate-series bug for NFP. The corrected NFP walk-forward is identical to what the engine would produce if its NFP path were isolated. The NFP bug-exposure is zero.

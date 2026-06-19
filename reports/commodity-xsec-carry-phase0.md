# Phase-0 — Cross-sectional commodity CARRY / basis (dated contracts)

_run 2026-06-19T06:46:03.052025+00:00_

**VERDICT: INCONCLUSIVE** — cross-sectional dated-basis carry does NOT clear the scored bar in the proposed (long-backwardation) direction; the signal that yfinance dated data can build is CONFOUNDED by front-price reversion and the window is one ~3y regime.


## Data reality (the binding constraint)

- yfinance serves the CONTINUOUS front generics (`CL=F` ...) back to ~2000, but serves DATED contracts (`CLZ26.NYM` ...) ONLY while still listed; EXPIRED dated contracts are deleted (404 — verified CLZ24/CLM25/etc all empty). A deep stitched chain of expired deferreds is IMPOSSIBLE from Yahoo.

- The currently-live deferreds carry history only back to their listing date (CL ~2018, NG ~2014, most metals/grains 2021-2024). To keep a basis ALIVE in the past we had to reach to a ~24-month-out deferred, which makes the basis a FAR-dated annualized carry, not the literature's adjacent-contract carry.

- Usable full cross-section: **16 commodities, 2023-05-17..2026-06-19 (~3.1y, post-2023 only)**.


## Headline numbers (REAL, computed)

- Forward cross-sectional rank-IC is significant but **NEGATIVE & deepening with horizon**: 5d -0.0862 (t -4.398), 21d -0.1557 (t -4.029), 63d -0.2594 (t -3.655), 126d -0.2925 (t -3.274). All survive BH-FDR q<=0.10 — but with the WRONG sign vs the storage-theory claim.

- Naive long-backwardation / short-contango tercile L/S (vol-target 10%, 9bps): Sharpe **-1.532**, CAGR -18.92%, maxDD -50.5%. DSR 0.0 (FAILS).

- Beats EW-long B&H? **False** (EW-long Sharpe 0.846). Beats per-commodity 200dma? **False** (200dma Sharpe 0.52).


## Why the sign is the WRONG kind of evidence (the confound)

- Per-commodity time-series rank-corr(basis_t, own 63d fwd return) is negative for ~15/16 names (WTI -0.55, Soybean -0.64, Cotton -0.73). With a far/sticky ~24mo deferred leg, `basis=(front-def)/def` is dominated by FRONT-PRICE ELEVATION, which mean-reverts — a near-mechanical negative time-series relationship, NOT a carry edge.

- Clean check on the deep EIA WTI term structure (c1-vs-c4, 1985-2026, ~9800 obs): carry-timing rank-corr is also negative (-0.08 @21d, -0.17 @63d). Carry is a CROSS-SECTIONAL premium in the literature, NOT a single-name timing signal; the yfinance dated construction collapses toward the (negative) timing relationship.

- Demeaning/z-scoring the basis by its own 252d history shrinks the negative IC (63d: -0.26 raw -> -0.08 demeaned, t -1.9) but does not flip it positive — so there is no rescued positive carry premium hiding under the level artifact either.


## Gate tally

- [PASS] fwd_rank_IC_survives_BH_q<=0.10
- [FAIL] tercile_L/S_DSR>=0.90
- [PASS] split_half_same_sign
- [PASS] leave_one_crisis_out_stable
- [FAIL] beats_EW_long_BH
- [FAIL] beats_per_commodity_200dma


## Honest-N

- ~3.1y single regime (post-2023), ~12 non-overlapping quarters, a thin 16-commodity cross-section. Far too few independent regimes for any DSR claim even if the sign had been right.


## Bottom line

- Proposed tier was SCORED ('basis IC +0.15, carry harvesting works'). The data yfinance can actually provide does NOT support a scored cross-sectional dated-basis carry leg: the constructible signal is confounded, the realized L/S loses to two dumb baselines, and the only window is one ~3y regime. **INCONCLUSIVE on a true carry edge — not a clean rejection, a data-inadequacy verdict.** A proper test needs a dated-history vendor (CME/Bloomberg/Quandl-Stevens) with expired contracts to stitch a constant-maturity adjacent-month basis over 20+ years.


## The log
```
==============================================================================
PHASE-0: Cross-sectional commodity CARRY / basis (dated contracts)
run: 2026-06-19T06:46:00.283052+00:00
==============================================================================
[collect] cache hit -> /Users/chriswong/Documents/Cluade/Macro Dashboard/data/commodity_xsec/raw_closes.parquet

[data] wide frame (7217, 85), 1997-10-29..2026-06-19
[basis] WTI       n=  757 2023-06-16..2026-06-19 gap~24.42mo  mean_basis=+0.067 bckwd%=0.976
[basis] NatGas    n=  757 2023-06-16..2026-06-19 gap~24.05mo  mean_basis=-0.199 bckwd%=0.018
[basis] Gold      n=  757 2023-06-16..2026-06-19 gap~24.43mo  mean_basis=-0.040 bckwd%=0.0
[basis] Silver    n=  756 2023-06-16..2026-06-19 gap~24.41mo  mean_basis=-0.039 bckwd%=0.0
[basis] Copper    n=  756 2023-06-16..2026-06-19 gap~24.41mo  mean_basis=-0.026 bckwd%=0.033
[basis] Corn      n=  755 2023-06-16..2026-06-18 gap~24.44mo  mean_basis=-0.037 bckwd%=0.148
[basis] Soybean   n=  776 2023-05-17..2026-06-18 gap~24.12mo  mean_basis=+0.006 bckwd%=0.539
[basis] Platinum  n=  602 2024-01-29..2026-06-19 gap~21.67mo  mean_basis=-0.030 bckwd%=0.0
[basis] Wheat     n=  487 2024-07-12..2026-06-18 gap~18.31mo  mean_basis=-0.087 bckwd%=0.0
[basis] HeatOil   n=  757 2023-06-16..2026-06-19 gap~24.42mo  mean_basis=+0.079 bckwd%=0.937
[basis] Gasoline  n=  756 2023-06-16..2026-06-19 gap~24.43mo  mean_basis=+0.108 bckwd%=1.0
[basis] SoyOil    n=  755 2023-06-16..2026-06-18 gap~24.44mo  mean_basis=+0.021 bckwd%=0.727
[basis] SoyMeal   n=  755 2023-06-16..2026-06-18 gap~24.44mo  mean_basis=-0.011 bckwd%=0.417
[basis] Sugar     n=  559 2024-04-01..2026-06-18 gap~22.33mo  mean_basis=+0.002 bckwd%=0.488
[basis] Coffee    n=  559 2024-04-01..2026-06-18 gap~22.33mo  mean_basis=+0.115 bckwd%=1.0
[basis] Cotton    n=  559 2024-04-01..2026-06-18 gap~22.33mo  mean_basis=-0.034 bckwd%=0.086

[panel] commodities with usable dated basis: 16 -> ['WTI', 'NatGas', 'Gold', 'Silver', 'Copper', 'Corn', 'Soybean', 'Platinum', 'Wheat', 'HeatOil', 'Gasoline', 'SoyOil', 'SoyMeal', 'Sugar', 'Coffee', 'Cotton']
[panel] 16 commodities, 2023-05-17..2026-06-19 (~3.1y), 778 rows
[panel] cross-section width: median=16 max=16 (dates with >=4 names: 756)

--- FORWARD CROSS-SECTIONAL RANK-IC (signal=basis.shift(1), target=front fwd ret) ---
  h=  5d: mean_IC=-0.0862  IC-IR=-0.242  t_HAC=-4.398  p_HAC=0.0  hit=0.396  n=374
  h= 21d: mean_IC=-0.1557  IC-IR=-0.451  t_HAC=-4.029  p_HAC=0.0001  hit=0.313  n=182
  h= 63d: mean_IC=-0.2594  IC-IR=-0.724  t_HAC=-3.655  p_HAC=0.0003  hit=0.276  n=58
  h=126d: mean_IC=-0.2925  IC-IR=-1.034  t_HAC=-3.274  p_HAC=0.0011  hit=0.154  n=26

  Benjamini-Hochberg FDR (q<=0.10) across horizons:
    h126: p=0.0011 q=0.0011 reject=True
    h63: p=0.0003 q=0.0004 reject=True
    h21: p=0.0001 q=0.0002 reject=True
    h5: p=0.0 q=0.0 reject=True

--- TERCILE L/S CARRY PORTFOLIO (vol-target 10%, net 9bps one-way) ---
  L/S net: Sharpe=-1.532 CAGR=-18.92% maxDD=-50.5% vol=13.1% n=752 (3.0y)
  L/S gross (no cost): Sharpe=-1.471 CAGR=-18.26%
  annual turnover ~8.9x  -> cost drag ~0.80%/yr
  DSR (n_trials=8): 0.0  -> FAILS multiple-testing haircut (DSR<0.90)
     sr_annual=-1.53 sr0_annual(haircut)=0.82 T=752 skew=-1.102 kurt=17.505
  block-bootstrap 95% CI: Sharpe=[-2.54, -1.57, -0.68]  maxDD%=[-63.0, -49.0, -30.9]  P(Sharpe>0)=0.0

--- SPLIT-HALF OOS (same-sign Sharpe across halves?) ---
  first-half Sharpe=-1.462  second-half Sharpe=-1.691  same-sign=True

--- LEAVE-ONE-CRISIS-OUT (Sharpe with each crisis window removed) ---
  drop covid_2020        : Sharpe=-1.532
  drop oil_neg_2020      : Sharpe=-1.532
  drop war_inflation_22  : Sharpe=-1.532
  drop rate_shock_2023   : Sharpe=-1.487
  LOCO stable (sign holds dropping any crisis): True

--- DUMB BASELINES (same span/cost where applicable) ---
  EW-long commodity B&H : Sharpe=0.846 CAGR=11.69% maxDD=-12.7%
  per-commodity 200dma  : Sharpe=0.52 CAGR=4.48% maxDD=-11.7%
  carry L/S beats EW-long?  False   beats 200dma?  False

--- CONFOUND DIAGNOSTIC: per-commodity time-series rank-corr(basis_t, own 63d fwd ret) ---
  WTI       rankcorr_ts=-0.554  (n=694)
  NatGas    rankcorr_ts=-0.547  (n=694)
  Gold      rankcorr_ts=-0.282  (n=694)
  Silver    rankcorr_ts=-0.248  (n=693)
  Copper    rankcorr_ts=-0.309  (n=693)
  Corn      rankcorr_ts=-0.617  (n=691)
  Soybean   rankcorr_ts=-0.635  (n=712)
  Platinum  rankcorr_ts=+0.096  (n=539)
  Wheat     rankcorr_ts=-0.237  (n=423)
  HeatOil   rankcorr_ts=-0.319  (n=694)
  Gasoline  rankcorr_ts=-0.593  (n=693)
  SoyOil    rankcorr_ts=-0.617  (n=691)
  SoyMeal   rankcorr_ts=-0.522  (n=691)
  Sugar     rankcorr_ts=-0.293  (n=496)
  Coffee    rankcorr_ts=-0.491  (n=496)
  Cotton    rankcorr_ts=-0.727  (n=496)
  -> 94% of commodities show NEGATIVE basis->own-fwd-return: the basis is dominated by front-price elevation that mean-reverts (far/sticky deferred leg artifact).

--- CLEAN CHECK: deep EIA WTI term structure (c1 vs c4, 1985-2026) ---
  EIA WTI carry-timing rank-corr h=21d: -0.082  n=9836
  EIA WTI carry-timing rank-corr h=63d: -0.167  n=9794
  -> single-name carry timing is ALSO negative on 41y of clean data; carry is a cross-sectional premium, not a time-series signal (literature-consistent).

--- HONEST-N ---
  raw daily obs=752, but autocorrelated; ~12 non-overlapping quarters, and cross-section is only 16 commodities (~16 per date typical).
  Effective independent regimes are FEW (single ~3y window, post-2017 only).

==============================================================================
GATE TALLY
==============================================================================
  [PASS] fwd_rank_IC_survives_BH_q<=0.10
  [FAIL] tercile_L/S_DSR>=0.90
  [PASS] split_half_same_sign
  [PASS] leave_one_crisis_out_stable
  [FAIL] beats_EW_long_BH
  [FAIL] beats_per_commodity_200dma

VERDICT: INCONCLUSIVE
```

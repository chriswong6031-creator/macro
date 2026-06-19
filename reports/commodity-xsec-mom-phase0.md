# Cross-sectional commodity momentum (19-asset, deep) — Phase-0

```
========================================================================================================
CROSS-SECTIONAL COMMODITY MOMENTUM (19-asset, deep) — Phase-0 (READ-ONLY)
  universe (19): gold, silver, copper, platinum, palladium, wti, brent, natgas, heatoil, rbob, corn, soybean, wheat, coffee, cotton, sugar, cocoa, cattle, hogs
  full span 1997-10-29..2026-06-19; analysis from 2002-01-01
  12-1m xsec rank, LONG top-tercile/SHORT bottom-tercile EW, vol-target 10%, rebal 21d, next-bar, 9bps one-way
    gold       2000-08-30..2026-06-19  (25.8y, n=6475)
    silver     2000-08-30..2026-06-19  (25.8y, n=6477)
    copper     2000-08-30..2026-06-19  (25.8y, n=6480)
    platinum   1997-10-29..2026-06-19  (28.6y, n=6503)
    palladium  1998-09-28..2026-06-19  (27.7y, n=6514)
    wti        2000-08-23..2026-06-19  (25.8y, n=6484)
    brent      2007-07-30..2026-06-19  (18.9y, n=4702)
    natgas     2000-08-30..2026-06-19  (25.8y, n=6481)
    heatoil    2000-09-01..2026-06-19  (25.8y, n=6478)
    rbob       2000-11-01..2026-06-19  (25.6y, n=6439)
    corn       2000-07-17..2026-06-18  (25.9y, n=6486)
    soybean    2000-09-15..2026-06-18  (25.8y, n=6478)
    wheat      2000-07-17..2026-06-18  (25.9y, n=6498)
    coffee     2000-01-03..2026-06-18  (26.5y, n=6634)
    cotton     2000-01-03..2026-06-18  (26.5y, n=6636)
    sugar      2000-03-01..2026-06-18  (26.3y, n=6597)
    cocoa      2000-01-03..2026-06-18  (26.5y, n=6636)
    cattle     2001-03-01..2026-06-18  (25.3y, n=6341)
    hogs       2000-12-15..2026-06-18  (25.5y, n=6409)
========================================================================================================

### HEADLINE L/S vs DUMB BASELINES (net of cost, from 2002-01-01)
  xsec-mom L/S (12-1m, vt10)       CAGR= -3.01%  Sharpe=-0.23  MaxDD=  -64.7%  n=6167
  EW-long commodity B&H            CAGR= +9.42%  Sharpe=+0.64  MaxDD=  -52.9%  n=6165
  each-commodity 200dma (long/flat) CAGR= +1.08%  Sharpe=+0.18  MaxDD=  -38.3%  n=6167
  beats EW-long on Sharpe? NO  (-0.231 vs +0.636, margin -0.867)
  beats 200dma on Sharpe?  NO  (-0.231 vs +0.177)

### FORWARD RANK-IC (xsec signal vs fwd 21d return) + BH-FDR across variants
  mom_12_1  mean_IC=-0.0181  IC-IR=-0.057  t_HAC=-1.006  p_HAC=0.3143  hit=0.432  n=271
  mom_12    mean_IC=-0.0253  IC-IR=-0.076  t_HAC=-1.306  p_HAC=0.1916  hit=0.467  n=274
  mom_6_1   mean_IC=-0.0502  IC-IR=-0.159  t_HAC=-3.314  p_HAC=0.0009  hit=0.435  n=276
  mom_1     mean_IC=-0.0444  IC-IR=-0.137  t_HAC=-2.59  p_HAC=0.0096  hit=0.442  n=283
  BH-FDR (q<=0.10):
    mom_12_1  p=0.3143  q=0.3143  reject_null=False
    mom_12    p=0.1916  q=0.2555  reject_null=False
    mom_1     p=0.0096  q=0.0192  reject_null=True
    mom_6_1   p=0.0009  q=0.0036  reject_null=True
  -> headline mom_12_1 IC survives BH-FDR q<=0.10: False  (mean_IC=-0.0181, t_HAC=-1.006)

### DEFLATED SHARPE — grid = 4 lookbacks x 3 rebals = 12 trials
  grid annual-Sharpes: [-0.5, -0.4, -0.41, -0.34, -0.29, -0.23, -0.39, -0.3, -0.25, -0.47, -0.5, -0.23]
  best-in-grid: lb=21 skip=0 rebal=21  Sharpe=-0.23
  HEADLINE 12-1m/vt10: SR(ann)=-0.23  SR0(ann,haircut)=+0.34  skew=+0.44  kurt=11.3  T=6167
  DSR = 0.0025  (n_trials=12)  -> FAILS multiple-testing haircut (DSR<0.90)
  BEST-IN-GRID DSR = 0.0026  -> FAILS multiple-testing haircut (DSR<0.90)

### SPLIT-HALF — same-sign Sharpe (and report vs EW each half)
  first   (2002-01-02..2014-03-19): L/S Sharpe=-0.406  EW-long=+0.891  beats_EW=NO
  second  (2014-03-19..2026-06-19): L/S Sharpe=-0.062  EW-long=+0.370  beats_EW=NO
  -> same-sign = True   both-halves-positive = False

### BLOCK-BOOTSTRAP 95%% CI on L/S Sharpe (block=21, B=5000)
  Sharpe 95% CI [-0.64, -0.23, 0.17]   MaxDD% 95% CI [-86.0, -65.1, -34.4]   P(Sharpe>0)=0.129

### LEAVE-ONE-CRISIS-OUT — drop each crisis; L/S Sharpe stays >0 & beats EW
  drop 2008 GFC          : L/S Sharpe=-0.196  (EW +0.795)  -> WEAK
  drop 2014-16 oil bust  : L/S Sharpe=-0.275  (EW +0.791)  -> WEAK
  drop 2020 COVID        : L/S Sharpe=-0.348  (EW +0.801)  -> WEAK
  drop 2022 bear         : L/S Sharpe=-0.239  (EW +0.636)  -> WEAK
  -> leave-one-crisis-out holds on ALL: False

### CRISIS CONVEXITY — cumulative return through each window
  window                     L/S   EW-long    200dma
  2008 GFC                -11.0%    -33.2%    -11.1%
  2014-16 oil bust          5.8%    -35.9%    -12.6%
  2020 COVID               29.8%    -38.4%     -7.2%
  2022 bear                -1.0%     11.9%     -0.6%

### PURGED 5-FOLD CV (embargo=63d) — no fold should flip negative
  fold1: Sharpe=-0.43  (n=1170)
  fold2: Sharpe=-0.54  (n=1170)
  fold3: Sharpe=+0.01  (n=1171)
  fold4: Sharpe=-0.34  (n=1170)
  fold5: Sharpe=+0.37  (n=1171)
  -> no fold flips negative: False

### HONEST-N — a THIN cross-section; months autocorrelate
  raw daily rows: 6167   monthly rebals: ~293   span: ~24.5y
  cross-section width: 19 commodities (terciles ~6 long / 6 short) — THIN vs an equity factor (100s of names)
  Independent regimes ~ the 4 crisis clusters + a handful of multi-month commodity
  trends => honest-N ~6-10 regimes, NOT thousands of iid bets. A high in-sample IC-IR
  on 19 correlated assets is fragile; this is the small-N ceiling on commodity factors.

========================================================================================================
GATE SUMMARY:
  [FAIL] fwd rank-IC survives BH-FDR    mom_12_1 q=0.3143, mean_IC=-0.0181
  [FAIL] DSR>=0.90 (headline)           DSR=0.0025
  [PASS] same-sign split-half           {'first': -0.41, 'second': -0.06}
  [FAIL] leave-one-crisis-out           some WEAK
  [FAIL] beats EW-long Sharpe           -0.231 vs +0.636
  [FAIL] beats 200dma Sharpe            -0.231 vs +0.177
  [FAIL] no purged fold flips           [-0.43, -0.54, 0.01, -0.34, 0.37]

VERDICT: DISPLAY/KILLED
  scored requires ALL gates PASS. headline DSR=0.0025 (< 0.90); best-in-grid DSR=0.0026
========================================================================================================
```

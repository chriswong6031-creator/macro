# Diversified vol-targeted commodity TSMOM book — Phase-0

```
====================================================================================================
DIVERSIFIED VOL-TARGETED COMMODITY TSMOM BOOK — Phase-0 (READ-ONLY)
  legs: gold, silver, copper, crude, dollar  (1971-01-04..2026-06-18)
  12-1m sign trend, size=(0.15/rv63) clip[-2.0,2.0], next-bar, 8bps one-way, book=mean(legs); analysis from 2000-12-01
====================================================================================================

### HEADLINE BOOK vs DUMB BASELINES (net of cost, from 2000-12-01)
  TSMOM book (12-1m, vt15)       CAGR= +3.46%  Sharpe=+0.42  MaxDD=  -26.4%  n=6456
  EW-long commodity B&H          CAGR= +4.38%  Sharpe=+0.34  MaxDD=  -81.7%  n=6456
  each-leg 200dma (long/flat)    CAGR= +1.34%  Sharpe=+0.20  MaxDD=  -36.8%  n=6456
  beats EW-long on Sharpe? YES  (+0.423 vs +0.337, margin +0.087)
  beats 200dma on Sharpe?  YES  (+0.423 vs +0.195)
  MaxDD reduction vs EW-long: +55.3pp (book -26.4% vs EW -81.7%)

### PER-LEG STANDALONE (net) — what each sleeve contributes
    leg gold                     CAGR= +6.19%  Sharpe=+0.47  MaxDD=  -55.6%  n=6456
    leg silver                   CAGR= +2.90%  Sharpe=+0.26  MaxDD=  -48.4%  n=6456
    leg copper                   CAGR= +4.30%  Sharpe=+0.35  MaxDD=  -38.3%  n=6456
    leg crude                    CAGR= +1.63%  Sharpe=+0.18  MaxDD=  -52.3%  n=6456
    leg dollar                   CAGR= -1.64%  Sharpe=-0.06  MaxDD=  -60.8%  n=6456

### DEFLATED SHARPE — grid = 3 vol-targets x 4 lookbacks = 12 trials
  grid annual-Sharpes: [0.32, 0.25, 0.41, 0.36, 0.33, 0.25, 0.42, 0.37, 0.33, 0.26, 0.43, 0.39]
  best-in-grid: vt=0.2 lb=252 skip=21  Sharpe=+0.43  (DSR is computed on the HEADLINE 12-1m/vt15, haircut by the 12 trials)
  HEADLINE 12-1m/vt15: SR(ann)=+0.42  SR0(ann,haircut)=+0.33  skew=+0.13  kurt=11.2  T=6456
  DSR = 0.6842  (n_trials=12)  -> FAILS multiple-testing haircut (DSR<0.90)
  BEST-IN-GRID DSR = 0.7032  -> FAILS multiple-testing haircut (DSR<0.90)

### SPLIT-HALF — both halves must beat EW-long on Sharpe (SPEC gate)
  first   (2000-12-01..2013-06-14): book Sharpe=+0.498  EW-long=+0.661  beats=NO
  second  (2013-06-17..2026-06-18): book Sharpe=+0.351  EW-long=+0.118  beats=YES
  -> both-halves-beat-EW = False   same-sign = True

### DRAWDOWN-REDUCTION BOOTSTRAP (paired block=21, B=5000) — CI must EXCLUDE 0
  (book MaxDD - EW MaxDD) 95% CI = [-5.7, 44.5, 72.2] pp   P(book shallower)=0.943
  -> CI excludes 0: False  (overlaps 0)

### BLOCK-BOOTSTRAP 95%% CI on book Sharpe (block=21, B=5000)
  Sharpe 95% CI [0.05, 0.42, 0.8]   MaxDD% 95% CI [-45.8, -26.1, -16.2]   P(Sharpe>0)=0.985

### LEAVE-ONE-CRISIS-OUT — drop each crisis; book must stay > EW-long & keep DD edge
  drop 2008 GFC          : book Sharpe=+0.487 (EW +0.400, d=+0.087)  dMaxDD=+55.3pp  -> holds
  drop 2014-16 oil bust  : book Sharpe=+0.347 (EW +0.410, d=-0.063)  dMaxDD=+51.6pp  -> WEAK
  drop 2020 COVID        : book Sharpe=+0.369 (EW +0.679, d=-0.310)  dMaxDD=+19.0pp  -> WEAK
  drop 2022 bear         : book Sharpe=+0.448 (EW +0.340, d=+0.108)  dMaxDD=+58.2pp  -> holds
  -> leave-one-crisis-out holds on ALL: False

### CRISIS CONVEXITY — cumulative return through each window
  window                    book   EW-long    200dma
  2008 GFC                -10.0%    -23.3%     -7.4%
  2014-16 oil bust         25.5%    -26.5%     -6.7%
  2020 COVID               15.7%    -73.7%     -3.9%
  2022 bear                -2.2%      2.9%      2.0%

### PURGED 5-FOLD CV (embargo=63d) — no fold should flip negative
  fold1: Sharpe=+0.80  (n=1228)
  fold2: Sharpe=+0.32  (n=1228)
  fold3: Sharpe=+0.73  (n=1228)
  fold4: Sharpe=+0.31  (n=1228)
  fold5: Sharpe=+0.05  (n=1229)
  -> no fold flips negative: True

### HONEST-N — independent crisis clusters, not raw rows
  raw daily rows: 6456   span: ~25.5y
  INDEPENDENT trend-regime clusters tested = 4 crises + ~a handful of multi-month commodity up/down regimes => honest-N ~5-8 clusters.
  This is the SAME small-N problem that keeps cross-asset trend a CONFIRMER: the
  drawdown-shaped payoff rides on a handful of crises, not thousands of iid bets.

====================================================================================================
GATE SUMMARY:
  [FAIL] DSR>=0.90 (headline)       DSR=0.6842
  [PASS] beats EW-long Sharpe       +0.423 vs +0.337
  [PASS] beats 200dma Sharpe        +0.423 vs +0.195
  [FAIL] both halves beat EW        {'first': 0.5, 'second': 0.35}
  [FAIL] DD-reduction CI excl 0     [-5.7, 44.5, 72.2]
  [FAIL] leave-one-crisis-out       some WEAK
  [PASS] no purged fold flips       [0.8, 0.32, 0.73, 0.31, 0.05]

VERDICT: CONFIRMER/DISPLAY (DSR 0.6842 < 0.90)
====================================================================================================
```

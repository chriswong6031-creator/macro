# Foreign-index trend de-risk basket — Phase-0

```
==============================================================================
PHASE-0: Foreign-index trend de-risk basket  (trackB)
==============================================================================
cost_bps(one-way)=5.0  cash=local 3m short (0% floor where stale)
variants=['sma200', 'tsmom']  markets=['N225', 'GDAXI', 'FCHI', 'KS11', 'TWII', 'FTSE']

market  var       yrs   netSh  holdSh  netDD%  holdDD%   ddCut   tIn%
------------------------------------------------------------------------------
N225    sma200   61.4   0.566   0.433   -32.7    -81.9   -49.2   63.0
N225    tsmom    60.4   0.505   0.427   -57.7    -81.9   -24.2   64.5
GDAXI   sma200   38.5   0.612   0.492   -35.0    -72.7   -37.7   69.0
GDAXI   tsmom    37.5   0.523   0.468   -45.0    -72.7   -27.7   69.6
FCHI    sma200   36.3   0.421   0.303   -27.7    -65.3   -37.6   62.6
FCHI    tsmom    35.3   0.439   0.311   -44.7    -65.3   -20.6   65.8
KS11    sma200   29.5   0.761   0.464   -40.5    -64.7   -24.2   57.9
KS11    tsmom    28.5   0.568   0.560   -47.5    -55.7    -8.2   62.4
TWII    sma200   29.0   0.535   0.378   -36.1    -66.2   -30.1   63.7
TWII    tsmom    27.9   0.391   0.412   -56.3    -66.2    -9.9   65.6
FTSE    sma200   42.5   0.392   0.411   -39.3    -52.6   -13.2   67.2
FTSE    tsmom    41.5   0.456   0.389   -40.5    -52.6   -12.0   71.1

n_trials (markets x variants, NO cherry-pick) = 12

==============================================================================
POOLED EQUAL-WEIGHT BASKET  (the no-cherry-pick book)
==============================================================================

--- variant=sma200  members=['N225', 'GDAXI', 'FCHI', 'KS11', 'TWII', 'FTSE']  start=1997-07-02  yrs=29.0
  TREND BASKET : Sharpe 0.570  MaxDD -18.5%  CAGR 4.77%  finalx 3.85
  EW buy&hold  : Sharpe 0.384  MaxDD -57.0%  CAGR 4.97%
  flat 60/40   : Sharpe 0.462  MaxDD -36.7%  CAGR 4.01%

--- variant=tsmom  members=['N225', 'GDAXI', 'FCHI', 'KS11', 'TWII', 'FTSE']  start=1998-07-16  yrs=27.9
  TREND BASKET : Sharpe 0.460  MaxDD -33.6%  CAGR 4.38%  finalx 3.31
  EW buy&hold  : Sharpe 0.403  MaxDD -57.0%  CAGR 5.27%
  flat 60/40   : Sharpe 0.475  MaxDD -36.7%  CAGR 4.13%

==============================================================================
GATES  (primary = sma200 pooled basket, all markets)
==============================================================================

[GATE 1] Deflated Sharpe (pooled trend book, n_trials=12)
  DSR=0.9253  SR_ann=0.57  SR0_ann=0.31  T=7535  -> MARGINAL (0.90≤DSR<0.95)

[GATE 2] Drawdown-reduction block-bootstrap CI (trend vs EW buy&hold)
  (DD-reduction in pp = trend_MaxDD - hold_MaxDD; positive = trend tail SHALLOWER)
  DD-reduction (pp) CI [2.5/50/97.5] = [5.9, 25.1, 48.1]  prob(reduction>0) = 0.995  n=7535

[GATE 3] Split-half OOS (trend Sharpe vs buy&hold, both halves same sign)
  first : trendSh 0.58  bhSh 0.05  edge +0.530
  second: trendSh 0.57  bhSh 0.85  edge -0.280
  first MaxDD: trend -14.2%  bh -57.0%  reduction +42.8pp
  second MaxDD: trend -18.5%  bh -32.3%  reduction +13.8pp
  same-sign Sharpe-edge both halves: False  (HONEST: Sharpe edge does NOT survive — 2nd half trend < bh)
  same-sign DD-reduction both halves: True

[GATE 4] Per-crisis WITHIN-WINDOW tail-cut (the honest robustness test)
  (reduction pp = trendDD - bhDD; both<0, trend shallower => positive = overlay cut it)
  FULL-SAMPLE global DD-reduction = +38.5pp
  crisis     trendDD    bhDD  reduction
  Asian97      -10.8   -30.0      +19.2  OK
  Dotcom       -12.9   -53.1      +40.2  OK
  GFC          -10.2   -53.6      +43.4  OK
  COVID         -7.4   -32.3      +24.9  OK
  Bear2022      -8.5   -20.2      +11.7  OK
  -- (global-MaxDD row-deletion LOCO, WEAK metric, shown for transparency):
     drop Asian97  : global DD-reduction = +38.5pp
     drop Dotcom   : global DD-reduction = +35.1pp
     drop GFC      : global DD-reduction = +38.5pp
     drop COVID    : global DD-reduction = +38.9pp
     drop Bear2022 : global DD-reduction = +38.5pp

[GATE 5] Beats DUMB baselines
  trend : Sharpe 0.574  MaxDD -18.5%  CAGR 4.77%
  bh    : Sharpe 0.384  MaxDD -57.0%  CAGR 4.97%
  flat6040: Sharpe 0.462  MaxDD -36.7%  CAGR 4.01%
  beats both on Sharpe: True   cuts DD vs both: True
  POST-2004 (drop the megabear): trend Sh 0.516 DD -18.5%  |  bh Sh 0.560 DD -53.6%
    -> outside the megabear the Sharpe EDGE is gone (trend < bh); DD-cut kept.

[GATE 6] Honest-N
  independent crisis eras IN sample = 5 of 5
  markets = 6  (correlated in crises -> NOT 6 independent bets)
  The tail-cut edge is driven by a handful of shared global crises, not
  6 independent draws. Honest effective-N ~= crisis count, NOT row count.

==============================================================================
GATE SUMMARY
==============================================================================
  [PASS] DSR>=0.90 (pooled)
  [PASS] DD-reduction CI excludes 0
  [PASS] same-sign split-half
  [PASS] leave-one-crisis-out holds
  [PASS] beats dumb baseline
  [PASS] honest-N adequate

  secondary checks (tier-decisive):
  [FAIL] split-half SHARPE edge same-sign (return edge, not just tail)
  [FAIL] Sharpe edge survives dropping the 1998-2003 megabear
  [FAIL] DSR>=0.95 ('survives', vs merely 'marginal')

VERDICT: CONFIRMER (robust TAIL-cut across 5 crises, but Sharpe edge is DSR-marginal + not split-half/megabear-robust -> NOT a scored alpha)
```

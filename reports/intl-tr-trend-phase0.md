# Intl TOTAL-RETURN tradeable trend/macro overlay — Phase-0

```
================================================================================
PHASE-0: Intl TOTAL-RETURN tradeable trend / macro-gated overlay
================================================================================
data = data/intl/_etf_scratch/<TICKER>.parquet (yfinance auto_adjust=True, USD TR)
cost_bps(one-way)=7.0  cash=US 3m T-bill (DGS3MO) on the flat sleeve
trend variants=['sma200', 'tsmom']  macro-gate on ['EWJ', 'EWG', 'EWU', 'EWY', 'EWQ']
ETFs=['EWJ', 'EWG', 'EWU', 'EWY', 'EWA', 'EWQ']

etf   signal      yrs   netSh  holdSh  netDD%  holdDD%   ddCut  netCAGR   hCAGR   tIn%
--------------------------------------------------------------------------------
EWJ   sma200     29.5   0.230   0.270   -51.6    -58.9    -7.2     2.26    3.61   58.7
EWJ   tsmom      29.3   0.514   0.292   -33.1    -58.9   -25.8     6.70    4.13   59.9
EWJ   macro      24.2   0.345   0.386   -46.3    -54.5    -8.1     4.67    6.03   73.9
EWG   sma200     29.5   0.447   0.364   -50.2    -67.6   -17.3     6.01    6.22   65.8
EWG   tsmom      29.3   0.365   0.353   -51.5    -67.6   -16.1     5.03    5.93   65.8
EWG   macro      30.2   0.337   0.367   -58.0    -67.6    -9.6     4.65    6.27   69.1
EWU   sma200     29.5   0.317   0.346   -42.9    -64.0   -21.1     3.47    5.39   66.5
EWU   tsmom      29.3   0.459   0.344   -42.5    -64.0   -21.5     6.02    5.33   64.0
EWU   macro      30.2   0.393   0.372   -29.3    -64.0   -34.7     4.37    5.99   49.1
EWY   sma200     25.3   0.624   0.526   -37.8    -74.1   -36.4    11.61   12.48   61.5
EWY   tsmom      25.1   0.509   0.533   -45.9    -74.1   -28.2     9.43   12.68   63.2
EWY   macro      25.7   0.265   0.504   -79.3    -74.1     5.2     3.54   11.77   66.2
EWA   sma200     29.5   0.293   0.412   -50.3    -67.0   -16.7     3.45    7.65   68.0
EWA   tsmom      29.3   0.306   0.413   -47.7    -67.0   -19.3     4.06    7.67   67.8
EWQ   sma200     29.5   0.386   0.400   -34.0    -61.4   -27.4     4.96    7.07   69.3
EWQ   tsmom      29.3   0.356   0.395   -50.8    -61.4   -10.6     4.82    6.95   65.6
EWQ   macro      30.2   0.421   0.413   -45.4    -61.4   -16.0     6.10    7.38   69.1

n_trials (etf x signal, NO cherry-pick) = 17

================================================================================
PER-ETF / PER-SIGNAL SCORED-BAR CHECK (any single one can score)
================================================================================
  EWJ  sma200 : DSR= 0.280 beatsSharpe=0 cutsDD=1 sh-half(Sharpe)=0 DD-CI>0=0 post2010Sh=0 -> no
  EWJ  tsmom  : DSR= 0.824 beatsSharpe=1 cutsDD=1 sh-half(Sharpe)=0 DD-CI>0=1 post2010Sh=0 -> no
  EWJ  macro  : DSR= 0.448 beatsSharpe=0 cutsDD=1 sh-half(Sharpe)=0 DD-CI>0=0 post2010Sh=0 -> no
  EWG  sma200 : DSR= 0.719 beatsSharpe=1 cutsDD=1 sh-half(Sharpe)=1 DD-CI>0=0 post2010Sh=1 -> no
  EWG  tsmom  : DSR= 0.552 beatsSharpe=1 cutsDD=1 sh-half(Sharpe)=0 DD-CI>0=0 post2010Sh=0 -> no
  EWG  macro  : DSR= 0.506 beatsSharpe=0 cutsDD=1 sh-half(Sharpe)=0 DD-CI>0=0 post2010Sh=0 -> no
  EWU  sma200 : DSR= 0.451 beatsSharpe=0 cutsDD=1 sh-half(Sharpe)=0 DD-CI>0=0 post2010Sh=0 -> no
  EWU  tsmom  : DSR= 0.735 beatsSharpe=1 cutsDD=1 sh-half(Sharpe)=0 DD-CI>0=0 post2010Sh=0 -> no
  EWU  macro  : DSR= 0.624 beatsSharpe=1 cutsDD=1 sh-half(Sharpe)=0 DD-CI>0=0 post2010Sh=0 -> no
  EWY  sma200 : DSR= 0.903 beatsSharpe=1 cutsDD=1 sh-half(Sharpe)=1 DD-CI>0=0 post2010Sh=1 -> no
  EWY  tsmom  : DSR= 0.758 beatsSharpe=0 cutsDD=1 sh-half(Sharpe)=0 DD-CI>0=0 post2010Sh=0 -> no
  EWY  macro  : DSR= 0.312 beatsSharpe=0 cutsDD=0 sh-half(Sharpe)=0 DD-CI>0=0 post2010Sh=0 -> no
  EWA  sma200 : DSR= 0.403 beatsSharpe=0 cutsDD=1 sh-half(Sharpe)=0 DD-CI>0=0 post2010Sh=0 -> no
  EWA  tsmom  : DSR= 0.427 beatsSharpe=0 cutsDD=1 sh-half(Sharpe)=0 DD-CI>0=0 post2010Sh=0 -> no
  EWQ  sma200 : DSR= 0.600 beatsSharpe=0 cutsDD=1 sh-half(Sharpe)=0 DD-CI>0=0 post2010Sh=0 -> no
  EWQ  tsmom  : DSR= 0.533 beatsSharpe=0 cutsDD=1 sh-half(Sharpe)=0 DD-CI>0=0 post2010Sh=0 -> no
  EWQ  macro  : DSR= 0.679 beatsSharpe=1 cutsDD=1 sh-half(Sharpe)=0 DD-CI>0=0 post2010Sh=0 -> no

  any single ETF/signal clears the FULL per-ETF SCORED bar? False
  (full bar = DSR>=0.90 AND same-sign split-half Sharpe AND beats buy&hold Sharpe
   AND single-market DD-reduction CI excludes 0 AND Sharpe edge survives post-2010)

================================================================================
POOLED EQUAL-WEIGHT BASKETS
================================================================================

--- trend/sma200  members=['EWJ', 'EWG', 'EWU', 'EWY', 'EWA', 'EWQ']  start=2001-02-27  yrs=25.3
  STRAT     : Sharpe 0.580  MaxDD -23.9%  CAGR 6.42%  finalx 4.83
  EW buy&hold: Sharpe 0.454  MaxDD -61.9%  CAGR 7.91%
  flat 60/40 : Sharpe 0.508  MaxDD -41.4%  CAGR 6.06%

--- trend/tsmom  members=['EWJ', 'EWG', 'EWU', 'EWY', 'EWA', 'EWQ']  start=2001-05-14  yrs=25.1
  STRAT     : Sharpe 0.490  MaxDD -40.2%  CAGR 6.09%  finalx 4.41
  EW buy&hold: Sharpe 0.458  MaxDD -61.9%  CAGR 7.99%
  flat 60/40 : Sharpe 0.511  MaxDD -41.4%  CAGR 6.10%

--- macro/curve-gate  members=['EWJ', 'EWG', 'EWU', 'EWY', 'EWQ']  start=2002-04-01  yrs=24.2
  STRAT     : Sharpe 0.410  MaxDD -39.0%  CAGR 4.63%  finalx 2.99
  EW buy&hold: Sharpe 0.453  MaxDD -61.3%  CAGR 7.90%
  flat 60/40 : Sharpe 0.506  MaxDD -40.9%  CAGR 6.03%

================================================================================
GATES  (primary = trend/sma200 pooled basket, all 6 ETFs)
================================================================================

[GATE 1] DSR (pooled, n_trials=17)
  DSR=0.8478  SR_ann=0.58  SR0_ann=0.37  T=6364  -> FAILS multiple-testing haircut (DSR<0.90)

[GATE 2] Drawdown-reduction block-bootstrap CI (strat vs EW buy&hold)
  DD-reduction(pp) CI[2.5/50/97.5]=[6.2, 25.8, 50.4]  prob(>0)=0.996  n=6364

[GATE 3] Split-half OOS
  first : strat 0.68  bh 0.44  edge +0.240
  second: strat 0.46  bh 0.48  edge -0.020
  first MaxDD: strat -22.9%  bh -61.9%  reduction +39.0pp
  second MaxDD: strat -23.9%  bh -40.3%  reduction +16.4pp
  same-sign Sharpe-edge both halves: False
  same-sign DD-reduction both halves: True

[GATE 4] Leave-one-crisis-out {GFC,EuroDebt,COVID,Bear2022} + within-window cut
  FULL-SAMPLE global DD-reduction = +38.0pp
  crisis     stratDD    bhDD  reduction
  Dotcom       -11.9   -29.1      +17.2  OK (non-LOCO)
  GFC          -17.7   -61.9      +44.2  OK
  EuroDebt     -15.7   -28.8      +13.2  OK
  COVID         -8.1   -37.2      +29.1  OK
  Bear2022      -6.7   -30.2      +23.4  OK
  -- global-MaxDD row-deletion LOCO (drop each crisis, recompute global DD-reduction):
     drop GFC      : global DD-reduction = +16.4pp  OK
     drop EuroDebt : global DD-reduction = +38.0pp  OK
     drop COVID    : global DD-reduction = +38.0pp  OK
     drop Bear2022 : global DD-reduction = +38.0pp  OK

[GATE 5] Beats DUMB baselines (Sharpe AND MaxDD vs buy&hold + flat-60/40)
  strat : Sharpe 0.575  MaxDD -23.9%  CAGR 6.42%
  bh    : Sharpe 0.454  MaxDD -61.9%  CAGR 7.91%
  flat6040: Sharpe 0.508  MaxDD -41.4%  CAGR 6.06%
  beats both on Sharpe: True   cuts DD vs both: True
  POST-2010 (drop GFC): strat Sh 0.393 DD -23.9%  |  bh Sh 0.480 DD -40.3%

[GATE 6] Honest-N
  independent crisis eras IN sample = 5 of 5
  members correlated in crises -> NOT independent bets; effective-N ~= crisis count

  GATE SUMMARY:
    [FAIL] DSR>=0.90 (pooled)
    [PASS] DD-reduction CI excludes 0
    [PASS] same-sign split-half (DD)
    [PASS] leave-one-crisis-out holds
    [PASS] beats dumb baseline
    [PASS] honest-N adequate
  secondary: split-half SHARPE edge same-sign = False  |  Sharpe survives post-2010 = False  |  DSR>=0.95 = False

================================================================================
GATES  (secondary pooled = trend/tsmom)
================================================================================

[GATE 1] DSR (pooled, n_trials=17)
  DSR=0.7139  SR_ann=0.49  SR0_ann=0.37  T=6311  -> FAILS multiple-testing haircut (DSR<0.90)

[GATE 2] Drawdown-reduction block-bootstrap CI (strat vs EW buy&hold)
  DD-reduction(pp) CI[2.5/50/97.5]=[-5.9, 13.3, 40.7]  prob(>0)=0.898  n=6311

[GATE 3] Split-half OOS
  first : strat 0.67  bh 0.45  edge +0.220
  second: strat 0.28  bh 0.49  edge -0.210
  first MaxDD: strat -25.7%  bh -61.9%  reduction +36.2pp
  second MaxDD: strat -40.2%  bh -40.3%  reduction +0.1pp
  same-sign Sharpe-edge both halves: False
  same-sign DD-reduction both halves: True

[GATE 4] Leave-one-crisis-out {GFC,EuroDebt,COVID,Bear2022} + within-window cut
  FULL-SAMPLE global DD-reduction = +21.7pp
  crisis     stratDD    bhDD  reduction
  Dotcom       -10.0   -29.1      +19.1  OK (non-LOCO)
  GFC          -19.7   -61.9      +42.2  OK
  EuroDebt     -23.9   -28.8       +4.9  OK
  COVID        -36.7   -37.2       +0.5  OK
  Bear2022     -10.4   -30.2      +19.8  OK
  -- global-MaxDD row-deletion LOCO (drop each crisis, recompute global DD-reduction):
     drop GFC      : global DD-reduction = +0.1pp  OK
     drop EuroDebt : global DD-reduction = +21.7pp  OK
     drop COVID    : global DD-reduction = +36.2pp  OK
     drop Bear2022 : global DD-reduction = +21.7pp  OK

[GATE 5] Beats DUMB baselines (Sharpe AND MaxDD vs buy&hold + flat-60/40)
  strat : Sharpe 0.488  MaxDD -40.2%  CAGR 6.09%
  bh    : Sharpe 0.458  MaxDD -61.9%  CAGR 7.99%
  flat6040: Sharpe 0.511  MaxDD -41.4%  CAGR 6.10%
  beats both on Sharpe: False   cuts DD vs both: True
  POST-2010 (drop GFC): strat Sh 0.299 DD -40.2%  |  bh Sh 0.480 DD -40.3%

[GATE 6] Honest-N
  independent crisis eras IN sample = 5 of 5
  members correlated in crises -> NOT independent bets; effective-N ~= crisis count

  GATE SUMMARY:
    [FAIL] DSR>=0.90 (pooled)
    [FAIL] DD-reduction CI excludes 0
    [PASS] same-sign split-half (DD)
    [PASS] leave-one-crisis-out holds
    [FAIL] beats dumb baseline
    [PASS] honest-N adequate
  secondary: split-half SHARPE edge same-sign = False  |  Sharpe survives post-2010 = False  |  DSR>=0.95 = False

================================================================================
GATES  (secondary pooled = macro/curve-gate, 4 ETFs)
================================================================================

[GATE 1] DSR (pooled, n_trials=17)
  DSR=0.5708  SR_ann=0.41  SR0_ann=0.37  T=6094  -> FAILS multiple-testing haircut (DSR<0.90)

[GATE 2] Drawdown-reduction block-bootstrap CI (strat vs EW buy&hold)
  DD-reduction(pp) CI[2.5/50/97.5]=[1.6, 18.8, 39.3]  prob(>0)=0.985  n=6094

[GATE 3] Split-half OOS
  first : strat 0.4  bh 0.42  edge -0.020
  second: strat 0.41  bh 0.51  edge -0.100
  first MaxDD: strat -26.7%  bh -61.3%  reduction +34.6pp
  second MaxDD: strat -39.0%  bh -40.3%  reduction +1.3pp
  same-sign Sharpe-edge both halves: False
  same-sign DD-reduction both halves: True

[GATE 4] Leave-one-crisis-out {GFC,EuroDebt,COVID,Bear2022} + within-window cut
  FULL-SAMPLE global DD-reduction = +22.3pp
  crisis     stratDD    bhDD  reduction
  Dotcom       -22.8   -31.5       +8.7  OK (non-LOCO)
  GFC          -21.4   -61.3      +39.9  OK
  EuroDebt     -14.9   -28.8      +13.9  OK
  COVID        -19.0   -35.8      +16.7  OK
  Bear2022     -32.3   -32.3       +0.0  FAIL
  -- global-MaxDD row-deletion LOCO (drop each crisis, recompute global DD-reduction):
     drop GFC      : global DD-reduction = +1.3pp  OK
     drop EuroDebt : global DD-reduction = +22.3pp  OK
     drop COVID    : global DD-reduction = +24.3pp  OK
     drop Bear2022 : global DD-reduction = +34.6pp  OK

[GATE 5] Beats DUMB baselines (Sharpe AND MaxDD vs buy&hold + flat-60/40)
  strat : Sharpe 0.410  MaxDD -39.0%  CAGR 4.63%
  bh    : Sharpe 0.453  MaxDD -61.3%  CAGR 7.90%
  flat6040: Sharpe 0.506  MaxDD -40.9%  CAGR 6.03%
  beats both on Sharpe: False   cuts DD vs both: True
  POST-2010 (drop GFC): strat Sh 0.417 DD -39.0%  |  bh Sh 0.494 DD -40.3%

[GATE 6] Honest-N
  independent crisis eras IN sample = 5 of 5
  members correlated in crises -> NOT independent bets; effective-N ~= crisis count

  GATE SUMMARY:
    [FAIL] DSR>=0.90 (pooled)
    [PASS] DD-reduction CI excludes 0
    [PASS] same-sign split-half (DD)
    [FAIL] leave-one-crisis-out holds
    [FAIL] beats dumb baseline
    [PASS] honest-N adequate
  secondary: split-half SHARPE edge same-sign = False  |  Sharpe survives post-2010 = False  |  DSR>=0.95 = False

================================================================================
FINAL VERDICT
================================================================================
  [trend/sma200 pooled] gates={'DSR>=0.90 (pooled)': 0, 'DD-reduction CI excludes 0': 1, 'same-sign split-half (DD)': 1, 'leave-one-crisis-out holds': 1, 'beats dumb baseline': 1, 'honest-N adequate': 1}
           DSR=0.8478 ss_sharpe=0 g5_post=0 -> CONFIRMER
  [trend/tsmom pooled] gates={'DSR>=0.90 (pooled)': 0, 'DD-reduction CI excludes 0': 0, 'same-sign split-half (DD)': 1, 'leave-one-crisis-out holds': 1, 'beats dumb baseline': 0, 'honest-N adequate': 1}
           DSR=0.7139 ss_sharpe=0 g5_post=0 -> KILLED
  [macro/curve pooled] gates={'DSR>=0.90 (pooled)': 0, 'DD-reduction CI excludes 0': 1, 'same-sign split-half (DD)': 1, 'leave-one-crisis-out holds': 0, 'beats dumb baseline': 0, 'honest-N adequate': 1}
           DSR=0.5708 ss_sharpe=0 g5_post=0 -> DISPLAY

  vs PRICE-INDEX version (intl-trend-overlay-phase0): CONFIRMER
     (tail-cut robust across crises, but Sharpe edge DSR-marginal + not
      split-half/megabear-robust).

  OVERALL (best archetype) = CONFIRMER
  per-archetype: {'trend/sma200': 'CONFIRMER', 'trend/tsmom': 'KILLED', 'macro/curve': 'DISPLAY'}
  any single ETF scored: False
```

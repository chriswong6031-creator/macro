```
####################################################################################################
INTERNATIONAL MACRO-TIMED EQUITY SLEEVES (JP/EZ/GB/KR) — Phase-0
  port of S&P/Macro Vector (long/flat equity-vs-bills, scored on Sharpe+MaxDD reduction)
  macro lag = +1m publication; cost = 3.0bps one-way; cash = local short_3m
####################################################################################################

====================================================================================================
[JP]  px=_N225  window=2002-05-01 -> 2026-06-18  legs_have={c:1 s:1 sh:1}
====================================================================================================
  buy & hold (no cash)     CAGR= +8.09%  Sharpe=+0.45  MaxDD=  -61.4%  n=5907
  200dma long/flat         CAGR= +5.12%  Sharpe=+0.41  MaxDD=  -32.2%  n=5907
  DUMB curve-inv gate      CAGR= +6.63%  Sharpe=+0.41  MaxDD=  -61.4%  n=5907
  MACRO composite          CAGR= +6.45%  Sharpe=+0.45  MaxDD=  -48.2%  n=5907
  composite de-risked time-in-flat ~ 53.2% of days
  split-half Sharpe +0.27 / +0.70  same-sign=YES
  beats DUMB curve gate (Sharpe&DD)=True   beats 200dma=False   shallower-DD-than-B&H=True
  leave-one-crisis-out (composite vs B&H, DD-edge must persist):
    drop dotcom_00    compSharpe=+0.55  compDD= -48.2%  bhDD= -61.4%  edge-holds=True
    drop gfc_08       compSharpe=+0.65  compDD= -33.6%  bhDD= -36.5%  edge-holds=True
    drop covid_20     compSharpe=+0.48  compDD= -48.2%  bhDD= -61.4%  edge-holds=True
    drop rate_22      compSharpe=+0.46  compDD= -48.2%  bhDD= -61.4%  edge-holds=True

====================================================================================================
[EZ]  px=_GDAXI (fallback, longer)  window=1994-02-01 -> 2026-06-17  legs_have={c:1 s:1 sh:1}
====================================================================================================
  buy & hold (no cash)     CAGR= +7.75%  Sharpe=+0.45  MaxDD=  -72.7%  n=8203
  200dma long/flat         CAGR= +8.15%  Sharpe=+0.63  MaxDD=  -34.6%  n=8203
  DUMB curve-inv gate      CAGR= +8.81%  Sharpe=+0.51  MaxDD=  -72.7%  n=8203
  MACRO composite          CAGR= +6.20%  Sharpe=+0.43  MaxDD=  -66.9%  n=8203
  composite de-risked time-in-flat ~ 53.4% of days
  split-half Sharpe +0.44 / +0.44  same-sign=YES
  beats DUMB curve gate (Sharpe&DD)=False   beats 200dma=False   shallower-DD-than-B&H=True
  leave-one-crisis-out (composite vs B&H, DD-edge must persist):
    drop gfc_08       compSharpe=+0.46  compDD= -66.9%  bhDD= -72.7%  edge-holds=True
    drop eurozone_11  compSharpe=+0.46  compDD= -66.9%  bhDD= -72.7%  edge-holds=True
    drop covid_20     compSharpe=+0.50  compDD= -66.9%  bhDD= -72.7%  edge-holds=True
    drop rate_22      compSharpe=+0.46  compDD= -66.9%  bhDD= -72.7%  edge-holds=True

====================================================================================================
[GB]  px=_FTSE  window=1984-01-03 -> 2026-06-17  legs_have={c:1 s:1 sh:1}
====================================================================================================
  buy & hold (no cash)     CAGR= +5.69%  Sharpe=+0.41  MaxDD=  -52.6%  n=10724
  200dma long/flat         CAGR= +3.95%  Sharpe=+0.42  MaxDD=  -36.5%  n=10724
  DUMB curve-inv gate      CAGR= +6.85%  Sharpe=+0.60  MaxDD=  -38.8%  n=10724
  MACRO composite          CAGR= +5.28%  Sharpe=+0.53  MaxDD=  -40.2%  n=10724
  composite de-risked time-in-flat ~ 72.1% of days
  split-half Sharpe +0.63 / +0.42  same-sign=YES
  beats DUMB curve gate (Sharpe&DD)=False   beats 200dma=False   shallower-DD-than-B&H=True
  leave-one-crisis-out (composite vs B&H, DD-edge must persist):
    drop dotcom_00    compSharpe=+0.71  compDD= -34.4%  bhDD= -47.8%  edge-holds=True
    drop gfc_08       compSharpe=+0.56  compDD= -40.2%  bhDD= -52.6%  edge-holds=True
    drop covid_20     compSharpe=+0.58  compDD= -40.2%  bhDD= -52.6%  edge-holds=True
    drop rate_22      compSharpe=+0.53  compDD= -40.2%  bhDD= -52.6%  edge-holds=True

====================================================================================================
[KR]  px=_KS11  window=1996-12-11 -> 2026-06-18  legs_have={c:1 s:1 sh:1}
====================================================================================================
  buy & hold (no cash)     CAGR= +9.20%  Sharpe=+0.46  MaxDD=  -64.7%  n=7265
  200dma long/flat         CAGR=+11.98%  Sharpe=+0.75  MaxDD=  -38.9%  n=7265
  DUMB curve-inv gate      CAGR= +9.48%  Sharpe=+0.48  MaxDD=  -64.7%  n=7265
  MACRO composite          CAGR= +9.62%  Sharpe=+0.56  MaxDD=  -56.6%  n=7265
  composite de-risked time-in-flat ~ 50.2% of days
  split-half Sharpe +0.49 / +0.75  same-sign=YES
  beats DUMB curve gate (Sharpe&DD)=True   beats 200dma=False   shallower-DD-than-B&H=True
  leave-one-crisis-out (composite vs B&H, DD-edge must persist):
    drop dotcom_00    compSharpe=+0.74  compDD= -40.2%  bhDD= -64.7%  edge-holds=True
    drop gfc_08       compSharpe=+0.62  compDD= -56.6%  bhDD= -64.7%  edge-holds=True
    drop covid_20     compSharpe=+0.62  compDD= -56.6%  bhDD= -64.7%  edge-holds=True
    drop rate_22      compSharpe=+0.59  compDD= -56.6%  bhDD= -64.7%  edge-holds=True

====================================================================================================
### DEFLATED SHARPE (per market) — n_trials = 4 markets x 3 variants = 12
====================================================================================================
  [JP] DSR=0.6873 (FAILS multiple-testing haircut (DSR<0.90))  SR_ann=+0.45  SR0_ann=+0.35
  [EZ] DSR=0.7885 (FAILS multiple-testing haircut (DSR<0.90))  SR_ann=+0.43  SR0_ann=+0.29
  [GB] DSR=0.9571 (SURVIVES multiple-testing (DSR≥0.95))  SR_ann=+0.53  SR0_ann=+0.26
  [KR] DSR=0.9099 (MARGINAL (0.90≤DSR<0.95))  SR_ann=+0.56  SR0_ann=+0.31

====================================================================================================
### POOLED 'Intl Macro Vector' — equal-RISK (inverse-vol) across the 4 markets
====================================================================================================
  pooled B&H (eq-risk)     CAGR= +7.36%  Sharpe=+0.56  MaxDD=  -55.4%  n=10932
  pooled 200dma (eq-risk)  CAGR= +6.95%  Sharpe=+0.80  MaxDD=  -19.6%  n=10932
  pooled DUMB curve (eq-risk) CAGR= +8.07%  Sharpe=+0.78  MaxDD=  -42.5%  n=10932
  pooled MACRO (eq-risk)   CAGR= +6.80%  Sharpe=+0.72  MaxDD=  -39.2%  n=10932
  pooled split-half Sharpe +0.70 / +0.76  same-sign=YES
  pooled DSR=0.9978 (SURVIVES multiple-testing (DSR≥0.95))  SR_ann=+0.72
  pooled Sharpe 95% CI [0.35, 0.73, 1.1]  MaxDD 95% CI [-55.8, -34.9, -19.7]%
  pooled shallower-DD-than-eqrisk-B&H = True   beats 200dma (Sharpe&DD)=False   beats DUMB curve=False

====================================================================================================
### VERDICTS (scored requires: DSR>=0.90 AND same-sign split-half AND beats DUMB curve
###   AND beats 200dma AND leave-one-crisis-out holds AND honest-N >= 3 crises)
====================================================================================================
  [JP] CONFIRMER  (DSR=0.687)
        FAIL  DSR>=0.90
        PASS  same-sign split
        PASS  beats DUMB curve
        FAIL  beats 200dma
        PASS  LOCO holds
        PASS  honest-N>=3
  [EZ] CONFIRMER  (DSR=0.788)
        FAIL  DSR>=0.90
        PASS  same-sign split
        FAIL  beats DUMB curve
        FAIL  beats 200dma
        PASS  LOCO holds
        PASS  honest-N>=3
  [GB] CONFIRMER  (DSR=0.957)
        PASS  DSR>=0.90
        PASS  same-sign split
        FAIL  beats DUMB curve
        FAIL  beats 200dma
        PASS  LOCO holds
        PASS  honest-N>=3
  [KR] CONFIRMER  (DSR=0.910)
        PASS  DSR>=0.90
        PASS  same-sign split
        PASS  beats DUMB curve
        FAIL  beats 200dma
        PASS  LOCO holds
        PASS  honest-N>=3
  [POOLED] CONFIRMER  (DSR=0.998)
        PASS  DSR>=0.90
        PASS  same-sign split
        FAIL  beats DUMB curve
        FAIL  beats 200dma
        PASS  shallower-DD-than-B&H

====================================================================================================
READ-ME: a macro-timer SCORES only as a Sharpe+MaxDD-reduction tail-insurance sleeve that
  survives the multiple-testing haircut AND adds over the dumb curve-inversion gate AND
  does not hinge on a single crisis. With ~3-5 independent bears/market, honest-N is the
  binding constraint — most ports land CONFIRMER (real DD relief, but the edge is fragile).
====================================================================================================
```

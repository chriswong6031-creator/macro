# NAAIM Exposure Trend-Following Drawdown Overlay — Phase-0

Sample: 2006-07-12 -> 2026-06-17  (5015 trading days, NAAIM weekly n=1040)

Cost: 2.0 bps one-way; flat sleeve earns DFF.  Signal lag: last NAAIM print >= 7d before t, ffilled.


## Headline (net of cost)

```
strategy               CAGR%  Sharpe   MaxDD%    mult   yrs
NAAIM overlay           7.97   0.784    -20.2    4.61  19.9
SPY B&H                11.31   0.649    -55.2    8.47  19.9
200dma long/cash        8.67   0.779    -20.6    5.25  19.9
```

Sharpe: overlay 0.784 vs B&H 0.649 (BEATS) vs 200dma 0.779 (BEATS)
MaxDD: overlay -20.2 vs B&H -55.2 (DD-reduction +35.0pp) vs 200dma -20.6 (DD-reduction +0.4pp)

Spearman(NAAIM z, fwd-63d drawdown) = +0.218  (+ve => high exposure precedes SHALLOWER drawdowns = trend-following sign)

## GATE 1 — block-bootstrap CI on MaxDD reduction (overlay vs B&H)

```
DD-reduction (overlay MaxDD - B&H MaxDD; +ve=overlay shallower), bootstrap 95% CI (pp): [+7.0, +17.6, +34.2]
P(overlay DD shallower than B&H) = 1.000
GATE 1: PASS (CI excludes 0)
```

vs 200dma: DD-reduction 95% CI (pp): [-5.7, +4.0, +16.0]  P(shallower)=0.804  CI includes 0

## GATE 2 — split-half OOS (same-sign DD reduction in BOTH halves)

```
first   overlay MaxDD   -20.2  B&H MaxDD   -55.2  DD-reduction  +35.0pp  Sharpe 0.54 vs 0.43
second  overlay MaxDD   -17.9  B&H MaxDD   -33.7  DD-reduction  +15.8pp  Sharpe 0.99 vs 0.90
GATE 2: PASS (both halves same-sign positive DD-reduction)
```

## GATE 3 — leave-one-crisis-out {2008, 2020, 2022}

Re-measure overlay vs B&H DD-reduction with each crisis window EXCISED from the return path.

```
excised     overlay MaxDD   B&H MaxDD   DD-red pp  ov Sharpe  bh Sharpe
-2008               -17.9       -33.7        15.8       0.93       0.94
-2020               -20.2       -55.2        35.0       0.86       0.70
-2022               -20.2       -55.2        35.0       0.90       0.74
(full)              -20.2       -55.2        35.0       0.78       0.65
GATE 3: PASS (DD-reduction stays positive with each single crisis removed)
  edge concentration: full DD-red +35.0pp -> without 2008 +15.8pp (LEANS HEAVILY on 2008)
```

## GATE 4 — Deflated Sharpe (counting exposure-cutoff variants as trials)

```
variant                   Sharpe   MaxDD%
continuous NAAIM/100       0.784    -20.2  <- headline
binary cutoff>=30          0.741    -28.1
binary cutoff>=40          0.749    -23.8
binary cutoff>=50          0.727    -21.3
binary cutoff>=60          0.457    -28.2
half-derisk<40             0.743    -36.2
half-derisk<50             0.741    -36.4

N trials counted: 7   winner: continuous NAAIM/100
DSR(continuous overlay) = 0.9799  (sr_ann 0.78 vs haircut sr0_ann 0.32)
  SURVIVES multiple-testing (DSR≥0.95)
GATE 4: PASS (DSR >= 0.90)
```

## GATE 5 — beats the DUMB 200dma baseline (paired bootstrap, not point estimate)

```
Sharpe diff (overlay - 200dma), 95% CI: [-0.244, +0.008, +0.260]
P(overlay Sharpe > 200dma Sharpe) = 0.521
point estimate: overlay 0.784 vs 200dma 0.779 (+0.005)
GATE 5: FAIL (Sharpe-diff CI vs the dumb baseline excludes 0)
  ==> overlay does NOT reliably beat the free 200dma SMA on risk-adjusted return; the edge is a coin flip
  CAGR: overlay 7.97% LOSES to 200dma 8.67% and gives up 3.3pp/yr vs B&H (4.61x vs B&H 8.47x final wealth)
```

## Honest-N

The overlay's job is drawdown reduction in crises. INDEPENDENT crisis episodes in-sample (not the ~1040 weekly rows):
  2007-09 GFC, 2011 EU/US-downgrade, 2015-16 China/oil, 2018-Q4, 2020 COVID, 2022 rate shock, 2025 tariff  ~= 6-7 independent drawdown clusters.
That is the real sample size for the DD-reduction claim — small.

## VERDICT

**TIER: CONFIRMER**

Gate summary:
  beats B&H Sharpe (pt):   True
  beats 200dma Sharpe (pt):True  (but bootstrap CI includes 0 -> not reliable, see GATE 5)
  beats B&H MaxDD:         True (+35.0pp)
  beats 200dma MaxDD:      True (+0.4pp, i.e. ~tie)
  GATE 1 bootstrap DD-CI:  PASS (vs B&H)
  GATE 2 split-half:       PASS
  GATE 3 leave-1-crisis:   PASS (leans on 2008: True)
  GATE 4 DSR>=0.90:        PASS (DSR=0.9799)
  GATE 5 beats dumb basel: FAIL (Sharpe-diff vs 200dma CI excludes 0)

HONEST READ: the overlay is a genuine DRAWDOWN-REDUCTION sleeve vs buy-&-hold (-55% -> -20% MaxDD, bootstrap-significant), but it does NOT beat the free 200dma trend rule (Sharpe-diff CI straddles 0, P=0.52; it LOSES on CAGR 7.97 vs 8.67), and removing 2008 erases its Sharpe edge over B&H. NAAIM is just a noisy weekly proxy for the same trend a daily SMA captures more cheaply. Lead with drawdown-reduction; never market it as alpha.
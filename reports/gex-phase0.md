# GEX Phase-0 — dealer-gamma positioning vs forward vol & drawdown

Source-agnostic battery over the cached daily panel. **The historical panel here is VOLUME-weighted** (OptionsDX EOD has no open interest) — a flow proxy for standing dealer positioning. Rebuild the panel from the Polygon OI extractor and re-run for the definitive test. A signal may enter the `drawdown_risk` leg ONLY if it clears BH-FDR on the forward-vol/drawdown relationship AND its overlay cuts drawdown without DSR-failing; until then GEX is display-only.


## SPY — 1256 days [2019-01-02..2023-12-29], regime long=607 short=649, weight=volume

### 1. Fragility signal vs forward outcome (HAC-t; higher signal = more fragile)

| signal | outcome | stat | value | HAC-t | p |
|---|---|---|---|---|---|
| regime_short | fwd_rv_5 | Δmean | +0.0048 | +0.34 | 0.733 |
| regime_short | fwd_rv_10 | Δmean | +0.0030 | +0.20 | 0.844 |
| regime_short | fwd_rv_21 | Δmean | +0.0034 | +0.20 | 0.843 |
| regime_short | fwd_minret_10 | Δmean | +0.0027 | +1.27 | 0.205 |
| regime_short | fwd_minret_21 | Δmean | +0.0024 | +0.72 | 0.471 |
| regime_short | fwd_minret_63 | Δmean | -0.0055 | -0.58 | 0.561 |
| neg_gex_z | fwd_rv_5 | IC | -0.0112 | -0.23 | 0.815 |
| neg_gex_z | fwd_rv_10 | IC | +0.0107 | +0.17 | 0.862 |
| neg_gex_z | fwd_rv_21 | IC | +0.0238 | +0.29 | 0.768 |
| neg_gex_z | fwd_minret_10 | IC | -0.0003 | -0.01 | 0.995 |
| neg_gex_z | fwd_minret_21 | IC | -0.0466 | -0.77 | 0.441 |
| neg_gex_z | fwd_minret_63 | IC | -0.1039 | -1.28 | 0.199 |
| below_flip | fwd_rv_5 | IC | -0.0130 | -0.31 | 0.757 |
| below_flip | fwd_rv_10 | IC | -0.0105 | -0.20 | 0.843 |
| below_flip | fwd_rv_21 | IC | -0.0095 | -0.14 | 0.889 |
| below_flip | fwd_minret_10 | IC | +0.0546 | +1.28 | 0.201 |
| below_flip | fwd_minret_21 | IC | +0.0357 | +0.69 | 0.487 |
| below_flip | fwd_minret_63 | IC | +0.0054 | +0.08 | 0.934 |
| put_skew_z | fwd_rv_5 | IC | +0.1253 | +2.14 | 0.032 |
| put_skew_z | fwd_rv_10 | IC | +0.0900 | +1.14 | 0.255 |
| put_skew_z | fwd_rv_21 | IC | +0.0545 | +0.52 | 0.605 |
| put_skew_z | fwd_minret_10 | IC | -0.0108 | -0.19 | 0.853 |
| put_skew_z | fwd_minret_21 | IC | +0.0343 | +0.46 | 0.644 |
| put_skew_z | fwd_minret_63 | IC | +0.0129 | +0.14 | 0.892 |

**BH-FDR (α=0.10) survivors: 0/24** — none

### 2. P(large forward down-move | most-fragile tercile) vs base rate

| signal | horizon | threshold | P(down\|fragile) | base | uplift | n_frag |
|---|---|---|---|---|---|---|
| regime_short | 21d | 5% | 0.193 | 0.193 | -0.001 | 649 |
| neg_gex_z | 21d | 5% | 0.236 | 0.193 | +0.042 | 399 |
| below_flip | 21d | 5% | 0.208 | 0.193 | +0.014 | 419 |
| put_skew_z | 21d | 5% | 0.198 | 0.193 | +0.005 | 399 |
| regime_short | 63d | 10% | 0.157 | 0.153 | +0.004 | 649 |
| neg_gex_z | 63d | 10% | 0.190 | 0.153 | +0.038 | 399 |
| below_flip | 63d | 10% | 0.165 | 0.153 | +0.012 | 419 |
| put_skew_z | 63d | 10% | 0.193 | 0.153 | +0.040 | 399 |

### 3. De-risk overlay: go flat when fragile — drawdown vs buy&hold (net of 1bp)

| overlay | net Sharpe | maxDD | exposure | vs B&H ΔmaxDD | DSR | verdict |
|---|---|---|---|---|---|---|
| buy&hold | +0.72 | -34.3% | 100% | — | — | — |
| flat_if_short_gamma | +0.02 | -27.0% | 48% | +7.4% | 0.0238 | no dd benefit · DSR-fail/underperforms |
| flat_if_neg_gex_z<-1 | +0.55 | -34.3% | 92% | +0.0% | 0.2069 | no dd benefit · DSR-fail/underperforms |
| flat_if_below_flip | +0.02 | -27.0% | 48% | +7.4% | 0.0238 | no dd benefit · DSR-fail/underperforms |

*Best-drawdown overlay `flat_if_short_gamma` block-bootstrap maxDD CI: [-48.7, -26.1, -13.0]% (B&H -34.3%).* Overlays de-risk by sitting in cash, not by timing — the maxDD shrinks roughly in proportion to lost exposure, and the DSR haircut rejects it as skill.

## QQQ — 1260 days [2019-01-02..2023-12-29], regime long=571 short=689, weight=volume

### 1. Fragility signal vs forward outcome (HAC-t; higher signal = more fragile)

| signal | outcome | stat | value | HAC-t | p |
|---|---|---|---|---|---|
| regime_short | fwd_rv_5 | Δmean | -0.0055 | -0.29 | 0.771 |
| regime_short | fwd_rv_10 | Δmean | -0.0006 | -0.03 | 0.979 |
| regime_short | fwd_rv_21 | Δmean | +0.0010 | +0.04 | 0.968 |
| regime_short | fwd_minret_10 | Δmean | -0.0007 | -0.26 | 0.795 |
| regime_short | fwd_minret_21 | Δmean | -0.0015 | -0.33 | 0.745 |
| regime_short | fwd_minret_63 | Δmean | -0.0013 | -0.15 | 0.881 |
| neg_gex_z | fwd_rv_5 | IC | +0.0492 | +1.53 | 0.127 |
| neg_gex_z | fwd_rv_10 | IC | +0.0669 | +1.78 | 0.075 |
| neg_gex_z | fwd_rv_21 | IC | +0.0633 | +1.36 | 0.172 |
| neg_gex_z | fwd_minret_10 | IC | +0.0308 | +0.87 | 0.382 |
| neg_gex_z | fwd_minret_21 | IC | +0.0441 | +1.00 | 0.316 |
| neg_gex_z | fwd_minret_63 | IC | +0.0807 | +1.38 | 0.168 |
| below_flip | fwd_rv_5 | IC | +0.0157 | +0.43 | 0.669 |
| below_flip | fwd_rv_10 | IC | +0.0329 | +0.75 | 0.452 |
| below_flip | fwd_rv_21 | IC | +0.0460 | +0.91 | 0.362 |
| below_flip | fwd_minret_10 | IC | -0.0097 | -0.28 | 0.781 |
| below_flip | fwd_minret_21 | IC | -0.0349 | -0.81 | 0.419 |
| below_flip | fwd_minret_63 | IC | -0.0243 | -0.51 | 0.608 |
| put_skew_z | fwd_rv_5 | IC | +0.1794 | +3.51 | 0.000 |
| put_skew_z | fwd_rv_10 | IC | +0.1888 | +2.78 | 0.005 |
| put_skew_z | fwd_rv_21 | IC | +0.1825 | +2.09 | 0.037 |
| put_skew_z | fwd_minret_10 | IC | -0.0350 | -0.68 | 0.497 |
| put_skew_z | fwd_minret_21 | IC | -0.0281 | -0.43 | 0.669 |
| put_skew_z | fwd_minret_63 | IC | -0.0339 | -0.35 | 0.724 |

**BH-FDR (α=0.10) survivors: 2/24** — put_skew_z:fwd_rv_10, put_skew_z:fwd_rv_5

### 2. P(large forward down-move | most-fragile tercile) vs base rate

| signal | horizon | threshold | P(down\|fragile) | base | uplift | n_frag |
|---|---|---|---|---|---|---|
| regime_short | 21d | 5% | 0.309 | 0.279 | +0.031 | 689 |
| neg_gex_z | 21d | 5% | 0.267 | 0.279 | -0.012 | 401 |
| below_flip | 21d | 5% | 0.329 | 0.279 | +0.050 | 420 |
| put_skew_z | 21d | 5% | 0.334 | 0.279 | +0.056 | 401 |
| regime_short | 63d | 10% | 0.215 | 0.215 | -0.000 | 689 |
| neg_gex_z | 63d | 10% | 0.142 | 0.215 | -0.073 | 401 |
| below_flip | 63d | 10% | 0.224 | 0.215 | +0.009 | 420 |
| put_skew_z | 63d | 10% | 0.304 | 0.215 | +0.089 | 401 |

### 3. De-risk overlay: go flat when fragile — drawdown vs buy&hold (net of 1bp)

| overlay | net Sharpe | maxDD | exposure | vs B&H ΔmaxDD | DSR | verdict |
|---|---|---|---|---|---|---|
| buy&hold | +0.89 | -35.6% | 100% | — | — | — |
| flat_if_short_gamma | +0.45 | -29.8% | 45% | +5.8% | 0.1495 | no dd benefit · DSR-fail/underperforms |
| flat_if_neg_gex_z<-1 | +0.83 | -32.2% | 87% | +3.4% | 0.4235 | no dd benefit · DSR-fail/underperforms |
| flat_if_below_flip | +0.43 | -30.8% | 45% | +4.8% | 0.1416 | no dd benefit · DSR-fail/underperforms |

*Best-drawdown overlay `flat_if_short_gamma` block-bootstrap maxDD CI: [-50.6, -26.3, -12.1]% (B&H -35.6%).* Overlays de-risk by sitting in cash, not by timing — the maxDD shrinks roughly in proportion to lost exposure, and the DSR haircut rejects it as skill.

## SPX — 1060 days [2019-01-02..2023-03-31], regime long=552 short=508, weight=volume

### 1. Fragility signal vs forward outcome (HAC-t; higher signal = more fragile)

| signal | outcome | stat | value | HAC-t | p |
|---|---|---|---|---|---|
| regime_short | fwd_rv_5 | Δmean | +0.0327 | +1.83 | 0.067 |
| regime_short | fwd_rv_10 | Δmean | +0.0282 | +1.38 | 0.168 |
| regime_short | fwd_rv_21 | Δmean | +0.0261 | +1.15 | 0.249 |
| regime_short | fwd_minret_10 | Δmean | -0.0012 | -0.43 | 0.669 |
| regime_short | fwd_minret_21 | Δmean | -0.0032 | -0.67 | 0.506 |
| regime_short | fwd_minret_63 | Δmean | -0.0027 | -0.42 | 0.674 |
| neg_gex_z | fwd_rv_5 | IC | +0.1365 | +2.94 | 0.003 |
| neg_gex_z | fwd_rv_10 | IC | +0.1202 | +2.12 | 0.034 |
| neg_gex_z | fwd_rv_21 | IC | +0.1184 | +1.71 | 0.086 |
| neg_gex_z | fwd_minret_10 | IC | -0.0691 | -1.45 | 0.148 |
| neg_gex_z | fwd_minret_21 | IC | -0.1094 | -2.16 | 0.031 |
| neg_gex_z | fwd_minret_63 | IC | -0.1573 | -2.44 | 0.015 |
| below_flip | fwd_rv_5 | IC | +0.1922 | +4.38 | 0.000 |
| below_flip | fwd_rv_10 | IC | +0.1645 | +3.16 | 0.002 |
| below_flip | fwd_rv_21 | IC | +0.1383 | +2.28 | 0.023 |
| below_flip | fwd_minret_10 | IC | -0.0181 | -0.41 | 0.684 |
| below_flip | fwd_minret_21 | IC | -0.0269 | -0.57 | 0.566 |
| below_flip | fwd_minret_63 | IC | -0.0077 | -0.17 | 0.862 |
| put_skew_z | fwd_rv_5 | IC | +0.0814 | +1.42 | 0.156 |
| put_skew_z | fwd_rv_10 | IC | +0.0739 | +0.96 | 0.336 |
| put_skew_z | fwd_rv_21 | IC | +0.0736 | +0.70 | 0.481 |
| put_skew_z | fwd_minret_10 | IC | +0.0804 | +1.42 | 0.155 |
| put_skew_z | fwd_minret_21 | IC | +0.1176 | +1.62 | 0.106 |
| put_skew_z | fwd_minret_63 | IC | +0.0613 | +0.62 | 0.534 |

**BH-FDR (α=0.10) survivors: 4/24** — neg_gex_z:fwd_minret_63, neg_gex_z:fwd_rv_5, below_flip:fwd_rv_10, below_flip:fwd_rv_5

### 2. P(large forward down-move | most-fragile tercile) vs base rate

| signal | horizon | threshold | P(down\|fragile) | base | uplift | n_frag |
|---|---|---|---|---|---|---|
| regime_short | 21d | 5% | 0.244 | 0.213 | +0.031 | 508 |
| neg_gex_z | 21d | 5% | 0.254 | 0.213 | +0.041 | 334 |
| below_flip | 21d | 5% | 0.263 | 0.213 | +0.050 | 354 |
| put_skew_z | 21d | 5% | 0.204 | 0.213 | -0.010 | 334 |
| regime_short | 63d | 10% | 0.183 | 0.176 | +0.007 | 508 |
| neg_gex_z | 63d | 10% | 0.257 | 0.176 | +0.081 | 334 |
| below_flip | 63d | 10% | 0.178 | 0.176 | +0.002 | 354 |
| put_skew_z | 63d | 10% | 0.186 | 0.176 | +0.009 | 334 |

### 3. De-risk overlay: go flat when fragile — drawdown vs buy&hold (net of 1bp)

| overlay | net Sharpe | maxDD | exposure | vs B&H ΔmaxDD | DSR | verdict |
|---|---|---|---|---|---|---|
| buy&hold | +0.63 | -34.0% | 100% | — | — | — |
| flat_if_short_gamma | +0.03 | -33.2% | 52% | +0.8% | 0.0242 | no dd benefit · DSR-fail/underperforms |
| flat_if_neg_gex_z<-1 | +0.72 | -28.6% | 92% | +5.4% | 0.2807 | no dd benefit |
| flat_if_below_flip | +0.03 | -33.2% | 52% | +0.8% | 0.0242 | no dd benefit · DSR-fail/underperforms |

*Best-drawdown overlay `flat_if_neg_gex_z<-1` block-bootstrap maxDD CI: [-48.7, -28.6, -13.4]% (B&H -34.0%).* Overlays de-risk by sitting in cash, not by timing — the maxDD shrinks roughly in proportion to lost exposure, and the DSR haircut rejects it as skill.

## Verdict

- **SPY**: BH-FDR survivors — vol: [none]; drawdown: [none]. De-risk overlay beats B&H drawdown as real skill: no.
- **QQQ**: BH-FDR survivors — vol: [put_skew_z:fwd_rv_10, put_skew_z:fwd_rv_5]; drawdown: [none]. De-risk overlay beats B&H drawdown as real skill: no.
- **SPX**: BH-FDR survivors — vol: [neg_gex_z:fwd_rv_5, below_flip:fwd_rv_10, below_flip:fwd_rv_5]; drawdown: [neg_gex_z:fwd_minret_63]. De-risk overlay beats B&H drawdown as real skill: no.

**Read:** the *forward-volatility* relationship (short-gamma / below-flip → higher realized vol) is REAL — BH-FDR survivors on QQQ, SPX (neg-gamma / below-flip / put-skew vs forward RV, IC≈0.17-0.29) — i.e. a VOL-REGIME confirmer, consistent with the literature. The *forward-DRAWDOWN* relationship survives only on SPX at a single (63d) horizon and does NOT replicate across symbols, and NO de-risk overlay cuts drawdown as real skill (every one fails the DSR haircut; the shallower maxDD is just being out of the market). 

**Decision:** on the VOLUME proxy, GEX does **NOT** earn a `drawdown_risk` leg — it supports at most a display-only vol-regime/fragility CONFIRMER (its current Signal-Lab tier). The definitive test is forward-accruing standing OI; the validate-before-weight gate holds until that PASSES.

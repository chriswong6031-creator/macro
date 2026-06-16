# GEX Phase-0 — dealer-gamma positioning vs forward vol & drawdown  (massive panel)

Source-agnostic battery over the cached daily panel. **The historical panel here is VOLUME-weighted** (OptionsDX EOD has no open interest) — a flow proxy for standing dealer positioning. Rebuild the panel from the Polygon OI extractor and re-run for the definitive test. A signal may enter the `drawdown_risk` leg ONLY if it clears BH-FDR on the forward-vol/drawdown relationship AND its overlay cuts drawdown without DSR-failing; until then GEX is display-only.


## SPY — 497 days [2024-06-20..2026-06-12], regime long=211 short=286, weight=volume

### 1. Fragility signal vs forward outcome (HAC-t; higher signal = more fragile)

| signal | outcome | stat | value | HAC-t | p |
|---|---|---|---|---|---|
| regime_short | fwd_rv_5 | Δmean | +0.0415 | +1.78 | 0.075 |
| regime_short | fwd_rv_10 | Δmean | +0.0314 | +1.24 | 0.216 |
| regime_short | fwd_rv_21 | Δmean | +0.0223 | +0.87 | 0.386 |
| regime_short | fwd_minret_10 | Δmean | +0.0002 | +0.06 | 0.951 |
| regime_short | fwd_minret_21 | Δmean | -0.0004 | -0.10 | 0.924 |
| regime_short | fwd_minret_63 | Δmean | +0.0053 | +0.58 | 0.560 |
| neg_gex_z | fwd_rv_5 | IC | +0.1870 | +2.99 | 0.003 |
| neg_gex_z | fwd_rv_10 | IC | +0.1748 | +2.49 | 0.013 |
| neg_gex_z | fwd_rv_21 | IC | +0.1939 | +2.44 | 0.015 |
| neg_gex_z | fwd_minret_10 | IC | +0.0657 | +1.19 | 0.233 |
| neg_gex_z | fwd_minret_21 | IC | +0.0257 | +0.46 | 0.649 |
| neg_gex_z | fwd_minret_63 | IC | +0.0524 | +0.94 | 0.349 |
| below_flip | fwd_rv_5 | IC | +0.2294 | +3.68 | 0.000 |
| below_flip | fwd_rv_10 | IC | +0.1909 | +2.65 | 0.008 |
| below_flip | fwd_rv_21 | IC | +0.1837 | +2.25 | 0.025 |
| below_flip | fwd_minret_10 | IC | +0.0695 | +1.22 | 0.224 |
| below_flip | fwd_minret_21 | IC | +0.0726 | +1.18 | 0.238 |
| below_flip | fwd_minret_63 | IC | +0.1311 | +2.37 | 0.018 |
| put_skew_z | fwd_rv_5 | IC | +0.2363 | +3.38 | 0.001 |
| put_skew_z | fwd_rv_10 | IC | +0.1386 | +1.61 | 0.107 |
| put_skew_z | fwd_rv_21 | IC | +0.1760 | +2.04 | 0.041 |
| put_skew_z | fwd_minret_10 | IC | -0.0158 | -0.18 | 0.854 |
| put_skew_z | fwd_minret_21 | IC | -0.0319 | -0.34 | 0.732 |
| put_skew_z | fwd_minret_63 | IC | +0.0717 | +0.87 | 0.385 |

**BH-FDR (α=0.10) survivors: 8/24** — below_flip:fwd_rv_21, below_flip:fwd_minret_63, neg_gex_z:fwd_rv_21, neg_gex_z:fwd_rv_10, below_flip:fwd_rv_10, neg_gex_z:fwd_rv_5, put_skew_z:fwd_rv_5, below_flip:fwd_rv_5

### 2. P(large forward down-move | most-fragile tercile) vs base rate

| signal | horizon | threshold | P(down\|fragile) | base | uplift | n_frag |
|---|---|---|---|---|---|---|
| regime_short | 21d | 5% | 0.168 | 0.151 | +0.017 | 286 |
| neg_gex_z | 21d | 5% | 0.158 | 0.151 | +0.007 | 146 |
| below_flip | 21d | 5% | 0.151 | 0.151 | -0.000 | 166 |
| put_skew_z | 21d | 5% | 0.212 | 0.151 | +0.061 | 146 |
| regime_short | 63d | 10% | 0.126 | 0.123 | +0.003 | 286 |
| neg_gex_z | 63d | 10% | 0.164 | 0.123 | +0.042 | 146 |
| below_flip | 63d | 10% | 0.108 | 0.123 | -0.014 | 166 |
| put_skew_z | 63d | 10% | 0.130 | 0.123 | +0.007 | 146 |

### 3. De-risk overlay: go flat when fragile — drawdown vs buy&hold (net of 1bp)

| overlay | net Sharpe | maxDD | exposure | vs B&H ΔmaxDD | DSR | verdict |
|---|---|---|---|---|---|---|
| buy&hold | +1.00 | -19.0% | 100% | — | — | — |
| flat_if_short_gamma | +0.01 | -12.7% | 42% | +6.3% | 0.0222 | no dd benefit · DSR-fail/underperforms |
| flat_if_neg_gex_z<-1 | +0.80 | -15.3% | 90% | +3.7% | 0.1922 | no dd benefit · DSR-fail/underperforms |
| flat_if_below_flip | +0.01 | -12.7% | 42% | +6.3% | 0.0222 | no dd benefit · DSR-fail/underperforms |

*Best-drawdown overlay `flat_if_short_gamma` block-bootstrap maxDD CI: [-25.1, -11.9, -5.6]% (B&H -19.0%).* Overlays de-risk by sitting in cash, not by timing — the maxDD shrinks roughly in proportion to lost exposure, and the DSR haircut rejects it as skill.

## QQQ — 497 days [2024-06-20..2026-06-12], regime long=223 short=274, weight=volume

### 1. Fragility signal vs forward outcome (HAC-t; higher signal = more fragile)

| signal | outcome | stat | value | HAC-t | p |
|---|---|---|---|---|---|
| regime_short | fwd_rv_5 | Δmean | +0.0140 | +0.61 | 0.543 |
| regime_short | fwd_rv_10 | Δmean | +0.0020 | +0.08 | 0.936 |
| regime_short | fwd_rv_21 | Δmean | -0.0135 | -0.38 | 0.704 |
| regime_short | fwd_minret_10 | Δmean | +0.0083 | +2.31 | 0.021 |
| regime_short | fwd_minret_21 | Δmean | +0.0116 | +1.61 | 0.108 |
| regime_short | fwd_minret_63 | Δmean | +0.0223 | +1.47 | 0.142 |
| neg_gex_z | fwd_rv_5 | IC | +0.0444 | +0.68 | 0.494 |
| neg_gex_z | fwd_rv_10 | IC | -0.0012 | -0.02 | 0.987 |
| neg_gex_z | fwd_rv_21 | IC | -0.0102 | -0.13 | 0.898 |
| neg_gex_z | fwd_minret_10 | IC | +0.0966 | +1.76 | 0.078 |
| neg_gex_z | fwd_minret_21 | IC | +0.1094 | +1.82 | 0.069 |
| neg_gex_z | fwd_minret_63 | IC | +0.1385 | +1.99 | 0.047 |
| below_flip | fwd_rv_5 | IC | +0.0279 | +0.48 | 0.632 |
| below_flip | fwd_rv_10 | IC | -0.0436 | -0.65 | 0.514 |
| below_flip | fwd_rv_21 | IC | -0.0393 | -0.54 | 0.593 |
| below_flip | fwd_minret_10 | IC | +0.1421 | +2.62 | 0.009 |
| below_flip | fwd_minret_21 | IC | +0.1717 | +2.38 | 0.017 |
| below_flip | fwd_minret_63 | IC | +0.1970 | +2.46 | 0.014 |
| put_skew_z | fwd_rv_5 | IC | +0.1856 | +2.80 | 0.005 |
| put_skew_z | fwd_rv_10 | IC | +0.1011 | +1.22 | 0.224 |
| put_skew_z | fwd_rv_21 | IC | +0.1965 | +2.08 | 0.038 |
| put_skew_z | fwd_minret_10 | IC | +0.0332 | +0.42 | 0.671 |
| put_skew_z | fwd_minret_21 | IC | -0.0047 | -0.05 | 0.960 |
| put_skew_z | fwd_minret_63 | IC | +0.0241 | +0.31 | 0.753 |

**BH-FDR (α=0.10) survivors: 0/24** — none

### 2. P(large forward down-move | most-fragile tercile) vs base rate

| signal | horizon | threshold | P(down\|fragile) | base | uplift | n_frag |
|---|---|---|---|---|---|---|
| regime_short | 21d | 5% | 0.212 | 0.243 | -0.032 | 274 |
| neg_gex_z | 21d | 5% | 0.171 | 0.243 | -0.072 | 146 |
| below_flip | 21d | 5% | 0.211 | 0.243 | -0.033 | 166 |
| put_skew_z | 21d | 5% | 0.281 | 0.243 | +0.037 | 146 |
| regime_short | 63d | 10% | 0.153 | 0.207 | -0.054 | 274 |
| neg_gex_z | 63d | 10% | 0.144 | 0.207 | -0.063 | 146 |
| below_flip | 63d | 10% | 0.139 | 0.207 | -0.069 | 166 |
| put_skew_z | 63d | 10% | 0.158 | 0.207 | -0.050 | 146 |

### 3. De-risk overlay: go flat when fragile — drawdown vs buy&hold (net of 1bp)

| overlay | net Sharpe | maxDD | exposure | vs B&H ΔmaxDD | DSR | verdict |
|---|---|---|---|---|---|---|
| buy&hold | +1.05 | -22.9% | 100% | — | — | — |
| flat_if_short_gamma | -0.59 | -28.6% | 45% | -5.7% | 0.0019 | CUTS dd (just de-risks) · DSR-fail/underperforms |
| flat_if_neg_gex_z<-1 | +0.89 | -17.7% | 88% | +5.2% | 0.224 | no dd benefit · DSR-fail/underperforms |
| flat_if_below_flip | -0.59 | -28.6% | 45% | -5.7% | 0.0019 | CUTS dd (just de-risks) · DSR-fail/underperforms |

*Best-drawdown overlay `flat_if_neg_gex_z<-1` block-bootstrap maxDD CI: [-33.8, -17.6, -10.2]% (B&H -22.9%).* Overlays de-risk by sitting in cash, not by timing — the maxDD shrinks roughly in proportion to lost exposure, and the DSR haircut rejects it as skill.

## IWM — 497 days [2024-06-20..2026-06-12], regime long=113 short=384, weight=volume

### 1. Fragility signal vs forward outcome (HAC-t; higher signal = more fragile)

| signal | outcome | stat | value | HAC-t | p |
|---|---|---|---|---|---|
| regime_short | fwd_rv_5 | Δmean | +0.0293 | +0.92 | 0.356 |
| regime_short | fwd_rv_10 | Δmean | +0.0129 | +0.33 | 0.740 |
| regime_short | fwd_rv_21 | Δmean | +0.0089 | +0.18 | 0.855 |
| regime_short | fwd_minret_10 | Δmean | +0.0028 | +0.59 | 0.556 |
| regime_short | fwd_minret_21 | Δmean | +0.0021 | +0.22 | 0.825 |
| regime_short | fwd_minret_63 | Δmean | +0.0063 | +0.34 | 0.732 |
| neg_gex_z | fwd_rv_5 | IC | +0.1733 | +2.95 | 0.003 |
| neg_gex_z | fwd_rv_10 | IC | +0.2093 | +2.90 | 0.004 |
| neg_gex_z | fwd_rv_21 | IC | +0.2913 | +4.17 | 0.000 |
| neg_gex_z | fwd_minret_10 | IC | +0.0075 | +0.11 | 0.912 |
| neg_gex_z | fwd_minret_21 | IC | -0.0438 | -0.56 | 0.576 |
| neg_gex_z | fwd_minret_63 | IC | -0.0597 | -0.93 | 0.354 |
| below_flip | fwd_rv_5 | IC | +0.1703 | +2.66 | 0.008 |
| below_flip | fwd_rv_10 | IC | +0.1236 | +1.62 | 0.105 |
| below_flip | fwd_rv_21 | IC | +0.1391 | +1.46 | 0.144 |
| below_flip | fwd_minret_10 | IC | +0.0674 | +0.88 | 0.379 |
| below_flip | fwd_minret_21 | IC | +0.0587 | +0.67 | 0.506 |
| below_flip | fwd_minret_63 | IC | +0.0667 | +0.85 | 0.393 |
| put_skew_z | fwd_rv_5 | IC | +0.1498 | +2.44 | 0.015 |
| put_skew_z | fwd_rv_10 | IC | +0.0472 | +0.57 | 0.566 |
| put_skew_z | fwd_rv_21 | IC | +0.0766 | +0.86 | 0.390 |
| put_skew_z | fwd_minret_10 | IC | +0.0132 | +0.18 | 0.860 |
| put_skew_z | fwd_minret_21 | IC | +0.0133 | +0.16 | 0.875 |
| put_skew_z | fwd_minret_63 | IC | +0.1343 | +2.15 | 0.032 |

**BH-FDR (α=0.10) survivors: 5/24** — put_skew_z:fwd_rv_5, below_flip:fwd_rv_5, neg_gex_z:fwd_rv_10, neg_gex_z:fwd_rv_5, neg_gex_z:fwd_rv_21

### 2. P(large forward down-move | most-fragile tercile) vs base rate

| signal | horizon | threshold | P(down\|fragile) | base | uplift | n_frag |
|---|---|---|---|---|---|---|
| regime_short | 21d | 5% | 0.253 | 0.254 | -0.001 | 384 |
| neg_gex_z | 21d | 5% | 0.281 | 0.254 | +0.027 | 146 |
| below_flip | 21d | 5% | 0.258 | 0.254 | +0.004 | 159 |
| put_skew_z | 21d | 5% | 0.260 | 0.254 | +0.007 | 146 |
| regime_short | 63d | 10% | 0.172 | 0.185 | -0.013 | 384 |
| neg_gex_z | 63d | 10% | 0.226 | 0.185 | +0.041 | 146 |
| below_flip | 63d | 10% | 0.145 | 0.185 | -0.040 | 159 |
| put_skew_z | 63d | 10% | 0.199 | 0.185 | +0.014 | 146 |

### 3. De-risk overlay: go flat when fragile — drawdown vs buy&hold (net of 1bp)

| overlay | net Sharpe | maxDD | exposure | vs B&H ΔmaxDD | DSR | verdict |
|---|---|---|---|---|---|---|
| buy&hold | +0.98 | -27.9% | 100% | — | — | — |
| flat_if_short_gamma | +0.00 | -13.7% | 23% | +14.2% | 0.0215 | no dd benefit · DSR-fail/underperforms |
| flat_if_neg_gex_z<-1 | +0.09 | -28.8% | 83% | -0.9% | 0.0288 | no dd benefit · DSR-fail/underperforms |
| flat_if_below_flip | -0.26 | -18.9% | 27% | +9.0% | 0.0082 | no dd benefit · DSR-fail/underperforms |

*Best-drawdown overlay `flat_if_short_gamma` block-bootstrap maxDD CI: [-24.7, -12.8, -6.5]% (B&H -27.9%).* Overlays de-risk by sitting in cash, not by timing — the maxDD shrinks roughly in proportion to lost exposure, and the DSR haircut rejects it as skill.

## Verdict

- **SPY**: BH-FDR survivors — vol: [below_flip:fwd_rv_21, neg_gex_z:fwd_rv_21, neg_gex_z:fwd_rv_10, below_flip:fwd_rv_10, neg_gex_z:fwd_rv_5, put_skew_z:fwd_rv_5, below_flip:fwd_rv_5]; drawdown: [below_flip:fwd_minret_63]. De-risk overlay beats B&H drawdown as real skill: no.
- **QQQ**: BH-FDR survivors — vol: [none]; drawdown: [none]. De-risk overlay beats B&H drawdown as real skill: no.
- **IWM**: BH-FDR survivors — vol: [put_skew_z:fwd_rv_5, below_flip:fwd_rv_5, neg_gex_z:fwd_rv_10, neg_gex_z:fwd_rv_5, neg_gex_z:fwd_rv_21]; drawdown: [none]. De-risk overlay beats B&H drawdown as real skill: no.

**Read:** the *forward-volatility* relationship (short-gamma / below-flip → higher realized vol) is REAL — BH-FDR survivors on SPY, IWM (neg-gamma / below-flip / put-skew vs forward RV, IC≈0.17-0.29) — i.e. a VOL-REGIME confirmer, consistent with the literature. The *forward-DRAWDOWN* relationship survives only on SPY at a single (63d) horizon and does NOT replicate across symbols, and NO de-risk overlay cuts drawdown as real skill (every one fails the DSR haircut; the shallower maxDD is just being out of the market). 

**Decision:** on the VOLUME proxy, GEX does **NOT** earn a `drawdown_risk` leg — it supports at most a display-only vol-regime/fragility CONFIRMER (its current Signal-Lab tier). The definitive test is forward-accruing standing OI; the validate-before-weight gate holds until that PASSES.

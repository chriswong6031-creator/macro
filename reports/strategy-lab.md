# Strategy Lab — backtest scorecard

_Generated 2026-06-21T09:55:20+00:00_  ·  universe 110 deep-history mega-caps  ·  cost 5.0bps one-way  ·  DSR pass≥0.9, BH-FDR α=0.1

> **Survivorship caveat:** the price panel is 114 *currently-listed* mega-caps. Long-biased and cross-sectional results are an **optimistic bound / context**, not proven alpha.


## Time-series strategies (entry timing + trend/swing)

| strategy | family | h | verdict | Sharpe | bench | ΔSh | MaxDD | bench | DSR | IC t(names) | beat-bench DD% |
|---|---|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|
| Vol-targeted 200dma trend | trend | 63 | RISK-CONTROL (drawdown/de-risk) | 1.073 | 1.057 | 0.016 | -0.136 | -0.495 | 1.0 | -4.705 | 0.982 |
| Own 12-1 momentum > 0 | trend | 63 | RISK-CONTROL (drawdown/de-risk) | 1.067 | 1.057 | 0.01 | -0.304 | -0.495 | 1.0 | -3.103 | 0.773 |
| Above 200dma trend | trend | 63 | RISK-CONTROL (drawdown/de-risk) | 1.064 | 1.057 | 0.007 | -0.241 | -0.495 | 1.0 | -4.705 | 0.691 |
| Low-volatility state | trend | 63 | RISK-CONTROL (drawdown/de-risk) | 1.046 | 1.057 | -0.011 | -0.205 | -0.495 | 1.0 | -8.943 | 0.864 |
| RSI(2) oversold in uptrend | mean_reversion | 5 | ENTRY-SIGNAL (predictive timing overlay) | 1.016 | 1.057 | -0.041 | -0.152 | -0.495 | 1.0 | 9.875 | 0.973 |
| 50/200 MA cross | trend | 63 | RISK-CONTROL (drawdown/de-risk) | 1.016 | 1.057 | -0.042 | -0.287 | -0.495 | 1.0 | -2.432 | 0.727 |
| Rising 50dma | trend | 42 | NO EDGE | 0.94 | 1.057 | -0.117 | -0.188 | -0.495 | 1.0 | -3.792 | 0.764 |
| Pullback-from-20d-high reversion | mean_reversion | 10 | ENTRY-SIGNAL (predictive timing overlay) | 0.897 | 1.057 | -0.16 | -0.214 | -0.495 | 1.0 | 4.852 | 0.909 |
| Donchian 55/20 breakout | breakout | 63 | NO EDGE | 0.874 | 1.057 | -0.183 | -0.195 | -0.495 | 1.0 | -5.917 | 0.809 |
| Stretch-below-20dma reversion | mean_reversion | 8 | ENTRY-SIGNAL (predictive timing overlay) | 0.827 | 1.057 | -0.23 | -0.19 | -0.495 | 0.9999 | 6.076 | 0.927 |
| NR7 volatility-contraction breakout | breakout | 8 | NO EDGE | 0.758 | 1.057 | -0.3 | -0.175 | -0.495 | 0.9998 | -0.194 | 0.827 |
| Bollinger %b lower-band reversion | mean_reversion | 10 | ENTRY-SIGNAL (predictive timing overlay) | 0.7 | 1.057 | -0.357 | -0.141 | -0.495 | 0.9966 | 4.71 | 0.982 |
| Lower-low/higher-close reversal | entry_timing | 3 | NO EDGE | 0.647 | 1.057 | -0.41 | -0.123 | -0.495 | 0.9972 | -3.339 | 0.8 |
| RSI(14)<35 buy-the-dip | mean_reversion | 10 | ENTRY-SIGNAL (predictive timing overlay) | 0.602 | 1.057 | -0.455 | -0.089 | -0.495 | 0.9865 | 5.443 | 1.0 |
| Momentum acceleration | trend | 42 | NO EDGE | 0.481 | 1.056 | -0.574 | -0.231 | -0.495 | 0.9401 | 1.249 | 0.881 |
| Down-day fade in uptrend | entry_timing | 3 | ENTRY-SIGNAL (predictive timing overlay) | 0.465 | 1.057 | -0.592 | -0.17 | -0.495 | 0.8975 | 4.803 | 0.855 |
| Above 10-month MA trend | trend | 63 | RISK-CONTROL (drawdown/de-risk) | 1.057 | 1.057 | -0.0 | -0.24 | -0.495 | 1.0 | -4.472 | 0.709 |

## Cross-sectional selection (CONTEXT — survivorship-biased)

| strategy | mean IC | IC t(HAC) | IC hit | long Sh | EW Sh | verdict |
|---|--:|--:|--:|--:|--:|---|
| Cross-sectional 12-1 momentum | 0.035 | 3.869 | 0.563 | 1.148 | 1.058 | CONTEXT — IC FDR-significant |
| Cross-sectional 6-1 momentum | 0.0136 | 1.516 | 0.53 | 0.997 | 1.067 | NO XS EDGE (context-only) |
| Proximity to 52-week high | -0.0159 | -1.936 | 0.474 | 1.041 | 1.072 | NO XS EDGE (context-only) |
| Frog-in-the-pan continuity momentum | 0.0106 | 1.415 | 0.522 | 1.002 | 1.058 | NO XS EDGE (context-only) |
| Residual (beta-adj) 12-1 momentum | 0.019 | 1.912 | 0.545 | 1.115 | 1.063 | CONTEXT — IC FDR-significant |
| Low realized-vol (low-vol anomaly) | -0.0305 | -2.98 | 0.455 | 1.063 | 1.07 | NO XS EDGE (context-only) |

## Combined engines (built from the survivors)

**Entry-timing composite** (blended oversold overlay, gated by uptrend):

- Blended composite IC **0.0389** (t across names 9.741); best single leg 0.0345 → blend lift **0.0044**.
- Top-vs-bottom oversold-quintile 5-day forward spread **0.0039** (t 25.0).
- Trend-gated oversold entry MaxDD **-0.16** vs always-invested -0.495 (Sharpe 0.786 vs 1.057, time-in-market 0.613).
- _Entry composite is an OVERLAY: it improves the SHORT-HORIZON entry of a name already selected (positive blended IC, top-vs-bottom oversold quintile spread). It does not beat always-invested standalone — its role is better fills + shallower entry drawdown, gated by the validated uptrend filter._

**Selection composite** (12-1 + residual momentum, cross-sectional, CONTEXT):

- Blend IC 0.0352 (t_hac 3.908) vs momentum-only 0.035 (t_hac 3.869). _Survivorship-biased — never sizes alone._


## Institutional levers

**Vol-managed sizing** (constant-risk targeting):

| sleeve | Sharpe | CAGR | MaxDD |
|---|--:|--:|--:|
| buyhold | 1.056 | 0.1842 | -0.495 |
| voltarget_derisk | 1.154 | 0.0923 | -0.265 |
| voltarget_lever | 1.157 | 0.0941 | -0.267 |
| trend | 1.064 | 0.0991 | -0.241 |
| trend_voltarget | 1.075 | 0.0572 | -0.135 |

- Buy&hold → vol-target (de-risk): ΔSharpe **0.098**, ΔMaxDD **0.23** (less negative = shallower). _Vol-targeting holds ~constant risk → higher Sharpe and shallower drawdown vs the unscaled sleeve. A capital-efficiency lever, kept regardless of IC; the levered variant adds return in calm regimes._

**Regime-conditioning** (entry-composite IC by market regime):

- SPX bull-market IC 0.0336 (t 8.07) vs bear-market IC 0.0739 (t 9.81). Regime-dependent: **False**. Edge roughly regime-stable; light conditioning only.


## Read

- **Entry-timing overlays (significant short-horizon IC):** rsi2_oversold, bb_reversion, dd_reversion, dist_below_ma, gap_fade, oversold_uptrend
- **Tradable standalone (beats buy&hold net Sharpe, DSR+bootstrap+split):** none
- **Validated risk-control (de-risk/drawdown):** rsi2_oversold, tsmom_200, tsmom_10mo, tsmom_12_1, ma_cross_50_200, vol_scaled_trend, low_vol_state
- **Cross-sectional context (modest, survivorship-biased):** xs_mom_12_1, xs_resid_mom

# Bonds & bond-health — calibration report

Split-half boundary **2013-01-01**. Target: forward **63-day** S&P max drawdown (and P(>=10% drawdown)) + **252-day** forward NBER recession.

Discriminative calibration: each signal (as STRESS) vs strictly-forward S&P drawdown + NBER recession. IC = Spearman(stress, forward dd-depth). CONFIRMED needs positive sign in full+both halves AND high-tercile dd10 > base. No look-ahead.

Verdicts: **CONFIRMED** = stress→worse outcome, positive sign in full + both halves, |IC|≥0.10, and the high-stress tercile beats the base drawdown rate; **DIRECTIONAL** = full only; **CONTEXT** = weak/unstable (the prior over-weights it); **INVERTED** = predicts the wrong way. The composite's live span is ~2003+ (term-premium-limited), so the recession target is thin — the drawdown target carries the weight.


## Health-composite legs + the composite

| Signal | Verdict | IC dd (full/pre/post) | IC recession | hi-tercile P(dd10) vs base | span | n |
|---|---|---|--:|---|---|--:|
| recession (Recession-risk composite (0-100)) | **CONFIRMED** | 0.162/0.198/0.033 | 0.531 | 0.219 vs 0.123 (+9.6pp) | 1971-01-04..2026-03-17 | 14402 |
| drawdown (Drawdown-risk gauge (0-100, already MEASURED)) | **CONFIRMED** | 0.234/0.272/0.102 | 0.52 | 0.244 vs 0.127 (+11.7pp) | 1973-03-05..2026-03-17 | 13837 |
| credit (HY-OAS credit stress (0-100)) | **DIRECTIONAL** | 0.174/0.285/-0.089 | 0.284 | 0.289 vs 0.158 (+13.1pp) | 1996-12-31..2026-03-17 | 7621 |
| rates_vol (MOVE rates-vol stress (0-100)) | **CONFIRMED** | 0.168/0.251/0.083 | 0.183 | 0.205 vs 0.133 (+7.2pp) | 2002-11-12..2026-03-17 | 6091 |
| plumbing (SOFR-IORB funding stress (0-100)) | **CONTEXT** | -0.01/nan/-0.01 | None | 0.151 vs 0.147 (+0.4pp) | 2021-07-29..2026-03-17 | 1209 |
| composite (Bond-stress composite = 100 - health score (the headline)) | **CONFIRMED** | 0.223/0.266/0.065 | 0.557 | 0.241 vs 0.123 (+11.8pp) | 1971-01-04..2026-03-17 | 14402 |

## Diagnostic curve signals

| Signal | Verdict | IC dd (full/pre/post) | IC recession | hi-tercile P(dd10) vs base | span | n |
|---|---|---|--:|---|---|--:|
| ny_fed_prob (NY-Fed 3m10y recession probit) | **DIRECTIONAL** | 0.054/0.089/-0.017 | 0.363 | 0.167 vs 0.123 (+4.4pp) | 1971-01-04..2026-03-17 | 14402 |
| neg_ntfs (Near-term forward spread (sign-flipped: low = stress)) | **CONTEXT** | -0.018/0.07/-0.199 | 0.24 | 0.105 vs 0.117 (-1.2pp) | 1976-06-01..2026-03-17 | 12991 |
| hy_oas (High-yield OAS level (%)) | **DIRECTIONAL** | 0.174/0.285/-0.089 | 0.284 | 0.289 vs 0.158 (+13.1pp) | 1996-12-31..2026-03-17 | 7621 |

## Does the blend beat the best single leg?

Composite IC **0.223** vs best leg `drawdown` **0.234** (Δ -0.011). **best single leg (drawdown) BEATS the composite.**

## NY-Fed recession-probit reliability

Brier **0.1651** vs base-rate climatology 0.1806 (skill score 0.086; base recession rate 0.237). Reliability curve (predicted vs observed):

| prob bin | n | predicted | observed |
|---|--:|--:|--:|
| 0.0-0.2 | 10733 | 0.05 | 0.143 |
| 0.2-0.4 | 2203 | 0.284 | 0.497 |
| 0.4-0.6 | 746 | 0.491 | 0.649 |
| 0.6-0.8 | 442 | 0.67 | 0.373 |
| 0.8-1.0 | 89 | 0.87 | 1.0 |

## Measured-informed leg weights

Keep the prior magnitude, scale by the verdict (CONFIRMED 1.0 · DIRECTIONAL 0.5 · CONTEXT 0.25 · INVERTED 0.0), renormalized:

| leg | prior | measured |
|---|--:|--:|
| recession | 1.0 | 0.323 |
| drawdown | 1.0 | 0.323 |
| credit | 0.8 | 0.129 |
| rates_vol | 0.6 | 0.194 |
| plumbing | 0.4 | 0.032 |

_If a leg lands CONTEXT, the live composite (a prior) over-weights it; adopt the measured weights in `config.yml bonds.health.weights` only if they also hold on the next refresh. The recession/drawdown legs are the measured backbone._
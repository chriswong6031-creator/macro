# Bonds & bond-health — calibration report

Split-half boundary **2013-01-01**. Target: forward **63-day** S&P max drawdown (and P(>=10% drawdown)) + **252-day** forward NBER recession.

Discriminative calibration: each signal (as STRESS) vs strictly-forward S&P drawdown + NBER recession. IC = Spearman(stress, forward dd-depth). CONFIRMED needs positive sign in full+both halves AND high-tercile dd10 > base. No look-ahead.

Verdicts: **CONFIRMED** = stress→worse outcome, positive sign in full + both halves, |IC|≥0.10, and the high-stress tercile beats the base drawdown rate; **DIRECTIONAL** = full only; **CONTEXT** = weak/unstable (the prior over-weights it); **INVERTED** = predicts the wrong way. The composite's live span is ~2003+ (term-premium-limited), so the recession target is thin — the drawdown target carries the weight.


## Health-composite legs + the composite

| Signal | Verdict | IC dd (full/pre/post) | IC recession | hi-tercile P(dd10) vs base | span | n |
|---|---|---|--:|---|---|--:|
| recession (Recession-risk composite (0-100)) | **DIRECTIONAL** | 0.149/0.18/0.04 | 0.506 | 0.22 vs 0.122 (+9.8pp) | 1967-06-01..2026-05-26 | 15389 |
| drawdown (Drawdown-risk gauge (0-100, already MEASURED)) | **CONFIRMED** | 0.224/0.26/0.102 | 0.537 | 0.242 vs 0.125 (+11.7pp) | 1969-07-31..2026-05-26 | 14824 |
| credit (HY-OAS credit stress (0-100)) | **DIRECTIONAL** | 0.18/0.287/-0.07 | 0.286 | 0.287 vs 0.157 (+13.0pp) | 1996-12-31..2026-05-26 | 7671 |
| rates_vol (MOVE rates-vol stress (0-100)) | **CONFIRMED** | 0.168/0.244/0.079 | 0.182 | 0.204 vs 0.132 (+7.2pp) | 2002-11-12..2026-05-26 | 6141 |
| plumbing (SOFR-IORB funding stress (0-100)) | **CONTEXT** | -0.067/nan/-0.067 | None | 0.145 vs 0.141 (+0.4pp) | 2021-07-29..2026-05-26 | 1259 |
| composite (Bond-stress composite = 100 - health score (the headline)) | **CONFIRMED** | 0.207/0.241/0.073 | 0.545 | 0.24 vs 0.122 (+11.8pp) | 1967-06-01..2026-05-26 | 15389 |

## Diagnostic curve signals

| Signal | Verdict | IC dd (full/pre/post) | IC recession | hi-tercile P(dd10) vs base | span | n |
|---|---|---|--:|---|---|--:|
| ny_fed_prob (NY-Fed 3m10y recession probit) | **CONTEXT** | -0.023/-0.005/-0.019 | 0.218 | 0.13 vs 0.119 (+1.1pp) | 1981-09-01..2026-05-26 | 11671 |
| neg_ntfs (Near-term forward spread (sign-flipped: low = stress)) | **CONTEXT** | -0.042/0.054/-0.187 | 0.168 | 0.103 vs 0.119 (-1.6pp) | 1981-09-01..2026-05-26 | 11671 |
| hy_oas (High-yield OAS level (%)) | **DIRECTIONAL** | 0.18/0.288/-0.07 | 0.286 | 0.287 vs 0.157 (+13.0pp) | 1996-12-31..2026-05-26 | 7671 |

## Does the blend beat the best single leg?

Composite IC **0.207** vs best leg `drawdown` **0.224** (Δ -0.017). **best single leg (drawdown) BEATS the composite.**

## NY-Fed recession-probit reliability

Brier **0.1576** vs base-rate climatology 0.1501 (skill score -0.05; base recession rate 0.184). Reliability curve (predicted vs observed):

| prob bin | n | predicted | observed |
|---|--:|--:|--:|
| 0.0-0.2 | 8999 | 0.052 | 0.138 |
| 0.2-0.4 | 1808 | 0.278 | 0.404 |
| 0.4-0.6 | 395 | 0.495 | 0.337 |
| 0.6-0.8 | 280 | 0.662 | 0.011 |

## Measured-informed leg weights

Keep the prior magnitude, scale by the verdict (CONFIRMED 1.0 · DIRECTIONAL 0.5 · CONTEXT 0.25 · INVERTED 0.0), renormalized:

| leg | prior | measured |
|---|--:|--:|
| recession | 1.0 | 0.192 |
| drawdown | 1.0 | 0.385 |
| credit | 0.8 | 0.154 |
| rates_vol | 0.6 | 0.231 |
| plumbing | 0.4 | 0.038 |

_If a leg lands CONTEXT, the live composite (a prior) over-weights it; adopt the measured weights in `config.yml bonds.health.weights` only if they also hold on the next refresh. The recession/drawdown legs are the measured backbone._
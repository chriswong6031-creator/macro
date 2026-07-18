# Bonds & bond-health — calibration report

Split-half boundary **2013-01-01**. Target: forward **63-day** S&P max drawdown (and P(>=10% drawdown)) + **252-day** forward NBER recession.

Discriminative calibration: each signal (as STRESS) vs strictly-forward S&P drawdown + NBER recession. IC = Spearman(stress, forward dd-depth). CONFIRMED needs positive sign in full+both halves AND high-tercile dd10 > base. No look-ahead.

Verdicts: **CONFIRMED** = stress→worse outcome, positive sign in full + both halves, |IC|≥0.10, and the high-stress tercile beats the base drawdown rate; **DIRECTIONAL** = full only; **CONTEXT** = weak/unstable (the prior over-weights it); **INVERTED** = predicts the wrong way. The composite's live span is ~2003+ (term-premium-limited), so the recession target is thin — the drawdown target carries the weight.


## Health-composite legs + the composite

| Signal | Verdict | IC dd (full/pre/post) | IC recession | hi-tercile P(dd10) vs base | span | n |
|---|---|---|--:|---|---|--:|
| recession (Recession-risk composite (0-100)) | **DIRECTIONAL** | 0.149/0.179/0.037 | 0.506 | 0.22 vs 0.122 (+9.8pp) | 1967-06-01..2026-04-21 | 15364 |
| drawdown (Drawdown-risk gauge (0-100, already MEASURED)) | **CONFIRMED** | 0.225/0.261/0.103 | 0.538 | 0.243 vs 0.125 (+11.8pp) | 1969-07-31..2026-04-21 | 14799 |
| credit (HY-OAS credit stress (0-100)) | **DIRECTIONAL** | 0.177/0.287/-0.078 | 0.285 | 0.288 vs 0.158 (+13.0pp) | 1996-12-31..2026-04-21 | 7646 |
| rates_vol (MOVE rates-vol stress (0-100)) | **CONFIRMED** | 0.167/0.244/0.08 | 0.182 | 0.204 vs 0.132 (+7.2pp) | 2002-11-12..2026-04-21 | 6116 |
| plumbing (SOFR-IORB funding stress (0-100)) | **CONTEXT** | -0.046/nan/-0.046 | None | 0.148 vs 0.144 (+0.4pp) | 2021-07-29..2026-04-21 | 1234 |
| composite (Bond-stress composite = 100 - health score (the headline)) | **CONFIRMED** | 0.208/0.242/0.073 | 0.546 | 0.238 vs 0.122 (+11.6pp) | 1967-06-01..2026-04-21 | 15364 |

## Diagnostic curve signals

| Signal | Verdict | IC dd (full/pre/post) | IC recession | hi-tercile P(dd10) vs base | span | n |
|---|---|---|--:|---|---|--:|
| ny_fed_prob (NY-Fed 3m10y recession probit) | **DIRECTIONAL** | 0.053/0.079/-0.019 | 0.336 | 0.153 vs 0.121 (+3.2pp) | 1962-01-02..2026-04-21 | 16776 |
| neg_ntfs (Near-term forward spread (sign-flipped: low = stress)) | **CONTEXT** | -0.02/0.073/-0.198 | 0.238 | 0.103 vs 0.117 (-1.4pp) | 1976-06-01..2026-04-21 | 13016 |
| hy_oas (High-yield OAS level (%)) | **DIRECTIONAL** | 0.177/0.288/-0.078 | 0.285 | 0.288 vs 0.158 (+13.0pp) | 1996-12-31..2026-04-21 | 7646 |

## Does the blend beat the best single leg?

Composite IC **0.208** vs best leg `drawdown` **0.225** (Δ -0.017). **best single leg (drawdown) BEATS the composite.**

## NY-Fed recession-probit reliability

Brier **0.1642** vs base-rate climatology 0.1783 (skill score 0.079; base recession rate 0.232). Reliability curve (predicted vs observed):

| prob bin | n | predicted | observed |
|---|--:|--:|--:|
| 0.0-0.2 | 11962 | 0.058 | 0.144 |
| 0.2-0.4 | 3347 | 0.278 | 0.417 |
| 0.4-0.6 | 747 | 0.491 | 0.649 |
| 0.6-0.8 | 442 | 0.67 | 0.373 |
| 0.8-1.0 | 89 | 0.87 | 1.0 |

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
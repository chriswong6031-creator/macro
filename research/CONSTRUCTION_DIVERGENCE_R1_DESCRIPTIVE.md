# Construction-Divergence R-1 Descriptive Record

**Generated:** 2026-07-06T03:50:32.745495+00:00  
**Git SHA:** cf792be38411322b1d1a49b5b0f2211364c6ec2d  
**Status:** DESCRIPTIVE/ACCRUAL — not verdict-eligible  
**Registration:** research/HEALTHCARE_MEMBER_DISPERSION_ROTATION_NOTE.md §12 (LOCKED)

---

## Methodology

This descriptive study examines whether the state of the Invesco equal-weight (EW) sector ETFs at the time a SPDR cap-weight (cap) ETF enters a reduce-signal state (`_label ∈ {fading, deteriorating}` per `engine.theme_scoring._label`) carries information about the subsequent drawdown experience of the cap ETF. The gate machinery is imported unchanged from `scripts/calibrate_baskets.py` and `engine/theme_scoring.py` (implementation frozen at SHA `9a31b78ad0`): relative strength vs SPY (`rs = lvl/SPY`) plus cross-sector panel breadth, recomputed point-in-time with no look-ahead. Events are de-overlapped (≥15 trading days between onsets). The EW condition is evaluated at the same close `t` as the cap onset and classifies each event as *divergent* (cap reducing, EW not) or *confirmed* (both reducing). Forward outcomes are max absolute drawdown at 21d and 63d (t+1 onwards, matching `_fwd_dd` in `calibrate_baskets.py`). SPY-stress is SPY below its own 200d MA at `t`.

A no-lookahead audit asserts that the maximum feature index used for each event's condition equals the onset bar index (causal rolling windows). Three ablations are reported: condition-label shuffle within sector (999 draws); placebo condition using a rotated sector's EW label; and sector-matched random event dates. Calendar-time blocks (co-firing onsets within 7 trading days) are collapsed for the effective-t computation. No verdicts, no recommendations. Prior (registered §12): divergent = the validated early exit; expect no de-escalation evidence.

---

## Cohort Counts

| Cohort | N |
|---|---|
| Divergent (cap onset, EW not reducing) | 582 |
| Confirmed (both reducing) | 1102 |
| Cap-lags-EW (EW onset, cap not reducing) [desc. only] | 797 |
| **Total cap-onset events** | **1684** |

**Power floor:** PASS (smaller cohort n=582 vs threshold=40; decades with data=3 vs required=2)

---

## Divergent × Confirmed / Stress × Calm 2×2

| | Stress (SPY < 200d MA) | Calm | Total |
|---|---|---|---|
| Divergent | 115 | 467 | 582 |
| Confirmed  | 240 | 862 | 1102 |

Divergent rate in stress: 32.4% | in calm: 35.1%

---

## Forward Drawdown (Max Absolute) — 21d

| Cohort | N | Mean DD% | Median DD% | p10 DD% | p25 DD% | P(DD<−8%) |
|---|---|---|---|---|---|---|
| Divergent | 579 | -3.34 | -2.19 | -8.57 | -4.51 | 0.126 |
| Confirmed | 1099 | -3.62 | -2.44 | -8.99 | -5.04 | 0.12 |

## Forward Drawdown (Max Absolute) — 63d

| Cohort | N | Mean DD% | Median DD% | p10 DD% | p25 DD% | P(DD<−8%) |
|---|---|---|---|---|---|---|
| Divergent | 570 | -5.75 | -3.55 | -13.85 | -7.49 | 0.239 |
| Confirmed | 1090 | -6.16 | -3.78 | -15.47 | -8.02 | 0.252 |

## Forward Return (descriptive) — 21d and 63d

| Cohort | Mean ret21% | Median ret21% | Mean ret63% | Median ret63% |
|---|---|---|---|---|
| Divergent | 0.72 | 1.5 | 3.04 | 3.32 |
| Confirmed | 1.05 | 1.28 | 3.01 | 3.45 |

## Whipsaw Descriptive (leg = −8%, reversal grid {10,15,21} sessions)

| Cohort | Ws-leg-hit 10d% | Ws-leg-hit 15d% | Ws-leg-hit 21d% |
|---|---|---|---|
| Divergent | — | — | — |
| Confirmed | — | — | — |

## Stress-Stratified DD (21d)

| Cohort × Stress | N | Mean DD% | Median DD% | P(DD<−8%) |
|---|---|---|---|---|
| Divergent / Stress | 115 | -4.82 | -3.23 | 0.243 |
| Divergent / Calm | 464 | -2.97 | -2.05 | 0.097 |
| Confirmed / Stress | 240 | -5.84 | -3.78 | 0.275 |
| Confirmed / Calm | 859 | -3.0 | -2.24 | 0.077 |

## Block Bootstrap Effective-t (DD21 Contrast)

Raw contrast (divergent minus confirmed mean DD21): **0.28%**
t-raw: 1.173 | n_div: 579 | n_con: 1099
Effective-t (divergent): t_eff=408 / t_raw=579 (ratio=0.705)
Effective-t (confirmed): t_eff=598 / t_raw=1099 (ratio=0.544)
*descriptive contrast only; no verdict-bearing BH test on this stat per §12*

## Per-Decade Cells

| Decade | Cohort | N | DD21 Median% | DD63 Median% |
|---|---|---|---|---|
| 2000s | Divergent | 54 | -3.28 | -8.88 |
| 2000s | Confirmed | 117 | -4.55 | -10.3 |
| 2010s | Divergent | 316 | -1.5 | -2.97 |
| 2010s | Confirmed | 541 | -1.98 | -3.11 |
| 2020s | Divergent | 209 | -2.8 | -4.27 |
| 2020s | Confirmed | 436 | -2.85 | -4.21 |

## Ablations

### Condition-Label Shuffle (DD21)

Real contrast: **0.28%** | Shuffle mean: 0.06% ± 0.28% | Percentile of real: **77.9th** | N draws: 999
*negative contrast = divergent has deeper DD (opposite of early-exit hypothesis)*

### Condition-Label Shuffle (DD63)

Real contrast: **0.41%** | Shuffle mean: 0.1% ± 0.46% | Percentile of real: **74.1th** | N draws: 999

### Placebo Condition (Sector Rotation, DD21)

- note: placebo: each sector uses a different sector's EW label (rotation pairing)
- placebo_div_dd_mean_pct: -3.58
- placebo_con_dd_mean_pct: -3.26
- placebo_contrast_pct: -0.32
- placebo_div_n: 1396
- placebo_con_n: 282

### Random Event Dates (DD21)

Real contrast: **0.28%** | Placebo mean: 0.03% ± 0.23% | Percentile of real: **86.8th** | N draws: 999

---

## Operationalization Notes

- Panel breadth for cap ETFs: all 11 SPDR sector ETFs (same panel used in run_proxy).
- Panel breadth for EW ETFs: all 11 Invesco EW ETFs (RSPT/RSPG/RSPF/RSPH/RSPD/RSPS/RSPU/RSPM/RGI/RSPC/RSPR).
- Window start per pair: max(cap_first_valid_label, ew_first_valid_label, inception_override).
- EW labels evaluated at same bar i as cap onset (close t, per §12).
- Block bootstrap: circular block bootstrap via engine.validation.bootstrap_effective_t, block=7 trading days.
- Shuffle ablation: EW label array shuffled in place (non-None values only) within each sector; 999 draws.
- Placebo: each sector's cap events reclassified using the next sector's EW labels (rotation pairing).
- Random-date placebo: DD values shuffled within sector while keeping classification; 999 draws.
- cap_lags_ew events are descriptive escalation context only; never a key per §12.
- SPY stress: SPY close < 200d MA (min_periods=100) evaluated at onset bar i.

---

## Prior Check

> **Registered prior (§12):** divergent = validated early exit; expect NO de-escalation

The divergent cohort represents the early-exit scenario where the cap-weight ETF enters a reduce state while the equal-weight counterpart has not yet confirmed the deterioration. Per §12, the mechanism (cap leaders break first) means this cohort carries a null prior for de-escalation: early exits are expected to have at least as deep drawdowns as confirmed events, possibly less so only if the cap signal is reliably early. All verdict gates (§12) must be met before any de-escalation conclusion is possible; this descriptive run establishes the baseline statistics for that future evaluation.

---

*Run by scripts/study_construction_divergence.py | SHA cf792be38411 | 2026-07-06*
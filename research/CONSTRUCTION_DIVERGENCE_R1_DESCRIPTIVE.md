# Construction-Divergence R-1 Descriptive Record

**Generated:** 2026-07-06T03:57:58.568480+00:00  
**Git SHA:** e729361002c136630c1d0f87d27b0d173f57cf89  
**Status:** DESCRIPTIVE/ACCRUAL — not verdict-eligible  
**Registration:** research/HEALTHCARE_MEMBER_DISPERSION_ROTATION_NOTE.md §12 (LOCKED)

> **RE-CHECK NOTE (2026-07-07, RC-RUL-4 — research/TIME_CONFOUND_RECHECK_ADJUDICATION.md).**
> HC-RC-1 (PR #1850, `CONSTRUCTION_DIVERGENCE_R1_TC_RECHECK.md`) repaired this study's
> inference defects (CD-1/2/3: mis-ordered effective-t input, decorative block collapse,
> time-blind ablations) with real ±7d cross-sector co-firing blocks (419) and
> block-cluster bootstrap. **The "null held" lock is reaffirmed on the repaired
> machinery** (DD21 null; DD63 pooled marginal p=0.072 with CI including zero;
> DD63 stratified null in both stress strata). `scripts/study_construction_divergence_tc.py`
> is the mandatory apparatus for any future R-1 verdict batch; the DD63 tail asymmetry
> (divergent p10 shallower, non-overlapping cohort CIs) is a descriptive watch item.

---

## Methodology

This descriptive study examines whether the state of the Invesco equal-weight (EW) sector ETFs at the time a SPDR cap-weight (cap) ETF enters a reduce-signal state (`_label ∈ {fading, deteriorating}` per `engine.theme_scoring._label`) carries information about the subsequent drawdown experience of the cap ETF. The gate machinery is imported unchanged from `scripts/calibrate_baskets.py` and `engine/theme_scoring.py` (implementation frozen at SHA `9a31b78ad0`): relative strength vs SPY (`rs = lvl/SPY`) plus cross-sector panel breadth, recomputed point-in-time with no look-ahead. Events are de-overlapped (≥15 trading days between onsets). The EW condition is evaluated at the same close `t` as the cap onset and classifies each event as *divergent* (cap reducing, EW not) or *confirmed* (both reducing). Forward outcomes are max absolute drawdown at 21d and 63d (t+1 onwards, matching `_fwd_dd` in `calibrate_baskets.py`). SPY-stress is SPY below its own 200d MA at `t`.

A no-lookahead audit asserts that the maximum feature index used for each event's condition equals the onset bar index (causal rolling windows). Three ablations are reported: condition-label shuffle within sector (999 draws); placebo condition using a rotated sector's EW label; and sector-matched random event dates. Calendar-time blocks (co-firing onsets within 7 trading days) are collapsed for the effective-t computation. No verdicts, no recommendations. Prior (registered §12): divergent = the validated early exit; expect no de-escalation evidence.

---

## Cohort Counts

| Cohort | N |
|---|---|
| Divergent (cap onset, EW not reducing) | 315 |
| Confirmed (both reducing) | 485 |
| Cap-lags-EW (EW onset, cap not reducing) [desc. only] | 319 |
| **Total cap-onset events** | **800** |

**Power floor:** PASS (smaller cohort n=315 vs threshold=40; decades with data=3 vs required=2)

---

## Divergent × Confirmed / Stress × Calm 2×2

| | Stress (SPY < 200d MA) | Calm | Total |
|---|---|---|---|
| Divergent | 42 | 273 | 315 |
| Confirmed  | 74 | 411 | 485 |

Divergent rate in stress: 36.2% | in calm: 39.9%

---

## Forward Drawdown (Max Absolute) — 21d

| Cohort | N | Mean DD% | Median DD% | p10 DD% | p25 DD% | P(DD<−8%) |
|---|---|---|---|---|---|---|
| Divergent | 314 | -3.1 | -2.32 | -8.23 | -4.25 | 0.105 |
| Confirmed | 483 | -3.37 | -2.56 | -8.16 | -4.92 | 0.112 |

## Forward Drawdown (Max Absolute) — 63d

| Cohort | N | Mean DD% | Median DD% | p10 DD% | p25 DD% | P(DD<−8%) |
|---|---|---|---|---|---|---|
| Divergent | 312 | -5.31 | -3.48 | -12.35 | -6.9 | 0.224 |
| Confirmed | 480 | -6.17 | -4.19 | -15.12 | -8.51 | 0.265 |

## Forward Return (descriptive) — 21d and 63d

| Cohort | Mean ret21% | Median ret21% | Mean ret63% | Median ret63% |
|---|---|---|---|---|
| Divergent | 0.73 | 1.55 | 3.42 | 3.42 |
| Confirmed | 0.67 | 0.91 | 2.37 | 2.43 |

## Whipsaw Descriptive (leg = −8%, reversal grid {10,15,21} sessions)

| Cohort | Ws-leg-hit 10d% | Ws-leg-hit 15d% | Ws-leg-hit 21d% |
|---|---|---|---|
| Divergent | — | — | — |
| Confirmed | — | — | — |

## Stress-Stratified DD (21d)

| Cohort × Stress | N | Mean DD% | Median DD% | P(DD<−8%) |
|---|---|---|---|---|
| Divergent / Stress | 42 | -4.76 | -2.82 | 0.262 |
| Divergent / Calm | 272 | -2.84 | -2.24 | 0.081 |
| Confirmed / Stress | 74 | -5.54 | -3.78 | 0.324 |
| Confirmed / Calm | 409 | -2.97 | -2.45 | 0.073 |

## Block Bootstrap Effective-t (DD21 Contrast)

Raw contrast (divergent minus confirmed mean DD21): **0.27%**
t-raw: 0.947 | n_div: 314 | n_con: 483
Effective-t (divergent): t_eff=287 / t_raw=314 (ratio=0.914)
Effective-t (confirmed): t_eff=402 / t_raw=483 (ratio=0.832)
*descriptive contrast only; no verdict-bearing BH test on this stat per §12*

## Per-Decade Cells

| Decade | Cohort | N | DD21 Median% | DD63 Median% |
|---|---|---|---|---|
| 2000s | Divergent | 31 | -3.16 | -8.25 |
| 2000s | Confirmed | 42 | -2.92 | -7.21 |
| 2010s | Divergent | 171 | -1.38 | -2.62 |
| 2010s | Confirmed | 238 | -2.14 | -3.33 |
| 2020s | Divergent | 111 | -2.83 | -3.84 |
| 2020s | Confirmed | 201 | -3.01 | -4.67 |

## Ablations

### Condition-Label Shuffle (DD21)

Real contrast: **0.27%** | Shuffle mean: 0.06% ± 0.34% | Percentile of real: **72.7th** | N draws: 999
*negative contrast = divergent has deeper DD (opposite of early-exit hypothesis)*

### Condition-Label Shuffle (DD63)

Real contrast: **0.85%** | Shuffle mean: 0.1% ± 0.6% | Percentile of real: **89.8th** | N draws: 999

### Placebo Condition (Sector Rotation, DD21)

- note: placebo: each sector uses a different sector's EW label (rotation pairing)
- placebo_div_dd_mean_pct: -3.33
- placebo_con_dd_mean_pct: -2.92
- placebo_contrast_pct: -0.41
- placebo_div_n: 666
- placebo_con_n: 131

### Random Event Dates (DD21)

Real contrast: **0.27%** | Placebo mean: 0.0% ± 0.27% | Percentile of real: **81.4th** | N draws: 999

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

*Run by scripts/study_construction_divergence.py | SHA e729361002c1 | 2026-07-06*
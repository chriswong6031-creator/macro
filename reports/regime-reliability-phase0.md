# Regime-conditional signal reliability — Phase-0

Tests the external proposal `R[s,t] = E[strategy performance | regime]` against the
only multi-regime graded signal record in the repo.

- Substrate: `data/signal_archive/track_record.parquet` — **57,642 matured signals**, 1962-11-29 -> 2026-05-04, **763 distinct months**.
- Outcome: `fwd_mdd_60` (60d forward max drawdown, pp). Charter framing: drawdown / entry-quality, never return-alpha.
- Regime axis: `regime_at_entry` (bear, bull, choppy); family axis: `reason` (5 families).
- Deterministic: seed=7, month-block bootstrap B=600, era split 2010-01-01.

## 0. Which regime axes can carry a conditional claim at all?

```
regime-conditioning estimability  (n_rows=58149, gates: coverage>=20%, states>=2, months/state>=12)

  [PASS] regime_at_entry    cov=100.0%  states=3  min_state_months=725 1962-11-29..2026-07-31
         estimable: 3 states, thinnest spans 725 months
  [----] quad_hard_label    cov=  0.4%  states=2  min_state_months=  1 2026-07-01..2026-07-31
         insufficient_coverage: stamped on 0.4% of rows (floor 20%)
  [----] vol_regime         cov=  0.4%  states=1  min_state_months=  1 2026-07-01..2026-07-31
         insufficient_coverage: stamped on 0.4% of rows (floor 20%)
  [----] fused_risk_label   cov=  0.4%  states=4  min_state_months=  1 2026-07-01..2026-07-31
         insufficient_coverage: stamped on 0.4% of rows (floor 20%)
  [----] rate_pressure      cov=  0.4%  states=1  min_state_months=  1 2026-07-06..2026-07-31
         insufficient_coverage: stamped on 0.4% of rows (floor 20%)
  [----] risk_radar_state   cov=  0.4%  states=2  min_state_months=  1 2026-07-01..2026-07-31
         insufficient_coverage: stamped on 0.4% of rows (floor 20%)

  estimable axes: ['regime_at_entry']
```

Only `regime_at_entry` clears the gate. The five richer axes the proposal actually
wants (quad, vol regime, rate pressure, fused risk, radar state) are stamped on
**0.4%** of the record — one month — and `vol_regime` / `rate_pressure` are observed
in a **single state**, where a conditional expectation is undefined. The proposal's
16-signal regime vector is therefore untestable here regardless of its merit.

## 1. Raw cell means — and why they overstate the case

Mean 60d forward max drawdown (pp; less negative = more reliable):

```
regime_at_entry                      bear  bull  choppy
family                                                 
counter-trend, no 200-reclaim/hold  -9.70 -8.88   -8.13
failed reclaim-and-hold            -10.14 -8.17   -8.56
held confirmation                   -6.01 -5.13   -5.39
reclaimed 200 & held                -3.94 -5.88   -4.80
veto: bearish divergence            -9.24 -8.18   -8.59
```

`regime_at_entry` and `fwd_mdd_60` are both functions of the same price series, so a
bear-tape column is deeper for *every* family — a market main effect, not per-family
reliability. Month fixed effects remove it:

```
regime_at_entry                     bear  bull  choppy
family                                                
counter-trend, no 200-reclaim/hold -0.66 -1.77   -0.23
failed reclaim-and-hold            -1.22 -0.31   -0.48
held confirmation                   1.66  2.19    2.09
reclaimed 200 & held                3.31  1.95    2.79
veto: bearish divergence           -0.29 -0.41   -0.96
```

## 2. The interaction — what the proposal actually needs

`cell - family_mean - regime_mean + grand_mean`:

```
regime_at_entry                     bear  bull  choppy
family                                                
counter-trend, no 200-reclaim/hold  0.57 -1.49    0.37
failed reclaim-and-hold            -0.07 -0.11    0.04
held confirmation                   0.22 -0.19    0.02
reclaimed 200 & held                0.95 -1.36   -0.20
veto: bearish divergence            0.86 -0.21   -0.44
```

```
family main-effect spread     3.59 pp
regime main-effect spread     0.95 pp
largest |interaction|         1.49 pp
```

**Knowing the family is worth 3.8x more than knowing the regime.** The interaction the proposal would trade on is the smallest term.

Cell counts (note the two thinnest cells carry the two largest interactions):

```
regime_at_entry                     bear  bull  choppy
family                                                
counter-trend, no 200-reclaim/hold  5706    48    1700
failed reclaim-and-hold             1203  4787    1351
held confirmation                   1280  6096    1485
reclaimed 200 & held                 509    41     449
veto: bearish divergence             302  2075     478
```

## 3. Month-block bootstrap 95% CI on each interaction cell

B=600, resampling whole months (signals inside a month share their market).

| family | regime | n | interaction (pp) | 95% CI | excludes 0 |
|---|---|---:|---:|---|---|
| counter-trend, no 200-reclaim/hold | bear | 5706 | +0.57 | [+0.37, +0.76] | **yes** |
| counter-trend, no 200-reclaim/hold | bull | 48 | -1.49 | [-3.71, +0.20] | no |
| counter-trend, no 200-reclaim/hold | choppy | 1700 | +0.37 | [+0.00, +0.70] | **yes** |
| failed reclaim-and-hold | bear | 1203 | -0.07 | [-0.47, +0.33] | no |
| failed reclaim-and-hold | bull | 4787 | -0.11 | [-0.23, +0.04] | no |
| failed reclaim-and-hold | choppy | 1351 | +0.04 | [-0.27, +0.35] | no |
| held confirmation | bear | 1280 | +0.22 | [-0.15, +0.57] | no |
| held confirmation | bull | 6096 | -0.19 | [-0.30, -0.07] | **yes** |
| held confirmation | choppy | 1485 | +0.02 | [-0.26, +0.30] | no |
| reclaimed 200 & held | bear | 509 | +0.95 | [+0.53, +1.36] | **yes** |
| reclaimed 200 & held | bull | 41 | -1.36 | [-3.90, +0.70] | no |
| reclaimed 200 & held | choppy | 449 | -0.20 | [-0.67, +0.26] | no |
| veto: bearish divergence | bear | 302 | +0.86 | [-0.04, +1.73] | no |
| veto: bearish divergence | bull | 2075 | -0.21 | [-0.36, -0.04] | **yes** |
| veto: bearish divergence | choppy | 478 | -0.44 | [-1.02, +0.10] | no |

Cells whose CI excludes 0: **5/15**.

## 4. Era-split sign stability (split 2010-01-01, cells with n>=30 both eras)

The house kill standard: an effect whose sign flips between halves is noise.

| family | regime | pre-2010 | 2010+ | stable |
|---|---|---:|---:|---|
| counter-trend, no 200-reclaim/hold | bear | +0.51 | +0.68 | SAME |
| counter-trend, no 200-reclaim/hold | choppy | +0.27 | +0.50 | SAME |
| failed reclaim-and-hold | bear | -0.16 | +0.06 | **FLIP** |
| failed reclaim-and-hold | bull | -0.11 | -0.08 | SAME |
| failed reclaim-and-hold | choppy | +0.20 | -0.24 | **FLIP** |
| held confirmation | bear | +0.38 | -0.09 | **FLIP** |
| held confirmation | bull | -0.18 | -0.19 | SAME |
| held confirmation | choppy | -0.12 | +0.20 | **FLIP** |
| reclaimed 200 & held | bear | +0.86 | +1.09 | SAME |
| reclaimed 200 & held | choppy | -0.31 | -0.04 | SAME |
| veto: bearish divergence | bear | +1.88 | -0.57 | **FLIP** |
| veto: bearish divergence | bull | -0.29 | -0.08 | SAME |
| veto: bearish divergence | choppy | -0.67 | -0.06 | SAME |

Sign-stable **8/13 (62%)**. Coin-flip expectation is 50%.

## Verdict

- The regime axes the proposal specifies are **not estimable** here: 0.4% stamp coverage, one month, and two axes observed in a single state (§0).
- On the one axis with 64 years of coverage, the family x regime interaction is **3.8x smaller** than simply knowing the family (§2).
- The two largest interaction cells are the two **thinnest** (n=41-48); their CIs include 0 (§3).
- Sign stability across the era split is **62%** — at chance (§4).

**NULL.** A regime-conditional reliability table is not supportable on this record.
The dominant, era-stable, already-published term is *which family fired* — not the
regime it fired in. Closes this construction; re-opening requires the estimability
gate in `engine/regime_conditioning_coverage.py` to turn green on a richer axis.


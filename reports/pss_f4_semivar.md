# PSS-F4 — Downside-vol asymmetry flip (semivariance regime turn)

Reset-CONFIRMER / symmetry-reset construction (copy law R-W1T-3 — no 'bottom caller' / 'calls bottoms'). Pre-registered ruler + construction: script header, committed pre-run (prereg commit precedes results commit in git history; the absolute-threshold → per-name-baseline + dispersion-eligibility re-pin is disclosed there as amendments A1/A2/A3, all pre-outcome). Entry-timing ruler (§7), NOT hold returns (wrong-ruler check performed; motive #1458). Machinery (metric_arrays / null_stats / bars_for / tool_dates / _name_uplift per-name-first / c32_gate) COPIED from the W1 + F1 + F2 + F3 scripts. Inference: month-cluster bootstrap, NB=1000, seed 20260731. F4 makes NO pre-trough claim — it is an AT-TROUGH confirmer; its only path to usefulness is being a BETTER or genuinely COMPLEMENTARY at-trough confirmer than the incumbent. The commissioning session rules the verdict; this reports what was found.

> **Causal-timing erratum (2026-07-26):** the historical construction labels the
> first bar of a run that is only known retrospectively to survive P bars. For
> P=5, a live confirmation is observable four sessions later. Therefore the
> reported median tdt of −9td is an onset-label diagnostic; an actionable
> persistence confirmation is approximately −13td on the same runs. The
> historical label remains here for preregistered-result reproducibility. New
> work must use `_causal_sustained_run_fires` or the explicit confirmation-day
> state machines in `pss_f4_repair.py` / `pss_f4_hazard.py`.

## Coverage census (eligible / excluded, with reasons)

- Universe: 1300 W1-panel names with OHLC (semivariance on daily log returns; yahoo close is total-return adjusted, the ratio A nets it out).
- **F4-eligible: 1300** (FIT-era asymmetry spread A_hi−A_base ≥ 0.15 — min-baseline-asymmetry as DISPERSION, amendment A3 — AND ≥3 FIT + ≥3 TEST primary-cell (n=20, P=5) fires with resolvable mae63/prox).
- **Charter-named defensives (KO PG WMT COST) — the 'correctly-null' prediction, TESTED not assumed (amendment A3):**
  - KO: **ELIGIBLE** — FIT A_base 0.914, spread 0.482 (≥ 0.15); graded like any other name. NOT excluded as baseline-symmetric.
  - PG: not in the W1 panel (off-panel).
  - WMT: **ELIGIBLE** — FIT A_base 0.926, spread 0.474 (≥ 0.15); graded like any other name. NOT excluded as baseline-symmetric.
  - COST: **ELIGIBLE** — FIT A_base 0.824, spread 0.541 (≥ 0.15); graded like any other name. NOT excluded as baseline-symmetric.
  - FINDING: the charter predicted these live near A≈1 with 'no signal content' and would be correctly-null. The MEASURED data does NOT bear this out — their conditional (in-drawdown) asymmetry and their A-spread are normal, so they are ELIGIBLE and graded. The 'correctly-null defensives' prediction is reported as NOT confirmed (disclosed as a finding, not a coverage loss).

- Per-name FIT asymmetry axis (eligible names): A_base median 0.967 (deciles [0.9, 0.967, 1.043]); A_disp median 0.660; spread (A_hi−A_base) median 0.499, min 0.232. NOTE: A_base < 1 across the panel (amendment A1) — the reset level is the name's OWN trailing baseline, never an absolute 1.0.
- TEST F4 signals (primary cell, pooled): 26,099; total-vol-analog fires (TEST, pooled): 10,764.

Panel all-days OOS base rates (median across eligible names): MAE63 -8.16%, within-5%-of-low 16.3%, called-low 8.4%. (The charter's ~16% ambient within-5%-of-low is prong-1's null.)

## Grid (multiplicity budget: 4 cells) — TEST U_MAE / U_W5, name-level medians (no gate)

No per-name best-of-grid selection (DNR §2). Primary cell = (n=20, P=5). Point estimates are panel medians of per-name uplifts; the CI/inference rows are the pooled month-cluster bootstrap on the primary cell below. n = RV window (daily); P = persistence (consecutive symmetric bars, the dead-cat gate).

| cell | n names | U_MAE | U_W5 | median OOS fires/name |
|---|---|---|---|---|
| n=10, P=3 | 1300 | +0.79pp | -2.00pp | 46 |
| n=10, P=5 | 1300 | +1.51pp | -1.97pp | 37 |
| n=20, P=3 | 1300 | +0.74pp | -5.95pp | 24 |
| n=20, P=5 ★ | 1300 | +1.36pp | -5.98pp | 20 |

### Primary cell across eras (full TEST / 2021+ sub-window), no gate

| era | U_MAE | U_W5 |
|---|---|---|
| full TEST ≥2020-07 | +1.36pp | -5.98pp |
| 2021+ ≥2021-01 | +1.32pp | -6.08pp |

## Gate variants on the primary cell (pre-stated column pair: RAW / +C32), name-level medians

RAW = no terminality gate. +C32 = decline-deceleration terminality gate (roc20 stopped making new lows while close ≤ 60d low + rolling-low slope flattening; copied verbatim from pss_f1_downvol).

| variant | U_MAE OOS | U_W5 OOS | U_MAE 2021+ | U_W5 2021+ | n names OOS | median C32 fires/name |
|---|---|---|---|---|---|---|
| RAW (no gate) | +1.36pp | -5.98pp | +1.32pp | -6.08pp | 1300 | 20 |
| +C32 | +3.20pp | +73.70pp | +3.73pp | +74.10pp | 55 | 1 |

⚠️ **C32-gated U_W5 is DEGENERATE (small-sample artifact, NOT a signal) — read the CI, not the point estimate.** The C32 gate is so restrictive that the surviving names carry a median of ~1 gated fire EACH, so each name's within-5%-of-low RATE collapses to 0% or 100% and the cross-name median of those degenerate binary rates swings wildly (here to a physically implausible ~+74pp). The month-cluster bootstrap CI below correctly reports this column as `includes 0` (a wide, 0-straddling interval) — i.e. the C32-gated U_W5 estimates NOTHING. The C32-gated U_MAE (a continuous statistic) does NOT collapse this way and is read normally. This is a vacuous-green disclosure, not a result.

## Inference — month-cluster bootstrap (primary cell), vs BOTH nulls

Per-name-first collapse then cross-name median (matches the F1/F2/F3/W1-T machinery — the F1 E1 sign-flip bug is NOT repeated): within each month-cluster draw, U_MAE = name-median mae63 − name all-days median, U_W5 = name signal-day within-5%-of-low rate − name all-days rate, THEN the cross-name median. Two nulls: (a) all-DAYS base rate [inside the per-name uplift], (b) the TOTAL-VOL ANALOG (identical construction on directionless RV_tot — the asymmetry-adds-nothing mirror placebo). The F4 − total-vol-analog diff is PAIRED on the same resampled month-clusters.

Self-check (F1 E1 guard): direct per-name-median U_W5 = F4 -5.98pp / total-vol-analog -6.66pp; the bootstrap point estimates below must match these within bootstrap noise.

| quantity | full TEST | 2021+ |
|---|---|---|
| F4 U_MAE (vs all-days null), no gate | [+0.40, +2.29] excludes 0 ↑ | [+0.25, +2.32] excludes 0 ↑ |
| F4 U_W5 (vs all-days null), no gate | [-8.36, -5.93] excludes 0 ↓ | [-8.44, -6.02] excludes 0 ↓ |
| F4 U_MAE, +C32 | [+1.93, +5.28] excludes 0 ↑ | [+2.57, +5.61] excludes 0 ↑ |
| F4 U_W5, +C32 | [-6.23, +77.22] includes 0 | [-5.41, +76.88] includes 0 |
| total-vol-analog U_MAE (asymmetry-adds-nothing null) | [-1.60, +0.97] includes 0 | [-1.75, +0.97] includes 0 |
| total-vol-analog U_W5 (asymmetry-adds-nothing null) | [-10.27, -8.01] excludes 0 ↓ | [-10.59, -8.41] excludes 0 ↓ |
| F4 − total-vol-analog  U_MAE (FALSIFIER, paired) | [+0.43, +2.92] excludes 0 ↑ | [+0.52, +2.92] excludes 0 ↑ |
| F4 − total-vol-analog  U_W5 (FALSIFIER, paired) | [+0.54, +3.23] excludes 0 ↑ | [+0.88, +3.52] excludes 0 ↑ |

The FALSIFIER rows are the pre-stated kill (prong 2): if F4 − total-vol-analog does NOT exclude 0 (positive) on U_MAE/U_W5, the DIRECTIONAL asymmetry (the down/up ratio) carries no incremental information over plain vol-normalization, and F4 dies as a standalone construction. Printed regardless of outcome.

## Overlap / disjointness census — F4 vs total-vol analog (primary cell, TEST)

A is a RATIO and RV_tot is a LEVEL — an asymmetry flip can happen while total vol stays elevated, and vol can compress while A stays down-dominated. So F4 fires are NOT a subset of vol-compression days; the placebo is a matched-construction counterfactual, not a disjoint complement.

- BOTH F4 & total-vol-analog: 969 · F4-only (asymmetry flip w/o a coincident vol-compression run): 25,130 (96% of F4 fires) · analog-only: 9,795.
- F4-only share reflects how often the directional asymmetry flips without total vol simply compressing — the matched counterfactual is genuine, not a subset.

## Better at-trough confirmer OR redundant? — F4 vs incumbent (Stoch-RSI<20 @ derived rung, SAME names)

F4 makes NO pre-trough claim (charter): 'strictly earlier' is NOT required. The test (charter prong 2) is whether F4 is a BETTER at-trough confirmer (shallower MAE and/or closer td_to_trough) or just a REDUNDANT one. td_to_trough: negative = trough BEFORE the fire (late confirmer). Per-name medians over TEST, then panel median of those. If P pushes the fire so late that td is no better than the incumbent's −2..−10 AND MAE is no shallower, F4 has collapsed into another reset-confirmer with no gain.

| comparison | n names | F4 median tdt | incumbent median tdt | F4 − incumbent tdt | F4 median MAE | incumbent median MAE | F4 − inc MAE |
|---|---|---|---|---|---|---|---|
| F4 vs incumbent | 1300 | -9.0td | -2.0td | -8.0td | -6.79% | -8.20% | +1.21pp |
| F4 vs total-vol-analog (context) | 1300 | -9.0td | -19.0td | +9.0td | -6.79% | -8.21% | +1.47pp |

For tdt: MORE POSITIVE = closer to / before the trough = better. For F4 − incumbent MAE: POSITIVE = F4 shallower adverse excursion = better entry. F4 is a BETTER confirmer only if it improves on at least one axis at a meaningful margin; if both diffs sit near 0, F4 is REDUNDANT with the incumbent (the charter's prong-2 kill).

## 2022-class containment — P-sensitivity of H1-2022 false fires (the earliness-vs-2022-safety frontier)

Charter: too-short P re-imports the 2022 early-fire class (brief symmetry patches during relief bounces that re-invert to down-dominance within a few bars); a sufficiently long P should not trigger until the true trough. Fire counts H1-2022 (2022-01-01..2022-06-30) vs ±21td around the 2022-10-13 low, at n=20, ACROSS P=3 vs P=5 (RAW, no C32). NVDA is OFF-PANEL (W1 eligibility) — run from raw OHLCV, flagged.

| name | H1-2022 (P=3 / P=5) | ±21td 2022-low (P=3 / P=5) |
|---|---|---|
| NVDA (off-panel) | 2 / 1 | 1 / 1 |
| TSLA | 1 / 1 | 0 / 0 |
| AMZN | 3 / 2 | 1 / 0 |
| JPM | 4 / 4 | 1 / 1 |
| XOM | 3 / 2 | 1 / 1 |
| HD | 0 / 0 | 1 / 1 |
| **FOCUS TOTAL** | **13 / 10** | **5 / 4** |

If P=5 cuts the H1-2022 false-fire count vs P=3 while retaining near-low coverage, the persistence gate is doing its 2022-defense job; if H1-2022 fires are as frequent at P=5 as at P=3, the too-short-P failure class is not contained by persistence alone. Reported regardless of outcome.

## Product split (descriptive; near-low vs confirms-reset)

F4 primary-cell TEST fires (n=26,099): near-low (−2..+5td) 6% · confirmed-reset (<−2td) 66% · after-low (>+5td) 28% · median td_to_trough -9td.

## What was found (no verdict — the commissioning session rules)

- F4 (no gate) U_MAE vs the all-days null on full TEST: [+0.40, +2.29] (excludes 0 ↑); U_W5 [-8.36, -5.93] (excludes 0 ↓).
- The pre-stated FALSIFIER (F4 − total-vol analog, asymmetry-adds-nothing): U_MAE [+0.43, +2.92] (excludes 0 ↑), U_W5 [+0.54, +3.23] (excludes 0 ↑) on full TEST; 2021+ U_MAE [+0.52, +2.92] (excludes 0 ↑), U_W5 [+0.88, +3.52] (excludes 0 ↑).
- The +C32 gate column, the better-confirmer-or-redundant table (F4 vs incumbent on BOTH td_to_trough and MAE), the overlap census, and the 2022 P-sensitivity counts above are the pre-registered conditioner / falsifier reads. All nulls are printed. F4 makes NO pre-trough claim; the at-trough 'better or redundant' verdict input is the F4-vs-incumbent table.
- CAUTION on the +C32-gated U_W5 point estimate: the gate leaves ~1 fire per surviving name, so that binary-rate column is a small-sample artifact (its CI correctly includes 0 — it estimates nothing); the gated U_MAE (continuous) is unaffected. See the gate-variant degeneracy note above.

## Limitations

- Closes-only MAE/troughs (house shadow-book form); intraday lows are deeper. Comparable across cells/variants, not absolute.
- Yahoo close is total-return adjusted; semivariance is on log returns and A is a RATIO, so the TR adjustment nets out (level-invariant).
- Survivor tape (data/baskets/ohlcv holds today's listings); per-name own-baseline netting removes level bias, not composition bias.
- The symmetric-reset level is the name's OWN trailing baseline A_base, NOT an absolute 1.0 — the unconditional FIT A_base is <1 across the panel (amendment A1); the mechanism's asymmetry is CONDITIONAL on the decline (amendment A2, measured pre-outcome). The absolute-1.0 crossing in the charter sketch was degenerate against the data and re-pinned pre-outcome.
- Eligibility is DISPERSION (A_hi−A_base spread), not an absolute A_base gate (amendment A3): the charter's baseline-symmetric-defensives premise did not hold in the data, so defensives are eligible-and-graded and the 'correctly-null defensives' prediction is reported as NOT confirmed.
- ±31td proximity window is the §7 pin; long bear legs make 'the low' window-relative. The total-vol analog shares this window (fair test).
- Trailing bands are PIT (min 252 / cap 756 obs, shifted one bar); the leading region before the band fills never fires. n is the RV window (daily), P the persistence gate (the tunable) — the RV grain is daily, not rung-bar (pinned choice, disclosed).
- NVDA/PG are off the W1 panel (W1 eligibility); the 2022 P-sensitivity diagnostic runs NVDA as a raw-OHLCV exhibit, flagged.

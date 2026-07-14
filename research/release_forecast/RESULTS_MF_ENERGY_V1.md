# Results — MRI Track T mf_energy v1 (Mixed-Frequency Energy Accumulator)

**Run date:** 2026-07-10
**Spec:** research/release_forecast/PREREG_MF_ENERGY_V1.md (frozen 2026-07-10)
**Target:** cpi_headline (CPIAUCSL MoM % SA, ALFRED initial prints)
**Model:** mf_energy — reference-month gasoline accumulator + ex-energy AR(3)+seasonal + ridge head
**Anti-mining:** backtest run once after prereg commit; no spec changes post-results.

**Kill rule (T-1, MRI-R28 strongest-naive):** model MAE >= max(naive, expanding_mean, trailing_3m) in BOTH full AND 2021+ -> benchmark_only, NOT shadowed.
Early cutoff comparison is DESCRIPTIVE only — no kill rule applied there.

---

## T-1 Cutoff (Primary — Kill-Rule Evaluation)

**Predictions:** 292
**Verdict:** ACTIVE (shadow-eligible)
**Kill-rule detail:** ACTIVE (beats strongest naive on BOTH windows): full 0.1421 < 0.2568; 2021+ 0.1794 < 0.2524

### Era-Split Metrics (T-1)

| Era | n | MAE model | MAE naive | MAE exp-mean | MAE trail3m | MAE strongest | RMSE | Cov p10-p90 | Skew HR | Wilson 95% CI | Skew n | Pinball |
|-----|---|-----------|-----------|--------------|-------------|---------------|------|-------------|---------|---------------|--------|---------|
| Full (non-COVID) | 288 | 0.1421 | 0.2568 | 0.2262 | 0.2564 | 0.2568 | 0.1960 | 78.4% | 0.829 | [0.78, 0.869] | 275 | 0.2648 |
| pre-2010 | 96 | 0.1517 | 0.3340 | 0.2703 | 0.3408 | 0.3408 | 0.2033 | 72.2% | 0.892 | [0.807, 0.942] | 83 | 0.2844 |
| 2010–2020-02 | 122 | 0.1173 | 0.2081 | 0.1809 | 0.2072 | 0.2081 | 0.1566 | 85.2% | 0.844 | [0.77, 0.898] | 122 | 0.2138 |
| COVID (2020-03..06) | 4 | 0.1054 | 0.5611 | 0.5467 | 0.6513 | 0.6513 | 0.1148 | 100.0% | 1.000 | [0.51, 1.0] | 4 | 0.1647 |
| 2020-07..12 (recovery) | 6 | 0.0980 | 0.1477 | 0.1639 | 0.2616 | 0.2616 | 0.1135 | 100.0% | 0.833 | [0.436, 0.97] | 6 | 0.1673 |
| 2021+ | 64 | 0.1794 | 0.2442 | 0.2524 | 0.2233 | 0.2524 | 0.2508 | 70.3% | 0.719 | [0.599, 0.814] | 64 | 0.3493 |

---

## Early Cutoff (Descriptive — ~25 days before release)

**Note:** Kill rule does NOT apply here. This section evaluates the accumulator's
value claim: does within-month WTI accumulation improve accuracy at the early asof
vs the champion (which has no accumulator and relies on lag features only)?
The forward ledger is the sole judge of the value claim — this is exploratory.

**Predictions:** 292

### Era Metrics (Early, Descriptive)

| Era | n | MAE model | MAE naive | MAE exp-mean | MAE strongest | RMSE | Cov p10-p90 | Skew HR | Pinball |
|-----|---|-----------|-----------|--------------|---------------|------|-------------|---------|---------|
| Full (non-COVID) | 288 | 0.1432 | 0.2568 | 0.2262 | 0.2568 | 0.1975 | 78.4% | 0.826 | 0.2657 |
| 2021+ | 64 | 0.1813 | 0.2442 | 0.2524 | 0.2524 | 0.2592 | 73.4% | 0.719 | 0.3531 |

---

## Head-to-Head: mf_energy vs Champion

**Comparison basis:** mf_energy@early vs champion@early uses the SAME early-asof
convention (release_date - 26 days) for both models. CAVEAT: the two columns are
NOT computed over an identical matched fold set — champion@early yields fewer
valid folds (feature availability differs at early asofs), so the MAEs compare
overlapping-but-unequal samples (mf_energy n=288 non-COVID vs champion@early
n=228 matched). Read the deltas as indicative, not as a matched-pairs test; a
matched-fold table is the W11-G integration follow-up. Champion@T-1 is shown as
a reference for the standard-cutoff baseline. The early-cutoff comparison is
DESCRIPTIVE; kill rule applies at T-1 only.

| Metric | mf_energy@T-1 | mf_energy@early | champion@early | champion@T-1 (ref) |
|--------|---------------|-----------------|----------------|--------------------|
| Full MAE | 0.1421 | 0.1432 | 0.1478 | 0.1578 |
| 2021+ MAE | 0.1794 | 0.1813 | 0.1781 | 0.1732 |
| Full strongest_naive MAE | 0.2568 | — | — | 0.2568 |
| 2021+ strongest_naive MAE | 0.2524 | — | — | 0.2442 |
| Full RMSE | 0.1960 | 0.1975 | 0.1986 | 0.2055 |
| Full coverage | 78.4% | 78.4% | — | 71.6% |
| Pinball (full) | 0.2648 | 0.2657 | — | 0.2928 |
| n predictions | 292 | 292 | 228 | 292 |

---

## Kill-Rule Verdict (T-1, MRI-R28 + MRI-R36)

**Kill fired:** NO
**Detail:** ACTIVE (beats strongest naive on BOTH windows): full 0.1421 < 0.2568; 2021+ 0.1794 < 0.2524

**Outcome:** Track T / mf_energy is SHADOW-ELIGIBLE for cpi_headline.
Shadow rows tagged `mf_energy` will be wired in W11-G (Round 2 serial integration).
The forward ledger is the sole judge of the value-claim (early-cutoff accuracy vs champion).
Promotion to the card requires a program-level adjudication citing forward evidence
(guideline: n≥6 scored prints AND challenger MAE ≤ champion MAE).

---

## PIT / Provenance Notes

- CPIAUCSL: ALFRED initial prints via knowable_series() — fully PIT-safe.
- GASREGW: weekly, effectively unrevised (BLS survey). Only weeks with index date <= asof used.
- DCOILWTICO: daily, effectively unrevised (EIA spot price). Only dates <= asof used.
- WTI pass-through beta: estimated on weeks strictly BEFORE reference month M — no look-ahead.
- Gamma (headline ~ gasoline): estimated on months < M — no look-ahead.
- CPI RI weights: revision_optimistic (BLS flat file, not ALFRED-vintaged).

---

## Alignment with PREREG_MF_ENERGY_V1.md

One DECLARED implementation interpretation; all other specs implemented as
frozen. The prereg §2.1(b) wording defines a remaining week's WTI input as
"average daily WTI over trading days in that week where date <= D" — for a
remaining week (which by definition starts AFTER the asof D), that set is
empty, so the literal wording is unsatisfiable. The implementation uses the
nearest causally-available proxy: the 7-day WTI window ending at asof (the
latest observable WTI level) as the projected level for each remaining week.
This is a strict subset of information available at D (no lookahead — tested
by post-asof-spike invariance), is the natural reading of the spec's intent
(project unpublished weeks from the latest observable WTI), and was NOT chosen
by reference to results. Recorded here per §6; any alternative proxy would be
a new spec attempt.
This document constitutes the backtest-results record per §6 anti-mining law.

---

## MRI-R30 Recalibration (2026-07-10) — Vol-Scaled Residual Quantile Bands

**Spec:** research/release_forecast/PREREG_INTERVAL_RECAL_V1.md (frozen before run)
**Points unchanged** — only the bands move.

### mf_energy (cpi_headline) — BEFORE vs AFTER

| Era | n | p10-p90 BEFORE | p10-p90 AFTER | p25-p75 BEFORE | p25-p75 AFTER | Pinball BEFORE | Pinball AFTER |
|-----|---|----------------|---------------|----------------|---------------|----------------|---------------|
| Full | 292 | 78.7% | 76.1% | 48.1% | 46.6% | 0.263329 | 0.259808 |
| 2021+ | 64 | 70.3% | 71.9% | 48.4% | 45.3% | 0.349265 | 0.333935 |
| 2015+ | 136 | 78.7% | 75.7% | 50.0% | 47.1% | 0.273111 | 0.266452 |

**Verdict:** mf_energy was already in [70%,95%] before recalibration. Coverage decreases slightly on full window (78.7%→76.1%) but remains well within gate. 2021+ coverage improves marginally (70.3%→71.9%). Pinball improves on all eras. No coverage falsifier was triggered for this target. Shadow-eligible status (beat naive) unchanged.


---

## Addendum 2026-07-14 — corrected-formula re-run (post CPI June-2026 post-mortem)

**Defect (defect_notices.json DN-002):** `energy_contrib = gas_mom * (GASOLINE_RI_WEIGHT/100) * gamma`
applied the basket weight twice: gamma is the expanding bivariate OLS slope of cpi_hl_mom on
gasoline_mom (~0.039) and already embeds the ~2.895% basket share (weight alone implies a
slope of ~0.029). The extra `ri_weight/100` factor shrank the energy leg by exactly
1/(2.895/100) = 34.5x. On the contaminated 2026-07-13 ledger row: gas_mom = -9.592,
defective energy leg = -0.0109 pp, corrected = -0.3757 pp. Fixed 2026-07-14:
`energy_contrib = gas_mom * gamma` (train + serve; PREREG_MF_ENERGY_V1.md Amendment 2026-07-14).

**All numbers in the body above were measured under the defective formula and cannot
support promotion or kill decisions on their own.** The body is preserved unmodified as
the original record; this addendum is the corrected measurement.

### Corrected kill-rule detail (T-1, 2026-07-14 re-run) vs original

| Window | Original MAE | Corrected MAE | MAE strongest naive | Verdict |
|--------|-------------:|--------------:|--------------------:|---------|
| Full (non-COVID) | 0.1421 | 0.1453 | 0.2568 | ACTIVE / SHADOW-ELIGIBLE (unchanged) |
| 2021+ | 0.1794 | 0.1925 | 0.2524 | ACTIVE / SHADOW-ELIGIBLE (unchanged) |

Corrected-run artifacts: `results/backtest_mf_energy_v1_summary.json` (regenerated 2026-07-14;
pre-fix artifacts preserved in git history at the parent of the fix commit).

### Causal channel of the correction — read carefully

The head model z-scores its features, and z-scores are invariant under uniform column
scaling — so multiplying the entire energy_contrib column (train + prediction) by 34.5x
changes NOTHING through the direct energy channel. The correction moves predictions only
through the derived ex-energy series: `exenergy = target - energy_contrib` now subtracts a
34.5x larger (and noisier) energy estimate, which re-fits the AR(3)+seasonal leg. The modest
MAE degradation (Full 0.1421 -> 0.1453; 2021+ 0.1794 -> 0.1925) is the expected consequence
of that larger subtraction — it is a more honest decomposition, not evidence against the
correction. Dry-run at asof 2026-07-13: point -0.206 (defective) -> -0.2701 (corrected)
vs actual -0.4 — the miss shrinks from 0.194 pp to 0.130 pp.

Head-to-head caveat from the original body still applies to any corrected comparison:
champion@early is computed on fewer valid folds (n=228 vs 292), so those columns compare
overlapping-but-unequal samples — indicative, not a matched-pairs test. In the corrected
run, mf_energy 2021+ MAE (0.1925) now trails champion@T-1 (0.1616); descriptive only —
the kill rule is vs strongest naive, and the forward ledger remains the sole judge of the
early-cutoff value claim.

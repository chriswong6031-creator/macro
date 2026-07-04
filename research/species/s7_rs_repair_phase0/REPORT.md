# S7 RS-Repair Phase-0 — Results Report

**Program:** Setup-Species (research/SETUP_SPECIES_MASTERPLAN_BY_FABLE.md), S7 brought
forward from W3. **Pre-registration:** [SPEC.md](SPEC.md) (frozen 2026-07-03, before any
code ran). **Run:** 2026-07-04, after the massive-store 2023-02→2025-01 backfill completed.
**Provenance:** external Codex backtest triage (see memory `codex-bottom-backtest-verdict`
and `research/bottom_signal_backtest/`) supplied the opposite-sign external evidence that
justified pulling the two-sided S7 registration forward.

**In plain English:** we tested whether a beaten-down stock whose *relative strength is
already recovering* makes a better bottom-fishing entry than one still bleeding. Answer:
it depends entirely on what you measure recovery against. Recovery versus the S&P 500
tells you nothing (and was mildly worse). Recovery versus the stock's own sector peer
group — moving up the pecking order inside its cohort — cut stop-outs by ~6 points and
raised clean-liftoff rates by ~9 points, with confidence intervals that exclude zero.
The Codex "triple-lock" (require capitulation + RS repair + near-the-low all at once)
did **not** survive: the cohort-washout leg we already ship (COILED) does the work.

## 1. What ran

| | P1 (breadth) | P2 (era depth) |
|---|---|---|
| Universe | massive_stock_day, 20,177 tickers, liquidity-floored at fire date (63d median $vol ≥ $2M, close ≥ $2) | data/stocks deep panel, 224 names |
| Span | 2021-07 → 2026-07 (fires usable from ~2022-06 after warm-up) | 1963 → 2026 |
| F1 fires (dev) | 28,338 (of 47,941 total) | 22,142 |
| F2 fires (dev) | ~4,000 | 4,767 |
| Dev / holdout | dev ≤ 2024-12-31; holdout 2025-01 → 2026-06 (touched once, §7) | all-sample context arm |

The store's 2023-02→2025-01 gap was backfilled to completion before the P1 run
(pipeline waited on `_backfill_state.json`); the fire-per-month histogram is continuous
across both former gap boundaries. Contiguity guard dropped 0 fires post-backfill.
Sector-mapped strata (rs_sect, rs_cohort_rank, cohort_frac_w) cover the ~500 current-
S&P-500 names only → n≈3.5k of 28k dev fires; all deltas are measured against
same-computable-subset baselines, so the mapped-subset confound from the Codex run
cannot recur.

## 2. Metrics

Charter definitions: race stop-out (fill at close t+1 → close −5% before close +5%,
resolved within 131 bars; censoring-honest categories), clean8_21 (P1 co-primary),
clean15_126 (P2 co-primary), day-20 forward return, MFE/MAE-20d, 60d-undercut.
90% CIs by time-block bootstrap (2,000 draws).

## 3. Deviations from SPEC (all logged before holdout unlock)

- **D0a** F1 uses `resample("3B")` per `tuning_harness.py base3d` (the charter harness
  definition), not the engine's session-grouped 3D bars.
- **D0b** `above_10w` implemented as 50-trading-day SMA of daily closes.
- **D0c** P2 RS benchmark = `data/yahoo/SPY.parquet` (total-return) — internally
  consistent within P2; never mixed with P1/massive (price-return) series.
- **D0d** F2 oversold window = min(K,D) 3×2W-bars **including** the cross bar
  (Codex-faithful; their `shift(1)` quirk fixed per SPEC §3).
- **D1** Broad strata fire near-continuously → gap-episode clustering collapses to one
  block and the frozen ≥8-episode guardrail refuses verdicts on exactly the headline
  strata. Fallback: calendar-month block bootstrap (`OK (month-block D1)` in tables).
  Side effect: point estimates in previously-NO_VERDICT rows now use the table's stat
  (median tables previously displayed means in those rows).
- **D1b** Paired month-block **delta** bootstrap added (stat = A−B per draw) — the
  honest test when marginal CIs overlap.
- **D2** Post-build review fixes (before any full run): day-20 forward return replaced
  a mislabeled path-median; censoring-honest race categories; contiguity guard was
  silently inert due to a datetime-resolution unit bug (µs vs ns → gaps read 1000×
  too small) — fixed unit-safe and verified on synthetic gapped indices.

## 4. Dev results (F1/P1, 31 months, fires ≤ 2024-12-31)

### H-A — S7 two-sided: does RS repair stratify fire quality?

Paired deltas (repair − deterioration), month-block 90% CI:

| variant | stop-out Δ | clean8_21 Δ | verdict |
|---|---|---|---|
| rs_spy_slope20 (Codex naive form) | +2.3pp [−1.7, +6.3] | −0.7pp [−5.9, +5.2] | null / pointwise WORSE |
| rs_sect_slope20 (vs sector ETF) | −2.0pp [−5.7, +1.7] | +3.2pp [−2.5, +8.1] | weak, spans 0 |
| **rs_cohort_rank_slope20 (registered S7 form)** | **−5.7pp [−8.7, −1.9]** | **+8.8pp [+4.6, +11.8]** | **EXCLUDES 0 both** |
| S7 promotion bar: cohort-rank repair − rs_low stratum | −5.4pp [−9.0, −1.8] | +10.8pp [+4.6, +15.9] | **bar MET on dev** |

Marginal rates for the registered form: repair 38.0% stop-out / 62.0% liftoff /
+2.8% median fwd-20d (n=1,123) vs deterioration 43.7% / 56.3% / +2.0% (n=2,353).
P2 context: vs-SPY delta +0.2pp [−1.7, +2.1] over 382 gap-episodes — the naive form is
dead at every scale, replicating WAVE1 `rs_low` and refuting the Codex headline form.

Integrity: within-month permutation placebo — observed −5.67pp vs null mean −0.45pp
(sd 1.7pp), p≈0.000/200 draws. One fire hand-recomputed from raw parquet matches stored
fill price, stop bar, and time-to-fail exactly.

### H-B — triple-lock (registered legs: cohort≥40 ∩ rs_spy-repair ∩ loc60_15)

Pre-registered bars: ≥8pp below subset baseline AND ≥3pp below best pair. Result:
triple 36.8% vs baseline 41.9% = **5.1pp < 8pp — FAIL**; vs best pair 0.7pp < 3pp —
**FAIL**. Delta table: TRIPLE−baseline −6.9pp [−12.1, −1.2] excludes 0, but
TRIPLE−cohort≥40-only −3.3pp [−9.6, +3.1] spans 0. The conjunction adds nothing
reliable beyond the cohort leg — which is the already-validated COILED/S1 factor.
**Verdict: NO-GO as a required tier.** The pairwise failure signature was partially
present (location-only worsens stop-out on the broad set: 41.6% vs 43.5% baseline but
worse durability; cohort-only carries the effect) — the interaction story is NOT
supported at production-relevant magnitude.

### H-C — deep-tier bear robustness (reported, not gating)

cohort≥50 in bear regime (SPY < falling 200D): 31.9% stop-out point (n=454, 3 episodes,
NO_VERDICT) vs bull 40.9% [33.5, 57.0]. Directionally consistent with the external
bear-robustness claim; insufficient independent bear episodes for a verdict this cycle.

## 5. Dev verdicts

- **S7 (registered vs-cohort form): PASS on dev** — both primary and co-primary deltas
  exclude 0 and the rs_low promotion bar is met.
- **Codex vs-SPY RS-repair: REFUTED** — in-house WAVE1 prior replicates.
- **Triple-lock tier: NO-GO** — cohort washout (COILED) carries it; no new gate.

## 6. FROZEN holdout predictions (written before `--holdout` was ever run)

Holdout = P1 fires 2025-01-01 → 2026-06, one pass, definitions frozen as above.

- **P-A (S7 GO condition):** cohort-rank repair−deterioration delta is negative on
  stop-out AND positive on clean8_21 (both signs), AND ≥1 of the two delta CIs excludes
  0. Supplementary: repair−rs_low stop-out delta sign negative.
- **P-B:** vs-SPY repair delta spans 0 or is positive (refutation confirmed).
- **P-C:** triple-lock stays failed: TRIPLE−cohort-only delta CI spans 0 or improvement
  vs subset baseline < 8pp.
- **P-D (directional only):** cohort≥50 bear stop-out point ≤ bull point.

Registry action rules (frozen): P-A holds → S7 `validation_status` → `accruing`
(display-none, forward-ledger binding, quarterly come-back). P-A sign flips on both
metrics → record as falsification evidence and keep `phase0` pending W0.4 series.
Mixed → stay `phase0`, re-read after W0.4.

## 7. Holdout results (single pass, 2025-01 → 2026-07, 19 months, F1/P1)

19,541 F1 holdout fires (72 dropped by contiguity guard, 0.3%). Mapped-subset strata
n=725 repair / rs_low comparisons. Tables preserved in `results/holdout/`.

| frozen prediction | holdout outcome | scored |
|---|---|---|
| P-A: cohort-rank repair Δ signs hold AND ≥1 CI excludes 0 | stop-out **−2.7pp** [−7.2, +2.3]; clean8 **+4.0pp** [−1.2, +9.0] — both signs ✓, neither CI excludes 0 ✗; rs_low bar +1.2pp (flipped) ✗ | **FAIL (mixed)** |
| P-B: vs-SPY repair spans 0 or positive | **+7.4pp [+2.0, +13.2] EXCLUDES 0 — significantly WORSE** | **CONFIRMED+** |
| P-C: triple-lock stays failed | TRIPLE−baseline +1.1pp (worse than baseline); TRIPLE−cohort-only **+11.7pp [+0.9, +22.0] EXCLUDES 0 (worse)** | **CONFIRMED+** |
| P-D: bear cohort≥50 ≤ bull (directional) | 18.6% (n=215, 2 months, NO_VERDICT) vs 43.5% [37.3, 49.2] | direction ✓, still unpowered |

Consistency note: the holdout point (−2.7pp) lies inside the dev CI ([−8.7, −1.9]) —
attenuation in a thin, weak-for-bounces era (2025–26; cf. the Codex forensics finding
that 2024–25 was hostile to this signal class), not contradiction. Power at n=725 was
insufficient for the frozen significance bar.

## 8. Final verdicts & registry action

1. **S7 (registered vs-cohort form): stays `phase0`** per the frozen mixed-outcome rule.
   Dev PASS (both deltas exclude 0, promotion bar met) + holdout signs-hold-but-
   underpowered. Action: registry entry recorded with this evidence; re-read after the
   W0.4 within-cohort RS-rank *series* ships (the original W3 dependency — this run used
   an in-harness approximation) and/or one more quarter of fires accrues. No deployment.
2. **RS-vs-SPY slope repair: REFUTED (holdout-significant).** Recorded as
   adjacent-falsified on S7 and as rejection evidence: on modern-era bottom fires,
   absolute RS-vs-market repair selects WORSE entries. WAVE1's in-house prior stands.
3. **Triple-lock conjunction: NO-GO confirmed.** Failed pre-registered dev bars and is
   significantly worse than cohort-alone on holdout. The external Codex flagship combo
   does not survive an honest universe. Cohort washout (COILED/S1, already shipped)
   remains the load-bearing leg — re-validated here at 20k-name survivorship-honest
   breadth: cohort≥40 38.4% [31.1, 48.3] vs 43.5% broad baseline on dev.
4. **Deep-tier bear robustness (H-C):** twice-directional, never powered — remains a
   watch item inside S1's regime scope; no separate registration.

**What does NOT ship:** no engine wiring, no gate changes, no China port, no tier
promotion. The only artifacts are this research package, the S7 registry entry, and
the negative findings.

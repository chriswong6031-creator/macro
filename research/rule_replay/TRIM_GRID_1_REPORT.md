# TRIM-GRID-1 — Partial-Trim Exit Policy Surface Report

**exp_id:** trim_grid_v1
**Run date:** 2026-07-06
**Runtime:** 2756 seconds (~46 min)
**Verdict criteria:** descriptive-only
**Cumulative pooled replay trial count:** 37 (SUM); registry max-declared-budget: 15
**Status:** reported

---

## The NO-GO prior (stated first)

The exit-routing NO-GO is an established prior from the existing Oracle program: joint drawdown-AND-capture at 37–43% vs a 70% floor. This surface does NOT promote any exit rule to production behavior. Its job is to describe whether partial-trim scaled policies change the return/regret profile vs the all-or-nothing exits in exit_grid_v1. All outputs are display-only. No claim of statistical confirmation is made here or elsewhere in this document.

---

## RUL-F3.2 fire-tape counterfactual framing

This repo has **no held-position ledger** (`retro_grades` `hold_state`/`hold_days` are null; portfolio construction is docket-L8/Mastermind). All trim metrics attach to **fire events** on the replay tape. Every figure here is a hypothetical policy application on production fire events — no live portfolio is implied. Field names use `hypothetical_policy` / `counterfactual_path` semantics.

---

## Forking-paths contamination note (RUL-P3 / RUL-F3.5)

`derived_from_surface: exit_grid_v1`. The TRIM-GRID-1 cells were designed on the same fire tape already examined by exit_grid_v1. This contamination is permanent and irreversible. Any later promotion prereg on this tape must:
1. Carry `derived_from_surface: exit_grid_v1` (and now also `trim_grid_v1`).
2. State how its gate compensates — specifically: fresh OOS fires (≥ 2026-H2) plus stricter thresholds (RUL-F3.5).

---

## Cohort

- Source: `data/replay/replay_boarded.parquet`
- Filter: `verdict_type='fire' AND verdict_grade=True`
- n fires: **49,939** (same as exit_grid_v1)
- Episode clusters: **22,295** (using `episode_id` column from replay_boarded — format: `TICKER_YYYY-Www`)
- All fires are in the ERA LAW window (2021-07-06+, massive_stock_day source)
- Coverage: 100% of fires had valid price paths (split-adjusted)

**Survivorship note:** `verdict_grade=True` fires are the massive-era cohort with a delisted-name recall floor (dead_name_coverage_pct ~38%). Absolute rates are reported on this cohort. Right-tail retention is especially sensitive to this floor — see survivorship caveat below.

---

## Vintage stamp

- price_plane_id: massive_stock_day_v1
- adjustment_mode: split_adjusted_raw
- frame: pit_massive_era_law
- survivorship_biased: false
- era_law_cohort: verdict_grade_2021plus

---

## Episode-cluster independence note

22,295 clusters across 49,939 fires means the average fire count per cluster is approximately 2.2. Clusters are defined at the `TICKER_Www` week level. CIs are NOT computed in this descriptive batch; any inferential use requires episode-clustered bootstrap.

---

## ScaledPolicy semantics (RUL-F3.5 amendment)

A `scaled` policy partitions the position into legs, each exiting its fraction per its own policy. The fire's policy return = Σ fraction × leg_return. Foregone MFE and avoided MAE are fraction-weighted sums of per-leg values.

**EXIT-GRID-1 bug-class prevention:** Per-leg results that NEVER TRIGGERED (trail_stop/barrier/profit_take held to reference) are **included** at the reference-horizon return, NOT dropped. Dropping them was the aggregation error documented in EXIT-GRID-1 that sign-flipped wide-stop cells in the first run (the corrected aggregation includes all held-to-reference rows at the reference return). The same logic applies here: a profit_take leg that never touches its target holds to the 126-bar reference and is included at the reference return.

**profit_take(15) semantics:** exits at the first CLOSE ≥ +15% from entry (conservative close basis, first touch). If the target is never touched within the reference window, the leg holds to reference.

---

## Metric definitions

- `weighted_wr` = WR on weighted exit return (fraction-weighted sum of leg exits > 0)
- `weighted_mean_ret` = mean of fire-level weighted exit returns
- `weighted_median_ret` = median of fire-level weighted exit returns
- `weighted_foregone_mfe_126` = fraction-weighted sum of per-leg foregone MFE vs hold(126)
- `weighted_avoided_mae_126` = fraction-weighted sum of per-leg avoided MAE vs hold(126)
- `regret_ratio` = avoided_mae / foregone_mfe (>1 = saved more than gave up vs hold(126))
- `right_tail_retention` = mean scaled-policy return among fires in the top decile of hold(126) returns ÷ mean hold(126) return among those same fires
- `capital_freed_days` = weighted mean holding days across legs (vs 126-bar reference)
- `churn` = mean number of exit events per fire (n legs that actually triggered)

---

## Right-tail survivorship caveat

Right-tail retention is measured against the top decile of hold(126) returns. The massive-era cohort has a delisted-name recall floor (~38%); the right tail is where survivorship bites hardest — firms that kept rising vs those that fell and delisted. The right-tail capture rate is directionally informative but should not be over-interpreted as a precise measurement.

---

## Reference policies for comparison

From exit_grid_v1 (same cohort, same vintage):

| Reference policy | WR | mean ret | foregone MFE | avoided MAE | regret ratio |
|---|---|---|---|---|---|
| hold_21 | 0.577 | +1.9% | 0.1492 | 0.0773 | 0.52 |
| ema_trail_s8 | 0.623 | +4.4% | 0.1338 | 0.0999 | 0.75 |
| hold_126 | 0.590 | +7.3% | 0.00 | 0.00 | — |

---

## Per-cell results (trim_grid_v1)

*Full record: `data/rule_experiments/results/trim_grid_v1_summary.json` and `trim_grid_v1_perfire.parquet` (Mac-local).*

Reference horizon = 126 bars. All regret metrics are relative to hold(126) baseline.
- `foregone_mfe` = mean max(0, fwd_mfe_126 − weighted_mfe_to_exit)
- `avoided_mae` = mean max(0, |fwd_mdd_126| − |weighted_mae_to_exit|)
- `regret_ratio` = avoided_mae / foregone_mfe (>1 = saved more than gave up vs hold(126))
- `right_tail_retention` = mean scaled return among top-decile hold(126) fires ÷ mean hold(126) return in those fires
- `capital_freed_days` = weighted mean holding_days across legs
- `churn` = mean n_exit_events per fire (legs that actually triggered)

n_fires = 49,939 for all cells; clusters = 22,295 for all cells.

| Cell | WR | mean_ret | foregone_mfe | avoided_mae | regret_ratio | right_tail_retention | capital_freed_days | churn |
|---|---|---|---|---|---|---|---|---|
| trim50_h21_ema8 | 0.596 | +3.2% | 0.1415 | 0.0886 | 0.626 | 0.231 | 31.0d | 2.00 |
| trim50_h21_h126 | 0.602 | +4.6% | 0.0746 | 0.0387 | 0.518 | 0.586 | 107.1d | 2.00 |
| trim25_h21_ema8 | 0.605 | +3.8% | 0.1376 | 0.0943 | 0.685 | 0.260 | 31.2d | 2.00 |
| trim33_h21_h63_h126 | 0.604 | +4.5% | 0.0759 | 0.0377 | 0.496 | 0.550 | 102.1d | 3.00 |
| trim50_ema8_h126 | 0.625 | +5.9% | 0.0669 | 0.0500 | 0.747 | 0.645 | 107.6d | 2.00 |
| trim50_mfe15_ema8 | 0.679 | +4.7% | 0.1161 | 0.0568 | 0.489 | 0.291 | 78.5d | 1.52 |

**Reference policies (exit_grid_v1, same cohort):**

| Reference | WR | mean_ret | foregone_mfe | avoided_mae | regret_ratio |
|---|---|---|---|---|---|
| hold_21 | 0.577 | +1.9% | 0.1492 | 0.0773 | 0.52 |
| ema_trail_s8 | 0.623 | +4.4% | 0.1338 | 0.0999 | 0.75 |
| hold_126 | 0.590 | +7.3% | 0.00 | 0.00 | — |

*This report is descriptive — no promotion verdicts are issued.*

---

## Trial budget accounting (RUL-5)

| Event | Cells | Pooled `replay` SUM after |
|---|---|---|
| exit_grid_v1 (2026-07-05) | 15 | 15 |
| wait_grid_v1 (2026-07-06) | 10 | 25 |
| disp_gate_v1 (2026-07-06) | 6 | 31 |
| trim_grid_v1 (this PR) | 6 | **37** |

**Cumulative pooled replay SUM: 37**

**Registry max-declared-budget: 15** (largest single declared budget = exit_grid_v1, sourced from registry.jsonl records — NOTE: exit_grid_v1 never wrote a TrialLedger declared_budget row, so TrialLedger.effective_n('replay') currently returns 10 (wait_grid_v1); a ledger backfill is queued as separate hygiene work. Per RUL-5, both numbers are stated here: SUM=37, registry-max=15.)

Any future promotion prereg on this tape must account for N=37 cumulative trials at minimum.

---

## Key observations (descriptive — not conclusions)

1. **Blended holds (trim50_h21_h126, trim33_h21_h63_h126):** By construction, equal-weight blends of hold(21) and hold(126) must produce returns and WR between those two anchors. These cells serve as arithmetic baselines — the "expected" return for a 50/50 split is ~(1.9%+7.3%)/2 = +4.6%. Cells that deviate materially from this expectation carry genuine policy information.

2. **trim50_h21_ema8 vs trim25_h21_ema8:** The difference between these cells quantifies the marginal value of doubling the ema_trail weight. If the ema_trail leg is doing the work, the 25/75 split should outperform the 50/50 split on WR and mean return.

3. **trim50_ema8_h126:** This pairs the Oracle-ratified momentum-exhaustion exit with the longest hold. The WR floor comes from ema_trail (0.623 from exit_grid_v1); adding a 50% hold(126) leg raises the mean return and foregone MFE toward the hold(126) level.

4. **trim50_mfe15_ema8:** The profit_take(15%) leg is designed to lock in large winners early while letting the ema_trail leg manage the remainder. If the tape has few fires that reach +15%, the profit_take leg behaves like hold(126) (held-to-reference) and this cell converges toward trim50_ema8_h126. The difference between the two cells estimates how many fires actually reach the +15% threshold.

5. **Right-tail retention:** The key question is whether partial-trim policies preserve more or less of the hold(126) return among the top-decile fires. Any trim policy that exits early on winners must have right_tail_retention < 1.0 by construction; the question is how much is given up vs what is gained in capital recycling (capital_freed_days).

6. **Capital-freed days:** All trim cells must reduce mean holding days vs hold(126) = 126 bars. The question is whether the days freed by the early leg are proportional to the fraction trimmed. trim50_h21_ema8 should free roughly 50% × (126−21) / 126 ≈ 42% of the 126-day holding period on average, depending on when ema_trail fires.

---

## Comparison framework vs pure policies

The natural comparison for each trim cell is:
- **vs hold(21):** does adding the longer leg improve mean return and WR without proportionally increasing drawdown?
- **vs ema_trail_s8:** does adding the hold(21) anchor reduce churn without meaningfully sacrificing the WR advantage of ema_trail?
- **vs hold(126):** what fraction of the 126-day mean return (+7.3%) does each trim cell preserve, and at what capital cost?

These are descriptive comparisons only. No promotion is warranted without fresh OOS fires (≥2026-H2) and a pre-registered gate.

---

> **In plain English:** We tested six partial-selling strategies on every fire the system has ever approved (49,939 entries). Instead of exiting all at once, each strategy divides the position into two or three chunks, each chunk using a different exit rule. For example, "trim50_h21_ema8" sells half at the 21-session mark and lets the remaining half ride until the EMA momentum signal fires. The results show the arithmetic reality: partial-trim returns lie between those of their component exits, weighted by fraction. The interesting cells are where the interaction creates something different — whether the momentum exit on the remainder outperforms letting it all ride, or whether locking in a +15% gain on half protects against the tail. This batch is descriptive only and does not recommend any exit strategy.

---

## Appendix: cumulative pooled trial count

**37 cells declared** to date in the replay family. Both numbers per RUL-5: pooled SUM=37, registry max-declared-budget=15 (see budget-accounting note above for the TrialLedger gap).

*All numbers are close-to-close, split-adjusted (massive_stock_day_v1), next-bar fill (delay_n=1), conservative (exits fill on close of triggering bar). CIs require episode-clustered bootstrap not computed in this descriptive batch. See `data/rule_experiments/results/trim_grid_v1_summary.json` and `trim_grid_v1_perfire.parquet` (Mac-local) for the full record.*

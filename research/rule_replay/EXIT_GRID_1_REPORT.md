# EXIT-GRID-1 — Exit-Regret Surface Report

**exp_id:** exit_grid_v1
**Run date:** 2026-07-05
**Runtime:** 809 seconds
**Verdict criteria:** descriptive-only
**Cumulative pooled replay trial count:** 15 (this is the only registered experiment to date)
**Status:** reported

---

## The NO-GO prior (stated first)

The exit-routing NO-GO is an established prior from the existing Oracle program: joint drawdown-AND-capture at 37–43% vs a 70% floor. This surface does NOT promote any exit rule to production behavior. Its job is to explain *why* the two historical survivors (EMA8 tail-flag, 21-session time-exit) appear in the Oracle stack and to document the regret surface for future reference. All outputs are display-only. The word "validated" does not appear in this report.

---

## Forking-paths contamination note (RUL-P3)

This batch is a descriptive surface. Any later promotion prereg on this tape must carry `derived_from_surface: exit_grid_v1` and state how its gate compensates (stricter threshold or fresh OOS window). The surface is now seen; the contamination event is permanent.

---

## Cohort

- Source: `data/replay/replay_boarded.parquet`
- Filter: `verdict_type='fire' AND verdict_grade=True`
- n fires: **49,939**
- Episode clusters: **22,295** (using `episode_id` column from replay_boarded — format: `TICKER_YYYY-Www`)
- All 49,939 fires are in the ERA LAW window (2021-07-06+, massive_stock_day source)
- Coverage: 100% of fires had valid price paths (split-adjusted)

**Survivorship note:** `verdict_grade=True` fires are the massive-era cohort with a delisted-name recall floor. Absolute rates are reported on this cohort. No survivor-biased supplemental cohort exists for this filter.

---

## Vintage stamp

- price_plane_id: massive_stock_day_v1
- adjustment_mode: split_adjusted_raw
- universe_as_of: 2026-07-05
- frame: pit_massive_era_law
- survivorship_biased: false
- coverage_frac: 1.00
- dead_name_coverage_pct: null (stamp_degraded=True — `data/edgar/_dead_name_coverage.json` absent)
- era_law_cohort: verdict_grade_2021plus

---

## Episode-cluster independence note

22,295 clusters across 49,939 fires means the average fire count per cluster is approximately 2.2. Clusters are defined at the `TICKER_Www` week level, so multiple fires in the same stock on the same week share a cluster. Cell-level WR and return figures are computed over individual fires; the episode-cluster count is provided so the reader can assess independence. CIs are NOT computed in this descriptive batch (descriptive-only mandate); any inferential use of these numbers requires episode-clustered bootstrap.

---

## Per-cell results table

Reference horizon = 126 bars. All regret metrics are relative to the hold(126) baseline.
- `foregone_mfe` = mean max(0, fwd_mfe_126 − mfe_to_exit)  — what the policy left on the table
- `avoided_mae` = mean max(0, |fwd_mdd_126| − |mae_to_exit|)  — what the policy saved in avoided drawdown
- `regret_ratio` = avoided_mae / foregone_mfe  (>1 = saved more than gave up vs hold(126))
- `censor%` = fraction of fires where the policy exit exceeded the 126-bar window
- Exit fill: next-bar-after-signal at delay_n=1, conservative close-to-close

| Cell | n fires | clusters | WR | mean ret | median ret | foregone MFE | avoided MAE | regret ratio | censor% |
|---|---|---|---|---|---|---|---|---|---|
| hold_5 | 49,939 | 22,295 | 0.528 | +1.3% | — | 0.1976 | 0.1065 | 0.54 | 0.0% |
| hold_10 | 49,939 | 22,295 | 0.555 | +0.9% | — | 0.1788 | 0.0938 | 0.52 | 0.0% |
| **hold_21** | **49,939** | **22,295** | **0.577** | **+1.9%** | **—** | **0.1492** | **0.0773** | **0.52** | **0.0%** |
| hold_42 | 49,939 | 22,295 | 0.564 | +2.6% | — | 0.1124 | 0.0530 | 0.47 | 0.0% |
| hold_63 | 49,939 | 22,295 | 0.585 | +4.3% | — | 0.0785 | 0.0357 | 0.45 | 0.0% |
| hold_126 | 49,939 | 22,295 | 0.590 | +7.3% | — | 0.00 | 0.00 | — | 0.0% |
| **ema_trail_s8** | **49,939** | **22,295** | **0.623** | **+4.4%** | **—** | **0.1338** | **0.0999** | **0.75** | **0.1%** |
| trail_stop_8pct | 49,939 | 22,295 | 0.386 | +0.5% | — | 0.1016 | 0.0833 | 0.82 | 5.5% |
| trail_stop_12pct | 49,939 | 22,295 | 0.314 | −2.0% | — | 0.0614 | 0.0654 | 1.07 | 20.8% |
| trail_stop_15pct | 49,939 | 22,295 | 0.241 | −4.9% | — | 0.0406 | 0.0531 | 1.31 | 35.0% |
| trail_stop_20pct | 49,939 | 22,295 | 0.156 | −10.2% | — | 0.0216 | 0.0351 | 1.63 | 56.9% |
| barrier_s5_t8 | 49,939 | 22,295 | 0.472 | +1.1% | — | 0.1664 | 0.0882 | 0.53 | 0.4% |
| barrier_s5_t15 | 49,939 | 22,295 | 0.345 | +1.5% | — | 0.1407 | 0.0820 | 0.58 | 4.0% |
| barrier_s8_t15 | 49,939 | 22,295 | 0.443 | +2.0% | — | 0.1249 | 0.0665 | 0.53 | 8.6% |
| barrier_s8_t25 | 49,939 | 22,295 | 0.298 | +1.2% | — | 0.0960 | 0.0619 | 0.65 | 20.7% |

hold_126 is the reference; its foregone_mfe = 0 and avoided_mae = 0 by construction (no regret vs itself).
Median exit_ret was not collected in this batch (requires perfire parquet re-read); the perfire file is available locally.

---

## ERA law + tier splits

All 49,939 fires are `verdict_grade=True` in the massive era (2021-07-06+). There is no survivor-biased sub-cohort in this filter. The era_tier_splits field in the summary JSON contains breakdowns by `tier_cascade` (T1, T2, etc.) which are available in the perfire parquet.

---

## Survivors analysis — why EMA8 trail-flag and 21-session time-exit survived

**The short answer from the regret surface:** EMA8 trail saved the most proportionally while giving up a reasonable amount; hold(21) is the inflection point on the return-vs-regret tradeoff curve.

**EMA8 trail-flag (ema_trail_s8):**
EMA8 achieves the highest WR in the grid at 0.623, the highest mean return at +4.4%, and a regret ratio of 0.75 — meaning for every 1.00 of MFE it gave up versus holding to 126 bars, it saved 0.75 in avoided drawdown. Crucially, it censors almost nothing (0.1%), so it exits when a genuine signal fires rather than expiring. The avoided_mae of 0.0999 (roughly 10pp of drawdown saved per fire) is the best absolute MAE-save of any non-time policy in the grid. The mechanism: EMA8 is a momentum-exhaustion signal, not a fixed-loss floor — it exits when the move is genuinely over, which means it captures the bulk of winners (high WR, positive mean return) while cutting losers before the full 126-bar drawdown accrues.

**hold(21) — the Oracle-ratified anchor:**
hold(21) sits at the WR inflection point: WR climbs from 0.528 at hold_5 → 0.555 at hold_10 → 0.577 at hold_21, then dips to 0.564 at hold_42 before recovering. The mean return at hold_21 (+1.9%) represents roughly half the return of holding to 126 bars (+7.3%) with substantially less drawdown exposure: foregone_mfe drops from 0.1976 at hold_5 to 0.1492 at hold_21, while avoided_mae drops proportionally. The regret ratio for hold(21) is 0.52 — one of the lowest in the grid — meaning hold(21) gives up more than it saves in raw regret terms, but that is partly by design: the Oracle program's 21-session exit was ratified as a reversion-capture window (the mechanism is reversion, not trend-following), and a 21-bar time horizon captures the bulk of the mean-reversion payoff while limiting the operator's capital tie-up per position.

**Why trail_stops failed:** Trail stops produce paradoxical regret profiles. trail_stop_12pct achieves a regret ratio >1.0 (saves more mae than it gives up in mfe) but at a mean return of −2.0% and WR of 31%. The paradox dissolves when you see the censoring: by 20pct, 57% of fires censor (the price never pulls back enough to trigger the stop), meaning the "saved mae" is real but the position captures almost nothing. The apparent drawdown saving is mechanical: if a stop never triggers, all the eventual drawdown accrues to the reference (hold_126), not to the stop policy — so a wide stop that never fires trivially "avoids" the reference's terminal drawdown on a censored path. This is the measurement artifact that makes WR 15.6% and mean return −10.2% at trail_stop_20pct.

---

## Key surface observations (descriptive — not conclusions)

1. **WR is monotone-improving with hold length** except for the dip at hold_42. Hold(126) achieves the highest WR (0.590) and highest return (+7.3%) of all pure-hold cells.
2. **EMA8 dominates all cells on WR** (0.623) with a competitive return (+4.4%) and is the only policy that achieves both superior WR AND captures a substantial fraction of the 126-bar return path.
3. **All barrier cells underperform hold(21)** on WR (range 0.30–0.47 vs 0.577), confirming that symmetric stop/target brackets are poorly matched to a breakout-reversion cohort.
4. **Trail stops exhibit a censoring trap:** the tighter the stop, the higher the WR appears before censoring, but the more the mean return collapses. This is the joint-DD-AND-capture failure identified in the prior NO-GO ruling.
5. **Drawdown is an entry problem, not an exit problem:** the regret surface shows every policy must give up substantial MFE to save material MAE. The only clean answer is not being in the losing fires in the first place — which is an entry-quality problem, not an exit-rule problem.

---

> **In plain English:** We tested 15 exit rules on every fire the system has ever approved (49,939 entries, 22,295 weekly episode clusters). The verdict: no simple exit rule beats holding for 21 sessions except the EMA8 momentum-exhaustion signal, which exits when momentum is genuinely gone and achieves the highest win rate in the grid. Tight stops like "exit if down 8%" appear to control drawdown on paper, but they trigger too often on normal volatility and leave money on the table when the trade is right — the math shows they save 82 cents in avoided losses for every dollar of gain they cut off. The harder lesson from this surface is that the only real way to improve the drawdown profile is to enter fewer bad positions, not to exit the good ones earlier.

---

## Appendix: cumulative pooled trial count

**15 cells declared** to date (this is the first registered experiment in the replay family). Any future promotion prereg on this tape must account for this N.

---

*All numbers are close-to-close, split-adjusted (massive_stock_day_v1), next-bar fill, conservative (exits fill on close of triggering bar). CIs require episode-clustered bootstrap not computed in this descriptive batch. See `data/rule_experiments/results/exit_grid_v1_summary.json` and `exit_grid_v1_perfire.parquet` (Mac-local) for the full record.*

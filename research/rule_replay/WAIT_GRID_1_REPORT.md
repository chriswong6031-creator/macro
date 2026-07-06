# WAIT-GRID-1 — Fill-Delay Surface Report

**exp_id:** wait_grid_v1
**Run date:** 2026-07-06
**Runtime:** 51 seconds
**Verdict criteria:** descriptive-only
**Cumulative pooled replay trial count:** 25 (15 from EXIT-GRID-1 + 10 this batch)
**TrialLedger max()-basis (per-family budget, anti-gaming):** 15 (largest single declared budget across `replay` family)
**Status:** reported

---

## Interpretation guardrail (stated first)

This is the L7 abstention substrate — the descriptive surface that documents what
delaying entry costs or saves. **This report may describe what waiting cost or saved.
It may NOT recommend a delay policy or claim an edge.** Any later prereg on this
surface must carry `derived_from_surface: wait_grid_v1` and a compensating gate.
The surface is now seen; the contamination event is permanent.

---

## Descriptive-only mandate

No DSR (discovery success rate) is computed for descriptive batches (§0.5.6). The
TrialLedger logs the declared budget (10 cells) into `family='replay'` using
**max() semantics** — the per-family effective budget is the *largest single budget*
across all experiments in the family, which is 15 (from EXIT-GRID-1), not 25. The
**cumulative pooled SUM is 25** and is printed here per RUL-5. These two numbers
differ by design; neither drives a DSR for this descriptive batch.

---

## Cohort

- Source: `data/replay/replay_boarded.parquet`
- Filter: `verdict_type='fire' AND verdict_grade=True`
- n fires: **49,939**
- Episode clusters: **22,295** (using `episode_id` column from replay_boarded — format: `TICKER_YYYY-Www`)
- All 49,939 fires are in the ERA LAW window (2021-07-06+, massive_stock_day source)
- Coverage: 100% — all 992 tickers had valid price paths

**ERA LAW note:** `verdict_grade=True` fires are the massive-era cohort (2021-07-06+).
No survivor-biased sub-cohort applies to this filter.

---

## Vintage stamp

- price_plane_id: massive_stock_day_v1
- adjustment_mode: split_adjusted_raw
- universe_as_of: 2026-07-06
- frame: pit_massive_era_law
- survivorship_biased: false
- coverage_frac: 1.00
- dead_name_coverage_pct: 38.32
- era_law_cohort: verdict_grade_2021plus

---

## Episode-cluster independence note

22,295 clusters across 49,939 fires — approximately 2.2 fires per cluster on
average. Clusters are defined at the `TICKER_Www` week level, so multiple fires
in the same stock in the same week share a cluster. **CIs are NOT computed in
this descriptive batch.** Any inferential use of these numbers requires
episode-clustered bootstrap. All per-cell statistics carry the same cluster count
(22,295) because every cell evaluates the full fire cohort — delay shifts the
entry bar but does not drop any fire. This means fires that were originally in
the same cluster remain in the same cluster across delay levels, so **the
clustered independence structure is constant across the delay ladder**.

**Implication for any future inferential analysis:** delayed windows from the same
fire cluster are partially overlapping with the immediate-entry windows from the
same cluster (the 21-bar or 63-bar hold window shifts by delay_n bars, not by a
full hold period). Bootstrapped CIs on wait-cost comparisons must be computed as
*differences within fire* (paired), not as independent-sample tests across cells.

---

## Grid design

The grid crosses:
- **Delay ladder:** `delay_n ∈ {1, 2, 3, 5, 10}` bars
  - `delay_n=1` is the production fill (next-bar-after-signal, Oracle convention)
  - `delay_n>1` simulates waiting additional bars before filling
- **Hold anchors:** `hold(21)` (tactical / ratified Oracle anchor) and `hold(63)` (positional)
- **Reference horizon:** 126 bars (foregone MFE and avoided MAE are relative to hold(126))

All regret metrics (foregone MFE, avoided MAE) are measured **relative to the delayed
entry bar** — so each cell's entry price and forward path are anchored to its own
fill bar, making cells directly comparable on outcome, not on the absolute price level.

---

## Per-cell results table

hold(21) cells (tactical anchor):

| Cell | n fires | clusters | WR | mean ret | median ret | foregone MFE | avoided MAE | regret ratio | censor% |
|---|---|---|---|---|---|---|---|---|---|
| delay1_hold21 | 49,939 | 22,295 | 0.577 | +1.93% | +1.63% | 0.1492 | 0.0773 | 0.52 | 0.0% |
| delay2_hold21 | 49,939 | 22,295 | 0.575 | +1.94% | +1.61% | 0.1497 | 0.0776 | 0.52 | 0.0% |
| delay3_hold21 | 49,939 | 22,295 | 0.574 | +1.95% | +1.59% | 0.1501 | 0.0779 | 0.52 | 0.0% |
| delay5_hold21 | 49,939 | 22,295 | 0.576 | +1.96% | +1.56% | 0.1497 | 0.0787 | 0.53 | 0.0% |
| delay10_hold21 | 49,939 | 22,295 | 0.560 | +1.66% | +1.20% | 0.1491 | 0.0805 | 0.54 | 0.0% |

hold(63) cells (positional anchor):

| Cell | n fires | clusters | WR | mean ret | median ret | foregone MFE | avoided MAE | regret ratio | censor% |
|---|---|---|---|---|---|---|---|---|---|
| delay1_hold63 | 49,939 | 22,295 | 0.585 | +4.26% | +3.10% | 0.0785 | 0.0357 | 0.45 | 0.0% |
| delay2_hold63 | 49,939 | 22,295 | 0.587 | +4.33% | +3.15% | 0.0787 | 0.0359 | 0.46 | 0.0% |
| delay3_hold63 | 49,939 | 22,295 | 0.589 | +4.41% | +3.20% | 0.0789 | 0.0361 | 0.46 | 0.0% |
| delay5_hold63 | 49,939 | 22,295 | 0.588 | +4.41% | +3.18% | 0.0785 | 0.0367 | 0.47 | 0.0% |
| delay10_hold63 | 49,939 | 22,295 | 0.583 | +4.21% | +3.03% | 0.0778 | 0.0384 | 0.49 | 0.0% |

**Censoring (HOLD-policy):** zero censored fires (censored=True) across all 10
cells. The `censored` flag tracks fires where the HOLD policy exit bar or the
fill bar itself exceeds the available price series — that count is genuinely 0.

**Reference-horizon shortfall (distinct from censoring):** the 126-bar reference
horizon used to compute `foregone_mfe_126` / `avoided_mae_126` / `regret_ratio`
requires `fill_idx + 1 + 126` bars to exist in the price series. At `delay_n=1`
(base fill), `verdict_grade=True` guarantees the 126-bar window is available
(the grading gate in `scripts/replay_standout_pipeline.py` checks for a full
126-bar path at the base fill). At `delay_n>1`, the actual fill is
`base_fill + delay_n - 1` (`engine/rule_replay.py:642`), pushing the anchor
forward by `delay_n - 1` bars. Boundary fires — those within `delay_n - 1` bars
of the grading gate's 126-bar limit — lose the 126-bar reference window at
higher delay levels. Their `fwd_mfe_126` is set to None in the engine, which
propagates to `foregone_mfe_126 = None` and `avoided_mae_126 = None`.

The `_cell_stats` function uses `.dropna()` to compute regret means, silently
excluding these boundary fires without counting them or flagging them as
censored. In this particular run the `n_null_regret_126` count was not emitted
per cell (the harness has been corrected to emit it going forward); the observed
n_fires=49,939 at all delay levels is the HOLD-exit denominator (WR/mean_ret),
which is unaffected — but the regret mean denominator may be smaller at higher
delay levels for boundary fires.

**Implication for cross-delay regret comparisons:** the observed trend in
regret_ratio (0.52 → 0.54 at hold21; 0.45 → 0.49 at hold63) is computed on a
denominator that may shrink with `delay_n` for boundary fires. See the
"Censoring and short-path structure note" below for full discussion. Any
inferential use of the cross-delay regret pattern must first quantify the
boundary-fire shortfall per cell.

---

## Surface observations (descriptive — not conclusions)

**hold(21) — delay ladder:**
- WR is nearly flat from delay_n=1 to delay_n=5 (0.577 → 0.575 → 0.574 → 0.576), then
  drops noticeably at delay_n=10 (0.560, a -1.7pp decline from the immediate-entry baseline).
- Mean return is also nearly flat delay_n=1 to delay_n=5 (+1.93% to +1.96%), then falls
  at delay_n=10 (+1.66%, -0.27pp from the delay_n=1 baseline).
- Foregone MFE and avoided MAE are also nearly flat across delay_n=1 to delay_n=5,
  suggesting that the entry price shift from a 1–5 bar delay does not materially
  alter the forward return distribution measured from the delayed entry bar.
- The regret ratio rises slightly with delay: 0.52 at delay_n=1 to 0.54 at delay_n=10.
  A rising regret ratio means each bar of delay saves a slightly larger fraction of
  avoided MAE relative to foregone MFE — but both numerator and denominator are nearly
  constant until delay_n=10. **Confound flag:** this cross-delay regret comparison is
  computed on a denominator that may shrink with delay_n (boundary fires losing the
  126-bar reference window). The trend should not be read as a clean causal delay
  effect until per-cell `n_null_regret_126` counts are obtained.

**hold(63) — delay ladder:**
- WR is non-monotone: rises slightly delay_n=1 to delay_n=3 (0.585 → 0.589), then
  declines back to 0.583 at delay_n=10.
- Mean return follows a similar arc (+4.26% → +4.41% → +4.21%), with the +4.41%
  plateau at delay_n=3 and delay_n=5.
- The regret ratio rises from 0.45 at delay_n=1 to 0.49 at delay_n=10, driven by
  avoided MAE growing more than foregone MFE shrinks. **Confound flag:** same as
  hold(21) — the cross-delay regret comparison may be on a shrinking denominator
  of reference-horizon-eligible fires; treat as confounded until rerun with
  per-cell `n_null_regret_126` counts.

**Cross-hold comparison:**
- hold(63) dominates hold(21) on WR and mean return at every delay level, as
  expected from the EXIT-GRID-1 monotone-hold-length result.
- The delay effect is larger in proportional terms at hold(21) than hold(63): a
  delay_n=10 hold(21) loses -1.7pp WR and -0.27pp mean return vs delay_n=1, while
  a delay_n=10 hold(63) loses only -0.2pp WR and -0.05pp mean return. This is
  consistent with the hypothesis that at a shorter hold horizon, the signal's
  short-term timing content degrades more quickly than at a longer horizon.

---

## Censoring and short-path structure note

Zero short-path fires and zero censored fires (HOLD-policy censor) across all
cells. The `verdict_grade=True` grading gate guarantees a full 126-bar path at
the **base fill** (delay_n=1). HOLD-policy exit windows (21 or 63 bars) are
well within that limit, so no HOLD-exit is truncated.

However, the **126-bar reference horizon** used for regret metrics is a separate
requirement from HOLD-policy censoring. At delay_n>1, the actual fill bar is
`base_fill + delay_n - 1`. For a fire graded with exactly 126 bars remaining at
the base fill, shifting forward by `delay_n - 1` bars leaves fewer than 126 bars
for the reference-horizon window. These fires have `fwd_mfe_126 = None` and are
excluded from regret means via `.dropna()` — but they are **not** flagged as
censored (that flag tracks only HOLD-policy and fill-past-end cases), and
`n_fires` remains 49,939.

The number of such "reference-horizon-shortfall" fires grows with `delay_n`:
roughly the most recent `delay_n - 1` trading days of boundary fires lose the
reference window at each delay level. The harness now emits `n_null_regret_126`
per cell to track this. For this run the per-cell counts were not recorded (the
fix was applied after the run); future reruns will surface them.

**Impact on reported results:** WR, mean_ret, and median_ret are computed on the
HOLD-policy exit (21 or 63 bars) and are unaffected. The **cross-delay regret-
ratio trend** (0.52 → 0.54 at hold21; 0.45 → 0.49 at hold63) is computed on a
denominator that may shrink with `delay_n`. The direction and approximate
magnitude of the trend are unlikely to be fully explained by boundary-fire
dropout (the dropout is expected to be small relative to 49,939 fires), but the
trend should be interpreted as **potentially confounded** until per-cell
`n_null_regret_126` counts are obtained from a rerun.

---

## Tier splits (declared descriptive multiplicity per §6.1)

Tier split at delay_n=1 (production fill):

| Tier | n fires | clusters | WR (hold21) | WR (hold63) |
|---|---|---|---|---|
| T1 | 23,016 | 11,429 | 0.576 | 0.593 |
| T2 | 24,225 | 12,793 | 0.585 | 0.586 |
| T3 | 2,698 | 2,085 | 0.509 | — |

Tier split at delay_n=10:

| Tier | n fires | clusters | WR (hold21) |
|---|---|---|---|
| T1 | 23,016 | 11,429 | 0.561 |
| T2 | 24,225 | 12,793 | 0.561 |
| T3 | 2,698 | 2,085 | 0.537 |

**These splits are DECLARED DESCRIPTIVE MULTIPLICITY per §6.1 — not verdict cells.**
Tier splits show roughly consistent delay effects across tiers, with T3 (the smallest
cohort) showing lower WR at both delay levels and a smaller absolute decline from
delay_n=1 to delay_n=10. No tier receives a separate verdict; these are offered as
context for future pre-registered analyses.

---

## Era-law split

All 49,939 fires are `verdict_grade=True` in the massive era (2021-07-06+).
There is no survivor-biased sub-cohort in this filter. The `era_verdict_grade_2021plus`
split matches the full cohort identically; the `era_survivor_biased` slot is empty
(0 fires) as expected.

---

## Year splits (declared descriptive multiplicity per §6.1)

Year splits are available in the perfire parquet but are not reproduced in detail
here; the perfire file is Mac-local and gitignored. The year dimension is declared
as descriptive multiplicity per §6.1. The cohort spans 2021-07-06 to 2026-07-06
(5 calendar years). Year×delay interactions would require episode-clustered
analysis not conducted in this descriptive batch.

---

## Cumulative pooled trial count accounting (per §0.5.6 and RUL-5)

**Cumulative pooled replay trial SUM = 25**
- EXIT-GRID-1: 15 cells
- WAIT-GRID-1: 10 cells
- Total: **25**

**TrialLedger per-family max()-basis = 15**
The TrialLedger's `log_declared_budget` keeps a per-family maximum (anti-gaming:
the largest single declared budget is the effective budget, preventing inflation by
splitting one large grid into many small registrations). The largest single declared
budget in `family='replay'` is 15 (EXIT-GRID-1). For descriptive-only batches, no
DSR is computed regardless of which count is used (§0.5.6). The distinction becomes
load-bearing only when a promotion prereg is filed; at that point both numbers must
be disclosed to the reviewer.

---

> **In plain English:** We asked whether waiting before buying the signal — 1, 2, 3, 5, or 10 bars after the signal fired — would improve or hurt outcomes. The answer across both the 21-session and 63-session hold horizons is: **short delays (1–5 bars) make essentially no difference; a 10-bar delay hurts**, particularly at the 21-session horizon where win rate drops about 1.7 percentage points. This is a descriptive surface only — it does not tell us whether to wait or not wait, because we have not pre-registered a gate or a comparison direction for this question. What the surface shows is that the Oracle signal's edge does not sharpen with a brief waiting period; if anything, the signal's timing content degrades noticeably only at the longest delay tested. Any future study asking whether waiting improves outcomes for specific name types or market regimes must carry a forking-paths stamp citing this surface.

---

## Appendix: cumulative pooled trial count

**25 cells declared** to date across `family='replay'` (EXIT-GRID-1: 15 + WAIT-GRID-1: 10).
Any future promotion prereg on this tape must account for this full N.

---

*All numbers are close-to-close, split-adjusted (massive_stock_day_v1), next-bar fill
at the delay_n bar, conservative (exits fill on close of triggering bar). MAE/MFE
measured relative to the delayed entry price. CIs require episode-clustered bootstrap
not computed in this descriptive batch. See
`data/rule_experiments/results/wait_grid_v1_summary.json` and
`wait_grid_v1_perfire.parquet` (Mac-local) for the full record.*

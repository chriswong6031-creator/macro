# Prophet Evaluation Specification

**Authored** 2026-08-12 · **Scope** Prophet US, traced to the shipped implementation ·
**Status** specification; no Prophet tuning is proposed here (handoff PART IV explicitly
forbids retuning unless evaluation uncovers an obvious issue — §7 records the one issue found,
which is an evaluation defect, not a model defect).

---

## 1. What Prophet actually is, in code

Prophet is not one engine. It is **three surfaces with different output classes**, which is why
a single metric has never fit it and never will.

| Surface | Output class | Artifact | Graded by | Benchmark? |
|---|---|---|---|---|
| **A — The Board** | Ranking | `site/factordata/us_standouts.json` (committed daily; ~90 revisions since 2026-06-16 per the grader's own docstring — not independently counted here) | `scripts/grade_us_board.py` → `data/us_board_ledger/retro_grades.parquet` | **yes** — vs SPY *and* the name's sector ETF, at 5/10/21/63d, per lane, with precision@k and Wilson CIs |
| **B — The Plan** | Predictive (dated, directional, with targets) | `data/prophet/ledger.jsonl` | closure rules + `reconcile_prophet_live.py` | **no** — `stock_result_pct` is raw return |
| **C — Live states** | Detection / state machine | R2 armed pack → served live plane | `engine/prophet_live/live_states.py`, 5-min pass | n/a — intraday state, not a return claim |

Supporting machinery: `engine/prophet_bridge.py`, `prophet_doors.py`, `prophet_integrity.py`,
`prophet_stage_{fusion,inputs,shadow}.py`, `prophet_miss_audit.py`, `us_prophet_grades.py`,
`engine/prophet_arena.py`, `engine/metabolism/standout_auditor.py` (per-pick autopsies), and
`scripts/{build_prophet, prophet_live_evaluator, prophet_postmortem, grade_us_board,
grade_us_prophet_candidates, run_prophet_pick_autopsies, reconcile_prophet_live}.py`.

**Ledger law (G0.2), already enforced.** `prophet_live_evaluator.py` runs 80+ times a session and
writes **nothing** under `data/`; the nightly reconciler is the sole ledger writer. This is
correct and must survive every change proposed here — an intraday lane that could write the
ledger would let an intraday view rewrite the forward record.

---

## 2. The live record, recomputed at HEAD

Surface B, `data/prophet/ledger.jsonl`, 2026-03-18 → 2026-07-31:

| Measure | Value |
|---|---|
| Closed plans | 28 |
| **Honest N** (distinct signal dates) | **24** |
| Distinct assets | 26 |
| Win rate | 32.1% (9/28) |
| Mean / median | +0.514% / −4.60% |
| sd / se / **t** | 15.26 / 2.88 / **+0.178** |
| 95% CI | [−5.14%, +6.17%] |
| Winners / losers | 9 @ +19.73% / 19 @ −8.59% |
| Payoff | 2.30× → breakeven 30.3% vs actual 32.1% |
| Mean days held | 26.1 |

| outcome | n | mean |
|---|---|---|
| `T1_HIT` | 7 | +22.60% |
| `T2_HIT` | 1 | +13.03% |
| `EXPIRED` | 9 | −4.44% |
| `INVALIDATED` | 11 | −10.62% |

**Read.** A low-hit-rate, positive-skew profile running 1.8pp above its own breakeven, with a
t-statistic of 0.178. Under `MASTERMIND_EVALUATION_STANDARDS.md` §4.7 (50-observation reporting
floor) Prophet may currently report **accrual status only** in any external surface. That is the
correct disposition for n=24 episodes, and it is not a criticism of the model.

**Look-count caution (§4.8).** The same series read 12.5% win rate at n=16 on 2026-08-05 and
32.1% at n=28 one week later. No decision may be conditioned on it in either direction yet.

---

## 3. Selection quality — the per-pick metric set

For every plan, at 1D / 3D / 5D / 10D / 20D, computed at the declared horizon and **never read
as a verdict before it**:

- forward return, raw
- **forward return vs SPY** (missing today — §7)
- **forward return vs the name's sector ETF** (missing today — §7; `grade_us_board.py` already
  computes exactly this for surface A and its logic is directly reusable)
- **MFE** (maximum favourable excursion) and **MAE** (maximum adverse excursion), both missing
  today and both cheap from the same price series
- realised holding period vs planned horizon
- `plan_adherence` (already stored — an unusual and valuable field: it separates "the signal was
  wrong" from "the plan was not followed")

MFE/MAE matter more here than in most systems because the outcome distribution is bimodal:
`T1_HIT` averages +22.6% and `INVALIDATED` averages −10.6%. Without excursion data it is
impossible to tell whether the 11 invalidated plans were *wrong* or merely *stopped out before
being right* — and those two diagnoses imply opposite fixes (change the thesis vs. widen the
invalidation band). **This single distinction is worth more than any other metric on the list.**

---

## 4. Ranking quality — surface A

Already implemented by `grade_us_board.py` and already correct in structure. The specification
is to *read* it properly:

- **Decile / lane monotonicity** — does `buy` beat `watch` beat `laggard` at each horizon?
- **Rank-IC** — Spearman of board rank against forward sector-relative return, per as-of date,
  aggregated with date-blocked CIs.
- **Precision@k** — already emitted.
- **Monotonicity is the diagnostic, not the hit rate.** If the score carries information but the
  ordering does not monotonically map to forward performance, the scoring system holds
  information it is failing to convert into an ordering — a ranker problem, not a signal problem.

**Constraint that must not be violated:** `DNR:KILL-PROPHET-POP-MERGE` forbids any data-lane merge
of Top-setups into the graded board population, and forbids a single blended conviction×timing
ranking. Evaluation must therefore grade the board population *as governed*, and must never
propose a re-ranking that would alter it. A presentation-tier merge is the ratified form.

---

## 5. Entry timing — the highest-value segmentation

The handoff notes entry-state labels may carry significant predictive information, and the
repository agrees from several directions: `DNR:KILL-FRESH-TICKS-WINDOW` (a third-look null on
widening the admission window, with the finding that **waiting is mechanism-negative**:
entering at tick 3/4 instead of 2 costs −0.53/−0.38pp), and `DNR:KILL-ANTI-CHASE`-adjacent
species like `Anti-Chase Hard Gate (F3 ext_z)`.

Segment every plan by entry state: **pre-breakout · breakout · post-breakout · already-extended**,
and report the full metric set of §3 within each. Two rules:

- **Pre-declare the bucket boundaries** (§6.1 of the standards) — the `ext_z` thresholds already
  used by the anti-chase gate are the natural, already-registered boundaries. Do not invent new
  ones after seeing results.
- **`FRESH_TICKS=2` is a pinned constant** with mirrors at `us_board_rank.py:84`,
  `check_board_contradictions.py:49` and `build_stock_library.py:4513`. Evaluation reports on it;
  changing it is an amendment requiring a fresh prereg, not a tuning knob.

---

## 6. Failure taxonomy

`engine/metabolism/standout_auditor.run_pick_autopsies()` already accrues **per-pick autopsy
artifacts** (`data/standout_audit/pick_autopsies/<market>/<pick_id>.json`), driven nightly via
`scripts/run_prophet_pick_autopsies.py` from `daily.yml`. Prophet therefore already converts
individual failures into structured records. What does not exist is a **closed vocabulary** that
lets failures cluster.

Proposed taxonomy — assigned deterministically where possible, left `unclassified` where not
(an honest `unclassified` bucket is mandatory; forcing every loser into a category manufactures
a pattern):

| Tag | Deterministic test |
|---|---|
| `picked_after_extension` | entry `ext_z` above the anti-chase threshold |
| `sector_reversal` | sector ETF return over the hold < −X% while the name tracked it |
| `market_regime_change` | `regime_vector` state transition inside the hold window |
| `earnings_shock` | earnings date inside the hold window, gap > Y% |
| `macro_shock` | a macro-release event inside the window with a market move > Z σ |
| `false_breakout` | MFE < entry+ε then close below the invalidation level |
| `liquidity_failure` | ADV percentile below the floor at entry |
| `crowded_unwind` | crowding/positioning input elevated at entry |
| `insufficient_confirmation` | confirmation count below the median of winners |
| `stale_feature` | any required input outside its `freshness_sla_hours` at signal time |
| `data_issue` | integrity flag from `prophet_integrity.py` |
| `unclassified` | none of the above fired |

`stale_feature` and `data_issue` are the two that must be checked **first**, because they are the
only tags that mean *the model was never given a fair chance* — and they are the only ones whose
remedy is an engineering fix rather than a research question.

The clustering step (taxonomy → grouped failures → a research task) is the missing link in the
flywheel (architecture §8) and applies beyond Prophet.

---

## 7. The one defect found

Per handoff PART IV this specification does not retune Prophet. Evaluation surfaced exactly one
obvious issue, and it is an **evaluation** defect:

> **The plan ledger has no benchmark field.** Schema: `[asof, asset, close_date, days_held,
> direction, id, option_result_pct, outcome, plan_adherence, schema, signal_date,
> stock_result_pct]`. Every number in §2 is therefore a **raw return**. Over 2026-03→07 a mean of
> +0.51% carries no information about whether Prophet beat SPY, its sectors, or a matched control.
>
> This is jarring precisely because Prophet's *board* grader already does it correctly, versus
> both SPY and the sector ETF. The surface carrying the public performance narrative is the one
> without a benchmark.

**Remedy (days, not weeks).** Add `bench_ret_pct`, `sector_ret_pct`, `excess_vs_bench_pct`,
`excess_vs_sector_pct`, `mfe_pct`, `mae_pct` to the plan-ledger schema; backfill all 28 closed
plans from the same price layer `grade_us_board.py` reads; make the reconciler populate them at
closure. Acceptance: every closed plan carries a non-null benchmark excess, and the recomputed
table in §2 reports alpha with a CI beside the raw return.

**Direction handling.** The ledger holds a `direction` field. Benchmark excess must be **signed
by direction** at write time — a short plan that falls beats a benchmark that rises. This is the
same trap as `qledger`'s raw `excess` (standards §4.1); the fix is to store the signed value and
document the convention in the schema comment line at the top of the file.

---

## 8. Regression: the Arena

`engine/prophet_arena.py` already implements the correct version-comparison mechanism:
K frozen challenger policies re-slice the **same** nightly candidate artifact the live path used,
each graded by the **same** closure rules onto its own prospective per-policy ledger. Its
docstring is explicit: *"nothing here is a backtest and nothing here is a backfill."*

Specification additions:

- The comparison scorecard is multidimensional and reported whole (standards §7.2): coverage,
  benchmark-relative alpha, worst drawdown, timing distribution, sector concentration, false
  positives, `INVALIDATED` rate, ranking monotonicity.
- **Leave-one-plane-out challengers** answer the attribution question (architecture §6): a
  challenger identical to the champion except one Neural Web plane is withheld.
- Challengers may not be promoted on a shorter record than the champion's own reporting floor
  (§4.7). The arena's value is that it makes challengers wait exactly as long as the incumbent did.

---

## 9. Scorecard

```
PROPHET US                                              validation_state: accruing
─────────────────────────────────────────────────────────────────────────────────
HEALTH        inputs 12/12 within SLA · 0 contradictions · integrity clean
BOARD (A)     rank-IC 21d …  ·  lane monotonicity buy>watch>laggard …
              graded vs SPY + sector ETF · precision@k · Wilson CI
PLANS (B)     28 closed / 24 episodes · win 32.1% · mean +0.51% · t=+0.18
              ⚠ raw return — no benchmark in schema (spec §7)
              ⚠ below the 50-episode reporting floor
AT ITS RULER  verdicts at declared horizon: 0
FAILURES      INVALIDATED 11 (−10.6%) · EXPIRED 9 (−4.4%)
              taxonomy: <n> stale_feature · <n> false_breakout · <n> unclassified
ARENA         4 challengers accruing · champion unchanged 14d · no promotion eligible
SINCE v3      coverage +18% · tail unchanged · timing unchanged
```

The two ⚠ lines carry the same visual weight as the numbers above them. A scorecard that renders
a t=0.18 result without them is a brochure.

---

## 10. Acceptance criteria for this specification

- [ ] Plan ledger carries direction-signed benchmark and sector excess, plus MFE/MAE, on all
      28 closed plans and every future closure (§7)
- [ ] §3 metric set computed at 1/3/5/10/20D, read as verdicts only at the declared horizon
- [ ] Entry-state segmentation using the pre-registered `ext_z` boundaries (§5)
- [ ] Failure taxonomy assigned on every closed plan, with an honest `unclassified` bucket (§6)
- [ ] Arena scorecard reports all eight dimensions together (§8)
- [ ] Scorecard renders what Prophet *cannot* claim as prominently as what it can (§9)
- [ ] No change to `FRESH_TICKS`, board population, or any live pick rule (§4, §5)

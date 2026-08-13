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
| **B — The Plan** | Predictive (dated, directional, with targets) | `data/prophet/ledger.jsonl` | closure rules in `build_prophet.advance_ledger` | **yes, since 2026-08-12** — vs SPY *and* sector ETF, direction-signed, in the `data/prophet/plan_grades.jsonl` **sidecar** (§2b, §7). `stock_result_pct` on the ledger itself remains a raw return and the ledger is never rewritten |
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

### 2b. The same record, benchmark-relative (Eval OS T2, 2026-08-12)

Every number above is a **raw return** — §7's defect. `data/prophet/plan_grades.jsonl`
(`engine/prophet_plan_grades.py`) now carries the benchmark legs beside the ledger, joined by
`id`, and the raw table above is **unchanged and stays**. Three properties define what these
numbers are and are not:

- **Direction-signed** at write time (positive = the plan beat the benchmark). All 28 plans are
  BULL today, so the convention is pinned by a synthetic short in `tests/test_prophet_plan_grades.py`.
- **Single price basis.** Both legs resolve adjusted-first through `engine.price_ladder`; a name
  with no adjusted series is **refused**, never differenced against an adjusted SPY.
- **`name_ret_pct` is not `stock_result_pct`.** The ledger measures from the plan's entry price
  on its management clock; the sidecar measures the tape from a next-bar fill after `signal_date`
  to `close_date`, because both legs of an excess must span the same bars.

| Measure (realised window, direction-signed) | Value |
|---|---|
| Plans priced on a single adjusted basis | **15 of 28** (13 refused, named below) |
| **Honest N** (distinct signal dates, priced) | **14** (24 across the full record) |
| Name tape return | +8.55% · sd 17.15 · se 4.43 · **t +1.93** · 95% CI [−0.13%, +17.23%] |
| SPY over the same bars | +2.33% · se 1.13 · t +2.07 · 95% CI [+0.12%, +4.54%] |
| **Excess vs SPY** | **+6.22%** · sd 15.15 · se 3.91 · **t +1.589** · 95% CI **[−1.45%, +13.89%]** · win 9/15 |
| Excess vs SPY, episode-clustered (n=14) | +6.51% · se 4.02 · t +1.621 · 95% CI [−1.36%, +14.39%] |
| **Excess vs sector ETF** (n=14) | **+4.85%** · sd 15.81 · se 4.23 · **t +1.147** · 95% CI **[−3.44%, +13.13%]** · win 7/14 |
| Excess vs sector, episode-clustered (n=13) | +5.01% · se 4.47 · t +1.122 · 95% CI [−3.75%, +13.77%] |

**Fixed-horizon ladder — excess vs SPY, direction-signed.** These do not depend on when the plan
was allowed to exit, so they are the cleaner read on selection:

| horizon | n | mean | t | 95% CI | win |
|---|---|---|---|---|---|
| 1 session | 15 | −0.24% | −0.417 | [−1.36%, +0.88%] | 8/15 |
| 3 sessions | 15 | +0.23% | +0.178 | [−2.33%, +2.79%] | 9/15 |
| 5 sessions | 15 | **−2.34%** | −1.409 | [−5.61%, +0.92%] | 5/15 |
| 10 sessions | 15 | **−1.48%** | −0.593 | [−6.37%, +3.41%] | 6/15 |
| 20 sessions | 14 | **−1.07%** | −0.263 | [−9.06%, +6.91%] | 6/14 |

**Read — the alpha is not established, and the +6.22% is biased upward.** No excess figure on
this page clears its own confidence interval; every one straddles zero. Two things then cut
*against* the headline:

1. **The coverage hole is not random — it is the losing half.** The 13 plans that could not be
   priced average **−3.40%** on the ledger's own raw number (median −5.72%, 3/13 positive), while
   the 15 that could average **+3.90%** (median −2.58%). The record as a whole averages +0.51%.
   The priced subset is therefore the flattering subset, and +6.22% is an upper-leaning estimate
   of a number whose honest value is lower. Refused: `ARES` `FBRT` `GPI` `HLI`×2 `MS` `MSFT`
   `PRGO` `QCOM`×2 `REZI` `SFM` `SYY` — **4 plans** because no adjusted series exists for the name
   at all in this checkout's price store (`HLI`×2, `PRGO`, `SFM`), **9** because every adjusted
   rung ends before the plan's own window. The second group is a *store staleness* hole, not a
   modelling one: those refusals are upgradable and the nightly will price them as the adjusted
   caches extend, which is exactly why a refusal row is re-gradable and a priced grade is frozen.
2. **At fixed horizons the excess is negative from 5 sessions out.** The positive realised-window
   number is therefore carried by *exit timing on a favourably-selected subset*, not by the
   selection itself. That is a real distinction and it points at §5, not at the ranker.

**Whole-record sensitivity — NOT admissible as a grade.** Differencing the ledger's own
entry-price-anchored `stock_result_pct` against adjusted SPY over each plan's window covers 27 of
28 plans and reads **−0.20%, t = −0.072, 95% CI [−5.69%, +5.29%], 8/27 positive**. It mixes an
entry-price name leg with a close-anchored adjusted benchmark — exactly the basis error the
sidecar refuses to commit — so it is quoted here only as a bound on direction, and it says the
full-record excess is **approximately zero, if anything slightly negative**. It is not written to
the sidecar and it may not be cited as Prophet's alpha.

**Excursions (close-only, direction-signed, realised window).** Mean MFE vs SPY **+12.95%**
(se 2.92) against mean MAE vs SPY **−6.27%** (se 1.35), and 13 of 15 plans reached a positive
excess excursion at some close. §3's "wrong, or stopped out before being right" question now has
data on it. These are close-only and under-state intraday excursions on both sides.

**Disposition under the standards.** 14 priced episodes (24 across the full record) against a
**50-matured-episode reporting floor** (`MASTERMIND_EVALUATION_STANDARDS.md` §4.7). **This alpha
figure is not a claim.** Prophet reports **accrual status only**; no surface may state that
Prophet beats SPY or its sectors, and no gate, rank or size may be conditioned on any number in
this section. §4.8's look-count caution applies to the excess series exactly as it applies to the
raw one — this is its first look.

---

## 3. Selection quality — the per-pick metric set

For every plan, at 1D / 3D / 5D / 10D / 20D, computed at the declared horizon and **never read
as a verdict before it**:

- forward return, raw
- **forward return vs SPY** — SHIPPED 2026-08-12, direction-signed, in `plan_grades.jsonl` (§2b)
- **forward return vs the name's sector ETF** — SHIPPED 2026-08-12; the sector map and
  `_GICS_ETF` table are shared with `grade_us_board.py` so the two surfaces cannot disagree
- **MFE** / **MAE** — SHIPPED 2026-08-12 as `mfe_close_*` / `mae_close_*`: CLOSE-ONLY, and named
  that way, because a close path under-states a true intraday excursion on both sides
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

**Remedy — SHIPPED 2026-08-12 (Eval OS T2), as a sidecar, not a schema change.** The proposal
above said "add fields to the plan-ledger schema". That was wrong in one respect and it was
changed deliberately: a forward ledger's entire evidentiary value is that nobody went back and
edited it, so the benchmark legs arrive **beside** it, in

```
data/prophet/plan_grades.jsonl        producer engine/prophet_plan_grades.py
```

joined by `id`, one row per `(id, horizon)` over 1/3/5/10/20 forward sessions plus the plan's own
realised window — the same claims/grades split `engine/qledger.py` already uses. `ledger.jsonl` is
byte-identical to its pre-T2 committed form and no existing row gained a field. Rows carry
`name_ret_pct`, `bench_ret_pct`, `sector_ret_pct`, `excess_vs_bench_pct`, `excess_vs_sector_pct`,
`mfe_close_pct`, `mae_close_pct`, `mfe_close_excess_vs_bench_pct`, `mae_close_excess_vs_bench_pct`,
`price_source`, `price_basis`, `refusal_reason`. `build_prophet.advance_ledger`'s caller grades
each night's closures immediately after they close, gated on `ledger_lane.nightly_advance_enabled()`
as the writer's first statement — so **G0.2 binds a rung tighter on the sidecar than on the ledger
itself**, and `prophet_live_evaluator.py` still writes nothing under `data/`.

Two things the original remedy did not anticipate, both load-bearing:

- **One price basis or no row.** Name prices and benchmark prices came from different stores with
  different basis conventions; `raw_name − adjusted_bench` is wrong across any split or dividend
  in the window. Every leg now resolves through `engine.price_ladder.resolve_close` with
  `allow_unadjusted=False`, and a name with no adjusted series is **refused with a stated reason**
  rather than priced on a mixed basis. That is why §2b prices 15 of 28 plans and not 28 — the
  acceptance line "every closed plan carries a non-null benchmark excess" is **superseded**: a
  disclosed refusal is the correct output, a manufactured number is not.
- **A refusal must still be a row.** An unpriceable plan emits a row with null metrics and a
  reason, and the nightly prints a `::warning` naming every one, because a missing row and a plan
  that never existed are indistinguishable. Refusals are the only rows that may later be
  **upgraded**; a priced grade is frozen.

**Direction handling — implemented.** `excess_vs_bench_pct`, `excess_vs_sector_pct` and both
excursion pairs are multiplied by the plan's `direction` at write time, so a short plan that falls
against a rising benchmark reads **positive** and the column pools across directions. The raw legs
stay unsigned so the tape is reconstructible. This is the same trap as `qledger`'s raw `excess`
(standards §4.1, `engine/qledger_validity.py` V1 `SIGNED_EXCESS_POOLED_ACROSS_DIRECTIONS`). The
convention is documented in the sidecar's own `#` header and pinned by a **synthetic short** in
`tests/test_prophet_plan_grades.py` — the live ledger is 100% BULL, so nothing but a synthetic
case can catch a sign flip.

**What §2b actually found is not the headline the remedy expected.** The excess is not
established (every CI straddles zero), the priced subset is the *winning* half of the record, and
the fixed-horizon ladder is negative from 5 sessions out. The benchmark field did not confirm
Prophet's edge; it made visible that there is not yet evidence of one.

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
              excess vs SPY +6.22% t=+1.59 CI[-1.45,+13.89] on 15/28 priced
              ⚠ 13 plans unpriceable on one basis — and they are the LOSING half
              ⚠ fixed-horizon excess NEGATIVE from 5 sessions out (spec §2b)
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

- [x] Plan record carries direction-signed benchmark and sector excess, plus close-only MFE/MAE,
      on every closed plan and every future closure — **as the `plan_grades.jsonl` sidecar, not as
      new ledger columns** (§7). All 28 plans are accounted for: 15 priced on a single adjusted
      basis, 13 refused **by name and reason**. "Non-null excess on all 28" is superseded by
      "one basis or no row" — see §7.
- [ ] §3 metric set computed at 1/3/5/10/20D, read as verdicts only at the declared horizon
- [ ] Entry-state segmentation using the pre-registered `ext_z` boundaries (§5)
- [ ] Failure taxonomy assigned on every closed plan, with an honest `unclassified` bucket (§6)
- [ ] Arena scorecard reports all eight dimensions together (§8)
- [ ] Scorecard renders what Prophet *cannot* claim as prominently as what it can (§9)
- [ ] No change to `FRESH_TICKS`, board population, or any live pick rule (§4, §5)

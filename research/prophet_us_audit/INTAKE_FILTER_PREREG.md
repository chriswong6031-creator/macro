# PREREG — do the plan-intake band/score filters forfeit board winners?

**Status:** PRE-REGISTERED, NOT RUN. **Tier:** research prereg. **Date:** 2026-08-04.
**Parent:** `research/PROPHET_US_SUPERINTELLIGENCE_ROADMAP_BY_FABLE.md` §4.4 action 3
(the W1 follow-up, now naming its key explicitly).
**Sibling instruments in this wave:** the nightly `name_score_scorecard` block in
`engine/prophet_miss_audit.py`, and the frozen-frame benchmark
`research/prophet_us_audit/name_score_pk_benchmark.py` (+ `..._results.json`).

> **THIS NOTE CHANGES NO GATE.** It registers a question, a frame, metrics and pass/fail
> bars in advance so the answer cannot be chosen after seeing it. It moves no key between
> tiers (G0.1), touches no filter, and confers no authority. Any change it might later
> justify is W5-class and stays sequenced behind **G0.2** — W0's nightly miss-audit
> artifact green for five consecutive nightlies — and behind operator ratification. The
> first W0 nightly had not yet run when this note was written; that is stated, not worked
> around.

---

## §0 The key-identity receipt (why this question is about `name_score`, not "the score")

The plan-intake filter reads `conviction.score` and `conviction.band`. Both are
`engine/name_score.py` outputs, by a backward-compat overwrite — the filter is therefore
keyed on a **buy-readiness timing screen**, not on the edge percentile the same block
computes and sets aside:

**Receipt — `scripts/build_stock_library.py`, lines 3187–3227** (the `for _safe, _rec in
to_write:` block opens at line 3199):

| line | statement | effect |
|---|---|---|
| 3205 | `_c["score_edge"] = _c.get("score")` | the within-market composite-z **edge percentile** is moved aside |
| 3207 | `_c["score_timing"] = _pot["score"]` | the **potential_score** is named `score_timing` |
| 3211 | `_c["rank_pctile"] = _c.get("score")` | the edge percentile is also kept as `rank_pctile` |
| 3212 | `_c["score"] = _pot["score"]` | **the displayed `conviction.score` becomes `potential_score`** |
| 3213–3224 | band cap | `_c["band"]` = the **potential band**, capped to `neutral` on a Lagging / no-clear-edge verdict |

So `conviction.score == name_score.potential_score` and `conviction.band ==` the
(verdict-capped) **potential band**. This identity is not only read from source: the
benchmark measures it against the grader's own PIT call ledger
(`data/name_score/us_calls.parquet`) and reports it as `key_identity` in
`name_score_pk_benchmark_results.json` —

* joined on `entry_date` (the ledger stamps `asof = utcnow().date()`, i.e. the build that
  runs after the board's own `as_of` close): **n = 195, exact-match 0.918, Spearman 0.9727**;
* the 16 mismatches sit on 2 dates (15 of them on 2026-07-06, the Monday after the long
  July-4 weekend, where the +1-day build-date alignment breaks) — a **join artifact**, not a
  score divergence;
* joined on `as_of` instead: exact-match 0.177 — the wrong alignment, reported so the
  reader can see which alignment is the real one.
* Caveat, stated: the ledger begins 2026-06-29 and so overlaps only the tail of the frame.
  The receipt is a **partial** verification of a full-frame identity.

**The two filter legs this note is about** (`engine/prophet_bridge.py::select_candidates`,
the pre-registered ADMISSION rule that W1 explicitly did **not** change — W1 moved the
SORT to the `us_prophet_v1` priority score and left admission alone):

| leg | line | rule | keyed on |
|---|---|---|---|
| **BAND** | 337–338 | `if band == "low": continue` | name_score potential band (verdict-capped) |
| **SCORE** | 343–346 | when `gate_go` is False: `act_level >= 2 or score >= 60` | name_score `potential_score` |

`N_CANDIDATES = 12` (line 101) caps each run.

---

## §1 The question (one sentence, falsifiable)

**Of the board buy-lane admissions that went on to be winners at the record horizon, what
share would the intake filter have refused a plan — and is that forfeit rate materially
worse than the forfeit rate on losers?**

A filter that refuses winners and losers at the same rate costs coverage but not selection.
A filter that refuses winners *more often than losers* is destroying value; a filter that
refuses losers more often than winners is earning its place. That asymmetry, not the raw
refusal count, is the measurement.

Two named sub-questions, because the legs can fail in opposite directions and a pooled
answer would hide it:

* **Q1 (BAND leg).** Does `band == "low"` forfeit winners? The band is verdict-capped, so a
  Lagging name can never carry a high band — the leg may be doing verdict work under a
  score's name.
* **Q2 (SCORE leg).** In `gate_go == False` runs, does `score >= 60` forfeit winners that
  `act_level >= 2` did not already admit? The `or` means the score leg only ever *widens*
  admission; the question is whether the names it *fails to widen to* were winners.

---

## §2 Frame (fixed in advance)

* **Population.** `data/us_board_ledger/retro_grades.parquet`, `lane == "buy"`,
  `horizon == 10` (the record basis; the same frame the §5 stand-ins and the P@k benchmark
  use). Present shape: 403 rows / 243 names / 10 admission cohorts, `entry_date`
  2026-06-16 … 2026-07-16.
* **Outcome.** `excess_spy` at H=10. **Winner :=** `excess_spy > +3pp`. **Loser :=**
  `excess_spy < −3pp` (the stand-ins' stated threshold, kept identical so the two studies
  are comparable). The middle band is reported, never folded into either side.
* **Filter replay.** The legs are replayed from the ledger's own stamped `band`,
  `score`, and `act_level` columns. `gate_go` is a per-run market-state flag that the ledger
  does **not** carry, so BOTH branches are replayed and reported separately
  (`gate_go=True`: `act_level >= 2`; `gate_go=False`: `act_level >= 2 or score >= 60`) —
  never averaged into one number, and never guessed from a later artifact.
* **Coverage debt, named up front.** `act_level` is stamped on 226/403 rows and `band` on
  403/403. Rows with no `act_level` cannot have the gate branch replayed and are reported as
  a separate **unreplayable** cell with its n — never dropped into either arm, and never
  imputed. If the unreplayable share exceeds 50% the study reports NULL for the affected
  branch rather than a number from the replayable remainder (a resolution-conditioned
  denominator is forbidden here as everywhere).
* **Era caveat, binding.** This frame ENDS on 2026-07-16, the day the cascade inclusion gate
  began. Every cell inherits the era caveat; the study re-runs on the post-07-16 frame as it
  matures, and the pre-registered bars below apply to the re-run unchanged.

## §3 Metrics (fixed in advance)

Per leg (BAND, SCORE) and per `gate_go` branch:

1. **Forfeit rate on winners** `f_W` = share of winners the leg refuses.
2. **Forfeit rate on losers** `f_L` = share of losers the leg refuses.
3. **Forfeit asymmetry** `Δ = f_W − f_L` (percentage points). The primary statistic.
4. **Admitted-cohort quality**: loser rate, median `excess_spy`, **date-demeaned** median,
   and **per-name-first** median for admitted vs refused — the stand-ins' method guards,
   reported in full for both arms.
5. **Named forfeited winners**: every refused winner listed by ticker with its
   `entry_date`, `score`, `band`, `act_level` and `excess_spy`, so the verdict can be read
   name by name rather than in aggregate.
6. **n everywhere**: every cell prints its n. A cell with n < 20 is labelled **thin** and
   the verdict may not rest on it alone.
7. **Cohort-clustered uncertainty**: `Δ` is accompanied by a cohort-block bootstrap
   (resample the 10 admission cohorts with replacement, B = 20,000, fixed seed) — episodes
   inside one admission date are not independent draws.

## §4 Pass / fail bars (fixed in advance; the answer cannot be chosen after the fact)

For each leg, on the frame above:

| verdict | bar |
|---|---|
| **FORFEITS WINNERS** (leg is costing value) | `Δ = f_W − f_L ≥ +10pp` **and** the cohort-block bootstrap's 90% interval for `Δ` excludes 0 **and** the winner arm has n ≥ 20 |
| **EARNS ITS PLACE** (leg is refusing losers) | `Δ ≤ −10pp` with the same interval and n conditions, in the opposite direction |
| **NEUTRAL / COVERAGE-ONLY** | `|Δ| < 10pp`, or the interval includes 0 — the leg costs coverage without selecting |
| **NULL — not measurable** | winner-arm n < 20, or unreplayable share > 50%, or the leg refuses fewer than 5 rows. Printed as a null **with its reason**; a null is not a pass and not a 0. |

**Secondary, pre-registered, non-deciding:** if the leg is NEUTRAL but its refused arm
carries a materially better date-demeaned median than its admitted arm, that is recorded as
a *contra-indication* for a later study — it does not by itself move any verdict.

**What each verdict would (and would not) authorize.** Nothing automatically. A
FORFEITS-WINNERS verdict makes a filter change *eligible to be proposed* as a W5-class
change; it must then clear G0.2 (5 green W0 nightlies), be paired with the shadow-lane
accrual G0.4 requires, and be operator-ratified. An EARNS-ITS-PLACE verdict is a receipt to
print on the score's card, not a licence to widen the leg's authority.

## §5 Standing constraints this note inherits

* **G0.1** — no key moves tier here; `conviction.score` stays `display` with its measured
  card, per the roadmap's §4.4 adjudication set (demote / mine the legs / keep-with-card).
* **G0.4** — the graded `us_board_ledger` population is not touched; this is a read-only
  replay.
* **G0.5 / DNR:KILL-PROPHET-POP-MERGE** — no blended ranking is proposed, tested, or implied. The question
  is about a FILTER's asymmetry, not about a new composite.
* **Sole-advancer law** — the study writes only a results JSON beside this note; it advances
  no forward ledger.
* **Epistemics** — a null result is display-tier information and blocks nothing; it is
  printed with its reason, never hidden, and never rounded to 0.5.

## §6 What is already known (context, not a prejudgement)

From `name_score_pk_benchmark_results.json`, same frame, exploratory:

* the `name_score` ordering's precision is concentrated at the very top (P@1 0.764,
  permutation p ≈ 0.05 over 10 cohorts) and is gone by k = 5–10 (P@10 0.478 vs a 0.494 base);
* its cross-sectional rank-IC is slightly **negative** (−0.0150 by date);
* within a cohort it is **negatively** rank-correlated with the alpha edge (Spearman −0.251),
  so the intake filter and the `us_prophet_v1` sort are keyed on genuinely different axes —
  which is exactly why the filter's asymmetry has to be measured rather than assumed from
  the sort's ruling.

That is a reason to run this study, not an answer to it. The bars in §4 stand as written.

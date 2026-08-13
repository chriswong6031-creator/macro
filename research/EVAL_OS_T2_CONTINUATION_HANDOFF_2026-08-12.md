# Eval OS T2 (Prophet benchmark) — continuation handoff

**Date** 2026-08-12 · **Branch** `claude/eval-os-t2-prophet-benchmark` (pushed, **no PR**) ·
**Status** THE FINDING IS SOUND AND VERIFIED. THE CODE IS NOT SHIPPABLE. Park, do not merge.

---

## 0. The finding — Prophet has no measurable alpha at any fixed horizon

This is the first benchmark-relative read of Prophet's live plan record that has ever existed.
Every number below was **recomputed independently by the orchestrator** from
`data/prophet/plan_grades.jsonl` + `data/prophet/ledger.jsonl`, with Student's *t* intervals
(df = n−1), not by trusting the builder's report.

**Realised window — exit timing included:**

| leg | n | mean | t | 95% CI (t) |
|---|---|---|---|---|
| excess vs SPY | 15 | **+6.22%** | +1.59 | [−2.17%, +14.61%] |
| excess vs sector ETF | 14 | +4.85% | +1.15 | [−4.28%, +13.98%] |

**Fixed horizons — these do NOT depend on when a plan was allowed to exit, so they isolate
SELECTION quality:**

| horizon | n | mean excess vs SPY | t | 95% CI (t) |
|---|---|---|---|---|
| H=1 | 15 | −0.24% | −0.42 | [−1.46%, +0.99%] |
| H=3 | 15 | +0.23% | +0.18 | [−2.57%, +3.03%] |
| H=5 | 15 | **−2.34%** | −1.41 | [−5.91%, +1.22%] |
| H=10 | 15 | −1.48% | −0.59 | [−6.83%, +3.87%] |
| H=20 | 14 | −1.07% | −0.26 | [−9.87%, +7.73%] |

**Not one interval excludes zero.** The only positive headline (+6.22%) comes from the realised
window, which mixes selection with exit management — and it is biased upward (§0.1).

### 0.1 The coverage hole is the losing half — the +6.22% is selection-biased

Only 15 of 28 closed plans could be priced on a single adjusted basis. The 13 refusals are
**not a random subset** (orchestrator-verified):

```
PRICED    n=15  mean +3.90%  median −2.58%  positive 6/15
UNPRICED  n=13  mean −3.40%  median −5.72%  positive 3/13
FULL      n=28  mean +0.51%
=> the unpriced half is 7.30pp WORSE
```

So the priced subset is the flattering subset, and **+6.22% overstates whatever the true number
is.** Any future presentation of this figure must carry the coverage denominator and this bias
statement in the same breath.

### 0.2 Honest reading

Whatever edge Prophet has appears to sit in **exit management, not selection** — the realised
window (which includes exit timing) is positive while every fixed horizon (which strips it) is
flat-to-negative. And even the realised figure is not significant, is computed on the flattering
15, and rests on honest N = 14 distinct signal dates.

Under `MASTERMIND_EVALUATION_STANDARDS.md` §4.7 (50-episode reporting floor) **none of this may
appear in an external surface as a performance claim.** It is accrual status. Reporting it as
alpha would be the exact failure this program exists to prevent.

---

## 1. What is built and appears correct

- `engine/prophet_plan_grades.py` — direction-signed excess vs SPY and vs the name's GICS sector
  ETF, plus close-only excursions, resolved **adjusted-first** through `engine.price_ladder`
  with `allow_unadjusted=False` as the refusal switch (TRAP 1 honoured: **zero rows mix a
  basis** — 15 plans `price_basis='adjusted'`, 13 refused with `price_basis=None`).
- `data/prophet/plan_grades.jsonl` — 102 rows, sidecar keyed by plan `id`, horizons
  `realized/1/3/5/10/20`.
- **The forward ledger was not disturbed.** `data/prophet/ledger.jsonl` is byte-identical to
  HEAD. The sidecar pattern (mirroring `qledger`'s claims/grades split) achieved its purpose.
- Excursions are honestly named `mfe_close_pct` / `mae_close_excess_vs_bench_pct` — every
  excursion column carries `close` (TRAP 4 honoured).
- Refusals are **named at runtime** via a bare `print("::warning …", flush=True)` (TRAP 5
  honoured in the code; violated in the doc — see M2).
- A useful extra field: `ledger_stock_result_pct` beside `name_ret_pct`, because the tape
  construction (next-bar fill) differs from the plan's management-clock entry — e.g.
  `KKR-BULL-20260318` reads +14.05% tape vs +6.42% ledger. Without both, the gap looks like a bug.

**Correction to the brief, discovered and flagged by the build:** `reconcile_prophet_live.py`
does NOT write `data/prophet/ledger.jsonl` — it reads an R2 event spool and writes
`data/prophet_live/forward.parquet`. The real sole closer is `scripts/build_prophet.py`
`advance_ledger()` → `_append_ledger_row()`. The sidecar hook went there. My V1 plan named the
wrong file; correct it when T2 resumes.

---

## 2. Blockers — fix before any PR

**B1 — a test pins a LIVE append-only store against a frozen artifact.**
`tests/test_prophet_plan_grades.py:277` asserts `ledger_ids <= graded_ids` over the committed
sidecar. The ledger grows nightly and `origin/main` has already added rows, so this reds main on
its own. **This is the third instance of this exact class in this program** (T1 round 1, T1
round 3, now T2). Use a fixture; never assert over a live append-only store.

**B2 — the spec text names the WRONG plans as unpriced.**
`research/MASTERMIND_PROPHET_EVAL_SPEC.md:111-116` lists 13 refusals whose membership and cause
decomposition contradict the shipped `plan_grades.jsonl`: four plans it calls refused
(`ARES-BULL-20260709`, `MSFT-BULL-20260720`, `QCOM-BULL-20260709`, `QCOM-BULL-20260710`) are
actually priced. A disclosure that misnames what it discloses is worse than no disclosure.
Regenerate the list from the artifact, never by hand.

## 3. Majors

- **M1 — the writer can destroy its own store.** `engine/prophet_plan_grades.py:296-299`:
  `if not target.read_text().startswith('#'): target.write_text(SIDECAR_HEADER)` **truncates the
  file**, wiping every existing row. And `:291` takes a full-file `write_text()` rewrite on every
  run, so the sidecar is not append-only in shape and re-running is **not** the no-op the build
  claimed. Make it append-only and never truncate.
- **M2 — every CI in §2b uses z=1.96 at n=13–15.** Student's t(df=14)=2.145 widens them 7–11%
  and flips one presented significance. All intervals in §0 above are already recomputed with t.
- **M3 — overlapping windows.** 69 of the 105 pairs among the 15 priced plans have overlapping
  holding windows, and two are the same name on near-identical windows
  (`QCOM-BULL-20260709` / `QCOM-BULL-20260710`). The published se/t assume independence. Use a
  date-blocked bootstrap, or state the dependence plainly.
- **M4 — the coverage hole is presented as self-healing on evidence that does not exist.**
  The "9 of 13 refuse only because the adjusted rung ends before the window, so they will resolve
  as the store advances" claim is not supported by anything measured. Either measure it or drop it.
- **M5 — `price_source` stamps only the NAME leg.** Bench and sector legs resolve through their
  own `resolve_adjusted_leg()` calls and their rungs are never disclosed on the row.

## 4. Not started

Nothing wires the sidecar into `config/synapse.yml`; if it becomes a consumed artifact it needs
a registry entry plus a `docs/SIGNAL_BUS.md` regeneration.

---

## 5. Exact next command

```bash
cd "/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/eval-os-t2-prophet-benchmark"
git log --oneline -2
python3 -m pytest tests/test_prophet_plan_grades.py -q     # expect B1 to be the fragile one
COLLECT_LANE=nightly python3 -m engine.prophet_plan_grades  # regenerates the sidecar
```

Fix order: **M1 (data-destroying) → B1 → B2 → M2 → M3.** M1 first because it can lose the store.

---

## 6. The lesson for the program

Three tasks, five workflow rounds, fifteen adversarial verdicts, all refuted — and the single
most repeated defect is **pinning a live, append-only, nightly-growing store inside a test or a
drift guard.** It appeared in T1 twice and T2 once, each time introduced by a different builder
that had been warned about it in its own brief.

That is worth a house law, not another reminder: *no test and no guard may assert over
`data/**` content that a nightly lane appends to.* Fixtures only. Add it to
`config/house_law_checks.yml` as a discipline-tier law with a grep-based check, and the next
three builders stop rediscovering it.

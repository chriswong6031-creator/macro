# CPI Lattice Batch 2 — BINDING VERDICT (within-family baselines; the CPI-020 re-test)

**Run date:** 2026-07-06 · **Branch:** feat/cycle-pattern-lattice2 · **Gates:** PREREGISTRATION.md §15
(frozen pre-run; criteria unmoved) · **Family:** `cycle_pattern_lattice_v1`, BH-FDR q=0.10 across the
full 135-cell search space · **Budget:** `rf.cycle_pattern.lattice_v1` n=135, declared pre-p-value ·
**Artifacts:** `data/cycle_pattern/lattice/batch2.json`, `batch2_cells.parquet`, 27 factory candidates
in `data/cycle_pattern/pattern_candidates.jsonl` (all `screened`, truth_guard: 0 collisions).

**Process disclosure:** two-commit discipline observed with the §15 tightening — the criteria commit
landed BEFORE any run against the real panel (pre-commit tests ran `-k "not smoke"`); the real-panel
smoke and the full run happened only after the criteria commit. No §14-style pre-commit dry-run.

---

## 0 · TL;DR

**27 of 135 cells clear the frozen within-family gate — and the named CPI-020 re-test (LT2-020)
FAILS it.** The batch-1 CN Downturn × broken-trend deep-tail lead survives directionally within
family (gap −0.0350, CI₉₅ [−0.0688, −0.0021], boot p = 0.04, era-stable) but does NOT survive
BH-FDR across the declared 135-cell family. Per the frozen outcome handling: truth
`cycle_truth_cn_downturn_broken_trend_tail_candidate_v1` → **retired**; a scoped null truth records
the kill. The 27 survivors are era-stable, family-honest phase/trend structure — the §14
confirmatory record now reproduced WITHOUT the family-composition confound — plus two genuinely
vol-adjusted risk cells (Peak = shallower tails within country and CN). 33 of the 48 §14 factory
candidates are mechanically resolved `screened → numeric_rejected`; 15 keep `screened` with batch-2
evidence.

## 1 · Promotion breakdown (all 135 cells queryable in the artifact)

| target | L-A | L-B | reading |
|---|---|---|---|
| `turn_event_3m` | 11 | 4 | turn arrival is phase-graded within EVERY family (Trough/Recovery/Downturn elevated; Expansion/Peak deferred); plus two coherent trend-splits (below) |
| `phase_persist_3m` | 10 | 0 | the complement: Recovery is fragile in all three families (us −0.172, country −0.165, cn −0.252); Peak persists (us +0.168, country +0.151) |
| `rdd_63d` | 2 | 0 | Peak carries SHALLOWER vol-adjusted 63d tails within country (+0.049) and CN (+0.071) — the KG-2/CPI-002 direction, now in vol-adjusted within-family form |

## 2 · Adjudication (the judge's reasoning, on the record)

1. **LT2-020 verdict — the frozen gate is the law.** The within-family gap is roughly 60% smaller
   than the batch-1 cross-family estimate (−0.0350 vs −0.0597; the cross-family diagnostic on the
   same cell reads −0.0729): the §14 baseline confound accounted for the larger part of the batch-1
   magnitude. What remains is directionally consistent, era-stable, and standalone-significant
   (p = 0.04) — and that is exactly the profile the multiplicity correction exists to discipline.
   0.04 does not survive BH q=0.10 alongside ~25 near-zero p-values in the same declared family.
   FAIL. Dead-stays-dead: reopening requires a new preregistered trial naming the null truth.
2. **The risk-relevant CN story survives in a different, gate-passing form.** The SAME conditioning
   cell on `turn_event_3m` promotes cleanly with its mirrored complement: broken-trend CN downturns
   show a turn DEFICIT (−0.086, CI [−0.126, −0.054], BH-pass) — they grind on rather than resolve
   within 3 months — while intact-trend CN downturns resolve faster (+0.160). The honest summary:
   "broken trend makes CN downturns longer, and possibly deeper — the depth claim did not clear the
   family-wide gate."
3. **The 21 L-A turn/persist survivors are confirmatory, not edges.** `phase_v2` is built from
   position + direction, and turn labels mechanically follow direction flips, so phase-graded turn
   arrival/persistence is hazard-adjacent KNOWN structure — but it is now established WITHIN each
   family, era-stable, PIT-pure, free of the §14 confound. This upgrades CPI-019's confirmatory
   record (its falsifier — "the structure is itself a family-composition artifact" — is answered:
   it is not). Display/structural authority only.
4. **The two `rdd_63d` Peak cells are the batch's genuinely new measurement.** Vol-adjusted forward
   63d tails are SHALLOWER at Peak than the family norm in country (+0.049) and CN (+0.071), both
   BH-surviving and era-stable — a stricter, within-family, vol-adjusted confirmation of the
   KG-2/CPI-002 "Peak precedes shallower drawdowns" structure. Filed as factory candidates,
   display-only; no page-authority change.
5. **§14 candidate resolution (mechanical, per frozen §15):** 33/48 batch-1 candidates fail the
   within-family gate → `screened → numeric_rejected` (kill evidence = batch2.json); 15/48 pass →
   keep `screened`, batch-2 stats recorded in the artifact's `batch1_candidate_resolutions` block.
   No batch-1 candidate advances past `screened` on batch-1 evidence alone.
6. **Diagnostic note:** `gap_xfam` in batch 2 is raw-mean-based (batch-1 gaps were shrunk-based),
   so xfam values are indicative, not exactly comparable to batch-1 numbers. It has no gate role.

## 3 · Outcome handling per §15 (all frozen pre-run)

- Truth `cycle_truth_cn_downturn_broken_trend_tail_candidate_v1`: `candidate → retired`
  (auto_demote_rule). New scoped null truth `cycle_truth_cn_downturn_broken_trend_tail_null_v1`
  records the kill with the within-family numbers.
- New display truth `cycle_truth_lattice2_within_family_structure_v1` records the 27-cell
  family-honest structure (incl. the CN turn-deficit pair and the two Peak rdd cells).
- CPI-019 (`cycle_truth_lattice1_confirmatory_and_baseline_confound_v1`): monitoring metric
  `batch2_within_family_retest` satisfied — structure reproduced, not an artifact; note appended
  (status stays `display`).
- 27 factory candidates written (`screened`, trial_family `lattice_v1`, truth_guard 0 flags);
  33 §14 candidates → `numeric_rejected` via `data/research_factory/transitions.jsonl`.
- No page-authority change. Exploration tables ship to the measurement research surface.

## 4 · Reproduce

```
python3 scripts/build_cycle_pattern_lattice_batch2.py      # deterministic (seed 7)
python3 -m pytest tests/test_cycle_pattern_lattice_batch2.py -q
python3 scripts/apply_cycle_pattern_lattice_batch2_outcomes.py   # idempotent outcome writes
```

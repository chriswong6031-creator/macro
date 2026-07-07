# CPI Lattice Batch 1 — BINDING VERDICT (third CPI discovery batch)

**Run date:** 2026-07-06 · **Branch:** feat/cycle-pattern-lattice1 · **Gates:** PREREGISTRATION.md §14
(frozen pre-run; criteria unmoved) · **Family:** `cycle_pattern_lattice_v0`, BH-FDR q=0.10 across the
full 135-cell search space · **Budget:** `rf.cycle_pattern.lattice_v0` n=135, declared pre-p-value ·
**Artifacts:** `data/cycle_pattern/lattice/batch1.json`, `batch1_cells.parquet`, 48 factory candidates
in `data/cycle_pattern/pattern_candidates.jsonl` (all `screened`, truth_guard: 0 collisions).

**Process disclosure:** the §14 text was authored before any run; the implementing agent executed a
scratch dry-run (temp output, production ledger untouched) before the criteria commit landed. The
criteria are character-identical pre- and post-dry-run (git history shows the §14 hunk in the
criteria commit); recorded here for the honesty ledger rather than hidden.

---

## 0 · TL;DR

**48 of 135 cells clear the frozen promotion gate — but adjudication classifies most as a baseline
confound plus known structure, not 48 edges.** The sanity gate reproduced KG-2 (Trough −0.099 deeper /
Peak −0.062 shallower raw-DD vs pooled −0.078). The load-bearing finding of the batch is
methodological: the §14 baseline (phase-pooled **across families**) conflates family base-rate
offsets with phase effects — CN-sector cells are systematically mirror-signed vs US/country in the
same phase (Trough turn-rate: US +0.096, country +0.057, **CN −0.095**; Peak: US −0.135, **CN
+0.100**), which is detector-threshold and cycle-speed composition, not cross-family alpha. One
substantive risk lead survives eyes-on review: **CN sectors in Downturn with broken trend carry
materially deeper vol-adjusted 63d tails** (rdd gap −0.0597, CI₉₅ [−0.119, −0.028], p≈0.000, n=145,
era-stable) — filed as a factory candidate for a within-family re-test, NOT displayed.

## 1 · Promotion breakdown (all 48 remain queryable in the artifact)

| target | L-A | L-B | adjudication class |
|---|---|---|---|
| `turn_event_3m` | 11 | 16 | family-composition confound + hazard-adjacent known structure → confirmatory only |
| `phase_persist_3m` | 7 | 9 | complement of the above (persistence ≈ 1 − turn rate) → confirmatory only |
| `rdd_63d` | 3 | 2 | the genuinely new surface; carries the same baseline confound; one strong lead (below) |

## 2 · Adjudication (the judge's reasoning, on the record)

1. **Why 48 "significant" cells ≠ 48 findings.** The phase-pooled baseline pools US sectors (14%
   ZigZag), countries (vol-scaled), and CN Shenwan (18–25%) — families with mechanically different
   turn frequencies and phase dynamics. A cell's gap vs that pool is significant whenever its family
   deviates from the blend, even if the family's *own* phase-conditional behavior is unremarkable.
   The mirror-signed CN pattern across nearly every phase is the fingerprint of this confound. The
   frozen gate operated exactly as registered; what it tests is simply weaker than what a
   decision-grade claim needs. This is the anti-mining law working at the adjudication layer.
2. **The confirmatory value is real and recorded** (CPI-019): phase-conditional structure in turn
   arrival and persistence exists, is era-stable, and is PIT-pure (no quad conditioning) — an
   independent reproduction of the hazard model's premise from a different estimator. It changes no
   authority anywhere.
3. **The one lead worth pursuing** (CPI-020): CN Downturn × trend_pass=0 on `rdd_63d` is coherent
   (broken-trend downturns in the policy-driven CN family have fatter vol-adjusted tails), the
   largest rdd gap in the batch, p≈0.000, era-stable, and it is a *within-CN-relevant* risk statement
   even under the cross-family baseline (deeper than the pool that CN otherwise hugs on rdd).
   Disposition: factory `human_review` → a §15-registered within-family re-test before any display.
4. **Batch-2 design consequence (for the next registration, not this one):** lattice baselines must
   be **within-family phase-pooled** (a cell vs its own family's phase mean), and promotions should
   require the within-family gap to clear — the cross-family pool becomes a disclosed diagnostic
   only. To be frozen as §15 before any batch-2 run.

## 3 · Outcome handling per §14

- 48 factory candidates written (`screened`, evidence = the batch artifact; truth_guard 0 flags) —
  they enter the review queue; none may touch any surface (authority `display_only`, consumer matrix
  forbids money-path).
- Truths appended: **CPI-019** (display, methods-scoped confirmatory + confound record),
  **CPI-020** (candidate, the CN Downturn broken-trend tail lead).
- No zero-promotion null applies. No page-authority change. Exploration tables ship to the
  measurement research surface.

## 4 · Reproduce

```
python3 scripts/build_cycle_pattern_lattice_phase0.py       # ~6s, deterministic (seed 7)
python3 -m pytest tests/test_cycle_pattern_lattice_phase0.py -q
```

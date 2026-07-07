# CPI TR-1 (next-phase transition model) — BINDING VERDICT (first CPI capacity trial)

**Run date:** 2026-07-06 (run_at 2026-07-07T00:27Z) · **Branch:** feat/cpi-tr1-transition ·
**Gates:** PREREGISTRATION.md §16 (frozen in the criteria commit before the run) · **Family:**
`cycle_pattern_tr`, BH-FDR q=0.10 across 6 cells · **Budget:** `rf.cycle_pattern.tr_v0` n=6,
declared pre-p-value · **Artifact:** `data/cycle_pattern/tr_trials/tr1_transition.json`.

---

## 0 · TL;DR

**4 of 6 cells pass — the CPI program's first gate-passing cells.** A pure-numpy L2 softmax over
*existing* PIT-pure hazard-panel columns (current-phase one-hot + the shipped W2.5-bound feature
set) beats the family-stratified Laplace transition-matrix baseline on out-of-sample multiclass
Brier in **all three families at the 1-month horizon** (ΔBrier +0.0030 us / +0.0055 country /
+0.0066 cn, every CI₉₀ above 0, years-positive 11/13/14 of 14) and in **country at 3 months**
(+0.0027, 12/14). The 3m edge is NOT established for us_sector or cn_sector (CIs straddle 0).
After 18 additive-feature cells produced 0 passes (§12–§13), this is direct evidence for the §13
synthesis: capacity enters as a **new model on a new target**, not as new columns on the pooled
hazard logistic.

## 1 · Ledger (frozen gate: CI₉₀ excl 0 positive side AND BH q=0.10 AND years+ ≥ 9/14)

| cell | ΔBrier (base − model) | CI₉₀ | boot p | years+ /14 | BH | Brier base → model | uplift | verdict |
|---|---|---|---|---|---|---|---|---|
| us_sector/1m | +0.002968 | [+0.001456, +0.004692] | 0.0050 | 11 | ✓ | 0.10982 → 0.10685 | 2.7% | **PASS** |
| us_sector/3m | +0.000499 | [−0.001265, +0.002171] | 0.2971 | 8 | ✗ | 0.13701 → 0.13651 | 0.4% | FAIL |
| country/1m | +0.005457 | [+0.003962, +0.006973] | 0.0012 | 13 | ✓ | 0.11325 → 0.10779 | 4.8% | **PASS** |
| country/3m | +0.002677 | [+0.001247, +0.004021] | 0.0012 | 12 | ✓ | 0.14504 → 0.14236 | 1.8% | **PASS** |
| cn_sector/1m | +0.006580 | [+0.005088, +0.008213] | 0.0012 | 14 | ✓ | 0.10765 → 0.10107 | 6.1% | **PASS** |
| cn_sector/3m | +0.001425 | [−0.000207, +0.002993] | 0.0749 | 10 | ✓* | 0.14791 → 0.14648 | 1.0% | FAIL |

\* cn/3m survives BH but its CI₉₀ lower bound is −0.0002 — the CI leg of the frozen conjunction
fails; the cell fails. us/3m fails all three legs. Design as frozen: 16,429 pre-embargo rows
(16,323 labeled 1m / 16,177 labeled 3m), 14 test years 2010–2023, W4.2 expanding-annual folds
(6-month embargo, min-train 400), one pooled softmax fit per fold per horizon (lr 0.15, iters 600,
l2 1.0, train-fold standardization), baseline transition matrix refit on the same train fold,
month-block bootstrap 800 draws seed 7, embargo < 2024-01-01 on fit AND gate. No calibration layer
(raw softmax gated — disclosed in §16).

## 2 · How strong is the baseline? (the bar the model had to clear)

The family transition matrix is NOT a straw man — it is a strong short-horizon predictor because
phases are sticky. Full-pre-embargo-sample diagonals P(next_h = j | j, family):

| family | Trough | Recovery | Expansion | Peak | Downturn |
|---|---|---|---|---|---|
| **1m** us_sector | 0.576 | 0.465 | 0.570 | 0.741 | 0.445 |
| **1m** country | 0.641 | 0.464 | 0.612 | 0.729 | 0.410 |
| **1m** cn_sector | 0.694 | 0.430 | 0.656 | 0.741 | 0.532 |
| **3m** us_sector | 0.300 | 0.268 | 0.418 | 0.569 | 0.188 |
| **3m** country | 0.363 | 0.217 | 0.406 | 0.517 | 0.160 |
| **3m** cn_sector | 0.435 | 0.213 | 0.466 | 0.555 | 0.257 |

Sanity gate (pipeline, printed, not a claim): Peak self-persistence > Recovery self-persistence in
every family on the 3m diagonal — the §15 batch-2 structure reproduces exactly (Recovery is the
most fragile phase everywhere; Peak the stickiest). Baseline multiclass Brier ≈ 0.108–0.113 (1m)
and 0.137–0.148 (3m); for reference a uniform 5-class predictor scores 0.16.

## 3 · Honest reading

1. **Where the edge comes from.** The baseline throws away everything about a month except
   (phase, family). The softmax additionally sees *where inside the phase* the instrument sits
   (pos_osc_s, osc_slope_s), its momentum/relative-strength state, and leg age. At 1 month, that
   within-phase position is strongly informative about whether the phase boundary gets crossed —
   the edge is largest in cn_sector (14/14 years positive) and smallest in us_sector (also the
   smallest family: 11 members vs 31/31 — a size-vs-edge link is plausible but NOT tested here).
   This is **model capacity over existing columns, exactly as registered** — no new information
   entered.
2. **Part of the 1m skill is oscillator continuation.** phase_v2 at t and t+1 share the pos_osc
   mechanics, so a model reading the continuous oscillator can anticipate threshold crossings the
   discrete matrix cannot see. That is a legitimate capability for a *display-class* next-phase
   probability, and precisely why this finding does NOT license any return-bearing consumer
   (forbidden consumers unchanged).
3. **The 3m story is honest decay, not noise.** Point estimates are positive in all three
   families, but only country clears the gate; us (+0.0005, 8/14) is indistinguishable from the
   matrix. Multi-month next-phase prediction beyond phase stickiness remains mostly OPEN — the
   same shape as the up-3m/6m PRIOR cells in W4.2.
4. **Scale check.** 2.7–6.1% Brier uplift at 1m is modest and real; it is uplift over a baseline
   that itself already encodes the §15 persistence structure. Nobody should read "softmax beats
   Markov by 5%" as a tradeable signal; it is a better *display probability* for "what comes
   next" (masterplan C4).
5. **What was NOT done:** no calibration variants, no alternative horizons/families/features, no
   per-family fits, no post-hoc tuning — the registration bars them and none were run. The
   trial-ledger row (n=6) was written at 00:27:45Z, before any p-value.

## 4 · Frozen outcome handling — applied

- **Display truth:** `cycle_truth_tr1_next_phase_softmax_skill_v1` (display, structural,
  pit_pure) appended to `data/cycle_pattern/truths.jsonl`, scoped to the 4 passing cells with the
  2 failing cells named inside the statement.
- **Factory candidates:** 4 rows (one per passing cell) appended to
  `data/cycle_pattern/pattern_candidates.jsonl` — status `screened`, trial_family `tr_v0`,
  authority `display_only`. Truth-guard cross-check against active promoted_null truths: **0
  flags** (target `next_phase_{1m,3m}` collides with no registered null).
- **No null truth:** the 0/6 branch did not fire. The us/3m and cn/3m FAILs are recorded here and
  in §16's results block; they are NOT promoted nulls (the frozen handling registers the single
  scoped null only on 0/6).
- **Page/UI unchanged.** Shipped-surface adoption (e.g. a next-phase strip on the measurement
  research surface) is a SEPARATE wave requiring its own review; the exploration tables
  (full-sample family transition matrices, both horizons) ship inside the artifact.
- Applied by `scripts/apply_cycle_pattern_tr1_outcomes.py` (idempotent).

## 5 · Process disclosures

- Two-commit discipline observed: §16 + runner + 17 tests committed (criteria commit) before any
  real-panel run; unit tests ran pre-commit with the real-panel smoke EXCLUDED (`-k "not
  smoke"`); the smoke and the real run happened only after the criteria commit.
- One typo fixed at criteria-commit time vs the drafted §16 text: panel epoch `price_c4414cdb` →
  `price_c4414dcb` (the on-disk artifact and the §12–§15 spelling). No numbers or criteria
  altered.
- Frozen-interpretation note (declared in the runner docstring at criteria time): the §16 sanity
  gate is evaluated on the **3m** transition diagonal — the §15 structure it cites is a 3-month
  persistence statement; the 1m diagonal is printed as disclosure with no gate role. (Both
  horizons in fact satisfy Peak > Recovery in every family.)
- The walk-forward is a faithful re-implementation of the W4.2 fold GEOMETRY (the W4.2
  `walk_forward` function itself is binary-logistic-specific); the gate math
  (`month_block_brier_gap_ci`, `_boot_pvalue`, `bh_fdr`) and embargo objects are imported
  verbatim and identity-pinned by tests.

## 6 · What this licenses next (docket, not registration)

- A follow-on adoption wave MAY propose the 1m next-phase probabilities as a display strip on the
  measurement surface (display_only, truth-layer note required).
- A TR-2 registration MAY test a calibration layer and/or the 3m horizon with a structurally
  different treatment (e.g. direct 3m softmax vs compounded 1m) — new budget, new section, and it
  must name this verdict.
- The IX-1 (index-level unit) and regime-vintage-spine items remain the docket per §13.

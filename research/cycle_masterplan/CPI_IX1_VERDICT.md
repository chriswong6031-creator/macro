# CPI IX-1 (index-level transfer test) — BINDING VERDICT (first index-unit trial)

**Run date:** 2026-07-07 (run_at 2026-07-07T01:04Z) · **Branch:** feat/cpi-ix1-trial ·
**Gates:** PREREGISTRATION.md §17 (frozen in the criteria commit before the run) · **Family:**
`cycle_pattern_ix`, BH-FDR q=0.10 across 4 cells · **Budget:** `rf.cycle_pattern.ix_v0` n=4,
declared pre-p-value · **Artifact:** `data/cycle_pattern/ix_trials/ix1_transfer.json`.

---

## 0 · TL;DR

**0 of 4 cells pass — the member-trained hazard model does NOT transfer to index level under the
frozen gate.** The up-direction cells show no earned skill (1m ΔBrier +0.0099 with a straddling
CI; 3m −0.0018, worse than the index KM point estimate). The down-direction cells are the honest
tension in this verdict: both show REAL pooled improvement (ΔBrier +0.0335 / +0.0290, CI₉₀
entirely above 0, boot p 0.011 / 0.001, both BH-survivors) — and both FAIL the third leg of the
frozen conjunction, sign-stability (5/13 and 7/13 positive years vs the bar ≥9), because the gain
is episodic: 2021 alone contributes a +0.31/+0.25 year-mean gap while 2020 is harmful (−0.16).
The pre-registered gate was built to refuse exactly this shape — pooled magnitude carried by a
minority of years — and it did. Per the frozen outcome handling, ONE scoped null truth ships;
no factory candidates; no page/UI change.

## 1 · Ledger (frozen gate: CI₉₀ excl 0 positive side AND BH q=0.10 AND years+ ≥ 9 of 14)

| cell | ΔBrier (KM − model) | CI₉₀ | boot p | years+ | BH | KM Brier → model | verdict |
|---|---|---|---|---|---|---|---|
| up/1m | +0.009875 | [−0.005589, +0.024679] | 0.1261 | 8/14 | ✗ | 0.24453 → 0.23465 | FAIL |
| up/3m | −0.001761 | [−0.019524, +0.013513] | 0.5918 | 8/14 | ✗ | 0.25705 → 0.25881 | FAIL |
| down/1m | +0.033462 | [+0.008407, +0.058964] | 0.0112 | 5/13 | ✓ | 0.24481 → 0.21135 | **FAIL** (sign-stability) |
| down/3m | +0.029016 | [+0.012940, +0.045508] | 0.0012 | 7/13 | ✓ | 0.16536 → 0.13634 | **FAIL** (sign-stability) |

Design as frozen: model arm fit on 16,429 pre-embargo MEMBER person-period rows per the W4.2
harness (expanding-annual folds 2010–2023, 6-month embargo, min-train 400, member train-fold
standardization, per-fold leak-free PAV), scored on 1,815 pre-embargo INDEX rows (1,003 up / 322
down OOS); baseline = age-pooled per-entity index KM refit on index train rows each fold
(engine/index_km, 30-row entity threshold → family pool → global pool); month-block bootstrap 800
draws seed 7; embargo < 2024-01-01 on ALL fitting and the gate. NO index-row fitting anywhere.

**Denominator disclosure:** 2017 has ZERO index down-leg OOS rows (no entity was in a confirmed
down leg at any 2017 month-end), so the down cells are judged on 13 test years. The frozen bar
stays ≥9 — a year with no rows cannot count as positive. Neither down cell is within 2 years of
the bar (5 and 7 vs 9), so this convention is not outcome-determining.

## 2 · How strong is the baseline? (the bar the model had to clear)

The age-pooled per-entity KM is a strong index-level null because index down-legs resolve fast
and entities differ persistently: pre-embargo P(y3|down) runs 0.75 (AAXJ) → 0.96 (ILF) and
P(y3|up) 0.31 (SPY) → 0.61 (ILF) — the entity identity alone carries most of the pooled variance
the member model has to rediscover through covariates. Its own OOS Brier: 0.245/0.257 (up 1m/3m),
0.245/0.165 (down 1m/3m — the 3m down bar is low because the high base rate ≈0.85 is easy to
call). Fallback usage matched the census: SPY-down (singleton us_market family — the family pool
IS SPY's own pooled rate) and the short-history blocs (VXUS from 2011) used the fallback chain in
early folds; disclosed, not tuned.

## 3 · Per-entity ΔBrier decomposition (disclosed diagnostic — is SPY driving or dragging?)

| entity | up/1m | up/3m | down/1m | down/3m |
|---|---|---|---|---|
| AAXJ | −0.0066 | +0.0100 | +0.0612 | +0.0646 |
| EEM | +0.0260 | +0.0155 | +0.0589 | +0.0614 |
| EFA | +0.0101 | −0.0015 | +0.0219 | +0.0044 |
| ILF | +0.0003 | −0.0138 | **−0.0389** | −0.0030 |
| SPY | −0.0007 | **−0.0270** | **+0.0951** | **+0.0661** |
| VGK | +0.0263 | +0.0067 | +0.0735 | +0.0137 |
| VPL | +0.0081 | −0.0012 | +0.0281 | +0.0248 |
| VXUS | +0.0174 | +0.0038 | +0.0196 | +0.0153 |

**Headline: SPY is the largest positive contributor in BOTH down cells (+0.095/+0.066) and the
largest drag at up/3m (−0.027).** The down-cell improvement is broad (7 of 8 entities positive at
1m; ILF the sole drag — the entity whose 0.96 down base rate the KM already nails), so the pooled
CI/BH passes were not a single-entity artifact; they were a single-ERA artifact, which is exactly
the axis the sign-stability leg tests. Point estimates only; no CI, no gate role.

## 4 · Honest reading

1. **The down-cell result is a real but unreliable transfer.** Within confirmed down-legs the
   member model's within-leg state (pos_osc, momentum, leg age) does move index-level trough
   odds — in the years where down-legs are numerous and prolonged (2014/15, 2018, 2021/22:
   17–61 down rows). In sparse-down years the KM's entity base rate wins. Pooled magnitude
   +0.03 Brier is large (14–18% of the bar), but 5/13 positive years means a user watching this
   surface would have been better served by the KM in MOST years. The registration's third leg
   exists precisely to keep that off a page.
2. **2021 is doing outsized work.** Year-mean gap +0.31 (1m) / +0.25 (3m) against cell means of
   +0.033/+0.029 — the China/EM down-cycle of 2021 (AAXJ/EEM legs) plus late-year VGK/VPL is the
   single dominant episode. 2020 flips harmful (−0.16): the COVID crash's instant V-bottom made
   the model's smooth within-leg hazard WORSE than the base rate. Episodic asymmetry, not steady
   skill.
3. **Up-direction transfer fails flat.** The member model's peak-hazard edge (HZ-up-1m PASS at
   member level) does not survive the unit change even directionally at 3m. Plausible mechanism
   (not tested here): index up-legs are long survivorship-composites of member legs — the
   member-level age/momentum profile mis-scales, and SPY (the only us_market entity, scored at
   the model's us_sector reference level per the disclosed family-dummy interpretation) is the
   biggest 3m drag.
4. **The gate structure carried the verdict.** Two of three legs passed in both down cells; a
   registration gated on CI + BH alone would have shipped 2/4 PASS. The sign-stability leg —
   frozen before any data was seen — is the whole difference between "this transfers" and the
   truthful "this worked in 2021."
5. **What was NOT done:** no stacking with the reserved index FT-4 covariates, no per-entity or
   per-direction refits, no calibration variants, no alternative horizons, no post-hoc gate
   re-reading — the registration bars them and none were run. The trial-ledger row (n=4) was
   written at 01:04:24.686Z, before any p-value; candidate count (4) printed first.

## 5 · Frozen outcome handling — applied

- **ONE scoped null truth:** `cycle_truth_ix1_index_transfer_null_v1` (promoted_null) appended to
  `data/cycle_pattern/truths.jsonl` — the §17-frozen 0/4 branch. The statement names the down
  cells' passing CI/BH legs and the year-concentration honestly (this null is about
  RELIABILITY, not about the pooled point estimate), and scopes the kill to THIS transfer recipe
  (member-fit logistic + member-fold standardization/PAV, no index-row fitting, no index
  covariates).
- **NO factory candidates** (frozen: candidates only on PASS).
- **Page/UI unchanged.** Engine-backing the markets.html US row was pre-committed as a SEPARATE
  adoption wave and is moot on 0/4. Exploration tables (full pre-embargo index KM table,
  per-entity ΔBrier decomposition) ship inside the artifact.
- Applied by `scripts/apply_cycle_pattern_ix1_outcomes.py` (idempotent).

## 6 · Process disclosures

- Two-commit discipline observed: §17 + runner + 19 tests committed (criteria commit 40d5144ed8)
  before any real-panel run; unit tests ran pre-commit with the real-panel smoke EXCLUDED
  (`pytest -k "not smoke"` → 18 passed); the smoke and the real run happened only after the
  criteria commit. §17 text appended verbatim from the registration draft (no edits, including
  no numeric edits).
- Frozen interpretations declared in the runner docstring at criteria time (mechanical readings,
  no tuning): (1) the §17 PAV phrase is implemented as the W4.2 harness's own fold-train-fit
  `p{h}_caloof` convention — the exact object the §12/§13 baseline arm gates on, which sees no
  test-window label of either panel; (2) index rows carry the reference-level member family
  dummies (us_market/bloc are not member families); (3) `build_design`'s median-impute applies
  per panel (index NaNs ≤1.9% of rows), while fold standardization is member-only.
- The walk-forward is a faithful re-implementation of the W4.2 fold GEOMETRY on the transfer
  split (member train → index test; the W4.2 `walk_forward` function scores member test rows
  only); the gate math (`month_block_brier_gap_ci`, `_boot_pvalue`, `bh_fdr`), the logistic, the
  index KM, the PAV objects, and the embargo objects are imported verbatim and identity-pinned
  by tests.
- The per-year gap means quoted in §4 are the sign-stability leg's own inputs (gate machinery,
  not new evaluations); the per-entity table is the §17-named disclosed diagnostic.

## 7 · What this licenses next (docket, not registration)

- The §17 falsifier (a): an index-covariate STACKING trial — member transfer scores + the
  reserved sync/phase-breadth/dispersion covariates fit at index level — under a NEW
  registration naming `cycle_truth_ix1_index_transfer_null_v1`. The down cells' passing CI/BH
  legs say there is signal worth stacking on; the failed leg says it needs a stabilizer.
- The §17 falsifier (b): a post-embargo accrual re-run (≥2024 adds down-leg years — the exact
  denominator the failed leg is starved of).
- The markets.html US row keeps its current sourcing; no engine-backing wave is licensed.

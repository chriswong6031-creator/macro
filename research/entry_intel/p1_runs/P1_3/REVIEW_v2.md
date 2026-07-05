# P1.3 Trio Ablation — ROUND-2 CONFORMANCE REVIEW (v2)

**Reviewer:** Opus conformance subagent (Round 2 — fresh reviewer, skeptical default), Entry Intelligence program
**Date:** 2026-07-05
**Round-2 runner report headline:** "Round-2 defect-corrected re-run OVERTURNS round-1 'TRIO CLOSED 0/30' … 22/30 survive BH … F1 ships-as-RW, F2 ships-as-RW, F3 ships-as-HARD-GATE. Both calibration controls PASS."
**Artifacts audited (round-2):** `run_P1_3_v2.py`, `RESULTS.md`, `results.json`, `_v2_state.json`, `_v2_run.log` in `research/entry_intel/p1_runs/P1_3/`
**Round-1 bounce audited:** `REVIEW.md`, `run_P1_3_v1_bounced.py` (same dir)
**Substrate recomputed against:** `data/replay/replay_boarded.parquet`, MD5 `906175f9eb8caa351ed6d7d5c56265d3` (matches results.json and my independent `md5 -q`)
**Binding law read in full:** PREREG (`P1_3_TRIO_ABLATION_PREREG.md`, APPROVED Fable 2026-07-05, §APPROVAL binding), `P0_MEASUREMENT_MEMO.md` v1.0 + §6 v1.1 amendments.

---

## FINAL VERDICT: **CONFORMANT** — accept the round-2 result; the round-1 BLOCKING defect is demonstrably dead.

The round-1 bounce was correct: the primary statistic was invalid (within-group bootstrap → `boot_p ≈ 0.50` by construction, independent of true effect). The round-2 re-run replaces it with an **episode-level label-permutation Mann-Whitney U null**, which I **independently reimplemented from scratch** (not calling the runner's function) and which reproduces every headline number exactly. The corrected null is genuinely null-centered, both calibration controls are genuine (I reran the negative control myself), the sanity gate has real power against the round-1 signature, and the trial grid / era / BH family / n-floors are conformant. The overturned verdict — **PARTIAL SURVIVORS** (F1→RW, F2→RW, F3→HG; none `falsified`) — is supported by the evidence.

Two **ADVISORY** items (neither blocks acceptance): the canonical filename `run_P1_3.py` still contains the buggy round-1 code, and the BH family contains p-values duplicated across terminal states within each (factor,mode,horizon) cell (a faithful consequence of the PREREG's own §5.1 forward-return test spec, not a v2 deviation).

---

## The round-1 defect is dead — reproduced and re-verified independently (BLOCKING check → PASS)

**Round-1 defect reproduced.** I re-ran the exact round-1 mechanism (`episode_bootstrap_mwu`, within-group episode resample) on T01 (F1 HG 21d):
- `obs_U = 348,341,197`; null `E[U] = 309,728,955`; `obs_dev = 38,612,242`.
- Bug bootstrap `boot_U` mean = **348,296,561 ≈ obs_U** (NOT ≈ null) → `boot_p = 0.4835`.
- Parametric MWU `p = 8.684e-128` (matches the REVIEW.md and RESULTS T01 value 8.68e-128); `r = -0.1247` (matches).
This confirms the round-1 REVIEW.md's diagnosis to the digit: the within-group resample centers the bootstrap U on the observed U, so `P(boot_dev ≥ obs_dev) ≈ 0.5` for every trial regardless of effect size.

**Corrected mechanism reproduced independently.** I wrote a standalone episode-level label-permutation test (shuffle whole-episode A/B labels, recompute pooled-row MWU U, two-sided `|U − E[U]|` p with +1 smoothing) — **without importing the runner's `episode_permutation_mwu`** — and got:

| Trial | My perm_p | RESULTS perm_p | My param_p | My r | Permutation U mean vs E[U] |
|---|---|---|---|---|---|
| T01 (F1 HG 21d) | 0.0002 | 0.0002 | 8.684e-128 | −0.1247 | 305.5M ≈ E[U] 309.7M ✅ null-centered |
| T21 (F3 HG 21d) | 0.0026 | 0.0026 | 6.874e-07 | −0.0612 | 54.87M ≈ E[U] 54.76M ✅ null-centered |
| T11 (F2 HG 21d) | 0.1766 | 0.1766 | 3.034e-02 | +0.0117 | 265.4M ≈ E[U] 265.5M ✅ null-centered |

The decisive contrast with round 1: the permutation U-distribution is now **null-centered** (mean ≈ E[U]), where the round-1 bug centered it on obs_U. And the corrected test **discriminates**: it flags the two real effects (F1, F3) at the floor / p=0.0026 while correctly leaving the genuine near-null F2 HG at p=0.18 — exactly the separation the round-1 reviewer predicted a valid test would produce.

**Sanity gate has genuine power (positive-controlled the guard).** The v2 gate halts if `perm_p > 0.3 AND param_p < 1e-6`. Applied to the round-1 T01 signature (boot_p 0.50, param_p 8.68e-128): `0.50 > 0.3` True AND `8.68e-128 < 1e-6` True → **would HALT**. On v2 T01 (perm_p 0.0002) it correctly does not trip. The guard is not a no-op; it fires on the exact failure it claims to catch.

---

## Per-check findings

### CHECK 1 — Round-1 BLOCKING defect demonstrably dead: **PASS (BLOCKING check cleared)**
Reproduced the buggy within-group bootstrap (`boot_p 0.48`, boot_U centered on obs_U) and independently reimplemented the corrected episode-level permutation null (reproduces perm_p on T01/T21/T11 exactly; U now null-centered). Sanity gate positive-controlled — would have halted round 1. `run_P1_3_v2.py` L209–291 is the corrected function; verified line-by-line against my reimplementation. **No residue of the round-1 defect.**

### CHECK 2 — Calibration controls genuine: **PASS**
- **Negative control (I reran it, 60 independent draws × 1000 perms on episode-permuted real labels):** rejection @α=0.05 = **0.067**; p-values uniform (mean 0.483, min 0.021, max 0.967 — spread across U(0,1), NOT clustered at 0.5); KS-uniform D=0.074, p=0.869. Consistent with the runner's 200-draw run (rejection 0.035, KS D=0.081, p=0.14). Both are correct size within sampling noise; the runner's is slightly conservative, mine slightly liberal — both within the n-driven band. The uniform spread is the empirical proof the corrected null is well-calibrated (and the definitive positive-control of the whole permutation apparatus).
- **Positive control (I reproduced the injection):** +0.05 return shift to synthetic episode-level group A → perm_p at the **floor** (1.9996e-04, matches RESULTS 2.00e-04); liftoff-rate Δ = +19.8pp (RESULTS +19.7pp); r ≈ −0.29. A non-injected random 50/50 episode split gave perm_p = 0.0255 (a legitimate U(0,1) draw, not the floor). Power against a real episode-level shift is demonstrated.
- Overall calibration **PASS**, genuine (not asserted).

### CHECK 3 — Trial grid / era / stamp / BH family / n-floors / power honesty: **PASS**
- **Grid:** 30 trials (`TRIAL_GRID`, L463–479) map line-for-line to PREREG §4; factor/mode/horizon/terminal-state tuples exact; Mode-B rows carry only STOPPED+CUSHIONED (no dead-money) per §4 design note; `assert len==30`. m=30 asserted in BH.
- **Era/stamp:** population = `verdict_type=='fire' & verdict_grade==True`; effective window **2022-06-30 → 2025-12-29** per §APPROVAL clause 1 (250-bar warmup; on-disk max is 2025-12-29, honestly stated as the realized ceiling vs the nominal 2026-07-02); survivor_bias all False (0 stamped, `assert stamped==0`); horizon_censored 7,701 pre-excluded via verdict_grade; stamp text printed. Baseline `state_15_126` (STOPPED 31,372 / CLEAN_LIFTOFF 16,549 / CUSHIONED 1,975 / DEAD_MONEY 43) matches §APPROVAL clause 3 to the row.
- **BH:** m=30, standard step-up with monotonicity (L301–312). I recomputed from the perm_p vector → **n_survive = 22, min BH-adj = 0.0006**; the per-trial BH-adj values (T17→0.0933, T19→0.0752, T21→0.0060, T24→0.0933, T27→0.0352, …) all reproduce.
- **n-floors:** THIN floor = 25 clusters; smallest would-block cell (F3, 1,270 clusters) well above floor; no cell falsely promoted or thinned.
- **Power honesty:** `insufficient_power_cells: []` correct — every cell exceeds the floor; no cell borrowed from stamped data (0 stamped rows exist).

### CHECK 4 — Independent recompute of headline numbers (≥3 required; ~15 recomputed): **PASS (all exact)**
Every number below recomputed by me from the parquet and matched RESULTS/results.json exactly:
- Census: vg fires 49,939; episode clusters 22,295; stamped 0; horizon_censored 7,701; era 2022-06-30→2025-12-29.
- Encodings: washout 22,965/26,974; rs quartiles 13016/12632/11101/9362, null 3,828; ext_z>2.0 = 2,299.
- Terminal Δpp: T01 +2.41, T02 −13.19, T03 −4.10, T04 −5.21, T11 +1.19, T21 −0.43, T22 −3.63, T24 −5.00.
- Fire-rate impact: F1 54.0% (26,974/49,939), F2 48.5% (22,378/46,111 on F2_valid), F3 4.6% (2,299/49,939).
- Both-halves: midpoint 2024-04-04, H1 23,984 / H2 25,955; T02 half deltas −14.00 / −12.29.
- RW construction: F1 moved_up group 20,698 / 29,241 (verified only bonus-recipients rise; 0 non-passers move up — faithful factor proxy).
- BH: n_survive 22, min 0.0006. Episode purity: F1_HG 50, F3_HG 343 impure episodes (exact).
- Statistical primaries: perm_p (T01 0.0002, T21 0.0026, T11 0.1766), param_p (T04 1.90e-79, T07 4.40e-96, T19 5.55e-04, T24 2.10e-03, T27 7.68e-05), r (all matched).

### CHECK 5 — RESULTS.md leads with verdict + defect section + plain-English box: **PASS**
- L3 leads with **WHOLE-STUDY VERDICT: PARTIAL SURVIVORS** and the retraction of the round-1 "TRIO CLOSED" headline (`§7.5` retract-by-name satisfied).
- "In plain English" box present (L20–28), plain-language and honest about the F1 horizon nuance.
- "Round-1 defect and fix" section present (L32–38): correctly describes the within-group-bootstrap defect, the permutation fix, the sanity gate, and why permutation over CR1.
- All PREREG §9 required sections present: preamble/census, per-factor results table, fire-rate impact table, both-halves sign-stability table, per-factor verdicts (§6-ordered), whole-study verdict, context appendices A/B/C, leak audit, statistical-method note.
- The round-1 REVIEW advisory (washout transcription "19,003/30,936") is **fixed** — RESULTS L81 now states the correct 22,965/26,974.
- Ship-logic spot-audited against trial data + PREREG §6: F1 GATE-REJECT+RW (T04 fav+BH+sign; 54%>40% & T01 unfav → gate rejected; RW ships via T09), F2 SHIPS-RW (HG null T11/T14; RW ships via T18/T20), F3 SHIPS-HG (T21/T24 fav+BH+sign; 4.6%<40%; RW sign-unstable). All correct.

---

## ADVISORY findings (do not block acceptance)

### ADVISORY-1 — Canonical `run_P1_3.py` still holds the BUGGY round-1 code.
`run_P1_3.py` is byte-identical to `run_P1_3_v1_bounced.py` (the defective within-group bootstrap). The corrected code is in `run_P1_3_v2.py`, which is what produced the current `results.json` / `RESULTS.md` / `_v2_state.json` / `_v2_run.log` (all consistent, verified). Risk: a future reader who runs the "canonical" `run_P1_3.py` reproduces the broken 0/30 result, not the shipped round-2 result. **Recommendation:** promote `run_P1_3_v2.py` to `run_P1_3.py` (keep the v1 as `_v1_bounced` for the record). Non-blocking because provenance of the round-2 result is unambiguous from the v2-suffixed artifacts.

### ADVISORY-2 — BH family contains p-values duplicated across terminal states within each cell.
Per PREREG §5.1 the primary test is a Mann-Whitney U on the **continuous forward-return distribution**, so within a single (factor, mode, horizon) cell the perm_p/param_p/r are identical across its terminal-state trials (e.g. T01/T02/T03 all carry perm_p=0.0002). The BH family (m=30) therefore contains only ~10 distinct p-values, each repeated ~3×. This is **faithful to the registered design** (round-1 did the same and passed grid-adherence; it is disclosed in RESULTS L97), and the runner did not deviate. Its one visible effect is that the **survivor count** (22/30) overstates the number of independent findings — a favorable cell contributes up to 3 "survivors" — while the number of independent *effects* is ~3 (F1 strong, F3 moderate, F2 weak). The factor-level verdicts correctly key off `survives_bh AND delta_favorable AND sign_stable`, so this does not mis-promote any factor; it is a reporting-transparency note. **Recommendation:** in downstream P2.1, cite the ~10 independent forward-return tests rather than "22/30 trials" as the strength-of-evidence headline.

### ADVISORY-3 — Deliverable path vs artifact path.
The round-2 artifacts and the round-1 bounce REVIEW.md live in `p1_runs/P1_3/`; this review was written to the task-specified `p1_runs/P1_3_TRIO_ABLATION/REVIEW_v2.md`. A future reader looking beside the artifacts (in `P1_3/`) will not find it. Non-blocking; flagged so the orchestrator can co-locate if desired.

---

## Statistical soundness note (permutation construction)

The corrected test permutes episode labels holding the **episode** count `n_ep_a` fixed, while the observed `obs_dev` uses `E[U] = n_a·n_b/2` with the true **row** counts. Under permutation, `n_rows_a` varies slightly with episode sizes, so each permutation recomputes its own `E[U]` from its drawn row counts (L282). I checked the magnitude: observed episode-based n_rows_a = 23,041 vs permutation-mean 21,458 (std 85) — a ~1,600-row offset that shifts `E[U]` negligibly relative to `obs_dev` = 38.6M. Impure episodes (F1_HG 50, F2_HG 1,729, F3_HG 343) are resampled whole (first-seen label), which coarsens — not biases — the clustered unit, if anything widening the null (conservative), as RESULTS L240 discloses. The negative control passing (uniform p, correct size) is the definitive empirical confirmation that this construction is well-calibrated. No concern.

---

## Recommendation to the Fable orchestrator

1. **ACCEPT** the round-2 result. The round-1 BLOCKING defect is corrected and independently verified dead; calibration is genuine; the overturned PARTIAL-SURVIVORS verdict (F1→RW, F2→RW, F3→HG; none `falsified`) is supported. The round-1 `falsified` proposal is correctly withdrawn.
2. Promote `run_P1_3_v2.py` → canonical `run_P1_3.py` (ADVISORY-1).
3. Carry ADVISORY-2 forward to P2.1: report ~3 independent factor effects (10 independent forward-return tests), not "22/30 trials," as the evidence-strength headline. F2's effect is genuinely marginal (|r| ≈ 0.01–0.02) — shadow-test with effect-size monitoring as RESULTS already flags.

**No git operations performed. This review is data for the Fable orchestrator.**

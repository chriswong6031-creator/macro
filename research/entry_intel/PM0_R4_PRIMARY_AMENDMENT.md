# PM0 — r4 PRIMARY-MACHINERY AMENDMENT (pre-inference; §7-failure remedy)

**Status: REGISTERED 2026-07-10 by Fable (main loop), BEFORE any real trial p-value was computed or
examined. Opus red-team of this amendment is BLOCKING before the §7 rerun.** Companion to
`PM0_PRICE_MEMORY_BUNDLE_PREREG.md` (r3, APPROVED 2026-07-06 — that document is immutable and is not
edited by this amendment) and `pm0_runs/EI_PM0_price_memory/EXECUTION_SPEC.md` (EX-1..EX-8).

## 1. What happened (the record)

The r3 prereg's blocking gates were executed in order: §4.4 feature-build QA passed (all five gates);
§7 calibration ran **and failed, twice**, before any real trial p-value existed:

- Run 1 (row-month grouping): PM2 negative control KS-p 0.0333 (< 0.05 floor); PM2 rej@0.05 0.11.
- EX-8 conformance fix (episode-first-month blocking, prereg §4.2's own straddle rule — straddling
  episodes had been leaking label-correlated rows across adjacent month blocks): PM4 KS 0.076 → 0.340,
  PM2 rej 0.11 → 0.08, but PM2 KS = **0.0412, still under the frozen 0.05 floor**.
- Diagnosis on the deterministic PM2 draws (seeds 777/20260706 derivations, reproduced exactly): the
  null p mass at p < 0.025 is 5.5% (2.2× nominal) and at p < 0.10 is 17% (1.7× nominal) — genuine
  left-tail anticonservatism of the registered **null-centered pivot month-block bootstrap** at m = 43
  blocks, concentrated exactly where BH at q ≤ 0.10 operates. All other criteria passed on all four
  instruments (rej ≤ 0.08, mean/median in band; PM1/PM3/PM4 KS 0.20/0.64/0.34); all eight positive
  controls passed (5.00pp injections detected, synthetic-family BH-adj ≤ 0.044).
- Per prereg §7: the study is INVALID as registered; blocker report to Fable. This document is that
  report and its adjudication. **The m = 20 family's FDR budget is unspent** — nothing real was tested.

## 2. Ruling

The registered **estimand and contrast are unchanged**: per-trial within-calendar-month contrast Δ̂
(episode-month blocking, both-groups-≥5 month qualification, harmonic weights) exactly as prereg §4.2 +
EX-8. The failed component is only the p-value machinery attached to Δ̂.

**Primary p (r4):** within-calendar-month episode-label permutation — the exchangeability class the
prereg's own §7.1 control already defines and implements:

- Episode-majority labels; episodes permute labels only among episodes assigned (first-row month) to
  the same calendar month; rows inherit their episode's permuted label (mixed-label fraction logged).
- Per permutation draw, the full registered statistic is recomputed (per-month qualification, Δ_m, w_m,
  weighted Δ̂*). **B = 5,000 draws**, seed derivation unchanged in constant (`default_rng([20260706,
  trial_idx])`), two-sided add-one p: `p = (1 + #{|Δ̂*_b| ≥ |Δ̂_obs|}) / (B + 1)`, with Δ̂_obs the
  registered row-level-label statistic.
- This is a calendar-composition-preserving null (DT-R14 / RR-1 compliance class: within-period label
  randomization), exact under within-month label exchangeability by construction — the left-tail
  anticonservatism of the small-m bootstrap cannot arise. It is also the machinery class every prior EI
  primary (P1.3-v2, P2.5) used, upgraded with the within-month restriction DT-R14 demands.

**The month-block bootstrap is demoted to a labeled CI diagnostic** (effect-size context beside Δ̂;
never verdict-feeding; its §7 calibration record — mild left-tail anticonservatism at m = 43 — is
printed wherever the CI appears).

**Known limitation (disclosed, inherited from the house permutation convention):** the permutation
null randomizes the episode-size↔label pairing within month; if label correlates with episode size and
size with incidence, exchangeability is imperfect. Mitigations in place: harmonic-weight recomputation
per draw, per-month blocking, favorable-direction requirement, THIN/event floors, and the bootstrap CI
printed beside every verdict-feeding p. Same property was accepted in P1.3-v2/P2.5.

Everything else in r3 stands verbatim: m = 20 family and BH q ≤ 0.10, floors, sign-stability halves at
2024-06-30, redundancy fence, verdict criteria §6, report contract §9, display-only ceiling and
DT-R2/DT-R7 forbidden-key law, PM5 data_blocked, grid-B DEAD_MONEY unregistered.

## 3. §7 controls under r4 (rerun in full, all four instruments + both positives)

- **Negative control:** 200 outer permuted-label draws per instrument (seed derivations unchanged:
  outer `[777, FEAT_IDX]`); per outer draw the r4 primary p is recomputed with **B_inner = 500** (a
  resolution economy only — the control checks the p-histogram at 200-draw granularity; inner seed
  `[20260706, FEAT_IDX, draw_idx]`). PASS criteria verbatim from r3 §7.1: rej@0.05 ≤ 0.12, mean and
  median p in 0.5 ± 0.1, KS-uniformity p ≥ 0.05. (For an exact test the expected outcome is uniformity
  up to discreteness; the control therefore verifies the implementation, which is its purpose under
  the P2.5 convention.)
- **Divergence sanity gate:** per EX-7, at trial level on the same MWU statistic (parametric p vs
  episode-permutation p of the same U; P2.5 signature; any trip HALTs inference before BH/verdicts).
- **Positive controls:** return instrument unchanged (episode-permutation MWU on the injected return
  must reject ≪ 0.05); incidence instrument re-run through the **r4 primary** (5pp of favorable group,
  whole episodes, month-stratified, seed 4242 derivations unchanged), must reach synthetic-family
  `min(1, p × 20) ≤ 0.10` per instrument.
- Either failure ⇒ INVALID, blocker report, no inference — unchanged.

## 4. Implementation contract

- Vectorized permutation engine (per-month episode row/event count arrays; batched draws); required
  equivalence tests, all blocking, run at calibration start per instrument: (a) the slow selection
  evaluator vs an independent inline row-assignment reference on the TRUE episode-majority selection;
  (b) 5 fixed label draws (seed [606, FEAT_IDX]) — selection evaluator vs independent reference;
  (c) the BATCHED numpy path (n_perm=7, seed [303, FEAT_IDX], selections collected) vs the slow
  evaluator on the identical selections — the test that validates the production null generator.
  (The registered row-level statistic differs from the majority-label statistic by the mixed-episode
  effect; that difference is informational, not asserted.)
- No real trial p-value is computed until §7 passes and `--authorize-one-shot` is given (unchanged
  stage gating).
- The two failed r3 calibration runs are preserved (`calibration_run1_FAILED.log`, run-2 log) and cited
  in RESULTS.md §1; results.json records `primary_machinery: "r4 within-month episode-label
  permutation"` and this amendment's path.

## 5. Multiplicity note

The m = 20 family ledger debits ONCE: the r3-registered family never produced an examined p-value; r4
replaces its machinery pre-observation. No trial was added, removed, or re-aimed; the §5 trial table is
untouched. This is machinery repair under the P1.3 round-1→round-2 precedent, not a second draw from
the family.

— Fable, 2026-07-10. Opus red-team verdict to be appended below before the §7 rerun.

---

## §REVIEW OF RECORD — Opus red-team, 2026-07-10

**VERDICT: CLEAR TO RERUN CALIBRATION. Zero BLOCKING findings.**

Adjudications: (1) statistical validity CLEAN — the within-month episode-label permutation is exact
under within-month exchangeability and cures the measured small-m bootstrap left-tail; the
row-level-obs vs majority-label-null convention was stress-tested and stays calibrated at up to 20%
mixed fraction (ADVISORY only). (2) Process legitimacy CLEAN — machinery repair under the P1.3
round-1→round-2 precedent; estimand/trial-table/m/q unchanged; both failed runs preserved; budget
unspent. (3) Implementation CLEAN — argpartition subset semantics, k_m edge cases, conservative
NaN-draw counting, deterministic vector seeds, BH fed by primary_perm_p only, bootstrap quarantined to
*_DIAGNOSTIC keys; batched-vs-slow equivalence verified. (4) No runtime blockers on the measured
substrate.

Advisories (non-gating, actioned or recorded): **A1** the negative control is structurally blind to
the disclosed episode-size↔label↔outcome confound (the permutation erases the correlation it would
need to detect) — RESULTS §7 leak-audit must state that a passing control does not certify the
size-exchangeability assumption [ACTIONED: disclosure added to the report generator]. **A2** seed
vectors [20260706,k] and [20260706,k,0] alias to identical streams (different datasets/stages; no
validity impact; namespace if ever touched). **A3** the equivalence suite is 52 checks (not 60);
tests (a)/(b) are structural sanity checks, (c) is the genuine batched-path validator [ACTIONED:
counts corrected here]. **A4** format-fragility nits unreachable on this substrate.

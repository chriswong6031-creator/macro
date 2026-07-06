# P2.5 Interaction PREREG — MULTIPLICITY / HONESTY RED-TEAM

**Auditor:** Opus subagent (Entry Intelligence, Fable orchestration) — multiplicity/honesty lane
**Date:** 2026-07-05
**Target:** `research/entry_intel/P2_5_INTERACTION_PREREG.md`
**Upstream diagnostic:** `research/entry_intel/p1_runs/P2_5_DIAGNOSTIC/` (RESULTS.md + results.json + run_P2_5_diagnostic.py)
**Method:** independent recompute of cited cell statistics from `P2_5_DIAGNOSTIC/results.json`; read of the diagnostic runner source; cross-check against F1 reprobe RESULTS/REVIEW and P0_MEASUREMENT_MEMO §6.

---

## VERDICT: **APPROVE-WITH-EDITS**

The PREREG's multiplicity architecture is sound: exactly 8 configs (at the cap), m declared exactly (16/14/12 with a logged thin-cell rule), one BH family at q≤0.10, RW-only with `gate_fire_rate_impact_pct=0.0` by construction, and a non-weaselly in-sample honesty clause. The double-dip protections (calibrated permutation, both-halves, shadow-only authorization, program-wide kill) are all present. **All four recomputed power-floor cells reproduce exactly** against the diagnostic JSON.

Two BLOCKING edits are required before execution. Both concern the **both-halves sign-stability gate — the single load-bearing double-dip protection** — and the config-selection rationale that leans on it:

1. The diagnostic's `sign_consistent()` function (the source of the `sc63=Y` labels the PREREG's §3 config-selection rationale relies on) is **buggy**: it tests both halves' 63d stop-out against the **21d** baseline (0.3848), not the 63d baseline (0.6231), so `sc63` returns `True` mechanically for every 63d cell. Under the correct baseline, **4 of the 5 headline cells (C3, C5, C6, proxy_equiv) flip sign between halves at 63d** — only C2 (d40plus) is genuinely 63d sign-stable. The PREREG must (a) not inherit this function, and (b) not present the diagnostic's `sc63=Y` as evidence the configs are half-stable.

2. The PREREG's §5.2 sign-stability definition is under-specified on the **baseline convention** — the exact defect that produced the bug. It must pin "same sign" to a per-horizon baseline (or a within-half moved-up-vs-not-moved-up contrast that needs no baseline at all), stated explicitly, or the runner may silently reproduce the 21d-baseline error.

The remaining items are ADVISORY (citation/typo drift that does not change any decision). None of the advisories block; the two blockers are edits to text, not to the study design — the design, once the sign-stability convention is pinned and the tainted rationale is corrected, is approvable.

---

## PER-CHECK FINDINGS

### CHECK 1 — Grid ≤8, m declared, one BH family, RW-only → **PASS (advisory nuance)**

- **Config count:** exactly 8 (C1–C8), at the cap. `research/entry_intel/P2_5_INTERACTION_PREREG.md:136-145`.
- **m declared exactly:** m=16 (8×2 horizons), with a pre-declared decrement to m=14 (one thin cell) or m=12 (both C7/C8 thin), decided at run start from the n_episode check and logged in the preamble before computation (`:124`, `:147`, `:180`). This is the correct, honest handling of the two estimated cells.
- **One BH family:** `P2_5_depth_interaction`, q≤0.10 across all m simultaneously (`:157`, `:180`, `:196`). §2.2 clause 6 (`:118`) forbids a 9th config within the family — post-hoc variation = new trial_id/new family. Clean.
- **RW-only:** every config is an additive `blend_sorted` +0.10 tilt; `gate_fire_rate_impact_pct = 0.0` for all configs by construction; R7 additive-lanes restated (`:128`, `:215`). No hard-gate path.

**ADVISORY 1a:** The grid is *at* the ceiling (8/8), and 2 of the 8 (C7, C8) are registered on **estimated** episode counts the diagnostic never computed as named cells (`:144-147`). C7's estimate (~1,380 ep) is close enough to the 25-cluster floor that it will pass, but the PREREG registers a trial whose power it did not measure. The thin-check-at-run-start mechanism handles this correctly, so it is not blocking — but a reader should note that C7/C8 are speculative slots consuming 4 of the 16 family degrees of freedom on directional guesses, not diagnostic-confirmed effects.

### CHECK 2 — In-sample honesty clause present and NOT weaselly → **PASS**

§2.2 (`:100-118`) is explicit and non-evasive. Direct quote: *"The depth threshold (>25% drawdown as the deep/shallow split) and the eight grid configs below were selected by examining the same 47,182-fire panel used in the diagnostic. This is not pretend-prospective pre-registration. It is genuine post-diagnostic registration."* The provenance is stated as **derived-from-this-panel** — exactly the standard demanded. Reinforced in §0 (`:32`), the §10.9 verbatim-in-results requirement (`:326`), and the §8 evidence_source field (`:282`). No weasel.

### CHECK 3 — Double-dip protections real → **PASS (with BLOCKING carve-out on both-halves; see Check 4/5)**

Four protections declared and binding (`:104-118`):
1. **Calibrated permutation inference** — episode-label-permutation, N_PERM=5,000, Phipson-Smyth +1, two-sided, reused verbatim from `run_P1_3_v2.py`; parametric p secondary. Real.
2. **Both calibration controls before the grid** — negative (rej ≤0.12, KS-p ≥0.05) + positive (+0.05 injection, perm_p≪0.05), grid INVALID if either fails (`:108-110`, §7). Mirrors the reprobe's passing controls (rej=0.085, KS-p=0.458, pos perm_p=2.0e-4). Real.
3. **Both-halves sign stability** — present as a gate (`:112`, §5.2) **but its executable definition is under-specified and its diagnostic-side implementation is bugged** → see BLOCKING-1 and BLOCKING-2 under Check 5.
4. **Shadow-only authorization** — a pass authorizes SHADOW rung only; forward ledger + CN/HK/CA passports are the only true OOS (`:116`, §8 flip criterion, §9). Real.

The architecture is real. The one protection whose *implementation* is compromised is #3, and it is the protection that most directly guards against the in-sample selection — hence BLOCKING.

### CHECK 4 — Power floors backed by the diagnostic's actual cell ns → **PASS (recompute exact)**

Independent recompute from `P2_5_DIAGNOSTIC/results.json` (baselines 21d=0.38481, 63d=0.62314):

| Config | Cell | PREREG n_fires / n_ep / 63d Δ | Recomputed n_fires / n_ep / 63d Δ | Match |
|---|---|---|---|---|
| C6 deep-trio | `partition_d.deep_washout_ac_pass_rs_fav` | 11,371 / 4,946 / −3.30 | 11,371 / 4,946 / **−3.30** | ✓ exact |
| C2 d40plus | `partition_a.d40plus` | 5,698 / 2,503 / −3.57 | 5,698 / 2,503 / **−3.57** | ✓ exact |
| C3 below200 | `partition_b.washout_true_below_200` | 23,780 / 10,266 / −2.23 | 23,780 / 10,266 / **−2.23** | ✓ exact |
| C5 trio | `partition_d.washout_ac_pass_rs_fav` | 20,146 / 8,882 / −1.10 | 20,146 / 8,882 / **−1.10** | ✓ exact |
| C1 (est) | `d25_40 ∪ d40plus` fire-count | 20,408 | 14,710+5,698 = **20,408** | ✓ exact |

All four adequately-powered cells (and the C1 fire-count estimate) reproduce to the penny. All exceed the 25-cluster floor by 2+ orders of magnitude. Power floors are genuine.

**ADVISORY 4a (C1 delta label):** The PREREG labels C1's 63d Δ as "−2.34 (d25_40 + d40plus combined)" (`:138`). A fire-weighted blend of the two component cells gives **−1.92pp**, not −2.34pp. The −2.34 is not reconstructable from the cells; it is a directional annotation, not a run input (the actual C1 trial computes its own delta at run time), so it does not affect any decision — but the parenthetical is imprecise and should be marked as an estimate or corrected.

### CHECK 5 — Both-halves sign stability: BLOCKING defects

**BLOCKING-1 (tainted config-selection rationale via a diagnostic bug).**
The diagnostic's `sign_consistent()` (`run_P2_5_diagnostic.py:455-470`) computes 63d sign-consistency by testing **both halves' 63d stop-out rate against `baseline_21["stop_out"]` (0.3848)** — the 21-day baseline — instead of the 63d baseline (0.6231). Every 63d cell's stop-out rate (~0.53–0.66) sits above 0.3848 in both halves, so `sc63` is `True` almost tautologically. Recompute against the correct 63d baseline:

| Cell | H1 63d stop | H2 63d stop | diag `sc63` (vs .3848) | corrected `sc63` (vs .6231) |
|---|---|---|---|---|
| C6 deep-trio | 0.5411 | 0.6321 | True | **False** (H1 −8.2pp fav, H2 +0.9pp unfav) |
| C5 trio | 0.5555 | 0.6634 | True | **False** (H1 −6.8pp, H2 +4.0pp) |
| C3 below200 | 0.5416 | 0.6561 | True | **False** (H1 −8.2pp, H2 +3.3pp) |
| proxy_equiv | 0.5287 | 0.6523 | True | **False** (H1 −9.4pp, H2 +2.9pp) |
| **C2 d40plus** | 0.5928 | 0.5824 | True | **True** (H1 −3.0pp, H2 −4.1pp — both favorable) |

Only **C2 (d40plus)** is genuinely 63d sign-stable. The diagnostic RESULTS.md ranking (`:201-202`) and its narrative ("deep-trio... sign-consistent 63d (Y)", `:214`) propagate the bugged `sc63=Y`. The PREREG's §3 config-selection rationale (`:126`) cites the diagnostic ranking as a selection criterion. **The rationale therefore imports a false half-stability claim for C3/C5/C6** — the very configs it foregrounds (deep-trio is named the "largest favorable 63d delta").

This does not corrupt the *study* (the PREREG recomputes sign stability fresh in §5.2 and will kill unstable configs when the grid runs — provided §5.2 is fixed per BLOCKING-2). It corrupts the *narrative basis for selecting* C3/C5/C6, and it means the PREREG's own §0/§2 framing ("the deep-trio shows the largest favorable delta of any adequately-powered cell") is presented without the countervailing fact that that cell's effect lives entirely in H1 and vanishes/reverses in H2. **Required edit:** add a note in §2.1/§3 that the diagnostic's `sc63` column is computed against the wrong baseline and is not evidence of half-stability; state that under the correct 63d baseline only d40plus is 63d half-stable pre-registration; and frame C3/C5/C6 as *hypotheses whose half-stability is explicitly in doubt*, to be settled by the §5.2 gate.

**BLOCKING-2 (§5.2 baseline convention under-specified — will reproduce the bug if inherited).**
§5.2 (`:198-200`) defines sign stability as "Δ(H1) and Δ(H2) have the same sign" but never states **what baseline each half-delta is measured against**. The diagnostic runner is the reference implementation the PREREG's stat machinery inherits ("reuse verbatim", `:106`, `:193`), and that implementation uses a single full-population 21d baseline for both halves and both horizons — the source of BLOCKING-1. If the P2.5 runner inherits `cell_report`/`sign_consistent` verbatim, it will silently reproduce the 21d-baseline error and pass configs that are not half-stable.

Note also that §5.2's stat is a *moved-up vs not-moved-up* contrast (RW Mode-B, `:191`), which is baseline-free by construction (the sign is the sign of the within-day two-group difference, not a cell-vs-baseline delta). If the runner uses the moved-up/not-moved-up Δ per half, the bug cannot occur — but that is not stated. **Required edit:** §5.2 must pin the half-delta convention explicitly — either "Δ per half = stop_out(moved_up) − stop_out(not_moved_up) computed within that half, no external baseline" (preferred, matches §5.1's primary statistic) OR "per-half delta vs that half's own horizon-matched baseline." Silence here is what let the diagnostic ship a mechanically-true `sc63`.

### CHECK 5 (kill criteria) — total and irreversible as written → **PASS**

§6.2 (`:228-234`) is total and irreversible: *"If no config (C1–C8) produces a favorable-direction, BH-surviving, sign-stable stop-out effect at either horizon, the washout-as-rank-input line is CLOSED program-wide."* Binds the boolean AND all depth/interaction cuts; requires a new PREREG *starting from new data* (e.g., a cross-market passport) to reopen; explicitly denies dead-money-only rescue (`:114`); explicitly exempts F2 (not washout-sourced). §9 routing (`:305-309`) closes any opened shadow entries as `falsified`. This is a genuine pre-committed kill, not an escape hatch. (Its bite depends on §5.2 being correct — see BLOCKING-2 — because a mis-computed sign-stability could *falsely spare* a config from the kill.)

### CHECK 6 — Dead-money-survival clause in ship-qualifying → **PASS**

§5.3 (`:202-204`) + §6.3 item 4 (`:242`): a config that passes stop-out BH + sign-stability must ALSO show dead-money Δ ≤ 0 at the surviving horizon in the same cell, else it "cannot promote — it has traded one harm for another." This directly guards against reversing the reprobe's T02 (−15.11pp dead-money) benefit. Present and load-bearing. Recompute confirms the candidate cells carry favorable 63d dead-money (deep-trio dm63 −0.085pp, d40plus −0.032pp) — near zero at 63d because dead-money is a 21d phenomenon (63d baseline dead-money is 0.08%), so the *binding* dead-money check is effectively the 21d co-benefit. **ADVISORY 6a:** §5.3 checks dead-money "at the same horizon"; at 63d the dead-money rate is ~0 for all cells so the check is vacuous at 63d — the meaningful dead-money protection is the 21d value (deep-trio −8.84pp, favorable). Recommend §5.3 specify the 21d dead-money as the binding co-benefit (or check both horizons) so the clause is not vacuously satisfied by a ~0 63d rate.

### CHECK 7 — No config sneaks a hard-gate mode → **PASS**

Scanned §3/§4/§6. Every config is an additive +0.10 rank-weight tilt on `blend_sorted` (`:128-132`); "RW mode does not remove fires from the board (R7 additive-lanes law)" (`:215`); `gate_fire_rate_impact_pct = 0.0` for all configs by construction; R4 restated ("hard-gate paths stay closed per P1.3 §6.2", `:13`, `:337`). No config carries a filter/block/exclude semantic. Clean.

### CHECK 8 — Diagnostic labeled non-verdict everywhere cited → **PASS**

The diagnostic is labeled IN-SAMPLE / sealed / non-verdict at every citation: §0 plain-English (`:24-32`), provenance line (`:9`), §2 header (`:70`), §2.1 header "sealed, not verdicts" (`:72`) + "labelled IN-SAMPLE throughout" (`:74`), §8 evidence_source "(in-sample)" (`:282`), §10.9 verbatim honesty statement (`:326`), §10.10 "sealed prior-study numbers, not re-run here" (`:327`). The diagnostic RESULTS.md itself is labeled "DIAGNOSTIC — IN-SAMPLE, NO VERDICTS" throughout. Consistent and correct.

---

## ADVISORY FINDINGS (non-blocking citation/provenance drift)

- **ADVISORY A (63d baseline citation mismatch).** The PREREG cites the unconditioned 63d stop-out baseline as **62.67%** (§0 `:26`, §2.1 `:76`), but the diagnostic results.json records it as **62.314%**. The 62.67% figure appears nowhere in the JSON as the 63d baseline (it is close to the washout=True 21d... no — it is unsourced). The diagnostic RESULTS.md table (`:42`) also prints 62.67%. The deltas reproduce because they were internally computed against 62.31%, so this is a display-citation error, not a computation error — but the PREREG's stated baseline is wrong by 0.36pp and should be corrected to 62.31% (or the source of 62.67% identified).

- **ADVISORY B (episode-count citation).** PREREG §1 (`:38`) and the diagnostic table (`:42`) reference the unconditioned episode count as ~20,703, while results.json records **21,053** episodes for the unconditioned defined population. Minor; does not affect any n-floor decision (all cells clear 25 by huge margins). Reconcile the cited figure.

- **ADVISORY C (diagnostic MD5 typo — upstream).** The diagnostic RESULTS.md header (`P2_5_DIAGNOSTIC/RESULTS.md:8`) prints replay MD5 `...56215d3`; the correct value (in results.json, `replay_md5_matches=True`, and the reprobe artifact) is `...56265d3`. The PREREG itself cites the correct `...56265d3` (`:10`). This is a typo confined to the upstream diagnostic markdown, not the PREREG — flagged so the cited-document error is on record. Fix in the diagnostic doc.

- **ADVISORY D (C1 63d Δ label −2.34 vs −1.92).** See Check 4 ADVISORY 4a — imprecise parenthetical, not a run input.

- **ADVISORY E (§5.3 63d dead-money check is vacuous).** See Check 6 ADVISORY 6a — pin the binding dead-money co-benefit to 21d.

- **ADVISORY F (grid at ceiling with 2 estimated slots).** See Check 1 ADVISORY 1a — C7/C8 consume 4 family DoF on directional guesses; acceptable under the thin-check rule but worth Fable's eye.

---

## REQUIRED EDITS (to move APPROVE-WITH-EDITS → clean)

1. **[BLOCKING-1]** In §2.1/§3: annotate that the diagnostic's `sc63` column is computed against the 21d baseline (a bug in `sign_consistent()`, `run_P2_5_diagnostic.py:470`) and is NOT evidence of half-stability. State that, recomputed against the 63d baseline, only C2/d40plus is 63d sign-stable pre-registration; frame C3/C5/C6 half-stability as explicitly-in-doubt hypotheses to be settled by §5.2. Remove any language implying the deep-trio is already sign-consistent at 63d.

2. **[BLOCKING-2]** In §5.2: pin the half-delta convention explicitly. Preferred: "per-half Δ = stop_out(moved_up) − stop_out(not_moved_up) computed within that half, no external baseline" (matches §5.1). This forecloses inheriting the diagnostic's 21d-baseline bug. Add a run-preamble assertion that the sign-stability baseline is horizon-matched (or baseline-free).

3. **[ADVISORY, recommended]** Correct the 62.67% → 62.31% baseline citation (§0, §2.1); reconcile the 20,703 → 21,053 episode figure; mark C1's −2.34 as an estimate; pin §5.3 dead-money co-benefit to 21d; fix the diagnostic RESULTS.md MD5 typo.

---

## BOTTOM LINE

The PREREG's multiplicity and honesty scaffolding is genuinely strong — capped grid, exact m, one BH family, real permutation calibration, a program-wide irreversible kill, a dead-money-survival gate, shadow-only authorization, and a candid in-sample clause that names its own selection sin. The recomputed power floors are exact. The single structural weakness is that its most important double-dip guard — both-halves sign stability — inherits a wrong-baseline implementation from the diagnostic that renders `sc63` mechanically true, and the config-selection rationale leans on that false signal. Fixing the two text/convention edits above converts a study whose sign-stability gate could rubber-stamp H1-only effects into one where the gate actually bites (and, on the corrected numbers, would kill C3/C5/C6 at 63d while sparing only d40plus — a materially different and more honest study). **APPROVE-WITH-EDITS.**

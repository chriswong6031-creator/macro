# P2 Cross-Doc Red-Team — Entry Intelligence Phase-2 Battery

**Reviewer:** Opus red-team subagent under Fable orchestration
**Date:** 2026-07-05
**Docs reviewed:**
1. `research/entry_intel/P2_1A_ANTICHASE_GATE_PREREG.md` (F3 anti-chase hard gate)
2. `research/entry_intel/P2_1B_RANKWEIGHT_PREREG.md` (F1/F2 rank-weight)
3. `research/entry_intel/P2_4_BOARD_CONTRACT_V2_DESIGN.md` (board contract v2)
4. `research/entry_intel/P1_2B_TAXONOMY_EXTENSION_SPEC.md` (taxonomy re-tag + mini-PREREG)
5. `research/entry_intel/P3_KERNEL_RANK_PREREG.md` (kernel-rank shadow)

**Evidence base verified against:** `p1_runs/P1_3/RESULTS.md` + `results.json` + `REVIEW_v2.md`; `p1_runs/p1_5_continuation/RESULTS.md`; `p1_runs/P1_1_SEPARABILITY/RESULTS.md` + `REVIEW.md`; `p1_runs/P1_2/RESULTS.md`. Constitution: `ENTRY_INTELLIGENCE_MASTERPLAN_BY_FABLE.md` (R1–R10, §6), `P0_MEASUREMENT_MEMO.md v1.0 + §6 v1.1`, `SETUP_SPECIES_MASTERPLAN_BY_FABLE.md §1/§3.1/§6`.

---

## VERDICT SUMMARY

| Doc | Verdict | Blocking | Advisory |
|---|---|---|---|
| P2.1a Anti-Chase gate | **APPROVE-WITH-EDITS** | 2 | 3 |
| P2.1b Rank-Weight | **APPROVE-WITH-EDITS** | 2 | 3 |
| P2.4 Board Contract v2 | **APPROVE-WITH-EDITS** | 1 | 3 |
| P1.2b Taxonomy Extension | **APPROVE-WITH-EDITS** | 1 | 2 |
| P3 Kernel-Rank | **APPROVE-WITH-EDITS** | 2 | 2 |
| **Cross-doc** | — | 2 | 2 |

No doc is a REWRITE; every number spot-checked matched the P1 artifacts exactly (details per doc). Every doc that touches `board_ordering` ships shadow-first with a pre-registered flip criterion (Article 2 satisfied). The blocking findings are all mechanical: naming errors, a fabricated citation for the C1 n-floor, and two under-specified shared dependencies. All are fixable with the edits below without re-running any study.

---

## CROSS-DOC FINDINGS (read first — these bind ≥2 documents)

### X-BLOCKING-1 — P2.1b names the F3 doc "P2.1c"; the F3 doc is "P2.1a". Broken cross-reference.

- `P2_1B_RANKWEIGHT_PREREG.md` §2 (L85): *"F3 (anti-chase, ext_z ≤ 2.0) — F3 ships as a hard gate under a separate PREREG (**P2.1c**, to be registered)."*
- The F3 PREREG exists and is titled **P2.1a** (`P2_1A_ANTICHASE_GATE_PREREG.md` L1/L5). It is not "to be registered" — it is in this same batch, DRAFT-pending-approval.
- **Mechanical edit (P2.1b §2, L85):** replace `a separate PREREG (P2.1c, to be registered)` with `a separate PREREG (P2.1a — P2_1A_ANTICHASE_GATE_PREREG.md, registered 2026-07-05)`.
- Same fix if any other `P2.1c` token exists (grep confirmed the only occurrence is L85).

### X-BLOCKING-2 — F1 washout PROXY→production concordance clause is present in BOTH P2.1b and P3, but the two are NOT operationally consistent. P3 defers to a clause it never binds to.

Task check (3) requires the concordance clause present in both docs AND consistent.

- **P2.1b defines it concretely** (§3.3): concordance = fraction of overlapping names where `replay washout_proximity == production COILED state` at signal date; **floor = 90%**; on fail → shadow does not ship, reprobe `P2_1B_F1_REPROBE_T01–T10`. Artifact: `research/entry_intel/p1_runs/P1_3/concordance_check.json`, GO/REPROBE verdict. A missing/REPROBE artifact raises `ConcordanceGateError` (§10.2).
- **P3 only gestures at it** (§2.1, L95; §1 table L48): cohort_washout cells are *"eligible for the kernel-rank computation only if a production-source equivalent is confirmed before the shadow column is written to any board output (**same requirement as P2.1b for this feature**)."* P3 never (a) restates the 90% floor, (b) states it reads P2.1b's `concordance_check.json`, or (c) defines what "confirmed" means on its own. If P3 executes before P2.1b's concordance gate has run — or interprets "confirmed" more loosely — the two docs apply *different* production-source bars to the *same* proxy feature, which is exactly the inconsistency this check exists to catch.
- **Second-order divergence:** P2.1b's concordance test is computed on the **overlapping names between the replay artifact and the current production board snapshot**; P3's cohort_washout cells are built on **all 49,939 verdict-grade replay fires**. If concordance passes at 90% on the overlap but the non-overlap replay tail (the bulk of the 49,939) has worse proxy fidelity, P3 imports proxy error that P2.1b's gate never measured. P3's fallback (omit the dimension, re-normalize to 0.86) is sound *if triggered*, but nothing wires the P2.1b REPROBE_REQUIRED verdict into P3's build to trigger it.
- **Mechanical edits:**
  - **P3 §2.1 (after L95):** add a binding sentence: *"'Confirmed' means the P2.1b concordance gate (`P2_1B_RANKWEIGHT_PREREG.md` §3.3) has run and returned GO (≥90% on overlapping names) — P3 reads `research/entry_intel/p1_runs/P1_3/concordance_check.json` at build time; a missing artifact or a REPROBE_REQUIRED verdict forces the omit-and-renormalize fallback (weights 0.34+0.28+0.24=0.86). P3 does not define an independent concordance bar."*
  - **P3 §7 trial ledger + §5 conformance checklist:** add a row/checkbox: *"cohort_washout inclusion requires P2.1b concordance GO artifact; else omitted (logged)."*
  - **P2.1b §3.3 (after L120):** add: *"Downstream consumers of the washout dimension (P3 kernel-rank) inherit this GO/REPROBE verdict via `concordance_check.json`; no consumer may apply a weaker production-source bar."*

### X-ADVISORY-1 — Two era-window strings coexist across the battery; both are correct to their source but the docs should say why they differ.

- P1.3-derived numbers (P2.1a, P2.1b, P2.4 Effect-3, P3 §1.3) use **2022-06-30 → 2025-12-29** (P1.3 last-graded fire ceiling).
- P1.1-derived numbers (P3 §1 feature survivors) use **2022-06-30 → 2026-07-02** (P1.1 data boundary).
- P1.5-derived numbers (P2.4 Effect-1/2) use **2022-06-30 → 2025-12-29** (RESULTS L111) though its preamble L46 states the boundary as 2026-07-02.
- All are faithfully transcribed. Non-blocking, but P3 §1 mixes both windows one paragraph apart (L43 vs L55/L65) without noting that the 2025-12-29 ceiling is the *fire-grading* ceiling and 2026-07-02 is the *pre-gate-pool* ceiling. **Edit (P3 §1):** one clause noting the two ceilings come from different populations (fires vs pre-gate pool) and both are memo-conformant.

### X-ADVISORY-2 — "22/30" disavowal is present and correct in all five docs; the positive framing is inconsistently worded.

Check (4) — no doc affirmatively cites 22/30 as a survival count (grep confirmed: every occurrence is a disavowal). Good. But the replacement headline varies: P2.1a §1.1 says *"~3 independent forward-return effects (approximately 10 independent continuous forward-return tests)"*; P2.1b §Constitutional-gates says *"~3 independent forward-return effects per factor (10 independent forward-return tests total)"* — "per factor" is imprecise (there are ~3 effects total across three factors, and ~3 sub-effects cited per factor). This is cosmetic; REVIEW_v2.md ADVISORY-2 says "~3 independent factor effects (10 independent forward-return tests)". **Edit (P2.1b L16):** drop "per factor" or change to "~3 independent factor effects (≈10 independent forward-return tests across the grid)".

---

## P2.1a — ANTI-CHASE HARD GATE

**Verdict: APPROVE-WITH-EDITS.** Shadow-first + flip criteria present and executable (§2.1–2.2); R7 additive-lanes honored ("Anti-Chase Watch" lane, §3.3); precedence with `extension_demote` specified without double-counting (§3.2); kill/rollback present (§5). Two blocking items: a fabricated citation propping up the C1 n-floor, and a rollback-metric mismatch.

**Number spot-check (≥3) — all EXACT vs `p1_runs/P1_3`:**
- T21 stop-out Δ=−0.43pp, BH-adj p=0.0060, sign-stable (H1 −0.87 / H2 −0.55) — matches RESULTS L121/L177 & results.json. ✓
- T22 dead-money Δ=−3.63pp, BH-adj p=0.0060 — matches RESULTS L122. ✓
- T24 63d stop-out Δ=−5.00pp, BH-adj p=0.0933, sign-stable (H1 −8.75 / H2 −1.55) — matches RESULTS L124/L180. ✓
- n_would_block=2,299; n_clusters_would_block=1,270; fire-rate impact 4.6% (2,299/49,939) — matches RESULTS L83/L142. ✓
- T23 context Δ=−0.97pp — matches RESULTS L123. ✓

### BLOCKING

**P2.1a-B1 — The C1 flip n-floor (1,270) rests on a fabricated masterplan citation and is not a power-derived floor.**
§2.2/C1 (L117–123) sets the shadow-ledger flip floor at **≥1,270 episode clusters** and justifies it as *"the species ladder's gate_weight rung floor for this species, per the EI masterplan §6/P2.1 definition ('episode-clustered n floor ≥ the species ladder's gate_weight rung floor')."* The quoted phrase **does not exist** in the masterplan — §6/P2.1 says only *"Promote P1.3 survivors via the ladder … ships shadow-first"* (verified: grep for "gate_weight rung floor" returns zero hits in both constitutions). The 1,270 figure is simply the *backtest's own would-block cluster count* (RESULTS L83) re-purposed as the prospective accrual target. Requiring the live ledger to reproduce the backtest's cluster count is not a statistical power argument; it conflates "how many clusters the historical gate touched" with "how many clusters are needed to confirm the effect prospectively." At ~5% board coverage this also implies a 6–18 month (§4.1 `maturation`) accrual with no stated power basis.
- **Mechanical edit:** (a) delete the fabricated quotation and its "per the EI masterplan §6/P2.1 definition" attribution; (b) either derive the floor from a power calculation for the C2 Wilson-lower-bound-on-stop-out-improvement test at the observed effect size (Δ≈0.43–5.0pp) — mirroring P3 §5.2's Fisher-z power derivation — or state explicitly that 1,270 is a *conservative floor chosen to match backtest coverage, not a power-derived minimum*, and cross-reference the actual constitution basis (SETUP_SPECIES_MASTERPLAN §1.3 flip-criteria template + episode-clustered n floors). Keep the ≥25-cluster constitutional minimum as the hard floor; justify anything above it.

**P2.1a-B2 — Rollback RB1 metric is not the same statistic as the flip criterion C2, so the gate can flip on one bound and roll back on its complement without a real regime change.**
Flip C2 (§2.2, L125–132) requires the Wilson **lower** bound on `stop_out_rate_blocked − stop_out_rate_unblocked` > 0 (blocked pool has *higher* stop-out — the good direction for a gate). Rollback RB1 (§5, L303–307) fires when the Wilson **upper** bound of the *improvement* < 0 on a fresh 200-cluster cohort. These are two different signed quantities described with two different bound-sides and two different sign conventions ("stop-out improvement" in RB1 vs "stop-out improvement (blocked > unblocked)" in C2). As written it is not verifiable that RB1 is the exact logical complement of C2, and the §6 acceptance criterion introduces yet a *third* framing (63d matched-unblocked, Wilson lower bound > 0). A reader cannot confirm the three gates are consistent.
- **Mechanical edit:** define one signed quantity once — e.g. `D = stop_out_rate(blocked) − stop_out_rate(unblocked)`, favorable = D>0 — and express C2 (flip), RB1 (rollback), and §6 (retention) all as bounds on that single `D` at a single stated horizon. State the horizon for each explicitly (C2 currently omits a horizon; §6 uses 63d; RB1 is horizon-silent). Recommend all three key off 63d, where the effect is largest (T24, −5.00pp).

### ADVISORY

**P2.1a-A1 — `p1_3_trials` registry field lists `T25_context_only` (§4.1, L276) but §1.1 promotes on T21/T22/T24.** T25 (63d dead-money, Δ=+0.09pp, unfavorable) is context, not a promotion trial; listing it in `trial_count: 4` / `p1_3_trials` alongside the three basis trials muddies the trial-ledger bookkeeping. Recommend `p1_3_trials: [T21, T22, T24]`, `trial_count: 3`, and move T25 to an explicit `context_trials` field.

**P2.1a-A2 — Fixture "NVDA_persistent_leader" (§4.1, L259) asserts NVDA reads ext_z<2 in "normal strong-trend periods" — this is an untested behavioral claim in a regression fixture.** The own-history z-scoring rationale is sound, but no artifact confirms NVDA's ext_z distribution. Recommend re-phrasing the fixture expectation as a computable assertion ("NVDA ext_z computed from engine/extension.py L92 on its own 252-bar history; fixture passes iff the specific dated snapshot yields ext_z<2") rather than a general claim, or flag it UNVERIFIED.

**P2.1a-A3 — RB3 recall trigger (§5, L313–316) references "durable-60D outcome rate" and the P1.4 recall audit; confirm the metric name matches P1.4's actual output.** P1.4 exists (`p1_runs/P1_4/`) but this red-team did not verify P1.4 emits a per-rejection-reason "durable-60D outcome rate" for blocked-by-F3 names. Recommend P2.1a cite the exact P1.4 column/metric it will read, or mark the dependency as "pending P1.4 schema confirmation."

---

## P2.1b — RANK-WEIGHT (F1 + F2)

**Verdict: APPROVE-WITH-EDITS.** Shadow-first + flip criteria present and executable (§5–6); R7 satisfied by construction (rank weight, `gate_fire_rate_impact_pct=0.0`, §9); the F1 PROXY→production concordance clause is the doc's strongest section (§3, genuinely binding with a fail path). Two blocking items: the P2.1c naming error (X-BLOCKING-1) and a flip-criterion inequality that is stated backwards in prose.

**Number spot-check (≥3) — all EXACT vs `p1_runs/P1_3`:**
- F1 T02 dead-money Δ=−13.19pp, perm_p=0.0002, BH-adj=0.0006, r=−0.1247, H1 −14.00 / H2 −12.29 — matches RESULTS L102/L158 & results.json. ✓
- F1 T09 RW 63d stop-out Δ=−4.55pp, BH-adj=0.0006, H1 −7.81 / H2 −0.78 — matches RESULTS L109/L165. ✓
- F1 gate-reject 54.0% (26,974/49,939 would-block) — matches RESULTS L140. ✓
- F2 T18 21d cushioned Δ=+0.15pp, BH-adj=0.0933; T20 63d cushioned Δ=+0.68pp, BH-adj=0.0752 — matches RESULTS L118/L120. ✓
- F2 T19 sign-flip H1 −1.02 / H2 +0.66 (correctly flagged NOT-ship) — matches RESULTS L175. ✓
- F2 HG 48.5% (22,378/46,111 on F2-valid) — matches RESULTS L141. ✓
- tier_frac=0.0238 — matches RESULTS L85. ✓

### BLOCKING

**P2.1b-B1 — (= X-BLOCKING-1) F3 doc mis-named "P2.1c".** See cross-doc section. Edit L85.

**P2.1b-B2 — The §6.2 flip inequality and its plain-English gloss describe opposite directions; as written the criterion is unfalsifiable.**
§6.2 (L212–214) states the flip requires:
`Wilson_lower(stop-out rate, bonus-cell) < Wilson_upper(stop-out rate, non-bonus-cell)`
then glosses it (L216) as *"the bonus cohort's stop-out is credibly lower than the non-bonus cohort's."* But `lower(A) < upper(B)` is an extremely weak condition — it holds even when A's stop-out is *higher* than B's, as long as the confidence intervals are wide enough to touch. The condition that actually encodes "bonus-cell stop-out credibly lower" is the reverse: `Wilson_upper(bonus-cell) < Wilson_lower(non-bonus-cell)` (the bonus interval sits entirely below the non-bonus interval), or a Wilson bound on the *difference* < 0. The reversal criterion §6.6 (L240) has the same structural problem mirrored. The prose intent is correct; the inequality is inverted.
- **Mechanical edit (§6.2, L212–216):** replace with a bound on the signed difference, matching the P2.1a fix: define `D_f = stop_out(bonus-cell) − stop_out(non-bonus-cell)`, favorable = D_f<0; flip requires `Wilson_upper(D_f) < 0` at both 21d and 63d (episode-clustered). Rewrite §6.6 as `Wilson_lower(D_f) > 0` (credibly worse). Delete the current `lower(A)<upper(B)` construction entirely.

### ADVISORY

**P2.1b-A1 — F1's ship basis leans on 63d, but the 21d leg is adverse (T07 stop-out +2.58pp) and §6.2 requires BOTH horizons to pass the flip.** RESULTS T07 shows RW 21d stop-out +2.58pp (unfavorable, sign-stable). §6.2 (L218) mandates both 21d and 63d pass. The 21d stop-out leg is *adverse* in the backtest, so a faithful shadow ledger will likely *fail* the 21d flip gate for F1 by construction — the flip may never fire even if the effect is real at 63d. This is arguably correct conservatism, but the doc should state it: F1's known-adverse 21d stop-out means the "both horizons" rule is effectively a 63d-only gate that F1 can only pass if the live 21d stop-out is *less adverse* than backtest. Recommend §6.2 add a sentence acknowledging the 21d leg is the binding constraint for F1 and that failure there is an expected, not anomalous, outcome.

**P2.1b-A2 — `blend_sorted_shadow` range and re-percentile-rank (§4.3) is internally slightly contradictory.** L158 says values are in [0.0, 1.20]; L160 then re-percentile-ranks within day to keep 0..1 "prevents the shadow column from exceeding 1.0 visually." If the column is re-percentiled, the [0.0,1.20] range never materializes in the stored/displayed column — only in the intermediate. Harmless, but recommend stating the [0.0,1.20] is pre-normalization intermediate and the emitted column is 0..1.

**P2.1b-A3 — Species registry `trial_count` for F1 (§7.1, L307) = 3 lists "T07, T09 (ship-qualifying RW); T02 (HG dead-money context)" but the concordance reprobe (§3.3) references T07/T08/T09/T10 as the RW reprobe set.** Minor inconsistency in which F1 RW trials are "ship-qualifying" (T07+T09) vs the reprobe grid (T07–T10). Not wrong — reprobe covers the fuller grid — but recommend a one-line note that the reprobe grid (T01–T10) is broader than the two ship-qualifying trials by design.

---

## P2.4 — BOARD CONTRACT v2

**Verdict: APPROVE-WITH-EDITS.** Correctly ranking-neutral — §3.3 and §5 draw an explicit, exhaustive P3 boundary (no `_combine_key`/`_asort`/`_atier`/admission change; `rank_by` stays "bottoming-alignment"); this is the cleanest boundary-with-P3 in the battery (Check 6 PASS). R7 honored via AC-1 byte-diff harness (§6). Not a PREREG, correctly self-declared (§7). One blocking item: an internal align_tier vocabulary inconsistency that makes the lane-assignment code un-runnable as written.

**Number spot-check (≥3) — all EXACT vs P1 artifacts:**
- Effect-1 ARMED-cont vs PRIME P(clean8_21) 30.65% vs 33.44%, Δ=−2.79pp, BH q(T1)=0.1225, H1 −1.46 / H2 −5.39, 410/642=63.9% — matches `p1_5_continuation/RESULTS.md` L61/L64/L68/L69. ✓
- Effect-1 n: ARMED-cont 1,752 fires / 1,322 clusters; PRIME 5,448 / 3,846 — matches RESULTS L61/L62/L136/L137. ✓
- Effect-2 T4 above_200=True 24.72% (n=890) vs False 36.77% (n=862), Δ=−12.06pp, BH q=0.0000 — matches RESULTS L92. ✓
- Effect-3 T21 Δ=−0.43pp perm_p=0.0026 BH=0.0060 r=−0.0612; T22 −3.63pp; T24 −5.00pp perm_p=0.0648 BH=0.0933; 4.6% (2,299/49,939) — matches P1.3 RESULTS/results.json. ✓

### BLOCKING

**P2.4-B1 — The lane-assignment code (§4.1 Step B) keys on `align_tier == "PRIME"/"ARMED"`, but §2's current-state table (L70) documents `us_standouts.json` emitting align_tier as `"aligned"/"near"`, and §3.1's lane table (L87) references both "PRIME" and "aligned" as bottoming sources. The value vocabulary is not pinned, so `_lane_for()` may match nothing.**
The P1.5 study and the masterplan both use literal align_tier values `PRIME/ARMED/APPROACHING` (confirmed: `p1_5_continuation/RESULTS.md` L19/L61; masterplan §1 L28). But P2.4 §2 (L70) states the live `us_standouts.json` align_tier column emits `"aligned"/"near"`. §3.1 row 1 (L87) then hedges: bottoming admits `align_tier == "PRIME"` **OR** `align_tier == "aligned" and weekly phase bottoming`. The Step-B code (L144–150) only tests `"PRIME"`/`"ARMED"`. If the production column actually carries `"aligned"/"near"` (the replay/board emission), `_lane_for()` returns `"bottoming"` for **every** row (the fall-through default), AC-3 (ARMED→continuation) silently never fires, and AC-2's lane-assignment-bug flag trips. AC-7 (weekly_phase present) would pass while lanes are all-bottoming — the build looks healthy but the core relabel is dead.
- **Mechanical edit:** (a) resolve the vocabulary empirically before build — grep the live `us_standouts.json` and the board builder for the exact align_tier value set; (b) pin one vocabulary in §3.1/§4.1 and map it explicitly (if the board emits `"aligned"/"near"`, the code must map `aligned`→PRIME-equivalent and the continuation test must key off whatever value ARMED-continuation rows actually carry — note P1.5 found ARMED rows exist in the *replay* `align_tier` but the *shipped board* column may differ); (c) make AC-3's protocol (L299) assert on the *actual* production value, and add a pre-build assertion that the align_tier value set is non-empty and matches the pinned vocabulary, else block (not fail) per the AC-7 pattern.

### ADVISORY

**P2.4-A1 — `_lane_for` folds APPROACHING and unknown-weekly-phase ARMED into "bottoming" (§4.1 L148–150); this is a silent semantic merge that AC-2/AC-3 do not police.** An ARMED fire with `weekly_phase != "rising"` (or null) lands in "bottoming," not "continuation" or "watch." P1.5 RESULTS L144 notes *every* ARMED fire in the replay carries `weekly_phase=='rising'` (n=0 non-rising ARMED), so today this branch is empty — but if the live board ever emits a non-rising ARMED fire, it is silently mislabeled bottoming. Recommend a `lane_counts`-adjacent monitor: log any `align_tier==ARMED and weekly_phase!=rising` count; if >0, flag for review (the P1.5 invariant would have broken).

**P2.4-A2 — Effect-2 T4 is imported as a display context field, but the doc must guard against it being read as a rank signal downstream.** §1 Effect-2 and the `200DMA−` badge (§4.2, L224) surface the +12pp T4 below-200DMA outperformance. This is correctly labeled "T4 context … does not override the T1 verdict" (L229). But P2.4 §9 routes `above_trend` to P3.1 as a stratification feature. Flag explicitly that T4's +12pp is a *sub-partition diagnostic* (BH within the P1.5 m=5 family, not a standalone validated lever) so P3.1 does not treat `above_trend` as a P1.1-survivor-equivalent. (P1.1 did test `side_200dma` and found it NO-SIGNAL/INVERTED — RESULTS L80–81 — which is the opposite sign context worth citing here.)

**P2.4-A3 — `setups.json` lane backfill default (§4.1 Step F, L192) assigns `"bottoming"` to any setups row not on the standout board.** A setups-desk name absent from the bottoming-aligned board defaulting to lane "bottoming" is a mislabel (it may be an alpha-ranked continuation or watch name). Recommend defaulting to `"watch"` or a distinct `"setups_only"` value rather than "bottoming," since "bottoming" is a positive structural claim the row has not earned.

---

## P1.2b — TAXONOMY EXTENSION

**Verdict: APPROVE-WITH-EDITS.** The surgical re-tag's byte-identity validation is present and executable (§2.3 Gate V1 fire-set byte-identity, V2 near-miss count conservation, V3 coverage plausibility) — Check (7) PASS in structure. BH family disjointness is correct and explicit: `ei_gate_pnl_p12b` m=16, NOT merged with original `ei_gate_pnl` m=72 (§3, §3.3, AC-4) — Check (4) PASS. R7 additive-lanes is respected (re-tag reclassifies labels, removes nothing). One blocking item: the byte-identity guard has a gap on the `near_miss` partition.

**Number spot-check (≥3) — all EXACT vs `p1_runs/P1_2/RESULTS.md`:**
- `not_topped_veto` 92,715; `board_rank_cutoff` 13,676; `extension_demote` 9,638; `knife_demote` 20,696; `sector_cap_displaced` 8,536 — matches P1.2 RESULTS L45–49 & P1.2b §1.1 table. ✓
- Substrate 961,656 rows — matches P1.2 RESULTS L7 & P1.2b L30. ✓
- Original BH family m=72 — matches P1.2 RESULTS L85. ✓
- P1.3-context effects (F1 T02 −13.19pp BH 0.0006; F3 T21 −0.43pp BH 0.0060, T24 −5.00pp BH 0.0933; F2 T18 BH 0.0933, T20 BH 0.0752) — all match P1.3 (§4 of P1.2b). ✓
- freshness_expired ~15,022 near-miss text hits; tier_cutoff ~131 rows — these are Opus-review figures cited as targets (§1.1); flagged UNVERIFIED below.

### BLOCKING

**P1.2b-B1 — Gate V2 (§2.3) only conserves the near_miss *count*; it does not prove the near_miss *set* is byte-identical. A re-tag bug that swaps one near_miss row for another (e.g., promotes a fire→near_miss while demoting a near_miss→rejection in the same pass) would conserve the count and pass V2 while corrupting the set.** Task check (7) requires the re-tag preserve fire AND near-miss sets byte-identical. V1 covers `fire` with a full `.equals()` on sorted rows. V2 (L131–136) only asserts `len(near_miss)==len(near_miss)`. §2.2 (L106) *claims* fire rows are never re-tagged and only null-rejection_reason near_miss/rejection rows are touched, but the validation does not *enforce* set-identity on near_miss the way V1 does for fire.
- **Mechanical edit (§2.3):** upgrade V2 to the V1 pattern — assert the `near_miss` row set (keyed by `ticker, signal_date`, excluding the `rejection_reason` column being re-tagged) is byte-identical between `replay_boarded` and `replay_boarded_p12b`. Since re-tag only writes `rejection_reason`, drop that column, sort, and `.equals()`. This closes the swap gap. Additionally assert the `verdict_type` column is byte-identical across the *whole* frame (guarantees no fire↔near_miss↔rejection migration anywhere).

### ADVISORY

**P1.2b-A1 — The freshness_expired (~15,022) and tier_cutoff (~131) target counts are Opus-review estimates, not artifact-verified; V3's plausibility ranges (1,000–30,000 / 50–400) and AC-1's ≥50 floor hinge on them.** §1.1 sources these from `REVIEW.md §D1`. If the reviewer's token-count was approximate, tier_cutoff at ~131 sitting between the n≥10 INCONCLUSIVE floor and n≥25 DEMOTE floor is fragile — a 50% miss (e.g. 65 rows) still clears AC-1's ≥50 but a larger miss blocks the run. This is correctly handled by AC-1's blocker-on-miss and AC-3's INCONCLUSIVE-is-honest, so it is advisory not blocking. Recommend the build's first step print the actual post-re-tag counts before any verdict computation, so a miss is caught at V3, not at trial time.

**P1.2b-A2 — §2.1 Change-2 `tier_cutoff` tagging keys on `verdict.get("tier_cascade") == "T4"` (L96), but the replay column is `tier_cascade` with values `T1/T2/T3` per P1.5's crosstab (RESULTS L30–35) — T4 may not appear in `tier_cascade` at all.** P1.5's align_tier×tier_cascade crosstab shows only T1/T2/T3 columns; the T4 semantic lives in the `gate_reason` free-text (`tier T4 (weight 0.4)`, per §1.1 L49), not necessarily in a `tier_cascade=="T4"` value. If the harness's `verdict` dict exposes T4 only in `gate_reason`, the L96 equality check finds nothing and V3 trips (tier_cutoff=0). Recommend the tagging predicate parse `gate_reason` for `tier T4` (matching how §1.1 found the ~131 rows) rather than assuming a `tier_cascade=="T4"` field exists, OR verify the harness verdict dict carries a distinct T4 tier value before relying on L96.

---

## P3 — KERNEL-RANK SHADOW

**Verdict: APPROVE-WITH-EDITS.** Shadow-first is airtight (§4.1: shadow column never reorders in v1, ledger + admin-only; §5 flip criterion with episode-clustered n floor 300, Wilson-lower-bound-on-difference > 0, perm p<0.10; §5.5 24-month kill criterion). R7 honored (§4.1 additional column). Boundary with P2.4 is respected from P3's side (§12 out-of-scope: no visible sort change, no gate change). Two blocking items: the shared-dependency under-specification (X-BLOCKING-2) and a feature-weight normalization that is mathematically mislabeled.

**Number spot-check (≥3) — all EXACT vs `p1_runs/P1_1` and `p1_runs/P1_3`:**
- P1.1 survivors: dist_52wh ρ_21d=−0.0845; cohort_washout +0.0773; ext_z −0.0707; ext_atr −0.0593; weekly_phase KW — matches `P1_1_SEPARABILITY/RESULTS.md` L141–145 survivor list. ✓
- P1.1 population 834,267 rows / 184 week clusters — matches RESULTS L30/L31 (Effective-N=184). ✓
- cohort_washout 100% proxy-sourced — matches `P1_1/REVIEW.md` A1 (L66). ✓
- washout NEAR/NOT_NEAR 22,965/26,974 — matches P1.3 RESULTS L81 (note sign: NEAR=True). ✓
- P1.3 F-effects (T21 −0.43pp/0.0060; T09 −4.55pp/0.0006; T02 −13.19pp/0.0006; T18/T20 cushioned; r values −0.0612/−0.0978/−0.0180) — all match P1.3. ✓
- 49,939 verdict-grade fires, 22,295 episode clusters — matches P1.3 RESULTS L76/L77. ✓

### BLOCKING

**P3-B1 — (= X-BLOCKING-2) The F1 washout production-source clause defers to P2.1b without binding to its 90% floor or its GO artifact, and P3's cell population (49,939 fires) is broader than P2.1b's concordance overlap.** See cross-doc section for the full finding and edits. This is blocking because P3 §2.1 makes cohort_washout (the #2-weighted feature, 0.31) conditional on a "production-source equivalent … confirmed" without any executable definition of "confirmed" — the shadow column could be built on unconfirmed proxy data if the clause is read loosely.

**P3-B2 — §3.5 feature-combination weights are called "normalized weight (rounded to 2dp)" but do not sum to 1 (0.34+0.31+0.28+0.24=1.17), and the doc both claims normalization and then explains the 1.17 as accepted — the two statements contradict.** §3.5 L208–214 presents a "Normalized weight" column (0.34/0.31/0.28/0.24) then §3.5 L218 says *"summed and divided by the total weight (0.34+0.31+0.28+0.24=1.17; the slight >1.00 is accepted)."* These are inconsistent: either the weights are pre-normalized to sum to 1 (they are not) or the combination divides by 1.17 at the end (it does). Calling the raw |ρ|-proportional column "Normalized weight" is a misnomer that will confuse the implementer about whether to divide by 1.17. The values themselves are correct as |ρ|-proportional (0.0845/0.0773/0.0707/0.0593 scaled), but they are *unnormalized* until the §3.5 L218 division.
- **Mechanical edit (§3.5):** rename the column "|ρ|-proportional weight (pre-normalization)" and state the combination is `Σ(wᵢ·wilson_loᵢ)/Σwᵢ` with `Σwᵢ=1.17` (or 0.86 in the washout-omitted fallback). Confirm the fallback arithmetic: 0.34+0.28+0.24=0.86 (L220) is correct. Do not label anything "normalized" until after the division.

### ADVISORY

**P3-A1 — §5.2 concedes the flip criterion's own n-floor (300 clusters) is below 80% power for the expected ρ-difference (~0.02), then defers to a per-evaluation power check.** L281 states SE≈0.058 at G=300, a ρ-diff of 0.02 is ~0.34 SE (well below 80% power), and the criterion "requires a ρ difference that yields at least 80% power at the observed n." This is honest but means the 300-floor is effectively a *lower bound that will rarely suffice* for the weak composite effect — the flip may be structurally unreachable within the 24-month kill window (§5.5) given F2's |r|≈0.01–0.02. Not blocking (the kill criterion correctly retires it), but recommend §5.2/§5.5 explicitly acknowledge that a null flip within 24 months is the *expected* outcome if the composite effect is as weak as the marginal F2 leg suggests, so retirement is not read as a bug.

**P3-A2 — §2.1 cohort_washout bucket counts (NEAR 22,965 / NOT_NEAR 26,974) equal the P1.3 washout True/False split, but P3's population is the 49,939 verdict-grade fires and P1.3's washout split was also on 49,939 — confirm these are the same rows.** They match numerically (22,965+26,974=49,939), so this is consistent. Advisory only: add a one-line confirmation that the §2.1 bucket counts are computed on the P3 cell-construction population (§1.3, 49,939 fires) and not inherited from P1.3's F1-HG population, which after the RW moved-up recode differs (T07 used 20,698/29,241). The equality here is because §2.1 uses the raw feature split, not the RW recode — worth stating to prevent an implementer using the wrong split.

---

## CHECKLIST DISPOSITION (task-specified)

1. **Cited numbers match P1 artifacts (≥3/doc):** PASS all five. Every spot-checked figure (≥5 per doc, ~30 total) matched RESULTS.md/results.json exactly, including sign-stability half-deltas and cluster counts. No approximations substituted for exact values.
2. **Shadow-first + pre-registered flip criteria on every board_ordering-touching doc (Article 2):** PASS. P2.1a (§2.1–2.2), P2.1b (§5–6), P3 (§4–5) each ship shadow-first with immutable pre-registered flip criteria. P2.4 is labeling-only (no ordering change) and correctly claims no shadow needed. P1.2b touches no board_ordering. Caveat: flip-criterion *inequalities* are mis-stated in P2.1a-B2 and P2.1b-B2 (fixable, not missing).
3. **F1/washout PROXY→production concordance clause in BOTH P2.1b and P3, consistent:** FAIL → X-BLOCKING-2. Present in both but P3 does not bind to P2.1b's 90% floor / GO artifact and applies to a broader population. Edits specified.
4. **BH families disjoint and correctly sized; no doc cites 22/30:** PASS. P1.2b `ei_gate_pnl_p12b` m=16 disjoint from `ei_gate_pnl` m=72 (verified P1.2 RESULTS). P3 §6 m=2 flip family. No doc affirmatively cites 22/30 (all five disavow it; grep-confirmed). Minor wording nit X-ADVISORY-2.
5. **P2.1a vs existing extension_demote precedence, no double-counting:** PASS. §3.2 cleanly separates score-penalty (existing, in stock_score.py) from lane-membership (new gate, at render stage); same `ext_z` read, different outputs. Consistent with P1.2's finding that extension_demote's KEEP verdict is non-informative (a measurement confound, not a production change).
6. **P2.4 ranking-neutral; boundary with P3 explicit:** PASS. §3.3 + §5 enumerate the frozen rank machinery; §5.3 P3 owns kernel-rank. Cleanest boundary in the battery.
7. **P1.2b surgical re-tag preserves fire/near-miss sets byte-identical (validation present):** PARTIAL → P1.2b-B1. Fire-set validation (V1) is complete; near-miss validation (V2) only conserves count, not set. Edit specified to close the swap gap.
8. **R7 additive-lanes compliance everywhere:** PASS. P2.1a (Anti-Chase Watch lane), P2.1b (rank weight, 0% fire impact), P2.4 (byte-diff harness AC-1 forbids row drops), P1.2b (re-tag removes nothing), P3 (additional column) all comply.
9. **Kill/rollback criteria on every promotion:** PASS. P2.1a §5 (RB1–RB3 + §6 retention), P2.1b §6.6 (shadow reversal), P3 §5.5 (24-month kill). Caveat: P2.1a rollback-metric consistency (B2) needs the single-signed-quantity fix.

---

## LANDING GUIDANCE FOR FABLE

All five approve **with edits**; none needs re-running a study. Priority order for the Sonnet edit pass:
1. **X-BLOCKING-1 / P2.1b-B1** (P2.1c→P2.1a rename) — one-line, do first.
2. **P2.1a-B1** (delete fabricated citation; re-derive or re-justify the 1,270 floor) — this is the most substantive correctness issue; the n-floor is currently unsupported.
3. **X-BLOCKING-2 / P3-B1** (bind P3's washout clause to P2.1b's concordance GO artifact) — the shared-dependency gap.
4. **P2.1a-B2 + P2.1b-B2 + P3-B2** (single-signed-quantity inequality fixes; feature-weight relabel) — mechanical, prevents un-runnable/unfalsifiable criteria.
5. **P2.4-B1** (pin align_tier vocabulary before build) — empirical grep first, then edit.
6. **P1.2b-B1** (upgrade V2 to set-identity) — closes the near-miss swap gap.

Advisories can be applied in the same pass or deferred; none blocks approval.

*Red-team complete 2026-07-05. No git operations performed. This document is data for the Fable orchestrator.*

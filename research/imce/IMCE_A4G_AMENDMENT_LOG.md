# IMCE-A4G / A4P — Preregistration Amendment Gate: Amendment Log

**File scope note (2026-08-21, A4P wave; updated 2026-08-22, A4P.1 wave):** this file now records THREE gates
in one append-only log, per the A4P commissioning instruction ("every edit gets an append-only entry in
`IMCE_A4G_AMENDMENT_LOG.md`") — the original A4G gate (AG1–AG18, below), the A4P "preregistration criteria
closure" gate (AP1–AP8, appended after the original Summary table), and the A4P.1 "fourth-gate REQUEST_CHANGES
preflight closure" gate (rulings tagged `AP9.R1`–`AP9.R7`, appended after the A4P Summary table). The filename
is retained unchanged (an owned-file constraint carried forward from the A4P commission) rather than renamed;
do not infer from the name alone which gate a given `AG`/`AP`/`R` tag belongs to — the tag prefix is
authoritative.

**Wave:** A4G (final preregistration amendment gate). **Records-only.** No `data/` write, no outcome access, no registration act.
**Commissioned by:** Fable, per Sol's A4G authorization (2026-08-21), settling the A3 reconciliation (`agentos/workstreams/WS-CYCLE-PATTERN-ISSUER-MECHANISM.md`, wave A3 entry) between:
- **Lane 1** — `research/imce/IMCE_HB0_SOURCE_DEFINITION_CENSUS_V1.md` (commissioned, Opus-red-teamed; frozen operational rulings; thirteen typed gaps, four REQUIRED-BEFORE-A4);
- **Lane 2** — `research/imce/hb0/*.md` (operator lane; nine adjudication artifacts + seven evidence packets; B=5 block-hardening proposal; six-regime cancellation record; corrections C1–C3).

**Authority for every amendment below:** Sol, A4G authorization 2026-08-21.
**Binds:** `research/imce/IMCE_PREREGISTRATION_AND_EVALUATION_CONTRACT_V1.md` (V1.1). This log is the detailed rationale/citation record behind the contract's Appendix B index and its inline `[AG<n>]` tags — the contract MD binds; this log explains, it does not itself amend anything not already reflected in the contract and its YAML projection.
**Scope discipline:** every amendment below is RECORDS-ONLY. None writes `data/trial_ledger.jsonl`, accesses any outcome, or registers the three `rf.cycle_pattern.imce_*` families. Registration remains a separate, future A4/IMCE-03 act.
**Ownership note [M10, A4G revision]:** this record, and the other four A4G deliverables, do not touch `agentos/`. The wave-boundary `WS-CYCLE-PATTERN-ISSUER-MECHANISM` state update and any handoff record for this wave are owned by the commissioning (Fable) session's closure, not by this packet — the same convention the A-waves used (e.g. `IMCE_HB0_SOURCE_DEFINITION_CENSUS_V1.md`'s own "Ownership note [M17]").

**Revision history:** V1 initial draft (this session, 2026-08-21) encoded all 18 rulings across the six-file scope. **Revision 1 (same session, 2026-08-21)** applies Fable's adjudication of an Opus red-team pass — verdict REVISE, 3 blockers + 7 majors + 10 minors, structure sound, 12/18 rulings clean on first pass, defects were stale references surviving outside the amended home clauses. Every blocker/major/minor is fixed in place (marked inline `[BLK-n]` / `[MAJ-n]` / `[M<n>-fix]`) rather than superseding this log with a second document. Headline fixes: AG5's cap reaches the binding §9a table and the come-back date (~2153, no basis election — BLK-1); the struck DEFF-rule citations in §0a/§13/Appendix A are corrected (BLK-2); the YAML block list is restored to a genuine 7-entry named taxonomy with `air_pocket_2018` folded back as a `sub_episodes` child (BLK-3); AG6's B≤3 cap is now cell-level, not feature-level, with the grind block's partial FY2016+ coverage disclosed (MAJ-1/M9); the LEN scoping fabricated a nonexistent "contract §2(b) confirmation note," now corrected with a genuine `[AG10-clarif]` ruling (MAJ-2); the struck-DEFF arithmetic in the roster-widening bullet no longer prints a bare `n_eff` (MAJ-3); four bare `n_eff` symbols in §12 are now `n_effective_blocks` (MAJ-4); the AG14 target-mapping requirement is now a binding stop condition (MAJ-5); Treasury CMT's rights verdict is downgraded to `S` after three failed owner-direct verification attempts this session (MAJ-6); and this AG3 entry's grep claim is corrected with exhaustive, exact counts (MAJ-7).

---

## AG1 — Promotion-bearing evidence is 100% prospective

**What changed:** Strengthened §0a's "not a promotion path" framing (A24) to an absolute rule: historical homebuilder replay (and, by the same logic, any other cohort's historical replay) carries **zero weight** in any future promotion decision, by any mechanism — prior, weight, hyperparameter, tiebreak, or otherwise.
**Where:** Contract §0a (new paragraph); YAML `prospective_accrual_first_posture.promotion_bearing_evidence_pct_prospective` / `.historical_replay_weight_in_promotion_decision` / `.historical_replay_may_supply_prior_to_prospective_cell`.
**Relationship to existing text:** generalizes §12's already-adopted "no role of any kind — prior, weight, hyperparameter, or otherwise — in any prospective cell" clause (the deleted sub-floor "prospective PRIOR" carry-path, G8-B7) from the specific sub-floor-pass case to the historical arm as a whole.
**Authority:** Sol, A4G authorization 2026-08-21.

---

## AG2 — Statistical-unit law amended: issuer replication may never raise independent-shock N

**What changed:** Generalized the existing A9 ban ("may never be increased by counting issuers, rows, targets, horizons, directions, or overlapping windows") into an explicit cap: no issuer-level pooling, weighting, or correlation-discounting construction may produce an `n_effective_blocks` value exceeding the raw non-overlapping closed-block count B.
**Where:** Contract §3 "Effective-block-count law" (new paragraph); YAML `effective_block_law.issuer_replication_may_raise_n: false`.
**Why:** This is the load-bearing rule that AG3 uses to strike the DEFF construction — the DEFF formula is struck *because* it violates AG2, not on stylistic grounds.
**Authority:** Sol, A4G authorization 2026-08-21.

---

## AG3 — STRIKE the `B·m/[1+(m-1)ρ]` construction as `n_effective_blocks`

**What changed:** The Round 3 contract's DEFF rule text — *"`n_effective_blocks` may be derived from issuer-episodes only via a design-effect estimator using a correlation parameter (ρ) that is frozen pre-outcome and fit on train folds only"* — is **deleted in its entirety** and replaced with an explicit strike notice plus a capped definition (`n_effective_blocks := min(B, any other candidate estimator)`).
**Why struck:** `DEFF = 1 + (m−1)·ρ`; `n_eff = (B×m)/DEFF`. For any ρ < 1 (i.e. anything short of perfect correlation), `DEFF < m`, so `n_eff = B·m/DEFF > B` — the formula mechanically manufactures independent-shock count out of issuer count, which is exactly what AG2/A9 forbid. This is not a parameter-choice problem (no value of ρ avoids it, short of ρ=1) — it is a structural defect in the construction itself.
**Consequence — closes lane-1 gap 9:** `IMCE_HB0_SOURCE_DEFINITION_CENSUS_V1.md` §8 item 9 flagged: *"ρ (the DEFF correlation parameter) is NOT frozen in HB-0 ... Until ρ is frozen, `n_effective_blocks` cannot be computed for any cell, and ρ remains a live analyst degree of freedom."* AG3 resolves this not by freezing ρ but by removing ρ from the definition of `n_effective_blocks` altogether — **ρ is no longer a required frozen parameter for N.** The parameter this contract now requires for N-accounting is B (the raw closed-block count), which is fixed by AG5/AG6 below.
**Where:** Contract §3 (STRUCK paragraph + capped-definition paragraph); YAML `effective_block_law.deff_formula_as_n_definition` (status: struck) and `.n_effective_blocks_capped_at_raw_block_count`.
**Grep verification [MAJ-7 fix, A4G revision 2026-08-21 — restates the original claim truthfully]:** the original AG3 entry undercounted this. Exact counts against the revised contract MD (`grep -noE '\(m[^)]{0,4}1\)' research/imce/IMCE_PREREGISTRATION_AND_EVALUATION_CONTRACT_V1.md`):

- The formula pattern `(m−1)` / `(m − 1)` appears **4 times across 3 locations**: §3's STRUCK clause (2 occurrences — the struck formula's own restatement, quoting the deleted Round-3 text), §3's AG4 "renamed and demoted" precision-diagnostic clause (1 occurrence — describing what the struck formula becomes, never `n_effective_blocks`), and Appendix B's own AG3 row (1 occurrence — traceability text describing what was struck, the same treatment Appendix B gives every amendment).
- The token `DEFF` appears **12 times total**: 4 inside the STRUCK clause itself (quoting/describing the struck formula), 2 inside the AG4 renamed-diagnostic clause, and 6 single-occurrence citation/annotation references acknowledging the strike (§0a line ~31, §2 roster-widening bullet ~line 80, §3 "pseudo-N unnecessary" note ~line 149, §3 AG9 clause ~line 159, §13 line ~390, Appendix A row A9 ~line 447) — every one of these six explicitly says "struck," "AG3 cap," or "was the DEFF rule, now struck."
- **Every occurrence, without exception, is either (a) inside the STRUCK clause describing what was deleted, (b) inside the AG4 clause describing the renamed, demoted, never-used-as-N precision diagnostic, or (c) an annotation/citation acknowledging the strike.** No occurrence anywhere in the contract defines, computes, or asserts `n_effective_blocks` via the DEFF/`(m−1)` construction as a live, operative rule. This is the corrected, exhaustively-counted version of the original (undercounted, single-example) grep claim.
**Authority:** Sol, A4G authorization 2026-08-21.

---

## AG4 — Within-block dependence survives only as a differently-named precision diagnostic

**What changed:** The struck DEFF/ρ construction is not deleted from the research record — it is renamed and demoted to `n_issuer_precision_diagnostic` (exact field name **frozen by AP8/M3(b)**, was "TBD at A4 registration" in this original AG4 draft — see the AP8 entry below), usable to characterize within-block issuer-pooling precision but explicitly barred from ever substituting for `n_effective_blocks`, from ever satisfying the §8 item 5 forty-block floor, and from carrying any promotion authority.
**Where:** Contract §3 (new paragraph); YAML `effective_block_law.within_block_issuer_dependence`.
**Why:** Preserves the analytic content lane 2 built (`IMCE_HB0_A4_CELL_BUDGET_INPUTS.md` §3, `IMCE_HB0_INDEPENDENT_BLOCK_LIST.md` §8 — the full ρ ∈ {0.5...0.95} sensitivity grid) as a legitimate, disclosed diagnostic, while closing the promotion-authority leak AG3 identified.
**Authority:** Sol, A4G authorization 2026-08-21.

**Revision note (2026-08-21, A4G revision, MAJ-4):** the pre-existing Round 3 promotion-decision text in contract §12 (Outcome handling) used the bare symbol `` `n_eff` `` at four sites — indistinguishable from the struck DEFF estimator's own variable name, and easy to misread as endorsing it post-AG3/AG4. All four replaced with the spelled-out `` `n_effective_blocks` ``: the zero-pass mechanical-determination sentence, the `promoted_null` bullet, the `underpowered_accruing` bullet, and the partial-pass fourth-branch sentence.

---

## AG5 — Historical replay carries FIVE closed non-overlapping blocks as an upper bound; reconciles C2

**What changed:** `n_effective_blocks` for general (non-cancellation) cells is capped at **B ≤ 5** — the five CLOSED, non-overlapping blocks (GFC bust, GFC recovery, 2014–2019 grind, pandemic boom, 2022–2023 rate shock). This is stated as an upper bound (block-to-block serial dependence, AG9, can only push it lower), and exact pseudo-N is declared unnecessary because the upper bound already fails the 40-block floor by roughly an order of magnitude.
**Resolves C2** (`IMCE_HB0_BLOCKERS_AND_FALSIFIERS.md` §5, row C2; `agentos/workstreams/WS-CYCLE-PATTERN-ISSUER-MECHANISM.md` A3 wave entry): lane 1's frozen list carries 7 named entries with the "2013 taper" item unresolved and the affordability era listed as a plain block; lane 2 hardens to B=5 on two independent admissibility grounds (non-overlap/distinct-shock failure for the taper; the closed-episode condition, already applied to the memory cohort's open HBM/AI episode per freeze §7.3, failing for the open affordability era). **RULING: B=5 wins for N-accounting.** Both lanes' lists are preserved — the named 7-entry taxonomy is retained verbatim in the contract's block-list table; only 5 of those 7 named entries contribute to `n_effective_blocks`.
**Where:** Contract §3 "Frozen historical block list" (restructured table) and "Effective-block-count law" (capped-definition paragraph, reconciliation paragraph); YAML `frozen_historical_block_list` (per-entry `counts_toward_n_effective_blocks`) and `effective_block_law.block_count_reconciliation`.
**Authority:** Sol, A4G authorization 2026-08-21.

**Revision note (2026-08-21, A4G revision — Fable adjudication of Opus red-team findings, BLK-1):** the original draft left AG5's cap out of the §9a BINDING reachable-status table (still reading the pre-AG5 "5–7" range there) and published the come-back date at the pre-hardening ~2145 figure with no basis stated. Both fixed: §9a's Homebuilders row now reads "≤5 general / ≤3 cancellation [AG5, AG6]"; the come-back date is now published at **~2153** (the B=5 hardened basis, `IMCE_HB0_A4_CELL_BUDGET_INPUTS.md` §7 second row) everywhere it appears (contract §13, Appendix B, YAML `prospective_law.come_back_date`) — **there is no basis election; B=5 is the sole N-accounting law (AG5), so ~2153 is the one figure.** The registration packet's "actual registration must state which basis it publishes and why" checklist item is deleted and replaced with the settled figure.

---

## AG6 — Cancellation cells have at most THREE denominator-reconstructable historical blocks

**What changed:** Cancellation-rate cells specifically are capped at **B ≤ 3** (not the general-cell B ≤ 5), because only three of the five closed blocks carry a denominator-reconstructable cancellation-rate disclosure across the roster: the 2014–2019 grind (from FY2016), the 2020–2021 pandemic boom, and the 2022–2023 rate shock. GFC bust and GFC recovery predate the stated-denominator era for most of the roster (PHM/NVR confirmed only FY2016+; KBH FY2008+ and self-contradictory in that filing; LEN states no formula anywhere the census could find).
**Where:** Contract §3 "Effective-block-count law" (capped-definition paragraph, bullet 2); YAML `effective_block_law.n_effective_blocks_capped_at_raw_block_count.cancellation_rate_cells`.
**Source:** `IMCE_HB0_A4_CELL_BUDGET_INPUTS.md` §4 ("Why the cancellation cell gets B = 3, not 5").
**Authority:** Sol, A4G authorization 2026-08-21.

**Revision note (2026-08-21, A4G revision, MAJ-1/M9):** two corrections. (1) **Cell-level, not feature-level scoping** — the original draft's six-cell disposition treated the B≤3 cap as applying only to "a feature's contribution" within an otherwise B≤5 cell; Fable's adjudication of the Opus red-team ruled this wrong: AG6 caps the CELL entire whenever its registered basis includes cancellation-rate data. Since `order_softness` (AG14) currently names cancellation-rate disclosure as part of its basis, every cell targeting it is a B≤3 cell as registered, not a conditional one; a future registration stripping cancellation from a cell's basis is a registration-time amendment with its own review, never an open election of this gate. (2) **Grind-block partial coverage** — the 2014–2019 grind block, one of the three B≤3-contributing blocks, itself carries only partial coverage: PHM's and NVR's cancellation-formula disclosures are confirmed only from FY2016 onward, so the 2014–FY2015 span within that block predates stated-denominator disclosure for those two issuers. Both corrections are now stated at every citation of the grind block and the cell-level cap (contract §3, §2; `IMCE_A4G_SIX_CELL_DISPOSITION.md`; YAML `effective_block_law.n_effective_blocks_capped_at_raw_block_count.cap_scoping` / `.grind_block_cancellation_coverage`).

---

## AG7 — "2013 taper" and "2018 air-pocket" are named subepisodes contributing zero N

**What changed:** Both are typed as named sub-episodes of their parent blocks (taper → sub-episode of GFC recovery/land-light era; air-pocket → sub-episode of the 2014–2019 grind, consistent with the frozen list's own nested wording "including the 2018 air-pocket"), contributing zero to `n_effective_blocks`. No boundary-date minting is required to reach this status.
**Closes lane-1 gap 12** (`IMCE_HB0_SOURCE_DEFINITION_CENSUS_V1.md` §8 item 12): *"The '2013 taper (partial)' block's exact start/end boundary dates are not given in the contract, and this document does not mint them ... Minting a specific '2013' boundary here ... would violate contract §3's effective-block-count/no-overlap law."* AG7 resolves this by making the exact date irrelevant to N-accounting — a sub-episode contributes zero regardless of its precise boundary.
**Where:** Contract §3 (block-list table types, "Named sub-episodes contribute ZERO N" paragraph); YAML `frozen_historical_block_list` entries `taper_2013_partial` / `air_pocket_2018` (`type: named_sub_episode_of_*`, `counts_toward_n_effective_blocks: false`).
**Authority:** Sol, A4G authorization 2026-08-21.

---

## AG8 — 2024–2026 affordability era is OPEN_ACCRUING

**What changed:** The affordability/incentive era block is typed `OPEN_ACCRUING`: zero historical N, and becomes prospective (contributing to `n_blocks_prosp`, not `n_blocks_hist`) only when lawfully closed by a pre-registered closing rule. No such closing rule is registered by this amendment.
**Why:** Consistent with the freeze's own treatment of the memory cohort's open HBM/AI episode (freeze §7.3): "the open HBM/AI episode has no closing disposition and is not a unit — counting it is a unit violation." The homebuilder family gets the same law.
**Where:** Contract §3 (block-list table, "2024–2026 affordability era is OPEN_ACCRUING" paragraph); §13 cross-reference (n_blocks_hist/n_blocks_prosp counters, unchanged mechanism, new concrete assignment); YAML `frozen_historical_block_list` entry `affordability_incentive_era` (`status: open_accruing`).
**Authority:** Sol, A4G authorization 2026-08-21.

---

## AG9 — Inference is block-cluster / leave-one-block-out; dependence adjustments may only reduce information

**What changed:** Explicit statement that cross-validation, bootstrap, and materiality tests operate at the block level, and that any dependence adjustment (issuer-level ρ, or a future block-level `rho_block`) may only ever REDUCE `n_effective_blocks` below its capped value — never raise the shock count above B.
**Why:** Names the direction-of-travel constraint that makes AG3's cap durable against future refinements — a future `rho_block` registration (proposed by `IMCE_HB0_INDEPENDENT_BLOCK_LIST.md` §3 D4, addressing block-to-block serial dependence that the struck DEFF construction never addressed) can only tighten the bound, never loosen it.
**Where:** Contract §3 (new paragraph); YAML `effective_block_law.inference_unit` / `.dependence_adjustment_direction`.
**Authority:** Sol, A4G authorization 2026-08-21.

---

## AG10 — C1 accepted: LEN exclusion reason restated

**What changed:** LEN's cancellation-rate-cell exclusion **stands** (no roster or cell change), but its recorded reason is restated from "no press-release cancellation rate; era-correlated missingness by construction" to **"no stated formula anywhere in LEN's disclosure record (denominator unverifiable) + era-correlated absence from the press-release channel specifically."**
**Why:** `IMCE_HB0_SOURCE_DEFINITION_CENSUS_V1.md` confirmed the press-release absence (zero cancellation-rate line items across 3 of 4 FY2025 quarterly releases reviewed) but also found LEN's own 10-K MD&A **does** disclose a cancellation figure (14%, FY2025) — so the original ground ("no press-release cancellation rate") was true of the EX-99.1 press-release channel only, not of LEN's full disclosure record. The stronger, correct ground — LEN states no cancellation-rate *formula* anywhere the census could find — is what actually leaves condition (4)'s "one canonical denominator per issuer" with nothing to freeze for LEN.
**Resolves C1** (`IMCE_HB0_BLOCKERS_AND_FALSIFIERS.md` §5, row C1; WS A3 entry: "C1 ACCEPTED in direction — the LEN exclusion STANDS but its recorded reason restates").
**Where:** Contract §2 Homebuilders (LEN bullet); YAML `homebuilders.len.exclusion_reason` / `.exclusion_reason_note`.
**Authority:** Sol, A4G authorization 2026-08-21.

**AG10-clarif (2026-08-21, A4G revision, MAJ-2):** the original draft's six-cell disposition attributed the exclusion's scope to a "contract §2(b) confirmation note" — **no such note exists in the contract.** That language was HB0 census evidence (`IMCE_HB0_SOURCE_DEFINITION_CENSUS_V1.md` §6b: "this document treats the exclusion as feature-level and universal ... pending confirmation"), never a contract clause, and the fabricated attribution is struck. In its place, a genuine contract-level clarifying ruling is added: LEN's exclusion is **cell-level** — LEN is excluded entirely (as an issuer) from any cell whose registered basis draws cancellation-rate input (the AG6/MAJ-1 B≤3 class); in every other cell, LEN remains a roster member and its cancellation-rate feature, if referenced non-primarily, is typed `missing` and never imputed under the [A19]/AG11 ban — it is not separately "excluded" from those cells. Where: contract §2 Homebuilders (LEN bullet, `[AG10-clarif]` paragraph); YAML `homebuilders.len.exclusion_scope` / `.non_cancellation_cell_treatment`; `IMCE_A4G_SIX_CELL_DISPOSITION.md` §1 (all six cells' LEN column restated on this clause).

---

## AG11 — C3 accepted: era-correlated-missingness ban extended to every era-correlated metric

**What changed:** The [A19] era-correlated missing-indicator ban, previously stated in the context of LEN's cancellation rate specifically, is extended to every era-correlated metric in the definition crosswalk — no missing-indicator on any such metric may enter a primary comparison, regardless of which metric it is.
**Why:** `IMCE_HB0_BLOCKERS_AND_FALSIFIERS.md` §5 row C3 found the identical structural pattern elsewhere: TOL's "spec[ulative] homes" disclosure label appears only from FY2023 (zero hits 2001–2020 — a terminology/disclosure-emphasis change, not necessarily a behavior change per §4.3's "disclosure onset ≠ behaviour onset" finding); PHM's "Unsold" unit split is confirmed only from FY2024; cancellation-formula disclosure itself appears issuer-by-issuer across FY2008–FY2016. "Widening a contract amendment's scope is itself an amendment" (lane 2's own framing) — this amendment performs that widening.
**Resolves C3.**
**Where:** Contract §10 Missingness and population law (extended [A19] bullet); YAML `missingness_law.era_correlated_missing_indicator_ban_scope` / `.era_correlated_missing_indicator_ban_examples`.
**Authority:** Sol, A4G authorization 2026-08-21.

---

## AG12 — TOL primary cancellation denominator = signed contracts in quarter; beginning-quarter backlog = mandatory printed sensitivity

**What changed:** Settles election E1 (`IMCE_HB0_A4_CELL_BUDGET_INPUTS.md` §8): TOL's canonical/primary cancellation-rate denominator is the **gross signed-contracts-in-quarter** basis (cross-issuer comparable with DHI/PHM/KBH's gross-orders convention). TOL's other disclosed basis — cancellations as a percentage of beginning-quarter backlog — is a **MANDATORY printed sensitivity** on every TOL cancellation readout, not an optional alternate-convention leg; a flip under that sensitivity is not a pass (§2(b)'s existing alternate-convention rule, unchanged in substance, now made concrete for TOL).
**Where:** Contract §2 Homebuilders (new TOL bullet); YAML `homebuilders.tol_cancellation_denominator`.
**Authority:** Sol, A4G authorization 2026-08-21.

---

## AG13 — NVR separate stratum: reaffirmed, no change

**What changed:** Nothing substantive — NVR's separate-stratum treatment (never pooled to raise n) is carried forward from [A18] unmodified. The mechanism basis is corrected to match `IMCE_HB0_SOURCE_DEFINITION_CENSUS_V1.md` §1's finding: NVR's own FY2025 10-K describes a **strong-majority option-lot model** ("we generally do not engage in land development"), not a categorical "~100%-option" model as the prior draft's citation implied.
**Where:** Contract §2 Homebuilders (NVR bullet, mechanism-basis correction); YAML `homebuilders.nvr.reaffirmed_by` / `.mechanism_basis`.
**Authority:** Sol, A4G authorization 2026-08-21.

---

## AG14 — State-vector observability scoping

**What changed:** Settles election E2 for 3 of the 4 D5 homebuilder mechanism-local states (`order_softness`, `completed_inventory_build`, `incentive_support`, `pace_recovery`):
- `order_softness` — broadly cohort-observable today (net orders/backlog/cancellation rate disclosed, in some form, by all six roster issuers).
- `completed_inventory_build` — may exist only as a **named three-issuer subset** (DHI, LEN, PHM), never as a full cohort claim.
- `incentive_support` and `pace_recovery` — remain **descriptive only** and may **not** be imputed into any cohort cell; each rests on a single disclosing issuer today (LEN for incentive figures, KBH for build/cycle time).
The exact mapping of the `rf.cycle_pattern.imce_phase_v0` family's 3 declared state targets against these 4 D5 states is left as an open A4 registration item — this amendment scopes observability, it does not itself re-map which target tracks which state, and it does not re-declare the frozen 6-cell budget. **[Superseded by AP1, A4P, 2026-08-21 — this open item is now CLOSED: all 3 targets, plus `imce_sync_v0` Cell 4, map to `order_softness`. This sentence is retained verbatim as the historical record of AG14's own scope; see the AP1 entry below for the closure.]**
**Where:** Contract §2 Homebuilders (new bullet); YAML `homebuilders.state_vector_observability_scoping`.
**Source:** `IMCE_HB0_A4_CELL_BUDGET_INPUTS.md` §2 ("mechanism-state coverage is uneven, and two states rest on one issuer") and §8 election E2.
**Authority:** Sol, A4G authorization 2026-08-21.

**Revision note (2026-08-21, A4G revision, MAJ-5):** the target-to-D5-state mapping open item was originally disclosed but not enforced — a future registration could in principle register an unmapped or descriptive-only-mapped target without anything stopping it. Made **BINDING**: contract §15/§15a now carries a new stop condition, "no `rf.cycle_pattern.imce_phase_v0` state target may be registered unless it is mapped to a named D5 state whose observability class is registered"; mirrored in YAML `stop_conditions` and the registration packet's criteria-commit checklist (§6 of `IMCE_A4G_PROPOSED_A4_REGISTRATION_PACKET.md`).

---

## AG15 — `pit_class` enum closed at exactly {pit_pure, revision_optimistic, mixed}

**What changed:** Explicit contract-level statement that `pit_class` is a closed enum of exactly three tokens, identical to `config/cycle_pattern/truth_schema.md`'s CPI enum. A3 lane-1's five-way `source_vintage_class` census vocabulary (`pit_pure`, `revision_optimistic`, `current_revised_only`, `prospective_from_capture`, `rights_blocked`) is a strictly-more-granular local diagnostic that must crosswalk down to one of the three before touching any cell — it never substitutes for `pit_class`. The full crosswalk and per-source mapping is in `IMCE_A4G_SOURCE_BOUNDARY_TABLE.md`.
**Resolves lane-1 gap 10** (`IMCE_HB0_SOURCE_DEFINITION_CENSUS_V1.md` §8 item 10 — "`pit_class` vocabulary not registered"): three prose verdicts were proposed as candidates without adoption; AG15 declines to mint any new token and instead confirms the existing three-value CPI enum is the only registered vocabulary, avoiding the exact vocabulary-fragmentation defect A2 (the CPI truth-contract audit) exists to fix.
**Where:** Contract §2 Homebuilders (Vintage rider bullet, extended); YAML `homebuilders.pit_class_enum`.
**Authority:** Sol, A4G authorization 2026-08-21.

---

## AG16 — No roster widening

**What changed:** Explicit statement that the six-name roster (DHI, PHM, TOL, KBH, LEN, NVR) stays frozen. Widening it — e.g. to the listed, continuously-public non-roster survivors named in `IMCE_HB0_SOURCE_DEFINITION_CENSUS_V1.md` §2d (HOV, BZH, MHO, MTH) — improves representativeness but supplies zero additional independent-shock power: at ρ≈0.8, going from m=5 to m=9 moves the struck-and-renamed `n_issuer_precision_diagnostic` (AG3/AG4 — never `n_eff`/`n_effective_blocks`) from ~6.0 to ~6.1 (survivorship census falsifier F-V4 / `IMCE_HB0_BLOCKERS_AND_FALSIFIERS.md` §4.2, F-4), shown only to demonstrate insensitivity — `n_effective_blocks` itself stays capped at B regardless of roster width. Representativeness and power are separate problems; the roster question is open to future amendment on representativeness grounds only, never as a power lever.
**Where:** Contract §2 Homebuilders (new bullet); YAML `homebuilders.roster_widening` / `.roster_widening_rationale`.
**Authority:** Sol, A4G authorization 2026-08-21.

**Revision note (2026-08-21, A4G revision, MAJ-3):** the original entry (and the contract clause it describes) printed this arithmetic as a bare "`n_eff`" figure — indistinguishable, on its face, from a live `n_effective_blocks` value, and one that exceeds the AG5 cap (B≤5) if misread that way. Relabeled per AG4 as the struck DEFF estimator's renamed diagnostic, with an explicit "shown only to demonstrate insensitivity" caveat, and the m=5 basis stated explicitly (the five pooled general-cell issuers — DHI, PHM, TOL, KBH, LEN; NVR held out as its own stratum).

---

## AG17 — Exact source-dated macro boundaries must be receipted before any outcome partition runs

**What changed:** A block boundary used to partition an actual outcome run must carry a citation to a dated macro-series or issuer-event source, not merely a narrative news citation — reflecting `IMCE_HB0_SOURCE_DEFINITION_CENSUS_V1.md` §6a's M4 correction that cancellation rate cannot certify its own block boundaries (it is `M_t` itself, so using it as "defining evidence" is circular). Uncertainty about a descriptive sub-episode's exact date (the 2013 taper, the 2018 air-pocket) may **not** be used to manufacture another block — both stay sub-episodes at zero N (AG7) regardless of whether their own boundary dates are ever receipted. New stop condition added to §15/§15a: a `not_yet_receipted` boundary blocks only an actual outcome partition on that boundary, not this contract's freeze.
**Where:** Contract §3 (new paragraph), §15/§15a (new stop condition); YAML `effective_block_law.macro_boundary_receipt_required_before_outcome_partition`, `stop_conditions` (new entry).
**Receipt status of every proposed month boundary:** `IMCE_A4G_SOURCE_BOUNDARY_TABLE.md` — most block-level boundaries (bust/recovery/grind/pandemic/rate-shock start-end months) are `not_yet_receipted` (sourced from narrative housing-market articles, not a dated macro-series print pinned to that exact month); a small number of dated events ARE receipted (PMMS construction break 2022-11-17; Centex→PHM merger close 2009-08-18; LEN Millrose spin-off close 2025-02-07) but those are issuer/source-structural events, not the block boundaries themselves.
**Authority:** Sol, A4G authorization 2026-08-21.

---

## AG18 — Macro legs must be rights-safe owner sources

**What changed:** Every macro/context leg feeding `C_t` or `M_t` must be a rights-safe OWNER source:
- **FRED and ALFRED excluded categorically** (clause (q), `DO_NOT_INGEST`, binds every use class including display tier).
- **Freddie Mac PMMS is HELD**, not GO and not blocked — genuinely PIT-pure (1971→present weekly archive) but the site terms bar redistribution/commercial exploitation without a separate licence, in tension with the archive's open availability. Treasury constant-maturity yields (confirmed `pit_pure`, public domain, full archive) are the primary rate leg in the interim.
- **No NAR series may be stored** (Existing-Home Sales, Housing Affordability Index) — NAR's terms bar storage in a retrieval system outright, not merely redistribution; self-archival does not cure it. An affordability construct is assembled from clean owner legs (Census NRS price + Treasury rate + Census/BLS income), never adopted from the NAR or NAHB indices.
- **A source without lawful, retrievable historical vintages stays `pit_class = revision_optimistic`** by default until an individually-cleared upgrade path executes (e.g. Census NRS's first-print release archive back to 1995 — costed, not yet executed).
**Where:** Contract §2 Homebuilders (new bullet), §4 Context `C_t` (cross-reference); YAML `homebuilders.rights_safe_macro_legs_only`.
**Source:** `IMCE_HB0_SOURCE_PIT_VINTAGE_MATRIX.md` §2 ("the rights finding — the affordability leg cannot be taken off the shelf") and §4 (mandatory disclosure list).
**Authority:** Sol, A4G authorization 2026-08-21.

**Revision note (2026-08-21, A4G revision, MAJ-6):** "Treasury constant-maturity yields ... the primary rate leg" was carried forward from prior HB0 evidence without this wave attempting its own owner-direct verification. This session attempted it: three `WebFetch` calls against `home.treasury.gov` (the daily Treasury par yield curve TextView page, the interest-rates-data landing page, and the domain root) each timed out at 60 seconds; a control fetch to `example.com` in the same session succeeded, ruling out a general tool failure. Per the ruling: **Treasury CMT (#13 in `IMCE_A4G_SOURCE_BOUNDARY_TABLE.md`) is downgraded from an implied `V` to explicit `S`**, with a note that the primary rate leg is unresolved-at-A4-verification while PMMS (#10) remains rights-HELD — both candidate rate legs currently lack a session-verified `V`-grade citation. Where: `IMCE_A4G_SOURCE_BOUNDARY_TABLE.md` §2 (row #13, Notes column), §4 (PMMS detail, "Interim primary rate leg" bullet), §5 (affordability-leg table).

---

## Summary table

| # | Ruling (one line) | Contract section(s) | Resolves |
|---|---|---|---|
| AG1 | 100% prospective promotion evidence; zero historical weight | §0a | — |
| AG2 | Issuer replication may never raise N | §3 | — |
| AG3 | STRIKE `B·m/[1+(m-1)ρ]` as `n_effective_blocks` | §3 | lane-1 gap 9 |
| AG4 | Within-block dependence → renamed precision diagnostic | §3 | — |
| AG5 | B≤5 upper bound (general cells) | §3, §2 | C2 |
| AG6 | B≤3 (cancellation cells) | §3, §2 | — |
| AG7 | Taper/air-pocket = subepisodes, zero N | §3 | lane-1 gap 12 |
| AG8 | Affordability era = OPEN_ACCRUING, zero N | §3, §13 | — |
| AG9 | Block-cluster/LOBO inference; dependence only reduces N | §3, §7, §8 | — |
| AG10 | LEN exclusion reason restated | §2 | C1 |
| AG11 | [A19] ban extended to every era-correlated metric | §10 | C3 |
| AG12 | TOL primary = signed contracts; backlog = mandatory sensitivity | §2 | E1 |
| AG13 | NVR stratum reaffirmed | §2 | — |
| AG14 | State-vector observability scoping | §2 | E2 (partial) |
| AG15 | `pit_class` enum closed at 3 tokens | §2 | lane-1 gap 10 |
| AG16 | No roster widening | §2 | — |
| AG17 | Macro boundaries must be receipted before outcome partition | §3, §15/§15a | lane-1 gap 11 |
| AG18 | Rights-safe macro legs only (FRED/ALFRED excl., PMMS held, no NAR) | §2, §4 | — |

**Elections from `IMCE_HB0_A4_CELL_BUDGET_INPUTS.md` §8 not settled by this gate (explicitly deferred to actual A4 registration):**
- E3 (`rho`/`rho_block` values) — moot: AG3/AG4 remove ρ from the N-definition; a future `rho_block` may still be registered for the AG4 precision diagnostic, at A4.
- E4 (whether taper/air-pocket stay sub-episodes) — **settled by AG7: yes.**
- E5 (MDC's admissibility if the roster is ever widened) — moot under AG16 (no widening); revisit only if AG16 is itself amended.
- E6 (Census NRS release-archive upgrade to `pit_pure`) — not executed; remains a costed, not-yet-executed A4 option (`IMCE_A4G_SOURCE_BOUNDARY_TABLE.md`).
- E1, E2 — **settled above by AG12 and AG14 respectively** (E2 only for `order_softness`/`completed_inventory_build`; `incentive_support`/`pace_recovery` are scoped to descriptive-only, which functionally answers E2's "drop" branch for those two without literally re-declaring the cell budget).

---

**This log authorizes nothing beyond itself.** No cell, model, score, or outcome computation has started here. No `rf.cycle_pattern.imce_*` family is registered. The next authorized act on this family is A4 registration proper (`declared_budget` trial-ledger rows, criteria commit, config_hash, repository pin) — see `IMCE_A4G_PROPOSED_A4_REGISTRATION_PACKET.md` for the exact proposed (not registered) content of that future act.

---
---

# IMCE-A4P — Preregistration Criteria Closure: Amendment Log (AP1–AP8)

**Wave:** A4P (preregistration criteria closure). **Records-only.** No `data/` write, no outcome access, no
registration act. Commissioned by Fable, per Sol's A4P authorization (2026-08-21), issued after Sol accepted
A4G (contract V1.1, PR #6189) — A4P closes every remaining open criterion the A4G six-cell disposition (§4)
and source/boundary table (§2 row 13, §6) left open, so that actual A4 registration becomes a mechanical act
with zero remaining discretionary choices except the four listed in
`IMCE_A4G_PROPOSED_A4_REGISTRATION_PACKET.md` §6 (as regenerated by AP7).
**Authority for every amendment below:** Sol, A4P authorization 2026-08-21.
**Binds:** `research/imce/IMCE_PREREGISTRATION_AND_EVALUATION_CONTRACT_V1.md`, now **V1.2**. This log entry
is the detailed rationale/citation record behind the contract's new Appendix C index and its inline `[AP<n>]`
tags — the contract MD binds; this log explains, it does not itself amend anything not already reflected in
the contract and its YAML projection.
**Scope discipline:** every amendment below is RECORDS-ONLY. None writes `data/trial_ledger.jsonl`, accesses
any outcome (issuer/ETF forward return, Brier, drawdown, model fit), or registers the three
`rf.cycle_pattern.imce_*` families. Registration remains a separate, future A4/IMCE-03 act. No FRED/ALFRED
fetch occurred (prohibited even to look); no NAR data was stored; no new PMMS use occurred (PMMS use in this
wave is limited to reading its already-public research-note PDF for a previously-established construction-
break date, consistent with the A4G wave's own precedent, §4 of `IMCE_A4G_SOURCE_BOUNDARY_TABLE.md`).

---

## AP1 — Phase-family target-to-D5-state mapping settled: `order_softness`, deterministic construction frozen

**What changed:** Settles the AG14/MAJ-5 open item (`IMCE_A4G_SIX_CELL_DISPOSITION.md` §4) that A4G left open.
All three `rf.cycle_pattern.imce_phase_v0` targets are now registered against the same D5 state,
`order_softness`: (a) next `order_softness` cohort state at +1 reporting period; (b) next `order_softness`
cohort state at +3 reporting periods; (c) `order_softness` false-repair/relapse within 3 reporting periods.
`rf.cycle_pattern.imce_sync_v0` Cell 4 (`next_local_state_1rp`) targets the same `order_softness` state as
phase target (a) — not a second, independently-defined state. `completed_inventory_build` is explicitly
**excluded** from all 3 phase-family target slots — it remains a named DHI/LEN/PHM three-issuer
descriptive/subset research object (AG14, unchanged), never a v0 cohort inferential target.
`incentive_support`/`pace_recovery` remain descriptive only (AG14, unchanged), mapped to nothing.
**New deterministic construction:** a dedicated new file,
`research/imce/IMCE_A4P_ORDER_SOFTNESS_STATE_CONSTRUCTION_V1.md`, freezes the exact, outcome-independent
construction — sign-only comparison of YoY net-orders direction and YoY cancellation-rate-point direction,
per issuer, pooled by mode across the same four-issuer population {DHI, PHM, KBH, TOL} that AP2 below settles
as the cell-level roster for every v0 historical cell (LEN excluded, NVR held out as its own stratum). No
grid search, no outcome-selected threshold (every comparison is a sign, never a fitted magnitude cutoff), no
issuer-specific tuning. Ties and zero-signal periods are typed `MIXED`, never broken by an invented tiebreak;
periods lacking a reconstructable input on both sides are typed `NOT_RECONSTRUCTABLE` and excluded, never
imputed (contract §10).
**Where:** Contract §1 (trial families — target definitions), §2 Homebuilders (state-vector observability
scoping bullet, AG14, extended), §15/§15a (stop condition — now discharged for `order_softness`, still
binding for any future target keyed to a `descriptive_only` state); new file
`IMCE_A4P_ORDER_SOFTNESS_STATE_CONSTRUCTION_V1.md`; YAML `trials[].targets`,
`homebuilders.state_vector_observability_scoping.exact_phase_family_target_to_d5_state_mapping`,
`stop_conditions`.
**Authority:** Sol, A4P authorization 2026-08-21.

---

## AP2 — Common v0 historical basis: ALL SIX v0 inferential historical cells are cancellation-scoped, B≤3

**What changed:** All six registered v0 historical cells (Cells 1–6, `IMCE_A4G_SIX_CELL_DISPOSITION.md` §1)
use the **same order-softness mechanism basis**, including lawfully reconstructable cancellation evidence
(AP1's construction, §1). This resolves the A4G six-cell disposition's remaining conditional item — Cells 5
and 6 (`imce_sync_v0`'s `forward_63d_drawdown_tail` and `imce_risk_v0`) were left conditional on an
undetermined `M_t` feature composition (`IMCE_A4G_SIX_CELL_DISPOSITION.md` §1, Cells 5–6: "B≤3 entire if
cancellation-rate is included... else B≤5"). AP2 settles the composition: every v0 historical cell's `M_t`
basis includes `order_softness`, and `order_softness` names cancellation-rate disclosure (AP1) — so **all
six cells are now B≤3-entire, uniformly, under the existing cell-level ruling (MAJ-1, AG6)**, not a mix of
B≤3 (Cells 1–4) and conditional-B≤3-or-B≤5 (Cells 5–6).
**Consequences, applied throughout the estate (never left standing at the old split):**
- **Historical block ceiling = B≤3 for all six v0 cells.** The general B≤5 cap (AG5) remains the standing
  law for the block list as a taxonomy and for any *future*, non-cancellation cell — but describes **none**
  of the six cells actually registered by this contract today.
- **LEN is excluded — cell-level — from all six v0 historical cells**, not only Cells 1–4. In every OTHER
  (hypothetically, non-registered) cell class, LEN remains a roster member with its cancellation feature
  typed `missing` (AG10-clarif, unchanged mechanism).
- **NVR remains a separate stratum**, never pooled, unchanged (AG13).
- **GFC blocks (#1 bust, #2 recovery) remain unusable** for all six cells — the cancellation denominator is
  not reconstructable in those blocks for most of the roster (AG6, unchanged finding), so the B≤3 basis draws
  only the 2014–2019 grind (partial FY2016+ PHM/NVR coverage), 2020–2021 pandemic boom, and 2022–2023 rate
  shock blocks — the same three blocks AG6 already named, now confirmed as the basis for the full six-cell
  family rather than four of six.
- **Binding, non-relaxable:** this B≤3 basis for the six registered cells may **never** be relaxed to B=5
  merely to obtain a larger nominal N. A future amendment could only change this by re-registering a cell's
  `M_t` basis to genuinely exclude `order_softness`/cancellation data — a different cell, not a reinterpretation of this one.
- **Roster-widening diagnostic clarified:** the AG16 roster-widening bullet's `n_issuer_precision_diagnostic`
  arithmetic (m=5, including LEN, "the five pooled general-cell issuers") described a *hypothetical* general
  (non-cancellation) cell. AP2 clarifies explicitly: **no currently registered cell is a general cell** — all
  six are cancellation-scoped — so that m=5 figure is illustrative of a hypothetical class only, never a
  description of a currently registered cell's issuer pool (which is m=4: DHI/PHM/KBH/TOL, LEN excluded).
- **Come-back date recomputed — B≤5 basis is now stale, per the "never leave a stale derived number standing
  silently" instruction.** The AG5 ~2153 figure was computed on the B=5 general-block basis
  (`IMCE_HB0_A4_CELL_BUDGET_INPUTS.md` §7: span 2006-01→2023-12 = 18.0y, 3.60y/block, `2026-08 + (40-5)×3.60
  ≈ 2153`). Since every registered historical cell is now B≤3 (the cancellation-block basis: 2014-01→2023-12
  = 9.9y over 3 blocks = 3.30y/block), the same method applied to B=3 gives:
  `come-back year ≈ 2026-08 + (40 − 3) × (9.9 / 3) = 2026.67 + 37 × 3.30 = 2026.67 + 122.1 ≈ 2148.8 → ~2149`.
  **~2149 is the published figure for the six registered v0 historical cells, superseding ~2153 (which itself
  superseded the pre-A4G ~2145)** — every occurrence updated: contract §13, Appendix B/C, YAML
  `prospective_law.come_back_date`, `IMCE_A4G_PROPOSED_A4_REGISTRATION_PACKET.md` §6 checklist item. The
  general B≤5 figure (~2153) is retained in this log and in `IMCE_HB0_A4_CELL_BUDGET_INPUTS.md` (not owned by
  this wave, not edited) as the *block-list-level* arithmetic — it no longer describes the six registered
  cells' own come-back date, which is ~2149.

  **[AP8 correction, F1]** The paragraph above is INACCURATE and is corrected here rather than rewritten in
  place (append-only discipline): **~2149 is NOT the promotion-relevant come-back date and never should have
  been described as "the published figure" without that qualifier.** AG1 ("promotion-bearing evidence is 100%
  PROSPECTIVE... historical replay carries zero weight... by any mechanism") and AP3 (minimum prospective
  share = 100%, exactly) together mean the three historical blocks these six cells have already accrued credit
  **zero**, not `B=3`, toward any promotion-relevant block count — so `(40−3)×3.30` double-counts historical
  evidence the contract itself zero-weights. **The genuinely promotion-relevant figure is `~2160`** (zero
  historical credit, inclusive fencepost: `2026 + 8/12 + 40 × (10.0/3) = 2026.6667 + 133.3333 = 2160.0`).
  **~2149 is demoted to an explicitly-labeled NON-PROMOTION diagnostic** — it still has a legitimate use (an
  order-of-magnitude illustration of the historical arm's distance from the 40-block floor, same as ~2153
  before it), but it is never again cited as a promotion timeline. **The claim above that "every occurrence
  updated" was itself only partially true when this AP2 entry was first written** — it correctly propagated
  ~2149 into the contract, YAML, and packet, but at the time this correction was needed, the YAML
  `prospective_law.come_back_date` block had NOT yet been updated to distinguish the promotion clock from the
  non-promotion diagnostic (it carried only the ~2149 figure under a `homebuilders_estimate` key with no
  promotion/non-promotion labeling) — that gap is what this AP8 pass closes: the YAML block is rewritten with
  a `promotion_clock_estimate` field (~2160) and the ~2149/~2153 figures relabeled
  `non_promotion_diagnostic_b3_total_block_estimate` / `non_promotion_diagnostic_prior_basis_b5`. See the
  full AP8 entry below for every file touched by this correction.
**Where:** Contract §3 (effective-block-count law, cell-level scoping paragraph — rewritten), §9a (Homebuilders
row), §13 (come-back date), Appendix B/C; `IMCE_A4G_SIX_CELL_DISPOSITION.md` §1 (Cells 5–6 rewritten to match
Cells 1–4), §2 (cross-cell summary rewritten), §3 (E2 fully settled), §4 (open item closed); YAML
`effective_block_law.n_effective_blocks_capped_at_raw_block_count`, `homebuilders.n_effective_blocks_cap_*`,
`prospective_law.come_back_date`.
**Authority:** Sol, A4P authorization 2026-08-21.

---

## AP3 — Minimum prospective share for promotion: 100%, machine-readable

**What changed:** Every remaining TBD is replaced with the machine-readable registration
`minimum_prospective_share_for_promotion = 100%` — already implied by AG1 ("promotion-bearing evidence is
100% prospective; zero historical weight of any kind"), now made explicit and machine-readable in both the
contract prose and the YAML field that previously carried `required_value_tbd_at_registration`.
**Where:** Contract §13 (preregistered minimum prospective share bullet); YAML
`prospective_law.preregistered_minimum_prospective_share_before_promotion`.
**Authority:** Sol, A4P authorization 2026-08-21.

---

## AP4 — Bootstrap: 800 draws, seed 7, house default frozen

**What changed:** Freezes the CPI house default bootstrap parameters for this contract's month/episode-block
bootstrap (contract §8 item 2, §11): **800 block-bootstrap draws, seed 7**, using the registered
block-cluster unit (contract §3 "Inference is block-cluster / leave-one-block-out," AG9). No tuning — this is
the same house default used elsewhere in the CPI estate, adopted verbatim, not fitted to this family's data.
**Where:** Contract §8 item 2 (bootstrap CI bullet), §11 (multiplicity and trial budget — "bootstrap draws and
seed" line); YAML `validation.bootstrap.draws_and_seed`.
**Authority:** Sol, A4P authorization 2026-08-21.

---

## AP5 — FDR: no new writer; binding runner obligation recorded (registration stop condition, not code)

**What changed:** No new FDR-partition writer, schema, ledger, or store is built by this wave (out of scope,
per the A4P commission — code changes are prohibited in a records-only wave). `imce_hist_v0`, `q=0.10`, and
the exact six cell IDs (contract §1, §11) remain frozen in the binding preregistration MD/YAML, unchanged in
substance. `TrialLedger` (`engine/trial_ledger.py`) owns only the three declared family budget rows (§1 of
`IMCE_A4G_PROPOSED_A4_REGISTRATION_PACKET.md`) — it has no FDR-partition-registration mechanism (already
disclosed, `IMCE_A4G_PROPOSED_A4_REGISTRATION_PACKET.md` §5, M6 fix). AP5 adds a **binding runner obligation**
— a registration stop condition, not a code change — to contract §15/§15a: the future runner that actually
computes historical cell verdicts **must** assert, before applying BH correction, that (a) exactly six
verdict-bearing historical cells are being corrected, (b) they are exactly the six registered cell IDs
**[AP8, M2 fix — repointed: these are now minted and enumerated in contract §11 and YAML
`six_cell_ids_union`, not merely "named in `IMCE_A4G_SIX_CELL_DISPOSITION.md` §0" as the original AP5 draft
said before the IDs themselves existed; the disposition document uses the same IDs but is no longer the
source of them]**, and (c) one BH correction runs across their union at q=0.10 — no
seventh cell may silently enter the denominator (e.g. a diagnostic, a sensitivity re-run, or a future cell
from a different family).
**Where:** Contract §15/§15a (new stop condition — "the future historical-cell runner asserts exactly the six
registered `imce_hist_v0` cell IDs before BH correction, and applies exactly one correction at q=0.10 over
their union"); YAML `stop_conditions` (new entry), `fdr.partitions[0].note` (extended with the runner
obligation).
**Authority:** Sol, A4P authorization 2026-08-21.

---

## AP6 — Macro boundary receipts: first-party, non-outcome sources; Treasury availability recorded; storage basis unsettled

**What changed:** Attempts, from first-party non-outcome sources, to receipt the closed-block boundaries
still marked `not_yet_receipted` in `IMCE_A4G_SOURCE_BOUNDARY_TABLE.md` §6, without any issuer/ETF forward-
outcome access. **Full detail, sources, URLs, and verdicts: `IMCE_A4G_SOURCE_BOUNDARY_TABLE.md` §6
(rewritten) and new §7 (Treasury CSV/XML archive receipt).** Summary:
- **Treasury CSV/XML archive (Sol-directed verification):** Sol's A4P commissioning message independently
  asserts Treasury publishes the Daily Treasury Par Yield Curve Rates with CSV/XML export and archived
  historical files. This session attempted its own owner-direct re-verification: 3 `WebFetch` calls against
  `home.treasury.gov` (the TextView query page, an `interest-rates-data-csv-archive` alias, and the
  `daily-treasury-rate-archives` index) — **all 3 timed out at 60s**, reproducing the identical failure
  pattern the A4G wave recorded under MAJ-6. A `WebSearch` pass (not owner-direct) corroborates the archive's
  existence and structure via search-result summaries (archive index at
  `home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rate-archives`; a
  dedicated XML files page at
  `home.treasury.gov/policy-issues/financing-the-government/interest-rate-statistics/interest-rate-xml-files`)
  — CSV download, XML feed, and raw-XML download are all reported as available. **Recorded as: Sol-attested
  (CEO-level, treated as authoritative for the fact of availability) + session `S`-grade (search-summarized,
  not independently page-opened) — the underlying page remains un-opened by any session to date.** The
  reuse/storage basis (redistribution/persistence rights) is explicitly **NOT settled** by this record and no
  persistent ingestion occurs in this wave or any prior one — a future A4 registration or ingestion-design
  session must resolve the storage basis before any `C_t`/`M_t` field is built on Treasury CMT.
- **Three genuinely new first-party, dated, non-outcome receipts found this session** (all macro/monetary
  events, never an issuer/ETF price or return): (1) Federal Reserve, `federalreserve.gov` press release,
  **owner-page opened directly this session (`V`-grade)** — 2022-03-16, FOMC raised the federal funds target
  range to 0.25%–0.50% from 0–0.25%, the first hike of the 2022 tightening cycle. (2) NBER Business Cycle
  Dating Committee, `nber.org`, **owner-page opened directly this session (`V`-grade)** — announced 2020-06-08,
  peak in monthly economic activity February 2020. (3) NBER, `nber.org`, **owner-page opened directly
  (`V`-grade)** — announced 2021-07-19, trough in monthly economic activity April 2020. A fourth candidate
  (Freddie Mac PMMS record-low press release, Dec 24 2020, 2.66%) returned HTTP 403 on direct fetch and is
  recorded `S`-grade (search-summarized only, via `freddiemac.gcs-web.com`).
- **Governing scope discipline (unchanged from AG17, restated here so it is not silently forgotten):** the
  NBER dates are a **general U.S. business-cycle** determination, not a housing-sector-specific one — housing
  did not bust during the Feb–Apr 2020 NBER recession, it boomed. These receipts are recorded as
  **corroborating/bracketing context for the proposed month boundaries they are temporally adjacent to** (the
  Fed hike brackets the 2022-01 rate-shock start within ~2.5 months; the NBER peak/trough brackets the 2020-03
  pandemic-boom start within 1–2 months), **never as a boundary-dating citation that redefines a housing block
  boundary** — using a general-economy date to assert a housing-specific boundary would be exactly the
  wrong-instrument substitution AG17/M4 exists to prevent. **No boundary is changed by this ruling** — none
  of the newly-found evidence contradicts a proposed month boundary; every proposed month boundary remains
  within the search evidence's bracket. Per the ruling's own instruction — "if a proposed boundary cannot be
  supported by the source evidence, change it NOW with an amendment-log entry — never after outcome access"
  (the A4P commissioning text verbatim, not paraphrased) — no change is made because no boundary was found
  unsupported, only under-evidenced.
- **Remaining gap, honestly named, not silently left:** the exact month-level start/end boundary of every
  block (GFC bust, GFC recovery, the grind block, the 2018 air-pocket sub-episode, the rate-shock block's own
  end date) is **still `not_yet_receipted`** — no first-party, housing-sector-specific, dated macro-series
  print pinned to those exact months was found in this session's bounded research pass. This is the same
  finding the A4G wave reached with its own research effort (`IMCE_A4G_SOURCE_BOUNDARY_TABLE.md` §6, prior
  text) — a systematic macro-series boundary-dating pass across all block boundaries (lane-1 gap 11) remains
  open, unperformed by this wave, and is named as a GAP in this wave's return packet rather than resolved by
  inventing a date or misapplying a general-economy source to a housing-specific claim.
  **[AP8 correction, see below] The year-level-fallback claim previously made here relied on a fabricated
  composite quotation and has been corrected** — see AP8's own entry for the honest, separately-cited
  treatment of contract §3 (the block-list intro paragraph), the AG17 paragraph, and §15/§15a's stop
  condition, none of which may be spliced together as if they were one continuous quote.
**Where:** `IMCE_A4G_SOURCE_BOUNDARY_TABLE.md` §2 (row 13, Notes extended), §6 (rewritten with new receipts),
new §7 (Treasury archive receipt detail); no contract-MD or YAML change — AG17/AG18's existing law already
covers this ruling's disposition (record receipts, change nothing that lacks contradicting evidence, do not
ingest).
**Authority:** Sol, A4P authorization 2026-08-21.

**Revision note (2026-08-21, A4P revision, AP8, M6):** Fable's adjudication of the Opus red-team found this
entry's original framing overstated completion — it read as a satisfied ruling rather than a partial one.
**Corrected: ruling 6's status is PARTIALLY EXECUTED / OPEN, not satisfied.** Of the 8 boundary rows in
`IMCE_A4G_SOURCE_BOUNDARY_TABLE.md` §6, **zero month-level boundaries are receipted; none was changed** (no
contradicting evidence found); 2 genuinely new bracketing receipts were obtained (NBER peak/trough, 1 Fed
press release), which is real progress on the surrounding record but not itself boundary receipting.
Month-level receipting for the remaining boundaries is escalated to Sol in this wave's return packet.
**Separately: the Treasury CSV/XML archive row is UPGRADED from `S` to `V`** — the commissioning (Fable)
session obtained the receipt directly via a real browser on 2026-08-21 (page content, URL, page stamp, 161
2026-YTD entries, CSV/XML/archive links, and a genuine construction-break receipt: the 2021-12-06 HS→MC spline
methodology change), attributed exactly "obtained by commissioning session via direct browser access
2026-08-21" — distinct from this build worker's own repeated `WebFetch` failures (6 total across two
sessions, unchanged, retained for the record). Storage/reuse basis remains explicitly unsettled; no
ingestion occurs. Full detail: `IMCE_A4G_SOURCE_BOUNDARY_TABLE.md` §2 row 13 (rewritten) and §7 (rewritten).
Also fixed in this revision: boundary:134's "authoritative" framing is softened to "asserted by the
commissioning authority; not itself a source receipt" wherever the original Sol-attestation language remains
relevant context (superseded in substance by the new `V`-grade receipt, but the grading discipline — an
assertion is not itself a receipt — is preserved as a general principle).

---

## AP7 — A4 registration packet regenerated: hashes recomputed, not preserved

**What changed:** `IMCE_A4G_PROPOSED_A4_REGISTRATION_PACKET.md` is regenerated to reflect every AP1–AP6
change. The three proposed `declared_budget` row `reason` strings changed (the "block basis <=5 general / <=3
cancellation-scoped [AG5/AG6]" language is stale after AP2 hardens all six cells to B≤3 uniformly) — because
`config_hash` is `sha1(family + "\x00" + canon({"__declared_budget__": n, "reason": reason}))` (verified
against `engine/trial_ledger.py` lines 53–62, 159–190; no engine code executed, a standalone pure-function
check only), a changed `reason` string changes the hash. **All three row hashes are recomputed, not carried
forward from A4G** — see EVIDENCE in this wave's return packet for the exact recomputation commands and
before/after hash values. **[AP8, m8 fix] The three superseded (A4G-era) hashes, recorded here durably for
the audit trail rather than left only in git history:** `rf.cycle_pattern.imce_phase_v0` was
`29dce2d62989e7f1`, `rf.cycle_pattern.imce_sync_v0` was `76b9eb13dcc0fbf8`, `rf.cycle_pattern.imce_risk_v0`
was `82749c8a20babb5a` — each superseded by the A4P-regenerated hash in the packet's §2–§4 (unchanged again by
this AP8 revision, since no `reason` string changed in this revision — see EVIDENCE). The criteria-commit checklist (§6) is updated: the come-back date line now reads
~2149 (AP2), not ~2153; a new checklist item records the AP1 phase-target mapping and the
`IMCE_A4P_ORDER_SOFTNESS_STATE_CONSTRUCTION_V1.md` construction as a registration precondition; a new item
records the AP4 bootstrap freeze (800/seed 7) as already-settled rather than "not yet chosen"; a new item
records the AP3 100% prospective-share figure as already-settled; a new item records the AP5 FDR runner
obligation. §7 ("what this document does NOT do") is unchanged in kind — the packet still proposes, never
performs, registration. **[AP8 correction, F5] The "~2149" figure named just above is now itself stale
narration** — AP8's F1 fix corrects the promotion-relevant figure to **~2160** (zero historical credit) and
demotes ~2149 to an explicitly-labeled non-promotion diagnostic; packet §6's checklist item now reads ~2160
as the promotion clock, not ~2149. This sentence is the correction; the paragraph above is left as the
historical record of what AP7 originally did.
**Where:** `IMCE_A4G_PROPOSED_A4_REGISTRATION_PACKET.md` (rewritten in full — §1 recomputation basis, §2–§4
new reasons/hashes, §6 checklist updated).
**Authority:** Sol, A4P authorization 2026-08-21 (ruling 7 — regenerate the packet after rulings 1–6).

---

## AP8 — Same-branch revision: fixes from two rounds of Fable's adjudication of Opus red-team passes on PR #6213

**Wave:** A4P, same branch (`claude/imce-a4p-criteria-closure`), two revision rounds, both same-day
2026-08-21. **Records-only** — no `data/` write, no outcome access, no trial family registered, no engine
code changed, no `reason` string changed on any `declared_budget` row (all three hashes re-verified stable
across both rounds).
**Authority:** Sol, A4P authorization 2026-08-21, via Fable's adjudication of two Opus red-team passes.
**Scope note:** this single entry consolidates BOTH revision rounds rather than splitting into AP8/AP9, since
both rounds landed on the same commissioning authorization and the same branch before any merge — every fix
below is tagged with its originating finding code (round 1: B1/B2/M1–M7/m1–m8/n1–n2; round 2: F1–F8 + the M2
inline nit) and the file(s) it touches. **This entry resolves the dangling "see the AP8 entry" pointers left
at AG4's original text (above) and in the Summary table's AP8 row (below) — both now resolve here.**

### Round 1 — 2 blockers + 7 majors + minors

- **B1 (blocker, fabricated composite quotation):** Deleted a composite quote that spliced contract §3's
  month-boundary clause into the AG17 paragraph via an ellipsis, presenting it as one continuous "AG17"
  quote and eliding §15/§15a's unconditional-sounding stop-condition wording. Contract §3, the AG17 paragraph,
  and §15/§15a are now cited separately with their true, non-overlapping scopes, plus an honestly-labeled
  inference (not a stated contract rule) reconciling them. **Where:** `IMCE_A4G_SOURCE_BOUNDARY_TABLE.md` §6
  (rewritten "Where an unreceipted boundary may be used..." passage); this log's AP6 entry (corrected bullet).
- **B2 (blocker, GFC-block readmission risk):** The `order_softness` construction now states explicitly (new
  §3.0) that block admissibility for the six registered cells is governed exclusively by the contract's
  registered block list — the construction computes states, it never admits a block; GFC bust/recovery stay
  unusable regardless of input availability. Added a ≥2-issuer floor (§3.1) before any cohort state may be
  minted, citing AG14's existing bar on a single-issuer reading wearing a cohort label. **Where:**
  `IMCE_A4P_ORDER_SOFTNESS_STATE_CONSTRUCTION_V1.md` §3.0, §3.1.
- **M1 (bootstrap unit):** Corrected "month/episode-block" to the registered macro-block cluster (the same
  unit AG9 already uses for inference); disclosed that `engine/grading_stats.py`'s `BOOT_DRAWS`/`BOOT_SEED`
  (800/7) supply only numeric defaults, never its date-blocked resampling unit; disclosed that a 3-cluster
  bootstrap is near-degenerate. **Where:** contract §8 item 2, §11; YAML `validation.bootstrap`.
- **M2 (six cell IDs):** Minted and froze `imce_phase_v0.next_order_softness_1rp` /
  `.next_order_softness_3rp` / `.order_softness_false_repair_3rp`, `imce_sync_v0.next_order_softness_1rp` /
  `.forward_63d_drawdown_tail`, `imce_risk_v0.forward_63_trading_day_drawdown_tail` — presented to Sol for
  ratification. **Where:** contract §11 (new table); YAML `trials[].cell_ids` / `six_cell_ids_union`;
  `IMCE_A4G_SIX_CELL_DISPOSITION.md` §0 table and per-cell headers.
- **M3 (packet restricted to exactly Sol's four A4 acts):** Deleted the invented separate "FDR-partition
  registration" act and its "enforced assertion" requirement (contradicted Sol's own ruling 5 — no new
  writer at A4); restated the runner obligation as binding a FUTURE evaluation-runner wave, not A4; froze
  `n_issuer_precision_diagnostic` as the exact field name (was TBD); deleted "execute verbatim or amend
  before executing," replaced with "execute verbatim or abort back to Sol." **Where:**
  `IMCE_A4G_PROPOSED_A4_REGISTRATION_PACKET.md` §5, §6 (rewritten), §7; contract §3 (`n_issuer_precision_diagnostic`); YAML `effective_block_law.within_block_issuer_dependence.field_name`.
- **M4 (come-back arithmetic, round 1 pass):** Recomputed on the B=3 basis (~2149), superseding the AG5 B=5
  basis (~2153) — **this round-1 fix was itself incomplete; see F1 below for the full correction to a
  zero-historical-credit promotion clock (~2160).**
- **M5 (census annotations):** Two additive-only annotation blocks added to
  `IMCE_HB0_SOURCE_DEFINITION_CENSUS_V1.md` at the three cited points — 12 insertions, 0 deletions, original
  A3 text untouched, per Sol's bar on reopening A3 work (newly granted owned-file scope).
- **M6 (ruling 6 honesty + Treasury receipt, round 1 pass):** Reframed as "PARTIALLY EXECUTED/OPEN, 0/8
  boundaries receipted, none changed"; recorded 3 new dated first-party bracketing receipts (NBER x2, Fed);
  Treasury CMT graded `S` (Sol-attested + search-corroborated only) — **round 1 did not yet have the real
  browser-obtained receipt; that arrived in round 2, see F-round-2's M6 continuation below.**
- **M7 (fail-closed era-coverage gate):** Checked `research/imce/hb0/evidence/L2/L3/L4_defs_*.md` — PHM and
  KBH carry `[VERIFIED]`-grade net-orders receipts covering 2014–2023; DHI and TOL carry only
  `INF`/`[SOURCE CLAIM]` grade. Added construction §1a: DHI/TOL contribute `NOT_RECONSTRUCTABLE` on orders
  for 2014–2023; coverage impact recorded in the disposition; escalated to Sol.
- **Minors m1–m8, n1–n2:** false-repair/relapse rule frozen exactly (construction §4); missing-orders-input
  lookup row split out (construction §2); AG12 TOL backlog-sensitivity registered as a mandatory diagnostic
  (construction §1b); (two-way) tie rule stated (construction §3.1, later extended to three-way by round 2's
  F2/F3 work); YAML prospective share made a non-numeric token (later corrected to numeric `1.0` by round 2);
  disposition's dangling "§4 open item" pointer fixed to "§4 CLOSED"; construction file named
  incorporated-by-reference (later formalized fully by F6 below); the three superseded A4G-era row hashes
  recorded durably in this log's AP7 entry; `hb0/` path prefix fixed in the construction file's §0; the
  boundary table's "XHB ETF drawdown" phrasing annotated as narrative-only, never a receipt.

### Round 2 — 1 blocker-class carryover + majors + nits (this pass)

- **F1 (blocker — M4's round-1 fix never reached the YAML or a corrective log note):** Rewrote YAML
  `prospective_law.come_back_date`: added `promotion_clock_estimate` (~2160, work shown: `2026.6667 + 40 ×
  (10.0/3) = 2160.0`); renamed the ~2149/~2153 fields to `non_promotion_diagnostic_b3_total_block_estimate` /
  `non_promotion_diagnostic_prior_basis_b5`; rewrote `recomputation_arithmetic` to the ~2160 form. Added an
  explicit `[AP8 correction, F1]` note directly after this log's AP2 come-back bullet stating ~2160 is the
  promotion-relevant figure and ~2149 is a non-promotion diagnostic. **Where:** YAML
  `prospective_law.come_back_date` (rewritten); this log's AP2 entry (correction note added).
- **F2 (major — AG14 contradiction, conservative resolution, no new authority minted):** (a) Historical
  `order_softness` reads (2014–2023) are now labelled `named_subset_basis: [PHM, KBH]` under AG14's
  three-issuer-subset discipline, never presented as full-cohort claims until DHI/TOL receipts exist; the
  PROSPECTIVE arm keeps the genuine cohort basis/label. (b) Contract's AG14 bullet ("disclosed... by all six
  roster issuers") now carries a scope note: broadly cohort-observable PROSPECTIVELY; historical
  reconstruction is currently limited to {PHM, KBH}. (c) Stated as two distinct thresholds: the ≥2-issuer
  floor (minimum to mint ANY pooled state) vs. the stricter, separate question of whether that state may
  carry the cohort LABEL. (d) Escalated to Sol: whether a ≥2-contributor read may ever bear the cohort label;
  named-subset labelling governs until ruled. **Where:** contract §2 Homebuilders (AG14 bullet, two new
  passages); `IMCE_A4P_ORDER_SOFTNESS_STATE_CONSTRUCTION_V1.md` §1a (new labelling paragraph), §3.1;
  `IMCE_A4G_SIX_CELL_DISPOSITION.md` §1 (labelling-consequence paragraph, per-cell rows for Cells 1–2).
- **F3 (major — unstated consequences of the M7 era gate, named for Sol's ratification review):** (1)
  Composing the §1a orders gate with the cancellation-rate eras (PHM FY2016+, KBH FY2008+): the grind block
  yields ZERO cohort states before FY2016 (PHM's cancellation input is `missing` until then, leaving KBH as
  sole contributor, below the ≥2 floor) — usable window is FY2016–2019, not the full 2014–2019 span. (2)
  With exactly two eligible historical contributors, every non-null, non-`MIXED` cohort state is
  definitionally a PHM–KBH agreement indicator — no historical reading is broader than that. **Where:**
  `IMCE_A4P_ORDER_SOFTNESS_STATE_CONSTRUCTION_V1.md` §1a (new "Unstated consequences" block);
  `IMCE_A4G_SIX_CELL_DISPOSITION.md` §1 (new "Unstated consequences" paragraph).
- **F4 (major — this AP8 entry itself):** Round 1 tagged dozens of fixes `[AP8, ...]` inline but never added
  a formal `## AP8` log entry, leaving `[AP8, M3(b)]`'s "see the AP8 entry below" (AG4's original text) and
  the Summary table's AP8 row ("see the AP8 entry above") dangling. This entry is that fix. Both section
  titles carrying "(AP1–AP7)" (this file's own header, and the A4P section's own title) are corrected to
  "(AP1–AP8)".
- **F5 (minor):** This log's AP7 entry narrated "the come-back date line now reads ~2149" as if that were the
  final state — corrected with an explicit note that ~2160 (not ~2149) is the packet's promotion-clock figure
  after F1.
- **F6 (minor — the "lossless" claim was never literally true):** Contract's A26 binding-rule header rewritten:
  the binding surface is the contract MD PLUS `IMCE_A4P_ORDER_SOFTNESS_STATE_CONSTRUCTION_V1.md` (incorporated
  by reference, named normatively); the YAML is a machine-readable projection of the REGISTRATION-RELEVANT
  FIELDS of both (carrying the construction file by path, never inlining it) — "lossless" dropped as
  inaccurate. **Where:** contract header (binding-rule line), Appendix A row A26; YAML header comment.
- **F7 (nit):** Disposition's per-cell "pooled population {DHI, PHM, KBH, TOL}" rows (Cells 1–2, inherited by
  Cells 3–6 via "same as Cell 1") now distinguish the nominal roster from the currently-eligible historical
  contributors {PHM, KBH}, pointing to construction §1a.
- **F8 (nit):** Boundary table §7 now notes the Treasury 2021-12-06 HS→MC construction break falls inside the
  pandemic-boom block (2020-03→2021-12) — impact nil for the six registered cells, since Treasury CMT is a
  candidate `C_t` leg only, never an `order_softness` construction input.
- **M2 inline nit:** The six cell ID strings are now inlined directly in the packet §6 checklist item, not
  only pointed to by reference, so the packet reads self-contained.

**Where (round 2, consolidated):** `IMCE_PREREGISTRATION_CANDIDATE_V1.yaml` (`prospective_law.come_back_date`,
header comment); this log (AP2 entry correction, this AP8 entry, header titles); contract MD (A26 header,
Appendix A row, AG14 bullet); `IMCE_A4P_ORDER_SOFTNESS_STATE_CONSTRUCTION_V1.md` (§1a, §3.1);
`IMCE_A4G_SIX_CELL_DISPOSITION.md` (§1, per-cell rows); `IMCE_A4G_SOURCE_BOUNDARY_TABLE.md` (§7);
`IMCE_A4G_PROPOSED_A4_REGISTRATION_PACKET.md` (§6 checklist item).
**Authority:** Sol, A4P authorization 2026-08-21, via Fable's adjudication (round 2) of an Opus red-team pass
on PR #6213 at head `fec9e1c345a396f177618fb0a57a6ca6f0e499ed`.

---

## A4P Summary table

| # | Ruling (one line) | Contract section(s) | Resolves |
|---|---|---|---|
| AP1 | Phase-family targets mapped to `order_softness`; deterministic construction frozen | §1, §2, §15/§15a; new file | AG14/MAJ-5 open item |
| AP2 | All six v0 historical cells cancellation-scoped, B≤3 | §1, §2, §3, §9a | Six-cell disposition §4 (Cells 5–6 conditional item) |
| AP3 | Minimum prospective share for promotion = 100%, machine-readable | §13 | remaining TBD |
| AP4 | Bootstrap: 800 draws, seed 7 (house default value convention) | §8, §11 | bootstrap draws/seed line |
| AP5 | No new FDR writer; binding runner obligation (six-cell assertion, one BH correction) | §15/§15a | — |
| AP6 | Macro boundary receipts: PARTIALLY EXECUTED/OPEN (0/8 boundaries receipted, none changed); Treasury `V`-grade receipt (AP8 revision) | `IMCE_A4G_SOURCE_BOUNDARY_TABLE.md` §2/§6/§7 | partial — lane-1 gap 11 remains open, escalated to Sol |
| AP7 | A4 packet regenerated; row hashes recomputed (reason strings changed) | packet §1–§6 | — |
| AP8 | Same-branch revision: fixes 2 blockers + 7 majors + minors from Fable's adjudication of the Opus red-team pass on PR #6213 — see the AP8 entry above and this log's revision notes on AP2/AP5/AP6 | §3, §8, §11, §13, §15/§15a, Appendix A/B/C headers; construction file; disposition; boundary table; packet; census annotations | corrects B1/B2/M1–M7 and all named minors |

---

---

## A4P.1 (fourth gate, 2026-08-22)

**Wave:** A4P.1 — Sol's fourth-gate REQUEST_CHANGES preflight closure. Records-only. No `data/` write, no
outcome access, no registration act. A4P accepted its own architecture (amendments AP1–AP8 are FINAL, never
reopened or rewritten by this section); Sol returned bounded REQUEST_CHANGES — seven rulings (R1–R7) closing
every remaining field A4 proper would otherwise have had to invent, interpret, or choose.
**Authority for every ruling below:** Sol, fourth-gate verdict, 2026-08-22.
**Scope discipline:** every ruling below is RECORDS-ONLY. None writes `data/trial_ledger.jsonl`, accesses any
outcome, or registers the three `rf.cycle_pattern.imce_*` families. Registration remains a separate, future
A4/IMCE-03 act — this wave freezes A4's transition table; it performs none of the flips.

### AP9.R1 — Retire the stale DEFF machine-readable denomination

**What changed:** `IMCE_PREREGISTRATION_CANDIDATE_V1.yaml`'s `coverage_abstention_claims` claim class carried
a live `denomination: effective_blocks_under_independent_shock_law_with_deff` field — a machine-readable
description still naming the struck DEFF construction (AG3) as the `n_effective_blocks` law, three gates after
AG3 struck it. Replaced with `denomination: independent_shock_blocks_capped_at_raw_closed_B`. The YAML's
already-`status: struck` `deff_formula_as_n_definition` block is compliant historical/struck record and is
left unchanged, per Sol's own carve-out ("historical/struck explanatory text may remain clearly marked as
struck"). A census of every registration-relevant artifact found no other LIVE machine-readable field
describing DEFF/ρ as the `n_effective_blocks` law — the only live hit was the YAML field itself
(`grep -rn "effective_blocks_under_independent_shock_law_with_deff" research/ agentos/ config/ engine/
scripts/` → 1 hit, now fixed, 0 remaining). The hb0 lane-2 artifacts (`IMCE_HB0_BLOCKERS_AND_FALSIFIERS.md`
B7; `IMCE_HB0_INDEPENDENT_BLOCK_LIST.md` D4 and §8; `IMCE_HB0_A4_CELL_BUDGET_INPUTS.md` §3 and item 10) still
carried LIVE prose recommending A4 register `rho_block` or print issuer-DEFF `n_effective_blocks` counts —
these are A3 lane-2 census artifacts, not the registration law, and per Sol's `[A4P.1]` annotation-only
convention they gain additive supersession notes marking those recommendations superseded by AG3 (DEFF struck)
and this ruling: A4 will not register any `rho`/`rho_block` value or print an issuer-DEFF `n_effective_blocks`
count.
**Census completion, red-team round 1 (MIN-2), pre-existing on main, not a regression:** YAML
`predetermined_historical_status.label_assignment` carried the value
`mechanical_by_preregistered_n_eff_vs_floor_computed_pre_outcome_never_post_hoc` — a bare `n_eff` token inside
the same class of live machine-readable field MAJ-4 (A4G) already swept from contract §12's prose. Renamed to
`mechanical_by_preregistered_n_effective_blocks_vs_floor_computed_pre_outcome_never_post_hoc`, comment-tagged
`[A4P.1 R1]`. This value predates A4P.1 (it was untouched since the original A4G MAJ-4 sweep, which fixed only
the contract MD's prose, never this YAML value) — it is a census gap this ruling's own R1 scope closes, not a
new defect introduced by this wave.
**Where:** YAML `prospective_accrual_first_posture.claim_classes[coverage_abstention_claims].denomination`;
`IMCE_HB0_BLOCKERS_AND_FALSIFIERS.md` (annotation after the B7 table row); `IMCE_HB0_INDEPENDENT_BLOCK_LIST.md`
(annotations after §D4 and after §8); `IMCE_HB0_A4_CELL_BUDGET_INPUTS.md` (annotations after §3's table and
after §5 item 10) — all four annotations additive-only, zero deletions of original A3 lane-2 text.
**Authority:** Sol, fourth-gate ruling R1, 2026-08-22.

### AP9.R2 — Freeze population and label semantics: historical v0 = named_subset_basis [PHM, KBH], permanent

**What changed:** Sol verbatim: *"Historical v0 population is permanently: named_subset_basis: [PHM, KBH] for
the six registered historical cells. Later DHI/TOL archaeology may improve descriptive evidence or support a
future v1, but may not widen v0 after registration. Prospective v0 eligible pooled cohort: [DHI, PHM, KBH,
TOL]. Label rule: 4/4 reconstructable → cohort; 2–3 reconstructable → named_subset + exact contributor list;
<2 → NOT_RECONSTRUCTABLE. Replace misleading live registration prose such as 'pooled homebuilder stratum'
wherever it would imply the historical v0 population is wider than PHM/KBH."* This closes AP8's own open
escalation F2(d) ("whether a ≥2-contributor `order_softness` read may ever bear the cohort label") — Sol's
three-row label rule answers it for every contributor count, not only the ≥2 floor case; named-subset
labelling continues to govern every historical read today (the eligible historical roster remains exactly
{PHM, KBH} — two contributors), but the rule now applies without a further Sol roundtrip once DHI/TOL era
receipts land or the prospective arm mints a 3- or 4-contributor state.
**Implementation:** (a) YAML gains machine-readable fields under `state_vector_observability_scoping.order_softness`
— `historical_v0_population` (`named_subset_basis: [PHM, KBH]`, `permanent_for_v0: true`,
`may_widen_v0_after_registration: false`), `prospective_v0_eligible_pooled_cohort: [DHI, PHM, KBH, TOL]`, and
`label_truth_table` (the three-row rule, machine-readable); `d5_state_construction_pooled_issuers` is clarified
in place as the PROSPECTIVE eligible cohort, not the historical population. (b) `cell_definition` strings and
prose reworded at: YAML `trials[0].cell_definition`; contract MD §1 (the `imce_phase_v0` row); disposition §0;
packet §2 (row and prose); construction file §3.1 (its own :202-area opening sentence) — each now states the
historical v0 population is the PHM/KBH named subset while the prospective v0 eligible cohort is `[DHI, PHM,
KBH, TOL]` under the label truth table, replacing every live "pooled homebuilder stratum" occurrence with an
annotation-marked "was" note. (c) HB0 census `IMCE_HB0_SOURCE_DEFINITION_CENSUS_V1.md`'s existing AP1/AP2
supersession annotation block (added in the A4P wave) already covers this population reframing generally; no
further edit was required there beyond what AP9.R3 also touches. (d) The construction doc's existing §3.1
(≥2-contributor floor, tie⇒MIXED, `named_subset_basis: [PHM, KBH]` historical reads) was found already
consistent with the truth table — no conflict, so nothing beyond §1a's F2(d) closure and §3.1's :202-area
wording was touched in that document, per Sol's own caution against a silent fix on any apparent conflict.
**Census (`pooled homebuilder stratum`), grep after edit:** every remaining hit is inside an annotation
bracket ("was 'pooled homebuilder stratum'") — zero live, unannotated occurrences remain.
**Where:** YAML (as above); contract MD §1; `IMCE_A4G_SIX_CELL_DISPOSITION.md` §0; `IMCE_A4G_PROPOSED_A4_REGISTRATION_PACKET.md`
§2; `IMCE_A4P_ORDER_SOFTNESS_STATE_CONSTRUCTION_V1.md` §1a (F2(d) closure), §3.1 (wording).
**Authority:** Sol, fourth-gate ruling R2, 2026-08-22.

### AP9.R3 — Final cell-ID ratification + sync-family naming normalization

**What changed:** Sol ratifies, verbatim, the exact freeze of the six cell IDs minted at AP8/M2:
`imce_phase_v0.next_order_softness_1rp`, `imce_phase_v0.next_order_softness_3rp`,
`imce_phase_v0.order_softness_false_repair_3rp`, `imce_sync_v0.next_order_softness_1rp`,
`imce_sync_v0.forward_63_trading_day_drawdown_tail`, `imce_risk_v0.forward_63_trading_day_drawdown_tail` — with
one normalization: *"Normalize the sync family's target nomenclature from forward_63d_drawdown_tail to
forward_63_trading_day_drawdown_tail anywhere that field identifies the actual target/cell. Both market-risk
cells bind to the same canonical 63-trading-day QLedger ruler; family prefix distinguishes the tests."* This
closes the prior wave's escalation item 4 (ratification of the six minted cell IDs).
**Implementation:** every LIVE registration-relevant site naming `forward_63d_drawdown_tail` normalized to
`forward_63_trading_day_drawdown_tail`: YAML (`trials[1].cell_definition`, `trials[1].cell_ids`,
`trials[2].cell_definition`, `six_cell_ids_union`); contract MD (§1 table, §3 AP2 paragraph, §11 table); six-cell
disposition (§0 table, Cell 5 header + Target row + observability row); packet (all three reason strings — see
AP9.R7 — plus the §3/§4 prose, the §6 precondition checklist's inlined cell-ID list). Historical record sites
(this log's own AG5 entry line and M2-minor entry) STAY as historical statements — they describe what was
minted BEFORE this normalization, not the current law; this new section is where the ratification +
normalization is recorded going forward. HB0 census `IMCE_HB0_SOURCE_DEFINITION_CENSUS_V1.md`'s two rows
naming the old cell definition (`imce_sync_v0`/`imce_risk_v0` rows in the §6b table) are A3-original text and
are left untouched, additive-only, per the existing supersession-annotation pattern (already covers naming
drift generally; no new annotation was needed beyond what already reads "come-back figure superseded" etc.
since those exact two table cells are not independently quoted elsewhere in this wave's tests).
**Census (`forward_63d_drawdown_tail`), grep after edit:** every remaining hit is either inside this log's own
historical AG5/M2 entries (lines ~307, ~570 — genuine historical statements, correctly unmodified) or inside
an annotation bracket ("was `forward_63d_drawdown_tail`") in a live document.
**Where:** YAML (as above); contract MD §1, §3, §11; `IMCE_A4G_SIX_CELL_DISPOSITION.md` §0 and Cell 5;
`IMCE_A4G_PROPOSED_A4_REGISTRATION_PACKET.md` §3, §4, §6.
**Authority:** Sol, fourth-gate ruling R3, 2026-08-22.

### AP9.R4 — Freeze the complete A4 registration state-transition, verbatim-or-abort

**What changed:** Sol verbatim: *"The A4 packet must say exactly what becomes true at registration... Search
for mutually contradictory registration-state fields. There must be one state, not a registered bit nested
inside a document that still calls itself candidate/not-declared."* A new packet section, §4a "A4 STATE
TRANSITION (frozen, verbatim-or-abort)", enumerates EVERY registration-state site across the contract MD, the
YAML, and the packet's own registration-state prose, with byte-exact old→new replacement pairs: YAML `status`,
`registration.registered`, `.repository_pin_observed`, `.config_hash`, `.freeze_location`'s second bullet,
top-level `requires_fable_adjudication`, and all three `trials[].status` fields; contract MD's opening Status
line and its §15a freeze-location/repository-pin bullets; and **the packet's own H1 title, §0 opening
paragraph (full — not merely its bold STATUS sentence), `Wave:` line's closing clause, and `Purpose:` line's
"PROPOSED — NOT REGISTERED" marking clause** [§4a.4, red-team round 1, MAJ-1 fix — the original version
covered only the packet's opening bold sentence, which would have left the untouched remainder of that same
paragraph, plus three more live sites, reading "future act"/"registers nothing"/"PROPOSED — NOT REGISTERED"
directly beneath a freshly-stamped "EXECUTED — REGISTERED" line, exactly the nested-contradiction defect
Sol's ruling forbids]. Three placeholder procedures are frozen deterministically [expanded from two,
red-team round 1, FIX-9/FIX-10]: `repository_pin_observed` = the full 40-hex SHA of `origin/main` observed at
A4 pickup via `git rev-parse origin/main`, recorded before any A4 edit; `registration.config_hash` = the git
blob SHA-1 of the contract MD **as stamped registered** in the A4 commit, via `git hash-object`, computed
AFTER the MD's frozen transition edits and BEFORE writing the YAML — the hash lands only in the YAML, never
self-referenced in the MD, and MUST be re-verified against the actually-committed head immediately before any
push, aborting and repairing on any mismatch (closes a silent-invalidation hole a later same-PR MD edit could
otherwise open); `<A4 registration commit date>` = the UTC calendar date, ISO-8601 `YYYY-MM-DD`, via `date -u
+%F`, observed at the moment the A4 registration commit is created. **A4P.1 itself performs NONE of these
flips** —
`IMCE_PREREGISTRATION_CANDIDATE_V1.yaml` and `IMCE_PREREGISTRATION_AND_EVALUATION_CONTRACT_V1.md` both stay
`candidate_not_registered`/unregistered after this wave lands, byte-identical on every registration-state field
to their pre-A4P.1 values (only the version/gate header fields and the R1/R2/R3/R5/R6 substantive fields this
log documents elsewhere changed). §6's four-acts list is updated to cross-reference this table and to record
Sol's explicit conditional authorization (quoted verbatim in AP9's closing section below) to start A4 proper
without a further Sol roundtrip, provided A4P.1 lands exactly as frozen with no new substantive finding.
**Registration-state contradiction census (candidate_not_registered / not_declared / "future act" /
not-yet-performed tokens), run after every other A4P.1 edit landed:** every live hit across the owned files is
either (a) the CURRENT, coherent, unregistered candidate state — the same value on every site, with a frozen
transition row in §4a above naming its exact A4-time replacement — or (b) a historical/log record (this log's
own closing sentences, correctly describing what remains a future act). `IMCE_CELH1_CYCLE_AUTOPSY_V1.md`'s own
`candidate_not_registered` status line is a DIFFERENT artifact (the A1 CELH autopsy record, not this family's
registration state) and is out of this wave's owned-file scope — noted, not touched. No contradiction was
found: no site claims `registered`/`declared` while a sibling site claims `candidate_not_registered`/
`not_declared` for the same family.
**Where:** `IMCE_A4G_PROPOSED_A4_REGISTRATION_PACKET.md` (new §4a, and §6 cross-references) — no change to any
live registration-state field in the contract MD or YAML.
**Authority:** Sol, fourth-gate ruling R4, 2026-08-22.

### AP9.R5 — Treasury CMT source-rights disposition: GO_LIMITED

**What changed:** Sol verbatim: *"Update the source-rights record: TREASURY_CMT = GO_LIMITED. Scope: internal
research persistence/use of the Treasury-published Daily Treasury Par Yield Curve values with first-party
Treasury provenance, retrieval timestamp, and methodology/source reference. Basis: Treasury is the publishing
federal agency; 17 U.S.C. §§101/105 place U.S.-Government works prepared as official duties outside U.S.
copyright protection. This does not grant rights to unrelated external/third-party content, linked datasets,
or raw underlying third-party quotations. PMMS remains HELD. FRED/ALFRED remain excluded. NAR storage remains
prohibited."* This closes the prior wave's escalation item 5 (Treasury CMT storage/reuse basis, previously
recorded as "REMAINS unsettled"). GO_LIMITED authorizes a FUTURE ingestion-design session only — this wave
still ingests nothing; no `data/` write and no persistent CMT ingestion occurs.
**Implementation:** `IMCE_A4G_SOURCE_BOUNDARY_TABLE.md` row 13 (Notes cell), §4 ("Interim primary rate leg"
bullet), and §7 ("Storage/reuse basis" closing paragraph) all rewritten from "REMAINS/STILL... unsettled" to
"SETTLED: GO_LIMITED," quoting Sol's ruling verbatim and attributed "Sol fourth-gate ruling R5, 2026-08-22";
§5's affordability-leg table Rate row updated to match. Contract MD §3's AG17 paragraph gains a short mirror
sentence pointing to the boundary table for the full ruling (this is a rights-disposition ruling, not a
boundary-receipt ruling — it is recorded in the boundary table's own Treasury row, not the boundary-date
table). YAML `rights_safe_macro_legs_only.treasury_cmt` gains `rights_disposition: GO_LIMITED` plus
`rights_disposition_scope`, `rights_disposition_basis`, `rights_disposition_excludes`, and
`rights_disposition_authorizes_future_ingestion_design_only: true` fields. PMMS, FRED/ALFRED, and NAR rows and
fields are UNCHANGED — PMMS stays `status: held`, FRED/ALFRED stay `fred_clause: q_do_not_ingest_binds_all_use_classes_incl_display_tier`,
`nar_series.may_be_stored: false` is untouched.
**Where:** `IMCE_A4G_SOURCE_BOUNDARY_TABLE.md` row 13, §4, §5, §7, header note; contract MD §3 (AG17
paragraph, one sentence); YAML `rights_safe_macro_legs_only.treasury_cmt`.
**Authority:** Sol, fourth-gate ruling R5, 2026-08-22.

### AP9.R6 — Boundaries remain honestly open; no receipt fabricated

**What changed:** Sol verbatim: *"Do not fabricate boundary receipts to make A4 green. A4 registration is
allowed with those receipts still open because the binding law is: no unreceipted boundary may be used to
partition an outcome run. After registration, a boundary evidence wave may either: receipt the already-frozen
v0 boundary from a lawful first-party source; or mark that block NOT_RECONSTRUCTABLE_FOR_V0_OUTCOME_PARTITION.
It may not move a registered v0 boundary after inspecting outcomes. A scientifically necessary different
boundary becomes a new preregistration/version."* No boundary receipt is invented by this ruling — every
boundary in `IMCE_A4G_SOURCE_BOUNDARY_TABLE.md` §6 that was `not_yet_receipted` before this wave stays exactly
that after it.
**Implementation:** YAML `effective_block_law` gains a new `post_registration_boundary_evidence_law` block —
`registration_permitted_with_open_boundary_receipts: true`; `post_registration_options` naming exactly the two
Sol-named dispositions (including the literal token `NOT_RECONSTRUCTABLE_FOR_V0_OUTCOME_PARTITION`);
`registered_v0_boundary_may_move_after_outcome_inspection: false`; `different_boundary_requires:
new_preregistration_version`. `month_boundaries_receipt_status: proposed_not_yet_receipted` is UNCHANGED.
Mirrored in contract MD §3 (a new sentence appended to the existing AG17 paragraph) and in
`IMCE_A4G_SOURCE_BOUNDARY_TABLE.md` §6's own preamble (a new paragraph quoting Sol verbatim, immediately after
the existing "no date below is invented" sentence).
**Where:** YAML `effective_block_law.post_registration_boundary_evidence_law`; contract MD §3 (AG17 paragraph);
`IMCE_A4G_SOURCE_BOUNDARY_TABLE.md` §6 preamble.
**Authority:** Sol, fourth-gate ruling R6, 2026-08-22.

### AP9.R7 — Regenerate the A4 rows/hashes

**What changed:** Sol verbatim: *"Because the population wording and canonical target naming change,
regenerate all affected declared_budget reason strings and hashes from the actual corrected packet. Do not
preserve an old hash merely because it was correct for V1.2 before A4P.1. Verify exact hash parity using the
existing engine/trial_ledger.py implementation without writing the production ledger."* All three reason
strings in `IMCE_A4G_PROPOSED_A4_REGISTRATION_PACKET.md` (§2–§4) were rewritten to V1.2.1 (A4P.1-amended)
wording carrying the PHM/KBH named-subset population phrasing (AP9.R2), the canonical
`forward_63_trading_day_drawdown_tail` naming (AP9.R3), and the unchanged binding citations (contract MD +
this log). Each family's `config_hash` was recomputed with the ACTUAL implementation: `engine/trial_ledger.py`'s
`_hash`/`_canon` functions were imported READ-ONLY (never `TrialLedger`, never `log_declared_budget`, never a
write to any ledger file, production or temp) and applied to the exact declared-budget config dict the module
itself constructs, `{"__declared_budget__": n, "reason": reason}`, keyed per `_hash(family, config) =
sha1(f"{family}\x00{_canon(config)}").hexdigest()[:16]` with `_canon = json.dumps(config, sort_keys=True,
default=str, separators=(",", ":"))` — read from the module before assuming its shape, not guessed. A
standalone scratchpad script computed all three hashes and was independently cross-checked with a second,
hand-inlined implementation of the identical formula (no import), which reproduced byte-identical output —
confirming the recomputation is not an artifact of the import path.

| Family | n | NEW `config_hash` (V1.2.1) | Superseded `config_hash` (V1.2) |
|---|---|---|---|
| `rf.cycle_pattern.imce_phase_v0` | 3 | `a3b8ac5c0d0205cb` | `d4fb6b5f517fe32c` |
| `rf.cycle_pattern.imce_sync_v0` | 2 | `1d69c1fa6b897b6a` | `f76dc44e1f5edc18` |
| `rf.cycle_pattern.imce_risk_v0` | 1 | `309d76c3a8dfbb5c` | `3eff3ee65158e41b` |

All three superseded V1.2 hashes are recorded above, never silently dropped, per Sol's own instruction.
**Where:** `IMCE_A4G_PROPOSED_A4_REGISTRATION_PACKET.md` §2–§4 (reason strings + `config_hash` values), §1
(regeneration note).
**Authority:** Sol, fourth-gate ruling R7, 2026-08-22.

### Sol's conditional authorization for A4 proper

Recorded verbatim — **Sol fourth-gate verdict, 2026-08-22 (relayed verbatim in the A4P.1 commissioning
instruction)** [red-team round 1, MAJ-2 adjudicated by Fable, who holds Sol's actual message: this quote and
the four-act list below are CONFIRMED verbatim Sol, not the commissioning session's own text — only the
attribution is sharpened here, the quoted content is unchanged]: *"If—and only if—A4P.1 lands exactly as above
with no new substantive finding, you do not need another Sol roundtrip to start A4 proper. This message is the
explicit conditional authorization."* The A4-proper act list, verbatim: *"1. observe and record current
repository pin; 2. append the three exact frozen declared_budget rows to canonical data/trial_ledger.jsonl;
3. stamp the complete registered MD/YAML state and contract hash exactly as frozen by A4P.1; 4. record/prove
that no outcome access occurred before the criteria/registration commit."* These four acts map exactly onto
`IMCE_A4G_PROPOSED_A4_REGISTRATION_PACKET.md` §6's existing four-acts numbering (Act 1↔1, Act 2↔2, Act 3↔3,
Act 4↔4), now cross-referencing the frozen §4a transition table for Acts 1 and 3.

### Revision record — red-team round 1 (Opus, adjudicated by Fable, 2026-08-22)

**Verdict: REVISE.** 1 major confirmed (MAJ-1) and fixed; 1 major (MAJ-2) adjudicated as a correct
verbatim-Sol quote needing only sharper attribution, not a demotion or reword; 7 minors and 2 nits fixed.
None of the fixes altered any of the three `declared_budget` reason strings — the hash-parity script was
re-run after every fix and confirmed the three `config_hash` values are UNCHANGED:
`a3b8ac5c0d0205cb` / `1d69c1fa6b897b6a` / `309d76c3a8dfbb5c`.

- **MAJ-1 (confirmed, fixed):** packet §4a.4 covered only the opening bold STATUS sentence, leaving the
  untouched remainder of that paragraph plus three more live registration-state sites (H1 title, `Wave:`
  line, `Purpose:` line) uncovered — exactly the "registered bit nested inside a document that still calls
  itself candidate/not-declared" defect ruling 4 forbids. Fixed: all four sites added to §4a.4 with byte-exact
  old→new pairs; a post-edit packet-internal registration-state census confirms zero uncovered live sites.
- **MAJ-2 (adjudicated, verbatim-confirmed — no reword):** Fable, who holds Sol's actual message, confirmed
  both challenged quotes (the conditional-authorization sentence and the four-act list) are verbatim Sol, not
  commissioning-session paraphrase. Only the attribution at both sites (this section above, and packet §6) is
  sharpened to "Sol fourth-gate verdict, 2026-08-22 (relayed verbatim in the A4P.1 commissioning instruction)"
  — the quoted content is byte-unchanged.
- **MIN-1 (fixed):** the four remaining "presented to Sol for ratification" live sites (YAML `cell_ids`
  comments ×2, contract MD §11, disposition §0) updated to "ratified + naming normalized by Sol's fourth gate
  [A4P.1 R3]," matching the wording already at the two sites R3 originally touched.
- **MIN-2 (fixed):** YAML `predetermined_historical_status.label_assignment` carried a bare `n_eff` token
  (the struck DEFF estimator's own variable name, same class MAJ-4/A4G already swept from contract §12) —
  renamed to `n_effective_blocks` inline, comment-tagged `[A4P.1 R1]`. Pre-existing on main since the original
  A4G MAJ-4 sweep (which fixed only the contract MD's prose, never this YAML value) — a census gap this
  wave's R1 scope closes, not a regression introduced by A4P.1.
- **MIN-3 (fixed):** `IMCE_A4G_SOURCE_BOUNDARY_TABLE.md` row 13's R5 quote was silently truncated at "…raw
  underlying third-party quotations." — the dropped final three sentences ("PMMS remains HELD. FRED/ALFRED
  remain excluded. NAR storage remains prohibited.") restored so the quote is complete.
- **MIN-4 (fixed):** the new HB0 census annotation claimed the "pooled homebuilder stratum" wording was "not
  reproduced in this table" — it IS in the table (row :332). Annotation corrected (this wave's own additive
  text, freely editable — the A3 original table stays untouched).
- **MIN-5 (fixed):** contract MD's "Freezer of record" bullet (§15a) listed V1/V1.1/V1.2 but not V1.2.1 —
  appended "Sol / fourth-gate verdict, 2026-08-22 (V1.2.1)."
- **MIN-6 (fixed):** Appendix D's R1 row claimed §0a was touched — it is byte-unchanged by R1 (§0a's
  coverage/abstention-claims bullet already cited the AG3 cap correctly before this wave). Row corrected to
  name the sections R1 actually touched (YAML fields + hb0 annotation files).
- **MIN-7 (fixed):** §4a's `<A4 registration commit date>` placeholder had no frozen format. Added as a third
  §4a.1 procedure: UTC calendar date, ISO-8601 `YYYY-MM-DD`, via `date -u +%F`.
- **config_hash hardening (reviewer PLAUSIBLE, accepted, fixed):** added a mandatory post-commit
  verification step to §4a.1 procedure 2 / §6 Act 3 — after the A4 registration commit is created,
  `git hash-object` on the committed contract MD MUST equal the YAML-recorded `registration.config_hash`;
  on mismatch A4 aborts and repairs before push. Closes the silent-invalidation hole where a later same-PR
  MD edit could invalidate an already-recorded hash unnoticed.
- **n1 (fixed):** YAML `label_truth_table.reconstructable_contributors` typing normalized to uniform list
  form: `[4]` / `[2, 3]` / `[0, 1]` (was a bare scalar `4` for the first row).
- **n2 (fixed):** WS/handoff self-reference pattern now cites PR #6237 / branch `claude/imce-a4p1-records`
  as the durable identifier, with an explicit note that any recorded head SHA necessarily predates the PR's
  own next commit — `gh pr view 6237 --json headRefOid` is the live source, these records are provenance
  snapshots only.

### AP9 Summary table

| # | Ruling (one line) | Files touched | Resolves |
|---|---|---|---|
| R1 | Retire the stale DEFF `n_effective_blocks` denomination; census + annotate hb0 lane-2 recommendations superseded | YAML; hb0/*.md (annotation-only) | stale-machine-readable-field defect |
| R2 | Historical v0 population permanently `named_subset_basis: [PHM, KBH]`; prospective eligible cohort `[DHI, PHM, KBH, TOL]`; three-row label truth table | YAML; contract MD; disposition; packet; construction file (§1a, §3.1 wording); census (existing annotation) | AP8 F2(d) escalation |
| R3 | Ratify the six minted cell IDs; normalize sync family naming to `forward_63_trading_day_drawdown_tail` | YAML; contract MD; disposition; packet | prior wave's escalation item 4 |
| R4 | Freeze the complete A4 registration state-transition, byte-exact, verbatim-or-abort, covering the contract MD, YAML, AND the packet's own title/opening paragraph/Wave-line/Purpose-line; three placeholder procedures frozen (repo pin, config_hash + post-commit verify-or-abort, commit date) | packet (new §4a) | "one state, not nested" requirement |
| R5 | Treasury CMT source-rights disposition: `GO_LIMITED`, scope + basis frozen verbatim | boundary table; contract MD (mirror sentence); YAML | prior wave's escalation item 5 |
| R6 | Boundary receipts remain honestly open; exactly the two named post-registration dispositions | YAML; contract MD (mirror sentence); boundary table | boundary-evidence-wave law |
| R7 | Regenerate all three declared_budget row reason strings and `config_hash` values; verify hash parity; record superseded hashes | packet §2–§4, §1 | stale-hash-after-wording-change defect |

---

**This log entry authorizes nothing beyond itself.** No cell, model, score, or outcome computation has
started here. No `rf.cycle_pattern.imce_*` family is registered. The next authorized act on this family is A4
registration proper — see `IMCE_A4G_PROPOSED_A4_REGISTRATION_PACKET.md` (as regenerated by AP7, corrected by
AP8, closed for registration by A4P.1's frozen §4a transition table) for the exact proposed (not registered)
content of that future act. Sol's conditional authorization above governs whether that act may proceed without
a further roundtrip.

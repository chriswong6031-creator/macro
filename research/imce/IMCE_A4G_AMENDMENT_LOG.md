# IMCE-A4G / A4P — Preregistration Amendment Gate: Amendment Log

**File scope note (2026-08-21, A4P wave):** this file now records TWO gates in one append-only log, per the
A4P commissioning instruction ("every edit gets an append-only entry in `IMCE_A4G_AMENDMENT_LOG.md`") — the
original A4G gate (AG1–AG18, below) and the A4P "preregistration criteria closure" gate (AP1–AP7, appended
at the end of this file, after the original Summary table). The filename is retained unchanged (an owned-file
constraint of the A4P commission) rather than renamed; do not infer from the name alone which gate a given
`AG`/`AP` tag belongs to — the tag prefix is authoritative.

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

# IMCE-A4P — Preregistration Criteria Closure: Amendment Log (AP1–AP7)

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
performs, registration.
**Where:** `IMCE_A4G_PROPOSED_A4_REGISTRATION_PACKET.md` (rewritten in full — §1 recomputation basis, §2–§4
new reasons/hashes, §6 checklist updated).
**Authority:** Sol, A4P authorization 2026-08-21 (ruling 7 — regenerate the packet after rulings 1–6).

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

**This log entry authorizes nothing beyond itself.** No cell, model, score, or outcome computation has
started here. No `rf.cycle_pattern.imce_*` family is registered. The next authorized act on this family is A4
registration proper — see `IMCE_A4G_PROPOSED_A4_REGISTRATION_PACKET.md` (as regenerated by AP7, corrected by
AP8) for the exact proposed (not registered) content of that future act.

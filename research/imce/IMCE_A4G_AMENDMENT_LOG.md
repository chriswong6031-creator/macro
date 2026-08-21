# IMCE-A4G — Preregistration Amendment Gate: Amendment Log

**Wave:** A4G (final preregistration amendment gate). **Records-only.** No `data/` write, no outcome access, no registration act.
**Commissioned by:** Fable, per Sol's A4G authorization (2026-08-21), settling the A3 reconciliation (`agentos/workstreams/WS-CYCLE-PATTERN-ISSUER-MECHANISM.md`, wave A3 entry) between:
- **Lane 1** — `research/imce/IMCE_HB0_SOURCE_DEFINITION_CENSUS_V1.md` (commissioned, Opus-red-teamed; frozen operational rulings; thirteen typed gaps, four REQUIRED-BEFORE-A4);
- **Lane 2** — `research/imce/hb0/*.md` (operator lane; nine adjudication artifacts + seven evidence packets; B=5 block-hardening proposal; six-regime cancellation record; corrections C1–C3).

**Authority for every amendment below:** Sol, A4G authorization 2026-08-21.
**Binds:** `research/imce/IMCE_PREREGISTRATION_AND_EVALUATION_CONTRACT_V1.md` (V1.1). This log is the detailed rationale/citation record behind the contract's Appendix B index and its inline `[AG<n>]` tags — the contract MD binds; this log explains, it does not itself amend anything not already reflected in the contract and its YAML projection.
**Scope discipline:** every amendment below is RECORDS-ONLY. None writes `data/trial_ledger.jsonl`, accesses any outcome, or registers the three `rf.cycle_pattern.imce_*` families. Registration remains a separate, future A4/IMCE-03 act.

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
**Grep verification:** the formula text appears exactly once in the amended contract MD, inside the STRUCK clause itself (`grep -n "m − 1" research/imce/IMCE_PREREGISTRATION_AND_EVALUATION_CONTRACT_V1.md`) — no live/operative instance of the formula as an N-definition survives.
**Authority:** Sol, A4G authorization 2026-08-21.

---

## AG4 — Within-block dependence survives only as a differently-named precision diagnostic

**What changed:** The struck DEFF/ρ construction is not deleted from the research record — it is renamed and demoted to `n_issuer_precision_diagnostic` (exact field name TBD at A4 registration), usable to characterize within-block issuer-pooling precision but explicitly barred from ever substituting for `n_effective_blocks`, from ever satisfying the §8 item 5 forty-block floor, and from carrying any promotion authority.
**Where:** Contract §3 (new paragraph); YAML `effective_block_law.within_block_issuer_dependence`.
**Why:** Preserves the analytic content lane 2 built (`IMCE_HB0_A4_CELL_BUDGET_INPUTS.md` §3, `IMCE_HB0_INDEPENDENT_BLOCK_LIST.md` §8 — the full ρ ∈ {0.5...0.95} sensitivity grid) as a legitimate, disclosed diagnostic, while closing the promotion-authority leak AG3 identified.
**Authority:** Sol, A4G authorization 2026-08-21.

---

## AG5 — Historical replay carries FIVE closed non-overlapping blocks as an upper bound; reconciles C2

**What changed:** `n_effective_blocks` for general (non-cancellation) cells is capped at **B ≤ 5** — the five CLOSED, non-overlapping blocks (GFC bust, GFC recovery, 2014–2019 grind, pandemic boom, 2022–2023 rate shock). This is stated as an upper bound (block-to-block serial dependence, AG9, can only push it lower), and exact pseudo-N is declared unnecessary because the upper bound already fails the 40-block floor by roughly an order of magnitude.
**Resolves C2** (`IMCE_HB0_BLOCKERS_AND_FALSIFIERS.md` §5, row C2; `agentos/workstreams/WS-CYCLE-PATTERN-ISSUER-MECHANISM.md` A3 wave entry): lane 1's frozen list carries 7 named entries with the "2013 taper" item unresolved and the affordability era listed as a plain block; lane 2 hardens to B=5 on two independent admissibility grounds (non-overlap/distinct-shock failure for the taper; the closed-episode condition, already applied to the memory cohort's open HBM/AI episode per freeze §7.3, failing for the open affordability era). **RULING: B=5 wins for N-accounting.** Both lanes' lists are preserved — the named 7-entry taxonomy is retained verbatim in the contract's block-list table; only 5 of those 7 named entries contribute to `n_effective_blocks`.
**Where:** Contract §3 "Frozen historical block list" (restructured table) and "Effective-block-count law" (capped-definition paragraph, reconciliation paragraph); YAML `frozen_historical_block_list` (per-entry `counts_toward_n_effective_blocks`) and `effective_block_law.block_count_reconciliation`.
**Authority:** Sol, A4G authorization 2026-08-21.

---

## AG6 — Cancellation cells have at most THREE denominator-reconstructable historical blocks

**What changed:** Cancellation-rate cells specifically are capped at **B ≤ 3** (not the general-cell B ≤ 5), because only three of the five closed blocks carry a denominator-reconstructable cancellation-rate disclosure across the roster: the 2014–2019 grind (from FY2016), the 2020–2021 pandemic boom, and the 2022–2023 rate shock. GFC bust and GFC recovery predate the stated-denominator era for most of the roster (PHM/NVR confirmed only FY2016+; KBH FY2008+ and self-contradictory in that filing; LEN states no formula anywhere the census could find).
**Where:** Contract §3 "Effective-block-count law" (capped-definition paragraph, bullet 2); YAML `effective_block_law.n_effective_blocks_capped_at_raw_block_count.cancellation_rate_cells`.
**Source:** `IMCE_HB0_A4_CELL_BUDGET_INPUTS.md` §4 ("Why the cancellation cell gets B = 3, not 5").
**Authority:** Sol, A4G authorization 2026-08-21.

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
The exact mapping of the `rf.cycle_pattern.imce_phase_v0` family's 3 declared state targets against these 4 D5 states is left as an open A4 registration item — this amendment scopes observability, it does not itself re-map which target tracks which state, and it does not re-declare the frozen 6-cell budget.
**Where:** Contract §2 Homebuilders (new bullet); YAML `homebuilders.state_vector_observability_scoping`.
**Source:** `IMCE_HB0_A4_CELL_BUDGET_INPUTS.md` §2 ("mechanism-state coverage is uneven, and two states rest on one issuer") and §8 election E2.
**Authority:** Sol, A4G authorization 2026-08-21.

---

## AG15 — `pit_class` enum closed at exactly {pit_pure, revision_optimistic, mixed}

**What changed:** Explicit contract-level statement that `pit_class` is a closed enum of exactly three tokens, identical to `config/cycle_pattern/truth_schema.md`'s CPI enum. A3 lane-1's five-way `source_vintage_class` census vocabulary (`pit_pure`, `revision_optimistic`, `current_revised_only`, `prospective_from_capture`, `rights_blocked`) is a strictly-more-granular local diagnostic that must crosswalk down to one of the three before touching any cell — it never substitutes for `pit_class`. The full crosswalk and per-source mapping is in `IMCE_A4G_SOURCE_BOUNDARY_TABLE.md`.
**Resolves lane-1 gap 10** (`IMCE_HB0_SOURCE_DEFINITION_CENSUS_V1.md` §8 item 10 — "`pit_class` vocabulary not registered"): three prose verdicts were proposed as candidates without adoption; AG15 declines to mint any new token and instead confirms the existing three-value CPI enum is the only registered vocabulary, avoiding the exact vocabulary-fragmentation defect A2 (the CPI truth-contract audit) exists to fix.
**Where:** Contract §2 Homebuilders (Vintage rider bullet, extended); YAML `homebuilders.pit_class_enum`.
**Authority:** Sol, A4G authorization 2026-08-21.

---

## AG16 — No roster widening

**What changed:** Explicit statement that the six-name roster (DHI, PHM, TOL, KBH, LEN, NVR) stays frozen. Widening it — e.g. to the listed, continuously-public non-roster survivors named in `IMCE_HB0_SOURCE_DEFINITION_CENSUS_V1.md` §2d (HOV, BZH, MHO, MTH) — improves representativeness but supplies zero additional independent-shock power: at ρ≈0.8, going from m=5 to m=9 moves `n_eff` from ~6.0 to ~6.1 (survivorship census falsifier F-V4 / `IMCE_HB0_BLOCKERS_AND_FALSIFIERS.md` §4.2, F-4). Representativeness and power are separate problems; the roster question is open to future amendment on representativeness grounds only, never as a power lever.
**Where:** Contract §2 Homebuilders (new bullet); YAML `homebuilders.roster_widening` / `.roster_widening_rationale`.
**Authority:** Sol, A4G authorization 2026-08-21.

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

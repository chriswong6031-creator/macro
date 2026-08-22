# IMCE Preregistration and Evaluation Contract — V1.2.1 (Amended, Frozen)
## Mechanism-conditioned market recognition, next-state, and 63-day risk research

**Status:** `candidate_not_registered`. This document has not been registered and no real outcome evaluation has been run. Registration (repository re-pin, `config_hash`, trial-ledger `declared_budget` rows) is a future act — IMCE-03 / A4.
**Binding rule [A26, qualified AP8 F6]:** The binding surface is this markdown document **PLUS**
`IMCE_A4P_ORDER_SOFTNESS_STATE_CONSTRUCTION_V1.md`, incorporated by reference and named normatively wherever
the contract cites `order_softness` (§1, §2, §15/§15a) — both BIND. `IMCE_PREREGISTRATION_CANDIDATE_V1.yaml`
is the machine-readable projection of the **registration-relevant fields of both** documents — it carries the
construction file by path (`d5_state_construction`), never inlines its content, and carries no independent
authority of its own; on any apparent divergence, the two markdown documents control. **The word "lossless"
is dropped** — the YAML is a partial, registration-focused projection (row schemas, cell IDs, block caps,
receipt statuses, etc.), not a byte-complete restatement of either markdown document's full prose; no claim
of completeness is made or intended.
**Authority:** Research/display only. All ranking, gating, sizing, escalation, origination, and trading authority fields are FALSE. No authority is granted, implied, or reserved by this document.
**Supersedes:** `IMCE_PREREGISTRATION_AND_EVALUATION_CONTRACT.md` (2026-08-20 Round 3 candidate) and `IMCE_PREREGISTRATION_CANDIDATE.yaml` (schema `imce.preregistration_candidate.v0`).
**Amendment provenance:** 26 amendments (A1–A26), adjudicated and frozen in `research/IMCE_ROUND3_ARCHITECTURE_FREEZE_BY_FABLE.md` (§9, D8), applied at V1 (2026-08-20). **V1.1 adds 18 further amendments (AG1–AG18), Sol's A4G preregistration-amendment-gate rulings, authorized 2026-08-21**, settling the A3 reconciliation (`IMCE_HB0_SOURCE_DEFINITION_CENSUS_V1.md` lane 1 × `research/imce/hb0/` lane 2) into one outcome-blind A4-ready specification. **V1.2 adds 8 amendments (AP1–AP8), Sol's A4P preregistration-criteria-closure rulings, authorized 2026-08-21 — the original 7 (AP1–AP7) plus AP8, the same-branch revision fixing Fable's adjudication of an Opus red-team pass on the resulting PR**, closing every remaining open criterion the A4G six-cell disposition and source/boundary table left open (phase-target mapping, historical basis uniformity, prospective share, bootstrap, FDR runner obligation, macro boundary receipts, packet regeneration, and — via AP8 — corrected quotation, block-admissibility, bootstrap-unit, cell-ID, four-acts, promotion-clock, honesty, and era-coverage defects), so that actual A4 registration is a mechanical act with zero remaining discretionary choices except the four named in `IMCE_A4G_PROPOSED_A4_REGISTRATION_PACKET.md` §6. **V1.2.1 closes Sol's fourth-gate REQUEST_CHANGES preflight (wave A4P.1, 7 rulings R1–R7, authorized 2026-08-22): retires the stale DEFF machine-readable denomination (R1); permanently freezes the historical v0 population as the PHM/KBH named subset, separate from a prospective eligible pooled cohort, under a three-row label truth table (R2); ratifies and normalizes the six frozen cell IDs to the canonical `forward_63_trading_day_drawdown_tail` naming (R3); freezes the complete A4 registration state-transition, byte-exact, verbatim-or-abort (R4); settles Treasury CMT's storage/reuse disposition as `GO_LIMITED` (R5); keeps boundary receipts honestly open with the two lawful post-registration dispositions named (R6); and regenerates all three declared_budget row reason strings and `config_hash` values (R7) — so that A4 proper remains a mechanical act, now with zero remaining ambiguity in any field it must write verbatim.** Full rationale, citations, and before/after text for each AG/AP/R amendment: `IMCE_A4G_AMENDMENT_LOG.md`. Every amended clause below carries a trailing `[A<n>]` (Round 3), `[AG<n>]` (A4G), `[AP<n>]` (A4P), or `[A4P.1 R<n>]` (A4P.1) tag; consolidated indices are Appendix A (A1–A26), Appendix B (AG1–AG18), and Appendix C (AP1–AP8); the A4P.1 rulings (R1–R7) are recorded in `IMCE_A4G_AMENDMENT_LOG.md`'s A4P.1 section.
**Date:** 2026-08-20 (V1); amended 2026-08-21 (V1.1, A4G); amended 2026-08-21 (V1.2, A4P); **amended 2026-08-22 (V1.2.1, A4P.1)**.

---

# 0. Constitutional question

The trial is not "does 2W MACD work?"

The trial is:

> **Given a mechanism state frozen from source-backed evidence independently of future price, does a fixed market-recognition vector add out-of-sample information about the registered next mechanism state or 63-trading-day risk/path target beyond the mechanism-only baseline?**

The trial can return a null. A null becomes durable CPI truth memory.

## 0a. Prospective-accrual-first posture [A24][AG1]

The historical arm of this contract is instrumentation, episode-record construction, and design validation. It is **explicitly not a promotion path** — see §9a for the predetermined per-cohort historical status table and §13 for the counters and minimum prospective share that gate any future promotion. **Three** claim classes exist and must never be conflated: [corrected — was mis-stated "Two" against the three bullets below; fixed under A4G red-team review, no ruling tag, pre-existing Round-3 defect]

**Promotion-bearing evidence is 100% PROSPECTIVE [AG1, A4G binding].** Historical homebuilder replay (or replay of any other cohort) carries **zero weight** in any future promotion decision, full stop. This is stronger than "not a promotion path": historical replay may not supply a prior, a weight, a hyperparameter, a tiebreak, or any other quantitative influence to a prospective cell's promotion decision, by any mechanism, direct or indirect. §12's "no role of any kind — prior, weight, hyperparameter, or otherwise" clause (deleting the sub-floor "prospective PRIOR" carry-path) already enacted this for the specific sub-floor-pass case; AG1 generalizes it to the historical arm as a whole, for every cell, pass or fail.

- **Cycle-block claims** (forecast/edge): unreachable from history at any current cohort's honest N; prospective-only.
- **Transcription/reproduction-fidelity claims** (passport-field reproduction, denominator-crosswalk fidelity): natural replicate is the issuer-quarter row; honest N is in the hundreds; reachable now; carry **zero forecast authority**. [G8-B5]
- **Coverage and abstention-calibration claims**: block-dependent by construction — a source outage or disclosure change hits every issuer in a period simultaneously — so these are denominated in effective blocks under the §3 independent-shock law and the AG3 cap (`n_effective_blocks ≤ B`) [BLK-2, corrects the struck DEFF-rule citation]; row counts are printed but never used as N. [G8-B5]

---

# 1. Trial families — provisional names

Fable must check `data/trial_ledger.jsonl`, name length, and collision before declaration.

| Family | Purpose | Candidate cell budget (frozen) [A5] |
|---|---|---|
| `rf.cycle_pattern.imce_phase_v0` | next family-local state / false-repair targets | **3 cells**: 3 state targets × historical v0 population `named_subset_basis: [PHM, KBH]` (prospective v0 eligible pooled cohort `[DHI, PHM, KBH, TOL]`, three-row label truth table, §2 Homebuilders / AG14 / **A4P.1 R2**) [was "pooled homebuilder stratum"] × contrast [M vs family/age prior] — **all 3 targets are mapped to the `order_softness` D5 state [AP1]:** (a) next `order_softness` cohort state at +1 reporting period, (b) next `order_softness` cohort state at +3 reporting periods, (c) `order_softness` false-repair/relapse within 3 reporting periods. Deterministic construction: `IMCE_A4P_ORDER_SOFTNESS_STATE_CONSTRUCTION_V1.md`. |
| `rf.cycle_pattern.imce_sync_v0` | incremental recognition over mechanism-only | **2 cells**: targets {`next_local_state_1rp`, `forward_63_trading_day_drawdown_tail`} × contrast [M+R vs M] — **`next_local_state_1rp` targets the same `order_softness` next-period cohort state as the phase family's 1-reporting-period target [AP1]**, not an independently-defined state. [**A4P.1 R3**: normalized from `forward_63d_drawdown_tail` — both market-risk cells bind to the same canonical 63-trading-day QLedger ruler; family prefix distinguishes the tests.] |
| `rf.cycle_pattern.imce_risk_v0` | 63-trading-day drawdown-tail and path targets | **1 cell**: `forward_63_trading_day_drawdown_tail` × [M vs family/stratum prior] |

**Historical total = 6 cells.** [A5] **All 6 cells share the same order-softness mechanism basis, including lawfully reconstructable cancellation evidence, and are therefore B≤3-entire (cancellation-scoped), uniformly [AP2] — see §3.**

BH-FDR at q=0.10 runs over the **union of these 6 historical cells as ONE partition**, named `imce_hist_v0`. The three `rf.*` family names above are trial-ledger provenance labels only — they are not separate FDR partitions. [A6]

No candidate may reach `screened` until its family is declared under Research Factory law.

---

# 2. Cohorts and eligibility

## CELH

- descriptive case only;
- no statistical promotion;
- may supply design, falsifiers, and prospective observations;
- may never be cited as evidence of issuer-specific forecast skill;
- barred/`DESCRIPTIVE` at 0 historical cells under §9a — this bar is by rule, not by count. [A1]

## Memory

Eligible only after product/epoch stratification and effective episode count are frozen.

- Honest N = 2 completed episodes + 1 OPEN episode. The open HBM/AI episode carries no closing disposition and is **ineligible as a graded unit**. [A14]
- Memory is `REGISTERED`-only with **0 historical inferential cells**; `leave_cycle_out` is undefined at B=2, so memory cannot even be `REPLAYED`. [A14]
- Two-axis coupling flag: the legacy and HBM axes are causally coupled from **2025** (HBM buildout itself caused legacy scarcity). They are neither two strata nor two independent blocks — the coupling date (2025) is registered here, and mechanism-grammar epochs may not cross folds. [A15]

## Homebuilders

Eligible after definition crosswalk, source-vintage policy, and macro-block clustering are frozen.

- (a) Episodes are re-keyed on **calendar month**; the fiscal→calendar crosswalk is frozen pre-outcome; no re-key is permitted after outcome access. [A17]
- (b) **One** canonical cancellation-rate denominator per issuer is frozen with a printed conversion; a mandatory alternate-convention sensitivity re-run is required; a result that flips under the alternate convention is **not a pass**. [A17]
- **LEN** is excluded from cancellation-rate cells. **[A18, restated by AG10 / C1]** Reason restated from the original "no press-release cancellation rate; era-correlated missingness by construction": LEN's own 10-K MD&A **does** disclose a cancellation figure (14%, FY2025) — the missingness is channel-scoped (absent from EX-99.1 press releases), not absolute. The exclusion **stands**, but its recorded ground is now: **"no stated formula anywhere in LEN's disclosure record (denominator unverifiable) + era-correlated absence from the press-release channel specifically."** It carries a Millrose Feb-2025 break flag (structural, independent of the cancellation exclusion); the exclusion is printed. **[AG10-clarif, MAJ-2 fix]** Scope of "excluded from cancellation-rate cells" is CELL-LEVEL, matching the AG6 cancellation-rate-cell class (B≤3, MAJ-1): LEN is excluded entirely — as an issuer, not merely as a feature — from any cell whose registered basis draws cancellation-rate input. In every OTHER cell (the general/non-cancellation class, B≤5), LEN remains a roster member and its cancellation-rate FEATURE, if ever referenced non-primarily, is typed `missing` and never imputed, per the [A19]/AG11 era-correlated-missingness ban — it is not separately "excluded" from those cells. (The prior draft's citation of a "contract §2(b) confirmation note" for this scoping was fabricated — no such note exists in this contract; that language was HB0 census evidence (`IMCE_HB0_SOURCE_DEFINITION_CENSUS_V1.md` §6b), not a contract clause, and is corrected here to an actual contract-level ruling.) **[AP2, A4P binding]** Since all 6 registered v0 historical cells now share the `order_softness` mechanism basis (cancellation-scoped, B≤3-entire — see §1, §3), **LEN is excluded — cell-level — from all 6 registered historical cells, not only the 4 (Cells 1–4) named at A4G.** The "general/non-cancellation class, B≤5" LEN-remains-a-roster-member branch above describes zero currently-registered cells today; it remains the standing law for any hypothetical future non-cancellation cell.
- **NVR** is a mechanism outlier (100%-option land model, corrected to a strong-majority option-lot model per NVR's own FY2025 10-K — "we generally do not engage in land development"): it is a separate stratum or a designated transfer test, **never pooled to raise n**. Inclusion/exclusion is frozen pre-outcome. **[A18, reaffirmed AG13 — no change; carried forward unmodified by A4G.]**
- **TOL cancellation-rate denominator [AG12, A4G binding — settles election E1].** TOL discloses cancellation on two conventions in the same exhibit: "as a percentage of signed contracts in quarter" and "as a percentage of beginning-quarter backlog." **Primary convention = gross signed contracts in the period** (cross-issuer comparable with DHI/PHM/KBH's gross-orders basis). **Beginning-quarter backlog basis is a MANDATORY printed sensitivity** for every TOL cancellation readout, not an optional alternate — a result that flips under the backlog basis is not a pass (contract §2(b) alternate-convention rule, unchanged).
- **Roster widening — NO. [AG16, A4G binding]** The six-name roster (DHI, PHM, TOL, KBH, LEN, NVR) stays frozen. Widening it (e.g. to HOV, BZH, MHO, MTH — the listed, continuously-public non-roster survivors named in `IMCE_HB0_SOURCE_DEFINITION_CENSUS_V1.md` §2d) improves representativeness but supplies **zero** additional independent-shock power. **[MAJ-3 correction]** The supporting arithmetic — at ρ≈0.8, moving from m=5 (the five pooled general-cell issuers: DHI, PHM, TOL, KBH, LEN; NVR held out as its own stratum) to m=9 moves the struck-and-renamed `n_issuer_precision_diagnostic` from ~6.0 to ~6.1 (survivorship census falsifier F-V4 / `IMCE_HB0_BLOCKERS_AND_FALSIFIERS.md` §4.2 F-4) — is the **struck DEFF estimator** (AG3), relabeled `n_issuer_precision_diagnostic` per AG4: it is **shown here only to demonstrate insensitivity to issuer count**, never as `n_effective_blocks`. `n_effective_blocks` itself stays capped at B (≤5 general / ≤3 cancellation, AG5/AG6) regardless of m, roster width, or this diagnostic's value. More issuers inside the same closed blocks are correlated rows, not new draws. Representativeness and statistical power are separate problems; only the roster question is open to future amendment, never as a power lever. **[AP2 clarification]** This m=5 figure is a **hypothetical general (non-cancellation) cell's** issuer pool — since AP2 hardens all 6 registered v0 historical cells to the cancellation-scoped B≤3 class (LEN excluded), no cell registered by this contract today has an m=5 issuer pool; the actual registered-cell issuer pool for the pooled `order_softness` cohort state is m=4 (DHI, PHM, KBH, TOL — see `IMCE_A4P_ORDER_SOFTNESS_STATE_CONSTRUCTION_V1.md` §3). This bullet's arithmetic remains valid as an illustrative diagnostic for a hypothetical future general cell; it does not describe any cell registered today.
- **Survivorship condition [G8-B4]:** the roster is a 2026-survivor roster over a window containing the 2006–2011 sector mortality event, and the ported episode substrate is survivor-stamped. IMCE-HB-0 must produce a named census of delisted/bankrupt/acquired homebuilders for the study window with an explicit inclusion decision; until it lands, every homebuilder cell readout carries a mandatory survivorship-bias disclosure and no cohort mean is quoted without it.
- **Epoch-clock rule [G8-M2]:** structural epochs drawn on the operating clock (business events) are descriptive partitions only; any block or epoch used to partition a **recognition-outcome** statistic must use recognition-clock (`available_at`) boundaries. Epochs are frozen before any outcome inspection, not merely before fitting.
- **Vintage rider [G8-M6]:** IMCE-HB-0 adds a per-source vintage audit for every macro/homebuilder source; a leg without retrievable vintages is declared `revision_optimistic` in `pit_class` and disclosed in every readout using it. **`pit_class` is a CLOSED enum of exactly three tokens [AG15, A4G binding]: `pit_pure`, `revision_optimistic`, `mixed`** (identical to `config/cycle_pattern/truth_schema.md`'s CPI enum) — no fourth token may ever be minted for this family; a source-census vocabulary finer than these three (e.g. HB-0's five-way `source_vintage_class`) is a local diagnostic that must crosswalk down to one of the three before it touches any cell, never substitute for the enum. See `IMCE_A4G_SOURCE_BOUNDARY_TABLE.md` for the per-source mapping.
- **Rights-safe macro legs only [AG18, A4G binding].** Every macro/context leg feeding `C_t` or `M_t` must be a rights-safe OWNER source: **FRED and ALFRED are excluded categorically** (clause (q), `DO_NOT_INGEST`, binds display tier too — no store/cache/archive/database incorporation in any use class). **Freddie Mac PMMS is HELD**, not GO and not blocked: its 1971→present weekly archive is genuinely PIT-pure, but the site terms bar redistribution/commercial exploitation without a separate licence, in tension with the archive's open availability — it may not be used until that rights question resolves; Treasury constant-maturity yields (confirmed `pit_pure`, public domain, full archive) are the primary rate leg in the interim. **No NAR series may be stored** (Existing-Home Sales, Housing Affordability Index) — NAR's terms bar storage in a retrieval system outright, not merely redistribution, so self-archival does not cure it; an affordability construct is assembled from clean owner legs (Census NRS price + Treasury rate + Census/BLS income), never adopted from the NAR or NAHB indices. **A macro source without lawful, retrievable historical vintages stays `pit_class = revision_optimistic`** by default (Census NRS/NRC, FHFA HPI, BEA RFI, Census C30, BLS CPI-shelter) until an individually-cleared upgrade path executes (e.g. Census NRS's first-print release archive, back to 1995 — costed, not yet executed).
- **State-vector observability scoping [AG14, A4G binding — settles election E2 for 3 of 4 D5 states].** The D5 homebuilder mechanism-local state vector is `order_softness` / `completed_inventory_build` / `incentive_support` / `pace_recovery`. Today: **`order_softness` is the only state broadly cohort-observable** (net orders/backlog/cancellation rate disclosed, in some form, by all six roster issuers). **[AP8, F2(b) scope note — the "all six roster issuers" claim is a PROSPECTIVE (current-format-disclosure) statement, not a historical-reconstruction statement.]** Broad cohort observability holds prospectively — every roster issuer's current disclosure format is receipted. **Historical reconstruction (2014–2023, the window the six registered cells' B≤3 basis draws on) is currently limited to the verified-era pair {PHM, KBH}** — DHI's and TOL's net-orders disclosure format is not positively receipted for that window (only inferred/source-claim grade); see `IMCE_A4P_ORDER_SOFTNESS_STATE_CONSTRUCTION_V1.md` §1a for the full fail-closed gate and citation trail. **A historical `order_softness` read is therefore a NAMED-SUBSET claim over {PHM, KBH}, not a full-cohort claim, until DHI's and TOL's pre-FY2025 disclosure format is receipted** — the same discipline `completed_inventory_build` already carries below, applied here for a different, currently-narrower reason (era-coverage, not permanent structural absence). **`completed_inventory_build` may exist only as a NAMED THREE-ISSUER SUBSET** (DHI ~9,300 completed unsold units, LEN ~5,000 + per-community ratio, PHM unit-level Unsold split; KBH qualitative-only, NVR combined-dollar-bucket-only, TOL `missing`) — any cell using it is a named-subset claim, never a cohort claim, and must be labelled as such. **`incentive_support` and `pace_recovery` remain descriptive and may NOT be imputed into any cohort cell** — each rests on a single disclosing issuer today (LEN for incentive figures; KBH for build/cycle time) and populating the other issuers by inference would violate §10's "missing is never zero" and the ordinal-sensor missingness rule. **The exact per-target mapping is now SETTLED [AP1, A4P binding]:** all 3 `rf.cycle_pattern.imce_phase_v0` targets, and `rf.cycle_pattern.imce_sync_v0` Cell 4, are mapped to `order_softness` (§1) — never to `completed_inventory_build` (which stays a named 3-issuer descriptive/subset research object, not a v0 cohort inferential target) or to `incentive_support`/`pace_recovery` (descriptive only, mapped to nothing). The deterministic, outcome-independent `order_softness` state construction is frozen in `IMCE_A4P_ORDER_SOFTNESS_STATE_CONSTRUCTION_V1.md` — sign-only comparison of YoY net-orders direction and YoY cancellation-rate-point direction per issuer, pooled by mode across the **nominal** roster {DHI, PHM, KBH, TOL} (LEN excluded per AP2, NVR held out as its own stratum) — **the historically-eligible roster is currently {PHM, KBH} only (construction §1a); prospectively, all four are eligible once their current-format disclosures are receipted** — no grid search, no outcome-selected threshold, no issuer-specific tuning; `NOT_RECONSTRUCTABLE` periods are typed explicitly and never imputed. **[AP8, F2(c)] Two distinct thresholds, stated separately, never conflated:** the ≥2-issuer floor (construction §3.1) is the AG14-derived MINIMUM contributor count for minting ANY pooled state at all (below it: `NOT_RECONSTRUCTABLE`, no state of any kind). Whether a state minted at exactly that floor may carry the COHORT label (vs. a named-subset label) is a stricter, separate question — AG14's own three-issuer `completed_inventory_build` precedent shows the cohort label requires broader-than-minimum coverage. **Open, escalated to Sol [AP8, F2(d)]: whether a ≥2-contributor `order_softness` read may ever bear the cohort label, or must always be named-subset-labelled regardless of contributor count. Until Sol rules, named-subset labelling governs every historical `order_softness` read.**
- Honest historical blocks for `n_effective_blocks` accounting: **≤5 as a closed-block UPPER BOUND, general cell; ≤3 for cancellation-rate cells [AG5, AG6 — see §3].** The 5–7 range in the frozen block list (§3 [A8]) names 7 labelled episodes; §3 below resolves how many of them count toward N. **[AP2, A4P binding] All 6 registered v0 historical cells (§1) are cancellation-scoped — the ≤3 basis applies uniformly; the ≤5 general basis describes no cell registered by this contract today** — see §3. Max reachable ladder rung on history: `REGISTERED`→`REPLAYED`, estimation-only readout, **never `DISPLAY`, never `PROMOTE_ELIGIBLE`**. [A1]

## Banks

Eligible after charter-parent-security identity and structural-event treatment are accepted.

- Call Report / UBPR / FR Y-9C historical data is declared `not_reconstructable` — the public series are current-revised, not point-in-time. Reconstructing an "as-of" read from revised series is **forbidden**. [A13]
- Banks are feasibility-only. **No bank cell may be declared** until a prospective self-archival lane exists: a start date, an archive manifest, and a hash-pinned vintage + observation date recorded per cutoff. [A13]
- Honest historical blocks: ~3, 0 PIT-clean (§9a). [A1]

---

# 3. Unit of observation and independence

## Research unit

A mechanism episode has:

- an opening state observation;
- an identity/structural epoch;
- an evidence cutoff;
- a family-local target window;
- a canonical market episode or market outcome anchor;
- a closing/target disposition.

Issuer-quarter rows inside one episode are not independent trials.

## Effective blocks

Cluster by shared industry/macro shock. Examples:

- one global memory correction;
- one national housing/rate shock;
- one banking funding/credit episode.

### Frozen historical block list [A8, restructured AG5/AG7/AG8]

The literal block list is frozen with boundary dates below. Any change requires a new amendment-log entry. **A4G restructures presentation only — no boundary is deleted, and no block is added or removed from the NAMED list; it re-types two entries as sub-episodes and one as open, per AG5/AG7/AG8 below.** Month-level boundaries are the A3 lane-2 hardening proposal (`IMCE_HB0_INDEPENDENT_BLOCK_LIST.md` §5); they are **PROPOSED, not yet receipted against a dated macro-series citation** at the boundary itself (lane-1 gap 11) — see `IMCE_A4G_SOURCE_BOUNDARY_TABLE.md` for the per-boundary receipt status. Using a proposed-but-unreceipted month boundary to partition a future outcome run is barred by AG17 below until it is receipted or the year-level boundary is used instead.

| # | Block | Year boundary (frozen) | Proposed month boundary (A3 lane-2, not yet receipted) | Counts toward `n_effective_blocks` |
|---|---|---|---|---|
| 1 | GFC bust | 2006–2009 | 2006-01 → 2009-12 | **YES** — closed, non-overlapping |
| 2 | GFC recovery / land-light era | 2010–2013 | 2010-01 → 2013-12 | **YES** — closed, non-overlapping |
| 2a | 2013 taper (partial) | *(no independent boundary — named sub-episode of #2)* | 2013-05 → 2013-12 | **ZERO — named sub-episode, not an independent block [AG7]** |
| 3 | 2014–2019 grind, including the 2018 air-pocket | 2014–2019 | 2014-01 → 2019-12 | **YES** — closed, non-overlapping |
| 3a | 2018 air-pocket | *(no independent boundary — named sub-episode of #3, already nested in the frozen list's own wording)* | 2018-07 → 2018-12 | **ZERO — named sub-episode, not an independent block [AG7]** |
| 4 | 2020–2021 pandemic boom | 2020–2021 | 2020-03 → 2021-12 | **YES** — closed, non-overlapping |
| 5 | 2022–2023 rate shock / cancellation spike | 2022–2023 | 2022-01 → 2023-12 | **YES** — closed, non-overlapping |
| 6 | 2024–2026 affordability/incentive era | 2024–2026 | 2024-01 → **open** | **ZERO — `OPEN_ACCRUING`, not a unit until lawfully closed [AG8]** |

### Effective-block-count law [A9, amended AG2/AG3/AG4/AG5/AG6/AG9 — STATISTICAL-UNIT LAW AMENDMENT, A4G binding]

The effective block count is the number of independent shock realizations. **It may never be increased by counting issuers, rows, targets, horizons, directions, or overlapping windows.** [A9, unchanged]

**Issuer replication may NEVER raise independent-shock N [AG2].** This generalizes the A9 ban: no issuer-level pooling, weighting, or correlation-discounting construction may produce an `n_effective_blocks` value that **exceeds the raw non-overlapping closed-block count B**. N is bounded above by B, always.

**STRUCK: the `n_eff = (B × m) / [1 + (m − 1)·ρ]` construction as a definition of `n_effective_blocks` [AG3].** This design-effect (DEFF) formula — proposed in `IMCE_HB0_A4_CELL_BUDGET_INPUTS.md` §3/§8 and `IMCE_HB0_INDEPENDENT_BLOCK_LIST.md` §8 as a candidate `n_effective_blocks` estimator — is struck from this contract as the definition of the statistical unit. It violates AG2/A9 by construction whenever it exceeds B: at ρ < 1 (any ρ short of perfect correlation), `DEFF = 1 + (m−1)ρ < m`, so `n_eff = B·m/DEFF > B` — the formula manufactures independent-shock count out of issuer count exactly as A9 forbids, regardless of how ρ is chosen. This closes lane-1 gap 9 (`IMCE_HB0_SOURCE_DEFINITION_CENSUS_V1.md` §8 item 9): **ρ is no longer a required frozen parameter for `n_effective_blocks`** — the parameter this contract now requires is B (the raw closed-block count) and nothing else. The prior Round-3 text ("DEFF rule: `n_effective_blocks` may be derived from issuer-episodes only via a design-effect estimator using a correlation parameter (ρ)...") is deleted in its entirety and replaced by this clause.

**`n_effective_blocks` is capped at the raw block count [AG3, AG5, AG6, M3-fix]: `n_effective_blocks = B, reduced only by a registered dependence adjustment (AG9)` — never derived upward from issuer count, and never exceeding B, where:**

- **General cells (all cell classes not scoped to cancellation-rate): B ≤ 5** — the five CLOSED, non-overlapping blocks in the table above (#1, #2, #3, #4, #5). This is an **upper bound**, not a point estimate — block-to-block serial dependence (AG9 below) can only push it lower. [AG5]
- **Cancellation-rate cells: B ≤ 3** — of the five closed blocks, only three carry a denominator-reconstructable cancellation-rate disclosure across the roster: the 2014–2019 grind, the 2020–2021 pandemic boom, and the 2022–2023 rate shock. **The 2014–2019 grind block carries only PARTIAL coverage** — its cancellation-rate denominator is confirmed only from FY2016 onward for PHM and NVR (2014–FY2015 within that block predate their stated-denominator disclosure), so even this block's contribution to B≤3 is a within-block partial-period claim, not full-block coverage; this is disclosed wherever the grind block is cited as one of the three cancellation-basis blocks. **[AG6, M9-fix]** Blocks #1 (GFC bust) and #2 (GFC recovery) predate the stated-denominator era for most of the roster entirely (PHM/NVR confirmed only FY2016+; KBH FY2008+ and self-contradictory in that filing; LEN never states a formula) — freezing a canonical denominator there would require assuming an unstated early convention matched the later stated one, which is exactly the flattening this contract exists to prevent.
- **Cell-level scoping, not feature-level [MAJ-1 ruling — settles the prior draft's ambiguity].** The B≤3 cap applies to a cell IN ITS ENTIRETY whenever that cell's REGISTERED input basis includes cancellation-rate data — never to "a feature's contribution" within an otherwise B≤5 cell. Today, `order_softness` (contract §2, AG14) is the one D5 state whose registered basis names cancellation-rate disclosure, so every cell whose target draws on `order_softness` (or on `next_local_state`-class targets built from it) is a B≤3 cell as currently registered. A future A4 registration that strips cancellation-rate out of a cell's basis to move it to the B≤5 general class is a registration-time amendment with its own review — not an open election of this gate, and not decided here. See `IMCE_A4G_SIX_CELL_DISPOSITION.md` for the settled per-cell disposition under this rule.
- **All six registered v0 historical cells share the order-softness mechanism basis — uniform B≤3 [AP2, A4P binding].** A4G left two of the six cells (`imce_sync_v0`'s `forward_63_trading_day_drawdown_tail` [**A4P.1 R3** normalized naming, was `forward_63d_drawdown_tail`], `imce_risk_v0`'s single cell) conditional on an undetermined `M_t` feature composition. AP2 settles it: every registered v0 historical cell's `M_t` basis includes `order_softness` (per AP1's target mapping and construction, `IMCE_A4P_ORDER_SOFTNESS_STATE_CONSTRUCTION_V1.md`), and `order_softness` names cancellation-rate disclosure — so **all 6 cells are B≤3-entire, uniformly**, under the cell-level rule above; none is, or was ever conditionally, a B≤5 general cell. Consequences, binding: (1) **LEN is excluded — cell-level — from all 6 registered historical cells**, not only four of them; (2) **NVR remains a separate stratum**, unchanged; (3) **GFC bust and GFC recovery (blocks #1, #2) remain unusable** for every registered cell — the B≤3 basis draws only the 2014–2019 grind (partial FY2016+ PHM/NVR coverage), 2020–2021 pandemic boom, and 2022–2023 rate shock blocks, the same three AG6 already named; (4) **this uniform B≤3 basis may NEVER be relaxed to B=5 merely to obtain a larger nominal N** — a future amendment could only change this by re-registering a *different* cell whose `M_t` basis genuinely excludes `order_softness`/cancellation data, never by reinterpreting one of these six; (5) the general B≤5 cap (AG5) remains the standing law for the block-list taxonomy and for any hypothetical future non-cancellation cell — it describes no cell registered by this contract today. **[AP8, M4 fix]** The genuinely promotion-relevant clock is **~2160**, computed on a zero-historical-credit, prospective-only basis at §13 — the historical-block-count illustration this paragraph originally cited (~2149, itself superseding the AG5 ~2153 B=5 figure) is a non-promotion diagnostic only; see §13 for the full correction and arithmetic.
- **Exact pseudo-N (a fitted ρ/DEFF point estimate) is unnecessary** — the upper bound already fails the §8 item 5 floor of 40 by roughly an order of magnitude on every cell class, so no analytic refinement changes any cell's predetermined `underpowered_accruing` status (§9a, §12). [AG5]

**Reconciliation of the A3-pair block counts [AG5, records the C2 disposition].** Lane 1 (`IMCE_HB0_SOURCE_DEFINITION_CENSUS_V1.md`) carried the frozen list's 7 labelled entries forward without resolving how many count toward N (its own gap 12: "the exact boundary-date determination is left as an open A4 item"). Lane 2 (`IMCE_HB0_INDEPENDENT_BLOCK_LIST.md` §2–§4) audited the same 7 entries against five admissibility conditions and hardened to **B = 5**, on two independent grounds: the 2013 taper overlaps block 2 and is the same rate/credit transmission channel (fails non-overlap and distinct-shock), and the 2024–2026 era is open (fails the "closed" condition already applied to the memory cohort's open HBM/AI episode, freeze §7.3). **RULING: B = 5 wins for N-accounting [AG5].** This is not a rejection of lane 1's 7-item NAMED list — that list is retained verbatim above as the frozen historical-episode taxonomy — it is a ruling that of the 7 named entries, 2 (the taper, the open era) contribute zero to `n_effective_blocks`, leaving 5 that do. Both lanes' language is preserved in this reconciliation rather than one being silently discarded.

**Named sub-episodes contribute ZERO N [AG7].** "2013 taper" and "2018 air-pocket" are named sub-episodes of blocks 2 and 3 respectively (table above) — retained for descriptive and diagnostic use (e.g. within-block regime narrative), contributing **zero** to `n_effective_blocks`. No boundary-date minting is required to reach this status; a sub-episode's uncertain exact start/end date is irrelevant to N-accounting once it is typed as contributing zero. This closes lane-1 gap 12: the "2013 taper" boundary dates need never be minted for the purpose of counting N, though they remain open for descriptive/diagnostic dating (`IMCE_A4G_SOURCE_BOUNDARY_TABLE.md`).

**2024–2026 affordability era is `OPEN_ACCRUING` [AG8].** Zero historical N. It becomes a prospective (not historical) block only when it is lawfully closed by a pre-registered closing rule — no such rule is registered by this amendment; registering one is a future A4/prospective-law act, not performed here. Until closed, it accrues toward `n_blocks_prosp` (§13), never `n_blocks_hist`.

**Within-block issuer dependence survives ONLY as a precision diagnostic, differently named [AG4].** The `DEFF = 1 + (m−1)·ρ` construction and its `n_eff = (B×m)/DEFF` output are not deleted from the research record — they are **renamed and demoted**. As **`n_issuer_precision_diagnostic` — the exact field name, frozen now [AP8, M3(b) fix; was "or an equivalent differently-named field chosen at A4 registration," leaving the name open — that open TBD is closed here]** — it may be computed, printed, and used to characterize within-block issuer-pooling precision — but it **can never be used as, mistaken for, or substituted for `n_effective_blocks`**, can **never satisfy the §8 item 5 forty-block floor**, and carries no promotion authority of any kind. `n_rows` and `n_issuers` remain printed for transparency; **promotion uses `n_effective_blocks` (capped at B per AG3/AG5/AG6) and nothing else.**

**Inference is block-cluster / leave-one-block-out [AG9].** Cross-validation, bootstrap, and materiality tests (§7, §8 item 7) operate at the block level. A dependence adjustment (issuer-level ρ, or a future block-level `rho_block` per `IMCE_HB0_INDEPENDENT_BLOCK_LIST.md` §3 D4) **may only ever REDUCE `n_effective_blocks` below its capped value — never increase the shock count** above the raw closed-block count B. Serial (block-to-block) dependence in particular is unaddressed by the struck DEFF construction (it discounted only within-block issuer correlation); any future `rho_block` registration can only tighten the bound, consistent with the upper-bound framing in AG5.

**Exact source-dated macro boundaries must be receipted before any outcome partition runs [AG17].** A block boundary used to partition an actual outcome run must carry a citation to a dated macro-series or issuer-event source, not merely a narrative news citation (per the M4 correction in `IMCE_HB0_SOURCE_DEFINITION_CENSUS_V1.md` §6a: cancellation rate cannot certify its own block boundaries, being `M_t` itself). **Uncertainty about a descriptive sub-episode's exact date may NOT be used to manufacture another block** — the 2013 taper and 2018 air-pocket stay sub-episodes at zero N (AG7) regardless of whether their own boundary dates are ever receipted. See `IMCE_A4G_SOURCE_BOUNDARY_TABLE.md` for the current receipt status of every block boundary; `not_yet_receipted` boundaries block only an actual outcome partition on that boundary, not this contract's freeze. **[A4P.1 R6, Sol fourth-gate ruling R6, 2026-08-22]** Registration is permitted with these receipts still open — the binding law is that no unreceipted boundary may be used to partition an outcome run. After registration, a boundary-evidence wave may only either receipt the already-frozen v0 boundary from a lawful first-party source, or mark that block `NOT_RECONSTRUCTABLE_FOR_V0_OUTCOME_PARTITION`; it may never move a registered v0 boundary after inspecting outcomes, and a scientifically necessary different boundary is a new preregistration/version, not an edit of this one. Full verbatim ruling: `IMCE_A4G_SOURCE_BOUNDARY_TABLE.md` §6.

`n_rows` and `n_issuers` are printed, but promotion uses `n_effective_blocks`.

---

# 4. Inputs

## Mechanism vector `M_t`

Only observations available at or before the cutoff, frozen by mechanism passport and sensor registry.

Ordinal-sensor law [A16]: Samsung/SK hynix wafer-starts and ASP fields are directional-only. They enter the passport as **ordinal** fields and are **forbidden in any cell requiring a cardinal level**. A directional field entering a cardinal model is a missingness event, never an imputation.

## Recognition vector `R_t`

Fixed before outcome access:

- canonical relative-strength fields;
- weekly state;
- fixed-anchor 2W MACD line/signal/histogram and closed-bar flag;
- revisions only from captured historical snapshots;
- positioning only on knowable/publication dates;
- event reaction fields frozen by a canonical event ID.

No per-name threshold or sensor selection.

**Design-provenance law [A4, executed and hardened per G8-M10/B3]:** `R_t` **is frozen as of the IMCE-00 architecture freeze (2026-08-20), before wave A1 (CELH autopsy)** — its fields are exactly those enumerated in this section, each telemetry field bound to a NAMED canonical construction chosen a priori by house default (fixed-anchor 2W MACD = classic 12-26-9 `engine/technicals.macd_hist`; confluence-contract references = `engine/canon.py` `w2_bull` RSI-MACD; never a third implementation). Disclosure: the G0–G8 census phase produced one unregistered descriptive recognition tape on CELH (G2) whose construction was the house default fixed before any outcome inspection; that tape is quarantined as census evidence — no truth statement, display, or registered cell may cite it, and no `R_t` field was added, removed, or re-parameterized after it existed. The previous disjunctive branch (provenance note + out-of-cohort validation) is DELETED as unexecutable — every available cohort is underpowered for such a validation.

## Context `C_t`

Registered macro/industry context from lawful source owners, with PIT class and rights. Context is descriptive unless the trial explicitly registers it. **[AG18, A4G binding] "Lawful source owners" excludes FRED and ALFRED categorically** (clause (q), `DO_NOT_INGEST`, binds every use class including display tier — no store/cache/archive/database incorporation) — see §2 Homebuilders "Rights-safe macro legs only" for the full rule and the PMMS-HELD / no-NAR-storage specifics, which apply to `C_t` for every cohort, not homebuilders alone.

---

# 5. Targets

## Phase / next-state family

- next family-local state at one reporting period;
- next family-local state at three reporting periods;
- false repair / relapse within three reporting periods.

Baseline: family/age transition matrix estimated only on the train fold.

## Synchronization family

Primary metric: paired improvement of `M_t + R_t` over `M_t` under the same fold, target, and missingness population.

Secondary comparisons — outside the FDR partition, zero budget, non-verdict-bearing, print-only [A7]:

- `R_t` versus age prior;
- `M_t` versus age prior;
- `M_t + R_t` versus tape-only.

Only the primary incremental comparison can support the synchronization claim.

## Risk family

- indicator that forward 63-trading-day maximum drawdown is worse than the family/stratum train-fold p10; the estimator, its stratum, and a minimum n below which the cell abstains are registered. [A23]
- 63-day excess-return/path distribution is **mandatory-print**, non-verdict-bearing (replaces "optional"). [A22]

Market grading uses QLedger's 63-trading-day ruler and canonical exchange calendar.

## Horizon law [A22][A26]

- Market primary horizon: **exactly 63 trading days**.
- 5d/21d substrate grade rows exist automatically under QLedger's grading ruler and are non-claim diagnostics — excluded from the FDR partition, excluded from every verdict.
- A genuine 21-trading-day claim requires its own declared, budgeted cell; it may never borrow the 63d cell's budget.
- **126 trading days may never be a QLedger claim.** 126d material is off-render descriptive only.

---

# 6. Baselines and negative controls

Required for every family:

1. family/age prior;
2. tape-only;
3. mechanism-only;
4. recognition-only;
5. mechanism + recognition;
6. matched macro/industry-state control;
7. shuffle mechanism labels within calendar/industry blocks;
8. pseudo-event dates matched on volatility/drawdown;
9. structural-epoch placebo — pre-declared per cohort now (homebuilders: epoch placebo), replacing the "or transfer test" analyst choice; [A22]
10. current-snapshot-backfill exclusion — this is a **rule**, not merely a control: absence of a captured historical snapshot ⇒ the field is `not_reconstructable` for that cutoff, is dropped, and is **never backfilled**; [A23]
11. leave-issuer-out — pre-declared LOO issuer list {DHI, PHM, TOL, KBH} plus a mechanical estimability rule, replacing "where possible"; [A22]
12. leave-cycle-out.

The CPI HAR-1 promoted null is a standing prior against generic analogues. No analogue output enters these trials unless Market Memory separately validates a compatible retrieval arm.

---

# 7. Cross-validation and embargo

- rolling or expanding-origin splits by calendar time;
- group split by effective cycle block;
- no source published after the test cutoff;
- embargo **exactly 63 trading days** between train and test labels when windows overlap, replacing "at least the target horizon"; [A22]
- acquisition/identity epochs do not cross folds by default;
- no parameter refit on the embargoed 2024+ prospective holdout — **that holdout is selected now**, replacing "if that holdout is selected"; [A22] **[AG8, M8-fix]** the embargoed 2024+ prospective holdout IS the `OPEN_ACCRUING` affordability era (§3) — it contributes zero historical N (AG8) precisely because it is still open, and only becomes a closed prospective block, hence a genuine holdout episode, once lawfully closed by a future pre-registered closing rule.
- every fold prints population, missingness, class balance, and source coverage.

---

# 8. Metrics and gates

## Probabilistic state targets

- multiclass or binary Brier score;
- paired ΔBrier versus the named baseline;
- calibration/ECE;
- era/year sign stability;
- class confusion and abstention.

## Risk target

- Brier and paired ΔBrier;
- precision/recall at a frozen threshold only if threshold registered;
- drawdown-tail coverage;
- no raw-row Wilson interval without effective-block adjustment.

## Promotion conjunction

A cell passes only if:

1. paired incremental metric favors the challenger;
2. **registered-block-cluster** bootstrap CI excludes zero on the positive side — **one-sided 90% CI**; resampling unit = the registered closed macro block (§3, the same block-cluster unit AG9 already uses for inference — never a date/month block) [AP8, M1 fix, corrects the prior "month/episode-block" phrasing]; bootstrap draws and seed registered: **800 draws, seed 7 — the CPI house default value convention, frozen, no tuning [AP4, A4P binding]. `engine/grading_stats.py`'s `BOOT_DRAWS`/`BOOT_SEED` constants (800/7) supply only these two numeric defaults — its `block_bootstrap_ci` resampling UNIT (whole calendar DATES/months, per its own docstring: "resamples whole stamp DATES... same-day cross-sectionally-correlated rows") is NOT imported; IMCE resamples registered macro blocks, not dates.** **Disclosure, same class as the BH-FDR low-n note (§8 item 3, `IMCE_HB0_A4_CELL_BUDGET_INPUTS.md` §6): a block bootstrap over 3 clusters (the B≤3 basis, AP2) is near-degenerate — with only 3 blocks, the space of distinct resample compositions is small enough that 800 draws mostly repeat a handful of possible cluster combinations, so the CI's nominal coverage is not a reliable small-sample guarantee at current B; this is disclosed, not hidden, and does not change the predetermined `underpowered_accruing` status.** [A21]
3. BH-FDR at q=0.10 survives within the declared family — the single partition `imce_hist_v0` over the 6 historical cells (§1); [A6]
4. sign is positive in **at least 2/3 of blocks**, replacing "preregistered minimum share"; [A21]
5. `n_effective_blocks >= 40`. Provenance: this floor was imported from BC-1, where the unit was *monthly panel stamps* — re-denominated in macro-cycle blocks it is a materially more stringent bar than any house precedent. **RULING: the 40-block floor is kept for `PROMOTE_ELIGIBLE`.** A separate, non-promoting rung MAY be added later with its own preregistered floor and a hard authority ceiling bound to the all-false YAML authority flags; no such rung exists in this contract today. [A12]
6. PIT, identity, source-rights, and structural-break gates pass;
7. no material result is carried by one cycle or one issuer — "material" means the sign must survive **every** leave-one-block-out AND **every** leave-one-issuer-out refit; [A21]
8. probability calibration passes, or output remains `PRIOR`/`ABSTAIN`.

A point estimate without the full conjunction is not a pass.

---

# 9. Sample floors and issuer residuals

- Family cell: 40 independent episode blocks minimum for measured status (provenance and ruling: §8 item 5). [A12]
- "Frozen hierarchy" means frozen **in the pre-outcome registration commit**. Cross-cohort pooling may shrink estimates but may **never** increase `n_effective_blocks`. [A10]
- Issuer-specific residual estimate: at least **8 independent episodes of that issuer**, drawn from **≥5 distinct blocks**, plus hierarchical shrinkage; research only. [A11]
- Any authority discussion for an issuer residual: at least **12 independent episodes**, drawn from **≥8 distinct blocks**, plus a matured prospective cohort; still requires separate promotion. Both rungs are **unreachable for every current cohort**, stated plainly. [A11]
- CELH: descriptive regardless of count under the current history.
- Sparse cells pool only under a frozen hierarchy (§9 above, [A10]); otherwise abstain.

---

# 9a. Reachable-status table (preregistered, pre-outcome) [A1]

| Cohort | Honest historical blocks | Historical cells | Max reachable ladder rung on history |
|---|---|---|---|
| CELH | barred by rule | 0 | `DESCRIPTIVE` |
| Homebuilders | **≤3, uniform, cancellation-scoped, ALL 6 cells [AP2]** (general ≤5 cap [AG5, AG6] describes no cell registered today; named 7-entry list retains 5 N-contributing blocks generally, but only 3 of those 5 carry cancellation-reconstructable disclosure — §3) | 6 (one BH partition `imce_hist_v0`, q=0.10) | `REGISTERED`→`REPLAYED`, estimation-only; never `DISPLAY`, never `PROMOTE_ELIGIBLE` |
| Memory | 2 completed + 1 open (ungradeable) | 0 | `REGISTERED` only |
| Banks | ~3, 0 PIT-clean | 0 | `DESCRIPTIVE` / feasibility |

**Preregistered expectation:** no cohort can satisfy the §8 `n_effective_blocks >= 40` conjunction item on historical data. Every historical cell's status outcome is fixed pre-outcome, invariant to what the data show.

---

# 10. Missingness and population law

- Missing is never zero.
- `not_licensed` and `not_reconstructable` are separate from `missing`.
- The primary comparison uses the same eligible population for baseline and challenger.
- Complete-case selection must not improve the challenger by silently removing hard cases. Mechanical test [A20]: a hashed population manifest is frozen pre-outcome; metrics are reported on the intersection population, and dropped-row counts are reported by reason.
- **An era-correlated missing indicator is forbidden in the primary comparison — disclosure alone is not sufficient.** [A19] Missing-indicator use elsewhere must still be preregistered and cannot become an era/proprietary-source proxy without disclosure. **[A19] scope extended by AG11 (A4G binding, records the C3 disposition): the ban applies to EVERY era-correlated metric, not only LEN's cancellation rate.** The homebuilder definition crosswalk found the identical structural pattern on other metrics — TOL's own "spec[ulative] homes" disclosure label appears only from FY2023 (zero hits 2001–2020, a terminology/disclosure-emphasis change, not necessarily a behavior change), PHM's "Unsold" unit split is confirmed only from FY2024, and cancellation-formula disclosure itself appears issuer-by-issuer across FY2008–FY2016. Any metric whose availability correlates with an era rather than with the underlying mechanism is subject to the same ban: no missing-indicator on it may enter a primary comparison, and disclosure of the pattern alone does not cure the prohibition.
- Coverage degradation can demote or abstain; it cannot be imputed by an LLM.

---

# 11. Multiplicity and trial budget

Before any real run, register:

- exact candidate cells — frozen at **6 historical cells** (§1); [A5] **minted and frozen as exactly these six dotted cell IDs [AP8, M2 binding — presented to Sol for ratification]:**

  | # | Cell ID | Family | Target (§1) |
  |---|---|---|---|
  | 1 | `imce_phase_v0.next_order_softness_1rp` | `rf.cycle_pattern.imce_phase_v0` | next `order_softness` cohort state, 1 reporting period |
  | 2 | `imce_phase_v0.next_order_softness_3rp` | `rf.cycle_pattern.imce_phase_v0` | next `order_softness` cohort state, 3 reporting periods |
  | 3 | `imce_phase_v0.order_softness_false_repair_3rp` | `rf.cycle_pattern.imce_phase_v0` | `order_softness` false-repair/relapse within 3 reporting periods |
  | 4 | `imce_sync_v0.next_order_softness_1rp` | `rf.cycle_pattern.imce_sync_v0` | `next_local_state_1rp`, mapped to `order_softness` (AP1) |
  | 5 | `imce_sync_v0.forward_63_trading_day_drawdown_tail` | `rf.cycle_pattern.imce_sync_v0` | `forward_63_trading_day_drawdown_tail`, contrast [M+R vs M] [**A4P.1 R3** normalized naming, was `forward_63d_drawdown_tail`] |
  | 6 | `imce_risk_v0.forward_63_trading_day_drawdown_tail` | `rf.cycle_pattern.imce_risk_v0` | `forward_63_trading_day_drawdown_tail`, [M vs family/stratum prior] |

  Derivation is mechanical: family (dropping the `rf.cycle_pattern.` prefix, implied) + target, using
  `order_softness` explicitly wherever AP1 maps a target to that D5 state (Cells 1–4), and each cell's own
  already-registered target string verbatim where the cell's target is a market/risk quantity, not a D5-state
  transition (Cells 5–6, which merely draw `order_softness` into their `M_t` input basis per AP2, §3 — see
  `IMCE_A4P_ORDER_SOFTNESS_STATE_CONSTRUCTION_V1.md` §3.0 on why a cell's `M_t` basis and its target identity
  are not the same thing). `IMCE_A4G_SIX_CELL_DISPOSITION.md` §0 and `IMCE_A4G_PROPOSED_A4_REGISTRATION_PACKET.md`
  use these exact IDs.
- families, targets, horizons, features, transformations;
- parameter ranges — **single frozen values are required**, replacing "preferably single frozen values"; any grid is counted into the cell budget; [A22]
- FDR family and q — single partition `imce_hist_v0` at q=0.10; [A6] **the future runner asserts exactly the six registered cell IDs above before BH correction, and applies exactly one correction at q=0.10 over their union — no seventh cell may silently enter the denominator [AP5, A4P binding, registration stop condition not code];**
- bootstrap draws and seed — **800 block-bootstrap draws, seed 7, CPI house default, frozen, no tuning [AP4]**;
- holdout dates — the 2024+ prospective holdout; **[AG8, M8-fix]** this holdout IS the `OPEN_ACCRUING` affordability era (§3, AG8) — zero historical N until lawfully closed, at which point it becomes a prospective block, never backfilled into `n_blocks_hist`;
- outcome handling for 0-pass, partial-pass, and harmful cells (§12).

Exploration may use shrunken estimates, but promotion remains subject to the frozen family-wide FDR.

---

# 12. Outcome handling

## Zero pass

`promoted_null` and `underpowered_accruing` are distinct labels, determined **mechanically** by preregistered `n_effective_blocks` [MAJ-4 fix, was bare `n_eff`] versus the floor computed pre-outcome — never by post-hoc judgment. [A2]

- `promoted_null`: a cell that reached its preregistered `n_effective_blocks` [MAJ-4 fix] floor and returned a genuine, adequately powered null; write one scoped `promoted_null` truth; numeric-reject candidates with gate artifact; no page or authority change; reopen only under a new registration naming the null and a structural reason.
- `underpowered_accruing`: a cell whose preregistered `n_effective_blocks` [MAJ-4 fix] sits below its floor. **All 6 historical cells in this contract are pre-labeled `underpowered_accruing`** (§9a); requeue-pointer semantics per house Research Factory runbook apply. [A2]
- **Status governance [G8-M7]:** `underpowered_accruing` is a Research-Factory/trial-ledger status ONLY. It is not a CPI truth status (the truth-schema enum is candidate/display/confirmer/scored/promoted_null/retired/superseded), and no row may enter the CPI registry under it without an explicit schema + consumer-matrix amendment — an unknown status would fence no surface. A sub-floor historical readout is not an earned null and is never printed as one; "no display" means no product-surface authority, not the hiding of an adjudicated null.

## Partial pass

- truth statement names passing and failing cells;
- no extrapolation to issuers/families/horizons not tested;
- display-only until prospective evidence matures;
- **Fourth branch [A3, hardened per G8-B7]:** a sub-floor nominal pass — a bootstrap/point-estimate pass on a cell below its preregistered `n_effective_blocks` [MAJ-4 fix, was bare `n_eff`] floor — is relabeled `underpowered_accruing`. The point estimate is **archived as a descriptive number only**: no display, no truth statement, no citation, **and no role of any kind — prior, weight, hyperparameter, or otherwise — in any prospective cell. Prospective cells are graded prior-free.** (The earlier "prospective PRIOR" carry-path is deleted: it was a laundering channel from the historical arm into the promotion arm.)

## Harmful

- record direction and magnitude of harm;
- retire the feature/model recipe;
- do not retry with threshold tweaks in the same family.

---

# 13. Prospective law

After registration:

- nightly is the sole forward-ledger advancer;
- first observation wins for a cutoff/episode;
- no historical backfill into the prospective cohort;
- corrections append and supersede, never rewrite the original decision-time packet;
- market and mechanism outcomes accrue separately;
- live and backtest badges never blend;
- come-back date is computed from accrual rate and n floor **and published at registration** — **the PROMOTION-CLOCK headline is `~2160` [AP8, M4 fix, A4P binding — corrects AP2's ~2149 figure, which itself does not describe promotion timing]**, computed on the ZERO-HISTORICAL-CREDIT basis §13 below derives; memory and banks later still. **[AP8, M4 fix — full correction, propagated from AP2's error]:** AP2 (below) computed a "come-back date" of ~2149 by crediting the SIX REGISTERED CELLS' existing historical block count (B=3) toward the 40-block floor — `2026-08 + (40-3)×years_per_block`. **This double-counts historical evidence that AG1 and AP3 already zero-weight for promotion**: AG1 states promotion-bearing evidence is "100% PROSPECTIVE... historical replay carries zero weight... by any mechanism, direct or indirect," and AP3 makes the preregistered minimum prospective share **exactly 100%** — so the 3 historical blocks the six registered cells have already accrued (2014–2023) contribute **zero**, not `B=3`, toward any promotion-relevant block count. **The correct promotion clock starts counting from zero PROSPECTIVE blocks today, not from the historical B=3.** Fencepost convention, pinned once and used consistently (AG5's own inclusive convention, `IMCE_HB0_A4_CELL_BUDGET_INPUTS.md` §7): the 2014-01→2023-12 span is **exactly 120 months = 10.0 years** over the 3 cancellation-basis blocks ⇒ **3.333.../year-per-block** (this ratio is used only as an ACCRUAL-RATE estimate — how fast a new closed block has historically formed — never as a credit toward the floor). Promotion-clock arithmetic, shown in full: `come_back_year ≈ 2026 + 8/12 + 40 × (10.0/3) = 2026.6667 + 40 × 3.3333 = 2026.6667 + 133.3333 = 2160.0 → ~2160`. **~2160 is the promotion-relevant headline; the AP2 ~2149 figure (and its AG5 ~2153 / pre-A4G ~2145 predecessors) is demoted to an explicitly-labeled NON-PROMOTION diagnostic** — see below — never cited as a promotion timeline again. [A24, AG1, AP2, AP3, AP8]
- **Non-promotion diagnostic, demoted and relabeled [AP8, M4 fix] — the historical-block-count illustration (formerly mislabeled "come-back date"):** `~2149` (B=3 uniform cancellation-scoped basis, six registered cells: span 2014-01→2023-12 = 9.9y over 3 blocks = 3.30y/block, `2026-08 + (40-3)×3.30 ≈ 2148.8`) and its predecessor `~2153` (B=5 general-block basis, `IMCE_HB0_A4_CELL_BUDGET_INPUTS.md` §7) are retained ONLY as illustrations of the historical arm's order-of-magnitude distance from the 40-block floor (contract §3 AG5: "the upper bound already fails the... floor of 40 by roughly an order of magnitude... so no analytic refinement changes any cell's predetermined `underpowered_accruing` status") — **neither figure is a promotion timeline and neither may be cited as one.** They answer "when would the historical arm's own block count nominally reach 40, hypothetically, if historical replay counted toward promotion" — a counterfactual AG1/AP3 already forecloses. The genuinely promotion-relevant figure is the `~2160` prospective-only clock above.
- two separate counters are maintained: `n_blocks_hist` and `n_blocks_prosp`. [A24]
- a **preregistered minimum prospective share** is required before any promotion: **100%, machine-readable [AP3, A4P binding]** — already implied by AG1 ("promotion-bearing evidence is 100% prospective; zero historical weight of any kind"), now made explicit. [A24, AP3]
- **claim-class taxonomy** (§0a, three classes per G8-B5): cycle-block claims (forecast/edge) are prospective-only and unreachable from history; transcription/reproduction-fidelity claims use the issuer-quarter row as the natural replicate, are reachable now, and carry zero forecast authority; coverage/abstention-calibration claims are block-denominated under the §3 independent-shock law and the AG3 cap (`n_effective_blocks ≤ B`) [BLK-2 correction — was "the DEFF rule", now struck]. [A24]

---

# 14. Authority ladder

`DESCRIPTIVE -> REGISTERED -> REPLAYED -> DISPLAY -> PROSPECTIVE_SHADOW -> PROMOTE_ELIGIBLE`

No step implies the next. Prophet opportunity authority requires a separate decision and consumer contract. Position sizing requires an additional independent gate.

The historical arm of this contract is instrumentation, episode-record construction, and design validation — explicitly **not** a promotion path (§0a, §9a). [A24]

---

# 15. Stop condition

This contract ends at preregistration design. Do not run it until:

- Fable accepts the IMCE architecture;
- pilot source/episode censuses return;
- owner and episode anchor are resolved;
- exact candidate count is frozen;
- trial-ledger families are declared;
- the criteria commit precedes real outcome access;
- **the reachable-status table (§9a) is recorded.** [A25]
- **every macro block boundary used to partition an outcome run is receipted against a dated macro-series or issuer-event source (§3 AG17); a `not_yet_receipted` boundary may not be used to partition an outcome run.** [AG17]
- **no `rf.cycle_pattern.imce_phase_v0` state target may be registered unless it is mapped to a named D5 state whose observability class is registered (§2 Homebuilders, AG14).** [AG14, MAJ-5] A target left unmapped, or mapped to a state typed `descriptive_only` (`incentive_support`, `pace_recovery`) without an explicit named-subset or single-issuer re-scoping accepted at registration, blocks that target's registration — this is binding on the registration act, not merely a disclosed open item. **[AP1, A4P — this condition is now DISCHARGED for the 3 declared phase-family targets and sync Cell 4: all are mapped to `order_softness`, §1, §2, `IMCE_A4P_ORDER_SOFTNESS_STATE_CONSTRUCTION_V1.md`. It remains binding on any future target this contract might add.]**
- **the future historical-cell runner asserts exactly the six registered `imce_hist_v0` cell IDs before applying BH correction, and applies exactly one correction at q=0.10 over their union — no seventh cell (a diagnostic, a sensitivity re-run, or a cell from a different family) may silently enter the denominator.** [AP5, A4P binding — registration stop condition, not a code requirement; no new FDR-partition writer, schema, ledger, or store is built by this rule]

---

# 15a. Freeze mechanics [A25]

- **Two-commit discipline:** the criteria commit strictly precedes the runner/outcome commit.
- **Freezer of record:** Fable / operator (V1); Sol / A4G authorization, 2026-08-21 (V1.1); Sol / A4P authorization, 2026-08-21 (V1.2).
- **Freeze location:** this document (V1.2.1) plus future trial-ledger `declared_budget` rows — IMCE-03 / A4 work, proposed-not-registered in `IMCE_A4G_PROPOSED_A4_REGISTRATION_PACKET.md`, not yet performed as an actual registration act. The deterministic `order_softness` construction is frozen normatively in `IMCE_A4P_ORDER_SOFTNESS_STATE_CONSTRUCTION_V1.md` [AP1].
- **Repository pin:** re-pinned at registration, a future act. No commit SHA in this document or its YAML projection is asserted as "registered" today.
- **`config_hash`:** recorded at registration.
- **New stop condition** (folded into §15 above): "reachable-status table not recorded."
- **A4G stop condition** (folded into §15 above): "a macro block boundary lacks a dated-source receipt and an outcome run would partition on it." [AG17]
- **A4G stop condition** (folded into §15 above): "a phase-family state target lacks a registered mapping to a named D5 state with a registered observability class." [AG14, MAJ-5]
- **A4P stop condition** (folded into §15 above, now DISCHARGED for the declared targets): the mapping condition above is satisfied for all 3 phase-family targets and sync Cell 4 — all map to `order_softness` with a registered deterministic construction. [AP1]
- **A4P stop condition** (folded into §15 above): "the future historical-cell runner has not asserted exactly the six registered `imce_hist_v0` cell IDs, or applies more than one BH correction, or a seventh cell enters the denominator." [AP5]

---

# Appendix A — Amendment index [A25]

Traceability map from each of the 26 adjudicated amendments to the section(s) it touches in this document. Amendment source: `research/IMCE_ROUND3_ARCHITECTURE_FREEZE_BY_FABLE.md` §9 / D8.

| Amendment | Section(s) touched |
|---|---|
| A1 | §2 (CELH, Homebuilders, Banks), §9a (new) |
| A2 | §12 Zero pass |
| A3 | §12 Partial pass (fourth branch) |
| A4 | §4 Recognition vector `R_t` |
| A5 | §1 (cell budgets) |
| A6 | §1, §8 item 3, §11 |
| A7 | §5 Synchronization family |
| A8 | §3 (frozen historical block list) |
| A9 | §3 (effective-block-count law, DEFF rule — **struck by AG3**, see Appendix B) |
| A10 | §9 (frozen hierarchy) |
| A11 | §9 (issuer-residual rungs) |
| A12 | §8 item 5, §9 |
| A13 | §2 Banks |
| A14 | §2 Memory |
| A15 | §2 Memory (coupling flag) |
| A16 | §4 Mechanism vector `M_t` (ordinal-sensor law) |
| A17 | §2 Homebuilders |
| A18 | §2 Homebuilders (LEN/NVR) |
| A19 | §10 (era-correlated missing indicator ban) |
| A20 | §10 (complete-case mechanical test) |
| A21 | §8 items 2, 4, 7 |
| A22 | §5, §6 items 9/11, §7, §11 |
| A23 | §5 Risk family, §6 item 10 |
| A24 | §0a (new), §13, §14 |
| A25 | §15, §15a (new), Appendix A (this table) |
| A26 | Header (binding statement); YAML registration-relevant-fields projection requirement — **[AP8 F6] "lossless" dropped, binding surface extended to include the construction file by reference** |

---

# Appendix B — A4G amendment index [AG1–AG18]

Traceability map from each of Sol's 18 A4G rulings (authorized 2026-08-21, the preregistration amendment gate) to the section(s) each touches in this document (V1.1). Full rationale, citations, and before/after text: `IMCE_A4G_AMENDMENT_LOG.md`. Authority for every row: **Sol, A4G authorization 2026-08-21.**

| Amendment | Ruling (short) | Section(s) touched |
|---|---|---|
| AG1 | Promotion-bearing evidence is 100% prospective; zero historical weight/prior of any kind | §0a |
| AG2 | Statistical-unit law: issuer replication may never raise independent-shock N | §3 (effective-block-count law) |
| AG3 | STRIKE `n_eff = B·m/[1+(m−1)ρ]` as the `n_effective_blocks` definition; ρ no longer a required frozen N-parameter (closes lane-1 gap 9) | §3 |
| AG4 | Within-block issuer dependence survives only as a differently-named precision diagnostic; never satisfies the 40-block floor | §3 |
| AG5 | Historical replay ≤5 closed non-overlapping blocks as an upper bound; exact pseudo-N unnecessary; reconciles lane-1 7-list vs lane-2 5-list (C2); come-back date published on the B=5 basis (~2153) — **[AP2 recomputed this on B=3 for all 6 registered cells (~2149); AP8 then demoted BOTH ~2153 and ~2149 to non-promotion diagnostics, since AG1/AP3's zero-historical-weight rule means the genuine promotion clock is a zero-historical-credit prospective-only figure, ~2160. AG5's B≤5 general-block-taxonomy finding itself is unchanged and still stands for the block list and any hypothetical future non-cancellation cell — see Appendix C.]** | §3, §2 Homebuilders, §9a, §13 |
| AG6 | Cancellation cells ≤3 denominator-reconstructable historical blocks (2014–2019 grind carries only partial FY2016+ coverage); cell-level scoping (MAJ-1) | §3, §2 Homebuilders |
| AG7 | "2013 taper" and "2018 air-pocket" are named sub-episodes, zero N; no boundary minting needed for N (closes lane-1 gap 12) | §3 (frozen historical block list) |
| AG8 | 2024–2026 affordability era is `OPEN_ACCRUING`: zero historical N until lawfully closed; the 2024+ prospective holdout IS this era | §3, §7, §11 |
| AG9 | Inference = block-cluster / leave-one-block-out; a dependence adjustment may only reduce, never increase, the shock count | §3 (effective-block-count law) |
| AG10 | C1 accepted: LEN exclusion reason restated (no stated formula + era-correlated press-release absence; 10-K MD&A does disclose 14%); AG10-clarif settles cell-level vs feature-level scoping (MAJ-2) | §2 Homebuilders |
| AG11 | C3 accepted: era-correlated-missingness ban [A19] extended to every era-correlated metric | §10 |
| AG12 | TOL primary cancellation denominator = signed contracts in quarter; beginning-quarter backlog = mandatory printed sensitivity | §2 Homebuilders |
| AG13 | NVR separate stratum — reaffirmed, no change | §2 Homebuilders |
| AG14 | State-vector observability scoping: `order_softness` cohort-wide; `completed_inventory_build` named 3-issuer subset; `incentive_support`/`pace_recovery` descriptive-only, never imputed into a cohort cell; mapping requirement made BINDING at registration (MAJ-5) | §2 Homebuilders, §15, §15a |
| AG15 | `pit_class` enum closed at exactly `{pit_pure, revision_optimistic, mixed}` | §2 Homebuilders |
| AG16 | No roster widening | §2 Homebuilders |
| AG17 | Exact source-dated macro boundaries must be receipted before any outcome partition runs; a descriptive sub-episode's date uncertainty may not manufacture another block | §3, §15, §15a |
| AG18 | Macro legs must be rights-safe owner sources: FRED/ALFRED excluded; PMMS HELD; no NAR storage; a source without lawful vintages stays `revision_optimistic` | §2 Homebuilders, §4 Context |

---

# Appendix C — A4P amendment index [AP1–AP8]

Traceability map from each of Sol's A4P rulings (7 original, authorized 2026-08-21, the preregistration criteria closure gate; AP8 is the same-branch revision fixing Fable's adjudication of the Opus red-team pass, same authorization date) to the section(s) each touches in this document (V1.2). Full rationale, citations, and before/after text: `IMCE_A4G_AMENDMENT_LOG.md` (A4P section, appended after the AG1–AG18 record). Authority for every row: **Sol, A4P authorization 2026-08-21.**

| Amendment | Ruling (short) | Section(s) touched |
|---|---|---|
| AP1 | Phase-family targets (and sync Cell 4) mapped to `order_softness`; deterministic construction frozen in a new normatively-referenced file | §1, §2 Homebuilders, §15/§15a |
| AP2 | All 6 registered v0 historical cells share the order-softness basis, uniformly B≤3; LEN excluded from all 6 | §1, §2 Homebuilders, §3, §9a |
| AP3 | Minimum prospective share for promotion = 100%, machine-readable | §13 |
| AP4 | Bootstrap: 800 draws, seed 7 (CPI house default value convention, frozen) | §8 item 2, §11 |
| AP5 | No new FDR-partition writer; binding runner obligation (six-cell assertion, one BH correction) as a registration stop condition | §11, §15/§15a |
| AP6 | Macro boundary receipts: partially executed / OPEN (0 of 8 boundaries receipted, none changed); Treasury CSV/XML archive receipt obtained by the commissioning session (V-grade, AP8 revision) | `IMCE_A4G_SOURCE_BOUNDARY_TABLE.md` §2/§6/§7 (no contract-MD change — AG17/AG18 law unchanged) |
| AP7 | A4 registration packet regenerated; `declared_budget` row hashes recomputed (not preserved) because `reason` strings changed | `IMCE_A4G_PROPOSED_A4_REGISTRATION_PACKET.md` (all sections) |
| AP8 | Same-branch revision fixing 2 blockers + 7 majors + minors from Fable's adjudication of the Opus red-team pass on PR #6213: corrected a fabricated composite AG17 quotation (B1); construction file admits blocks only per the contract's registered list, never itself, plus a ≥2-issuer cohort-minting floor (B2); bootstrap unit corrected to registered-block-cluster, not date/month (M1); six cell IDs minted and frozen (M2); packet restricted to exactly Sol's four A4 acts (M3); promotion clock corrected to zero-historical-credit ~2160, old figures demoted to non-promotion diagnostics (M4); additive-only annotations on the A3 census file (M5); ruling 6 honesty correction plus a real Treasury V-grade receipt (M6); fail-closed DHI/TOL era-coverage gate added (M7); plus all named minors | §3, §8, §11, §13, §15/§15a, Appendix A/B/C headers; `IMCE_A4P_ORDER_SOFTNESS_STATE_CONSTRUCTION_V1.md`; `IMCE_A4G_SIX_CELL_DISPOSITION.md`; `IMCE_A4G_SOURCE_BOUNDARY_TABLE.md`; `IMCE_A4G_PROPOSED_A4_REGISTRATION_PACKET.md`; `IMCE_HB0_SOURCE_DEFINITION_CENSUS_V1.md` (annotation-only) |

---

# Appendix D — A4P.1 amendment index [R1–R7]

Traceability map from each of Sol's 7 A4P.1 rulings (fourth-gate REQUEST_CHANGES preflight closure, authorized 2026-08-22) to the section(s) each touches in this document (V1.2.1). Full rationale, citations, and before/after text: `IMCE_A4G_AMENDMENT_LOG.md` (A4P.1 section, appended after the A4P Summary table). Authority for every row: **Sol, fourth-gate verdict, 2026-08-22.**

| Ruling | Ruling (short) | Section(s) touched |
|---|---|---|
| R1 | Retire the stale DEFF `n_effective_blocks` denomination from the coverage/abstention claim class; census every registration-relevant artifact for other live DEFF/ρ prose; annotate the hb0 lane-2 recommendations as superseded | §0a; YAML `prospective_accrual_first_posture.claim_classes[coverage_abstention_claims].denomination`; `IMCE_HB0_BLOCKERS_AND_FALSIFIERS.md`, `IMCE_HB0_INDEPENDENT_BLOCK_LIST.md`, `IMCE_HB0_A4_CELL_BUDGET_INPUTS.md` (annotation-only) |
| R2 | Freeze population and label semantics: historical v0 population permanently `named_subset_basis: [PHM, KBH]`; prospective v0 eligible pooled cohort `[DHI, PHM, KBH, TOL]`; three-row label truth table; reword misleading "pooled homebuilder stratum" prose | §1, §2 Homebuilders; YAML `state_vector_observability_scoping.order_softness`; `IMCE_A4G_SIX_CELL_DISPOSITION.md`; `IMCE_A4G_PROPOSED_A4_REGISTRATION_PACKET.md`; `IMCE_A4P_ORDER_SOFTNESS_STATE_CONSTRUCTION_V1.md` §3.1 label-semantics wording; `IMCE_HB0_SOURCE_DEFINITION_CENSUS_V1.md` (annotation-only) |
| R3 | Ratify the six frozen cell IDs; normalize the sync family's target nomenclature to `forward_63_trading_day_drawdown_tail` everywhere it identifies the actual target/cell | §1, §11, §11 table; YAML `trials[].cell_definition`/`.cell_ids`, `six_cell_ids_union`; `IMCE_A4G_SIX_CELL_DISPOSITION.md`; `IMCE_A4G_PROPOSED_A4_REGISTRATION_PACKET.md`; `IMCE_HB0_SOURCE_DEFINITION_CENSUS_V1.md` (annotation-only) |
| R4 | Freeze the complete A4 registration state-transition — every registration-state site enumerated with byte-exact old→new text; both placeholder procedures (`repository_pin_observed`, `config_hash`) frozen deterministically; A4P.1 performs none of the flips | `IMCE_A4G_PROPOSED_A4_REGISTRATION_PACKET.md` (new §"A4 STATE TRANSITION (frozen, verbatim-or-abort)") — no change to this contract's or the YAML's live status fields, which stay `candidate_not_registered` until A4 itself executes |
| R5 | Treasury CMT source-rights disposition: `GO_LIMITED`, scope + basis frozen verbatim; closes the prior wave's escalation item 5 | `IMCE_A4G_SOURCE_BOUNDARY_TABLE.md` row 13, §4, §7; YAML `rights_safe_macro_legs_only.treasury_cmt` |
| R6 | Boundary receipts remain honestly open — registration is permitted with open receipts; exactly the two named post-registration dispositions; a registered v0 boundary may never move after outcome inspection | YAML `effective_block_law.post_registration_boundary_evidence_law`; `IMCE_A4G_SOURCE_BOUNDARY_TABLE.md` §6 preamble; this contract's own AG17 law is restated, not changed |
| R7 | Regenerate all three declared_budget row reason strings and `config_hash` values from the corrected packet; verify exact hash parity against `engine/trial_ledger.py`; record the three superseded V1.2 hashes | `IMCE_A4G_PROPOSED_A4_REGISTRATION_PACKET.md` §2–§4; `IMCE_A4G_AMENDMENT_LOG.md` (A4P.1 section, superseded-hash record) |

---

**This document authorizes nothing beyond itself.** No cell, model, score, or outcome computation has started here. No `rf.cycle_pattern.imce_*` family is registered by V1.2.1. The next authorized act on this family is A4 registration proper, per the frozen state-transition table in `IMCE_A4G_PROPOSED_A4_REGISTRATION_PACKET.md` (as regenerated by AP7, corrected by AP8, closed for registration by A4P.1's R4).

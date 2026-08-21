# IMCE Preregistration and Evaluation Contract — V1.1 (Amended, Frozen)
## Mechanism-conditioned market recognition, next-state, and 63-day risk research

**Status:** `candidate_not_registered`. This document has not been registered and no real outcome evaluation has been run. Registration (repository re-pin, `config_hash`, trial-ledger `declared_budget` rows) is a future act — IMCE-03 / A4.
**Binding rule:** This markdown document BINDS. `IMCE_PREREGISTRATION_CANDIDATE_V1.yaml` is a lossless machine-readable projection of this document only — the YAML carries no independent authority; on any apparent divergence, this document controls. [A26]
**Authority:** Research/display only. All ranking, gating, sizing, escalation, origination, and trading authority fields are FALSE. No authority is granted, implied, or reserved by this document.
**Supersedes:** `IMCE_PREREGISTRATION_AND_EVALUATION_CONTRACT.md` (2026-08-20 Round 3 candidate) and `IMCE_PREREGISTRATION_CANDIDATE.yaml` (schema `imce.preregistration_candidate.v0`).
**Amendment provenance:** 26 amendments (A1–A26), adjudicated and frozen in `research/IMCE_ROUND3_ARCHITECTURE_FREEZE_BY_FABLE.md` (§9, D8), applied at V1 (2026-08-20). **V1.1 adds 18 further amendments (AG1–AG18), Sol's A4G preregistration-amendment-gate rulings, authorized 2026-08-21**, settling the A3 reconciliation (`IMCE_HB0_SOURCE_DEFINITION_CENSUS_V1.md` lane 1 × `research/imce/hb0/` lane 2) into one outcome-blind A4-ready specification. Full rationale, citations, and before/after text for each AG amendment: `IMCE_A4G_AMENDMENT_LOG.md`. Every amended clause below carries a trailing `[A<n>]` (Round 3) or `[AG<n>]` (A4G) tag; consolidated indices are Appendix A (A1–A26) and Appendix B (AG1–AG18).
**Date:** 2026-08-20 (V1); **amended 2026-08-21 (V1.1, A4G)**.

---

# 0. Constitutional question

The trial is not "does 2W MACD work?"

The trial is:

> **Given a mechanism state frozen from source-backed evidence independently of future price, does a fixed market-recognition vector add out-of-sample information about the registered next mechanism state or 63-trading-day risk/path target beyond the mechanism-only baseline?**

The trial can return a null. A null becomes durable CPI truth memory.

## 0a. Prospective-accrual-first posture [A24][AG1]

The historical arm of this contract is instrumentation, episode-record construction, and design validation. It is **explicitly not a promotion path** — see §9a for the predetermined per-cohort historical status table and §13 for the counters and minimum prospective share that gate any future promotion. Two claim classes exist and must never be conflated:

**Promotion-bearing evidence is 100% PROSPECTIVE [AG1, A4G binding].** Historical homebuilder replay (or replay of any other cohort) carries **zero weight** in any future promotion decision, full stop. This is stronger than "not a promotion path": historical replay may not supply a prior, a weight, a hyperparameter, a tiebreak, or any other quantitative influence to a prospective cell's promotion decision, by any mechanism, direct or indirect. §12's "no role of any kind — prior, weight, hyperparameter, or otherwise" clause (deleting the sub-floor "prospective PRIOR" carry-path) already enacted this for the specific sub-floor-pass case; AG1 generalizes it to the historical arm as a whole, for every cell, pass or fail.

- **Cycle-block claims** (forecast/edge): unreachable from history at any current cohort's honest N; prospective-only.
- **Transcription/reproduction-fidelity claims** (passport-field reproduction, denominator-crosswalk fidelity): natural replicate is the issuer-quarter row; honest N is in the hundreds; reachable now; carry **zero forecast authority**. [G8-B5]
- **Coverage and abstention-calibration claims**: block-dependent by construction — a source outage or disclosure change hits every issuer in a period simultaneously — so these are denominated in effective blocks under the §3 independent-shock law and the DEFF rule; row counts are printed but never used as N. [G8-B5]

---

# 1. Trial families — provisional names

Fable must check `data/trial_ledger.jsonl`, name length, and collision before declaration.

| Family | Purpose | Candidate cell budget (frozen) [A5] |
|---|---|---|
| `rf.cycle_pattern.imce_phase_v0` | next family-local state / false-repair targets | **3 cells**: 3 state targets × pooled homebuilder stratum × contrast [M vs family/age prior] |
| `rf.cycle_pattern.imce_sync_v0` | incremental recognition over mechanism-only | **2 cells**: targets {`next_local_state_1rp`, `forward_63d_drawdown_tail`} × contrast [M+R vs M] |
| `rf.cycle_pattern.imce_risk_v0` | 63-trading-day drawdown-tail and path targets | **1 cell**: `forward_63d_drawdown_tail` × [M vs family/stratum prior] |

**Historical total = 6 cells.** [A5]

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
- **LEN** is excluded from cancellation-rate cells. **[A18, restated by AG10 / C1]** Reason restated from the original "no press-release cancellation rate; era-correlated missingness by construction": LEN's own 10-K MD&A **does** disclose a cancellation figure (14%, FY2025) — the missingness is channel-scoped (absent from EX-99.1 press releases), not absolute. The exclusion **stands**, but its recorded ground is now: **"no stated formula anywhere in LEN's disclosure record (denominator unverifiable) + era-correlated absence from the press-release channel specifically."** It carries a Millrose Feb-2025 break flag (structural, independent of the cancellation exclusion); the exclusion is printed.
- **NVR** is a mechanism outlier (100%-option land model, corrected to a strong-majority option-lot model per NVR's own FY2025 10-K — "we generally do not engage in land development"): it is a separate stratum or a designated transfer test, **never pooled to raise n**. Inclusion/exclusion is frozen pre-outcome. **[A18, reaffirmed AG13 — no change; carried forward unmodified by A4G.]**
- **TOL cancellation-rate denominator [AG12, A4G binding — settles election E1].** TOL discloses cancellation on two conventions in the same exhibit: "as a percentage of signed contracts in quarter" and "as a percentage of beginning-quarter backlog." **Primary convention = gross signed contracts in the period** (cross-issuer comparable with DHI/PHM/KBH's gross-orders basis). **Beginning-quarter backlog basis is a MANDATORY printed sensitivity** for every TOL cancellation readout, not an optional alternate — a result that flips under the backlog basis is not a pass (contract §2(b) alternate-convention rule, unchanged).
- **Roster widening — NO. [AG16, A4G binding]** The six-name roster (DHI, PHM, TOL, KBH, LEN, NVR) stays frozen. Widening it (e.g. to HOV, BZH, MHO, MTH — the listed, continuously-public non-roster survivors named in `IMCE_HB0_SOURCE_DEFINITION_CENSUS_V1.md` §2d) improves representativeness but supplies **zero** additional independent-shock power (survivorship census falsifier F-V4 / F-4: at ρ≈0.8, going from m=5 to m=9 moves `n_eff` from ~6.0 to ~6.1) — more issuers inside the same closed blocks are correlated rows, not new draws. Representativeness and statistical power are separate problems; only the roster question is open to future amendment, never as a power lever.
- **Survivorship condition [G8-B4]:** the roster is a 2026-survivor roster over a window containing the 2006–2011 sector mortality event, and the ported episode substrate is survivor-stamped. IMCE-HB-0 must produce a named census of delisted/bankrupt/acquired homebuilders for the study window with an explicit inclusion decision; until it lands, every homebuilder cell readout carries a mandatory survivorship-bias disclosure and no cohort mean is quoted without it.
- **Epoch-clock rule [G8-M2]:** structural epochs drawn on the operating clock (business events) are descriptive partitions only; any block or epoch used to partition a **recognition-outcome** statistic must use recognition-clock (`available_at`) boundaries. Epochs are frozen before any outcome inspection, not merely before fitting.
- **Vintage rider [G8-M6]:** IMCE-HB-0 adds a per-source vintage audit for every macro/homebuilder source; a leg without retrievable vintages is declared `revision_optimistic` in `pit_class` and disclosed in every readout using it. **`pit_class` is a CLOSED enum of exactly three tokens [AG15, A4G binding]: `pit_pure`, `revision_optimistic`, `mixed`** (identical to `config/cycle_pattern/truth_schema.md`'s CPI enum) — no fourth token may ever be minted for this family; a source-census vocabulary finer than these three (e.g. HB-0's five-way `source_vintage_class`) is a local diagnostic that must crosswalk down to one of the three before it touches any cell, never substitute for the enum. See `IMCE_A4G_SOURCE_BOUNDARY_TABLE.md` for the per-source mapping.
- **Rights-safe macro legs only [AG18, A4G binding].** Every macro/context leg feeding `C_t` or `M_t` must be a rights-safe OWNER source: **FRED and ALFRED are excluded categorically** (clause (q), `DO_NOT_INGEST`, binds display tier too — no store/cache/archive/database incorporation in any use class). **Freddie Mac PMMS is HELD**, not GO and not blocked: its 1971→present weekly archive is genuinely PIT-pure, but the site terms bar redistribution/commercial exploitation without a separate licence, in tension with the archive's open availability — it may not be used until that rights question resolves; Treasury constant-maturity yields (confirmed `pit_pure`, public domain, full archive) are the primary rate leg in the interim. **No NAR series may be stored** (Existing-Home Sales, Housing Affordability Index) — NAR's terms bar storage in a retrieval system outright, not merely redistribution, so self-archival does not cure it; an affordability construct is assembled from clean owner legs (Census NRS price + Treasury rate + Census/BLS income), never adopted from the NAR or NAHB indices. **A macro source without lawful, retrievable historical vintages stays `pit_class = revision_optimistic`** by default (Census NRS/NRC, FHFA HPI, BEA RFI, Census C30, BLS CPI-shelter) until an individually-cleared upgrade path executes (e.g. Census NRS's first-print release archive, back to 1995 — costed, not yet executed).
- **State-vector observability scoping [AG14, A4G binding — settles election E2 for 3 of 4 D5 states].** The D5 homebuilder mechanism-local state vector is `order_softness` / `completed_inventory_build` / `incentive_support` / `pace_recovery`. Today: **`order_softness` is the only state broadly cohort-observable** (net orders/backlog/cancellation rate disclosed, in some form, by all six roster issuers). **`completed_inventory_build` may exist only as a NAMED THREE-ISSUER SUBSET** (DHI ~9,300 completed unsold units, LEN ~5,000 + per-community ratio, PHM unit-level Unsold split; KBH qualitative-only, NVR combined-dollar-bucket-only, TOL `missing`) — any cell using it is a named-subset claim, never a cohort claim, and must be labelled as such. **`incentive_support` and `pace_recovery` remain descriptive and may NOT be imputed into any cohort cell** — each rests on a single disclosing issuer today (LEN for incentive figures; KBH for build/cycle time) and populating the other issuers by inference would violate §10's "missing is never zero" and the ordinal-sensor missingness rule. The exact per-target mapping of the `rf.cycle_pattern.imce_phase_v0` family's 3 declared state targets (§1) against these four D5 states is an open A4 registration item — this amendment scopes observability, it does not itself re-declare the cell budget or re-map which named state each of the 3 phase-family targets tracks.
- Honest historical blocks for `n_effective_blocks` accounting: **≤5 as a closed-block UPPER BOUND, general cell; ≤3 for cancellation-rate cells [AG5, AG6 — see §3].** The 5–7 range in the frozen block list (§3 [A8]) names 7 labelled episodes; §3 below resolves how many of them count toward N. Max reachable ladder rung on history: `REGISTERED`→`REPLAYED`, estimation-only readout, **never `DISPLAY`, never `PROMOTE_ELIGIBLE`**. [A1]

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

**`n_effective_blocks` is capped at the raw block count [AG3, AG5, AG6]: `n_effective_blocks := min(B, [any other candidate estimator])`, where:**

- **General cells (all cell classes not scoped to cancellation-rate): B ≤ 5** — the five CLOSED, non-overlapping blocks in the table above (#1, #2, #3, #4, #5). This is an **upper bound**, not a point estimate — block-to-block serial dependence (AG9 below) can only push it lower. [AG5]
- **Cancellation-rate cells: B ≤ 3** — of the five closed blocks, only three carry a denominator-reconstructable cancellation-rate disclosure across the roster: the 2014–2019 grind (from FY2016), the 2020–2021 pandemic boom, and the 2022–2023 rate shock. Blocks #1 (GFC bust) and #2 (GFC recovery) predate the stated-denominator era for most of the roster (PHM/NVR confirmed only FY2016+; KBH FY2008+ and self-contradictory in that filing; LEN never states a formula) — freezing a canonical denominator there would require assuming an unstated early convention matched the later stated one, which is exactly the flattening this contract exists to prevent. **[AG6]**
- **Exact pseudo-N (a fitted ρ/DEFF point estimate) is unnecessary** — the upper bound already fails the §8 item 5 floor of 40 by roughly an order of magnitude on every cell class, so no analytic refinement changes any cell's predetermined `underpowered_accruing` status (§9a, §12). [AG5]

**Reconciliation of the A3-pair block counts [AG5, records the C2 disposition].** Lane 1 (`IMCE_HB0_SOURCE_DEFINITION_CENSUS_V1.md`) carried the frozen list's 7 labelled entries forward without resolving how many count toward N (its own gap 12: "the exact boundary-date determination is left as an open A4 item"). Lane 2 (`IMCE_HB0_INDEPENDENT_BLOCK_LIST.md` §2–§4) audited the same 7 entries against five admissibility conditions and hardened to **B = 5**, on two independent grounds: the 2013 taper overlaps block 2 and is the same rate/credit transmission channel (fails non-overlap and distinct-shock), and the 2024–2026 era is open (fails the "closed" condition already applied to the memory cohort's open HBM/AI episode, freeze §7.3). **RULING: B = 5 wins for N-accounting [AG5].** This is not a rejection of lane 1's 7-item NAMED list — that list is retained verbatim above as the frozen historical-episode taxonomy — it is a ruling that of the 7 named entries, 2 (the taper, the open era) contribute zero to `n_effective_blocks`, leaving 5 that do. Both lanes' language is preserved in this reconciliation rather than one being silently discarded.

**Named sub-episodes contribute ZERO N [AG7].** "2013 taper" and "2018 air-pocket" are named sub-episodes of blocks 2 and 3 respectively (table above) — retained for descriptive and diagnostic use (e.g. within-block regime narrative), contributing **zero** to `n_effective_blocks`. No boundary-date minting is required to reach this status; a sub-episode's uncertain exact start/end date is irrelevant to N-accounting once it is typed as contributing zero. This closes lane-1 gap 12: the "2013 taper" boundary dates need never be minted for the purpose of counting N, though they remain open for descriptive/diagnostic dating (`IMCE_A4G_SOURCE_BOUNDARY_TABLE.md`).

**2024–2026 affordability era is `OPEN_ACCRUING` [AG8].** Zero historical N. It becomes a prospective (not historical) block only when it is lawfully closed by a pre-registered closing rule — no such rule is registered by this amendment; registering one is a future A4/prospective-law act, not performed here. Until closed, it accrues toward `n_blocks_prosp` (§13), never `n_blocks_hist`.

**Within-block issuer dependence survives ONLY as a precision diagnostic, differently named [AG4].** The `DEFF = 1 + (m−1)·ρ` construction and its `n_eff = (B×m)/DEFF` output are not deleted from the research record — they are **renamed and demoted**. As `n_issuer_precision_diagnostic` (or an equivalent differently-named field chosen at A4 registration), it may be computed, printed, and used to characterize within-block issuer-pooling precision — but it **can never be used as, mistaken for, or substituted for `n_effective_blocks`**, can **never satisfy the §8 item 5 forty-block floor**, and carries no promotion authority of any kind. `n_rows` and `n_issuers` remain printed for transparency; **promotion uses `n_effective_blocks` (capped at B per AG3/AG5/AG6) and nothing else.**

**Inference is block-cluster / leave-one-block-out [AG9].** Cross-validation, bootstrap, and materiality tests (§7, §8 item 7) operate at the block level. A dependence adjustment (issuer-level ρ, or a future block-level `rho_block` per `IMCE_HB0_INDEPENDENT_BLOCK_LIST.md` §3 D4) **may only ever REDUCE `n_effective_blocks` below its capped value — never increase the shock count** above the raw closed-block count B. Serial (block-to-block) dependence in particular is unaddressed by the struck DEFF construction (it discounted only within-block issuer correlation); any future `rho_block` registration can only tighten the bound, consistent with the upper-bound framing in AG5.

**Exact source-dated macro boundaries must be receipted before any outcome partition runs [AG17].** A block boundary used to partition an actual outcome run must carry a citation to a dated macro-series or issuer-event source, not merely a narrative news citation (per the M4 correction in `IMCE_HB0_SOURCE_DEFINITION_CENSUS_V1.md` §6a: cancellation rate cannot certify its own block boundaries, being `M_t` itself). **Uncertainty about a descriptive sub-episode's exact date may NOT be used to manufacture another block** — the 2013 taper and 2018 air-pocket stay sub-episodes at zero N (AG7) regardless of whether their own boundary dates are ever receipted. See `IMCE_A4G_SOURCE_BOUNDARY_TABLE.md` for the current receipt status of every block boundary; `not_yet_receipted` boundaries block only an actual outcome partition on that boundary, not this contract's freeze.

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
- no parameter refit on the embargoed 2024+ prospective holdout — **that holdout is selected now**, replacing "if that holdout is selected"; [A22]
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
2. month/episode-block bootstrap CI excludes zero on the positive side — **one-sided 90% CI**; bootstrap draws and seed registered; [A21]
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
| Homebuilders | 5–7 | 6 (one BH partition `imce_hist_v0`, q=0.10) | `REGISTERED`→`REPLAYED`, estimation-only; never `DISPLAY`, never `PROMOTE_ELIGIBLE` |
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

- exact candidate cells — frozen at **6 historical cells** (§1); [A5]
- families, targets, horizons, features, transformations;
- parameter ranges — **single frozen values are required**, replacing "preferably single frozen values"; any grid is counted into the cell budget; [A22]
- FDR family and q — single partition `imce_hist_v0` at q=0.10; [A6]
- bootstrap draws and seed;
- holdout dates — the 2024+ prospective holdout;
- outcome handling for 0-pass, partial-pass, and harmful cells (§12).

Exploration may use shrunken estimates, but promotion remains subject to the frozen family-wide FDR.

---

# 12. Outcome handling

## Zero pass

`promoted_null` and `underpowered_accruing` are distinct labels, determined **mechanically** by preregistered `n_eff` versus the floor computed pre-outcome — never by post-hoc judgment. [A2]

- `promoted_null`: a cell that reached its preregistered `n_eff` floor and returned a genuine, adequately powered null; write one scoped `promoted_null` truth; numeric-reject candidates with gate artifact; no page or authority change; reopen only under a new registration naming the null and a structural reason.
- `underpowered_accruing`: a cell whose preregistered `n_eff` sits below its floor. **All 6 historical cells in this contract are pre-labeled `underpowered_accruing`** (§9a); requeue-pointer semantics per house Research Factory runbook apply. [A2]
- **Status governance [G8-M7]:** `underpowered_accruing` is a Research-Factory/trial-ledger status ONLY. It is not a CPI truth status (the truth-schema enum is candidate/display/confirmer/scored/promoted_null/retired/superseded), and no row may enter the CPI registry under it without an explicit schema + consumer-matrix amendment — an unknown status would fence no surface. A sub-floor historical readout is not an earned null and is never printed as one; "no display" means no product-surface authority, not the hiding of an adjudicated null.

## Partial pass

- truth statement names passing and failing cells;
- no extrapolation to issuers/families/horizons not tested;
- display-only until prospective evidence matures;
- **Fourth branch [A3, hardened per G8-B7]:** a sub-floor nominal pass — a bootstrap/point-estimate pass on a cell below its preregistered `n_eff` floor — is relabeled `underpowered_accruing`. The point estimate is **archived as a descriptive number only**: no display, no truth statement, no citation, **and no role of any kind — prior, weight, hyperparameter, or otherwise — in any prospective cell. Prospective cells are graded prior-free.** (The earlier "prospective PRIOR" carry-path is deleted: it was a laundering channel from the historical arm into the promotion arm.)

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
- come-back date is computed from accrual rate and n floor **and published at registration** (homebuilders reach the 40-block floor around ~2145 at the census accrual rate — §9a; memory and banks later still). [A24]
- two separate counters are maintained: `n_blocks_hist` and `n_blocks_prosp`. [A24]
- a **preregistered minimum prospective share** is required before any promotion. [A24]
- **claim-class taxonomy** (§0a, three classes per G8-B5): cycle-block claims (forecast/edge) are prospective-only and unreachable from history; transcription/reproduction-fidelity claims use the issuer-quarter row as the natural replicate, are reachable now, and carry zero forecast authority; coverage/abstention-calibration claims are block-denominated under the §3 independent-shock law with the DEFF rule. [A24]

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

---

# 15a. Freeze mechanics [A25]

- **Two-commit discipline:** the criteria commit strictly precedes the runner/outcome commit.
- **Freezer of record:** Fable / operator (V1); Sol / A4G authorization, 2026-08-21 (V1.1).
- **Freeze location:** this document (V1.1) plus future trial-ledger `declared_budget` rows — IMCE-03 / A4 work, proposed-not-registered in `IMCE_A4G_PROPOSED_A4_REGISTRATION_PACKET.md`, not yet performed as an actual registration act.
- **Repository pin:** re-pinned at registration, a future act. No commit SHA in this document or its YAML projection is asserted as "registered" today.
- **`config_hash`:** recorded at registration.
- **New stop condition** (folded into §15 above): "reachable-status table not recorded."
- **A4G stop condition** (folded into §15 above): "a macro block boundary lacks a dated-source receipt and an outcome run would partition on it." [AG17]

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
| A9 | §3 (effective-block-count law, DEFF rule) |
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
| A26 | Header (binding statement); full YAML lossless-projection requirement |

---

# Appendix B — A4G amendment index [AG1–AG18]

Traceability map from each of Sol's 18 A4G rulings (authorized 2026-08-21, the preregistration amendment gate) to the section(s) each touches in this document (V1.1). Full rationale, citations, and before/after text: `IMCE_A4G_AMENDMENT_LOG.md`. Authority for every row: **Sol, A4G authorization 2026-08-21.**

| Amendment | Ruling (short) | Section(s) touched |
|---|---|---|
| AG1 | Promotion-bearing evidence is 100% prospective; zero historical weight/prior of any kind | §0a |
| AG2 | Statistical-unit law: issuer replication may never raise independent-shock N | §3 (effective-block-count law) |
| AG3 | STRIKE `n_eff = B·m/[1+(m−1)ρ]` as the `n_effective_blocks` definition; ρ no longer a required frozen N-parameter (closes lane-1 gap 9) | §3 |
| AG4 | Within-block issuer dependence survives only as a differently-named precision diagnostic; never satisfies the 40-block floor | §3 |
| AG5 | Historical replay ≤5 closed non-overlapping blocks as an upper bound; exact pseudo-N unnecessary; reconciles lane-1 7-list vs lane-2 5-list (C2) | §3, §2 Homebuilders |
| AG6 | Cancellation cells ≤3 denominator-reconstructable historical blocks | §3, §2 Homebuilders |
| AG7 | "2013 taper" and "2018 air-pocket" are named sub-episodes, zero N; no boundary minting needed for N (closes lane-1 gap 12) | §3 (frozen historical block list) |
| AG8 | 2024–2026 affordability era is `OPEN_ACCRUING`: zero historical N until lawfully closed | §3, §13 |
| AG9 | Inference = block-cluster / leave-one-block-out; a dependence adjustment may only reduce, never increase, the shock count | §3, §7, §8 |
| AG10 | C1 accepted: LEN exclusion reason restated (no stated formula + era-correlated press-release absence; 10-K MD&A does disclose 14%) | §2 Homebuilders |
| AG11 | C3 accepted: era-correlated-missingness ban [A19] extended to every era-correlated metric | §10 |
| AG12 | TOL primary cancellation denominator = signed contracts in quarter; beginning-quarter backlog = mandatory printed sensitivity | §2 Homebuilders |
| AG13 | NVR separate stratum — reaffirmed, no change | §2 Homebuilders |
| AG14 | State-vector observability scoping: `order_softness` cohort-wide; `completed_inventory_build` named 3-issuer subset; `incentive_support`/`pace_recovery` descriptive-only, never imputed into a cohort cell | §2 Homebuilders |
| AG15 | `pit_class` enum closed at exactly `{pit_pure, revision_optimistic, mixed}` | §2 Homebuilders |
| AG16 | No roster widening | §2 Homebuilders |
| AG17 | Exact source-dated macro boundaries must be receipted before any outcome partition runs; a descriptive sub-episode's date uncertainty may not manufacture another block | §3, §15, §15a |
| AG18 | Macro legs must be rights-safe owner sources: FRED/ALFRED excluded; PMMS HELD; no NAR storage; a source without lawful vintages stays `revision_optimistic` | §2 Homebuilders, §4 Context |

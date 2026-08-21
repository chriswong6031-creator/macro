# IMCE Preregistration and Evaluation Contract — V1 (Amended, Frozen)
## Mechanism-conditioned market recognition, next-state, and 63-day risk research

**Status:** `candidate_not_registered`. This document has not been registered and no real outcome evaluation has been run. Registration (repository re-pin, `config_hash`, trial-ledger `declared_budget` rows) is a future act — IMCE-03.
**Binding rule:** This markdown document BINDS. `IMCE_PREREGISTRATION_CANDIDATE_V1.yaml` is a lossless machine-readable projection of this document only — the YAML carries no independent authority; on any apparent divergence, this document controls. [A26]
**Authority:** Research/display only. All ranking, gating, sizing, escalation, origination, and trading authority fields are FALSE. No authority is granted, implied, or reserved by this document.
**Supersedes:** `IMCE_PREREGISTRATION_AND_EVALUATION_CONTRACT.md` (2026-08-20 Round 3 candidate) and `IMCE_PREREGISTRATION_CANDIDATE.yaml` (schema `imce.preregistration_candidate.v0`).
**Amendment provenance:** 26 amendments (A1–A26), adjudicated and frozen in `research/IMCE_ROUND3_ARCHITECTURE_FREEZE_BY_FABLE.md` (§9, D8). This document applies all 26 without redesign. Every amended clause below carries a trailing `[A<n>]` tag so a reviewer can trace each change to its amendment; a consolidated index is in Appendix A.
**Date:** 2026-08-20

---

# 0. Constitutional question

The trial is not "does 2W MACD work?"

The trial is:

> **Given a mechanism state frozen from source-backed evidence independently of future price, does a fixed market-recognition vector add out-of-sample information about the registered next mechanism state or 63-trading-day risk/path target beyond the mechanism-only baseline?**

The trial can return a null. A null becomes durable CPI truth memory.

## 0a. Prospective-accrual-first posture [A24]

The historical arm of this contract is instrumentation, episode-record construction, and design validation. It is **explicitly not a promotion path** — see §9a for the predetermined per-cohort historical status table and §13 for the counters and minimum prospective share that gate any future promotion. Two claim classes exist and must never be conflated:

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
- **LEN** is excluded from cancellation-rate cells — its missingness is era-correlated by construction (no press-release cancellation rate) and it carries a Millrose Feb-2025 break flag; the exclusion is printed. [A18]
- **NVR** is a mechanism outlier (100%-option land model): it is a separate stratum or a designated transfer test, **never pooled to raise n**. Inclusion/exclusion is frozen pre-outcome. [A18]
- **Survivorship condition [G8-B4]:** the roster is a 2026-survivor roster over a window containing the 2006–2011 sector mortality event, and the ported episode substrate is survivor-stamped. IMCE-HB-0 must produce a named census of delisted/bankrupt/acquired homebuilders for the study window with an explicit inclusion decision; until it lands, every homebuilder cell readout carries a mandatory survivorship-bias disclosure and no cohort mean is quoted without it.
- **Epoch-clock rule [G8-M2]:** structural epochs drawn on the operating clock (business events) are descriptive partitions only; any block or epoch used to partition a **recognition-outcome** statistic must use recognition-clock (`available_at`) boundaries. Epochs are frozen before any outcome inspection, not merely before fitting.
- **Vintage rider [G8-M6]:** IMCE-HB-0 adds a per-source vintage audit for every macro/homebuilder source; a leg without retrievable vintages is declared `revision_optimistic` in `pit_class` and disclosed in every readout using it.
- Honest historical blocks: 5–7 (§9a). Max reachable ladder rung on history: `REGISTERED`→`REPLAYED`, estimation-only readout, **never `DISPLAY`, never `PROMOTE_ELIGIBLE`**. [A1]

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

### Frozen historical block list [A8]

The literal block list is frozen with boundary dates below. Any change requires a new amendment-log entry.

- GFC bust: 2006–2009
- GFC recovery / land-light era: 2010–2013
- 2013 taper (partial)
- 2014–2019 grind, including the 2018 air-pocket
- 2020–2021 pandemic boom
- 2022–2023 rate shock / cancellation spike
- 2024–2026 affordability/incentive era

### Effective-block-count law [A9]

The effective block count is the number of independent shock realizations. **It may never be increased by counting issuers, rows, targets, horizons, directions, or overlapping windows.**

DEFF rule: `n_effective_blocks` may be derived from issuer-episodes only via a design-effect estimator using a correlation parameter (ρ) that is frozen pre-outcome and fit on train folds only. The raw block count is always printed alongside the effective count.

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

Registered macro/industry context from lawful source owners, with PIT class and rights. Context is descriptive unless the trial explicitly registers it.

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
- **An era-correlated missing indicator is forbidden in the primary comparison — disclosure alone is not sufficient.** [A19] Missing-indicator use elsewhere must still be preregistered and cannot become an era/proprietary-source proxy without disclosure.
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

---

# 15a. Freeze mechanics [A25]

- **Two-commit discipline:** the criteria commit strictly precedes the runner/outcome commit.
- **Freezer of record:** Fable / operator.
- **Freeze location:** this document (V1) plus future trial-ledger `declared_budget` rows — IMCE-03 work, not yet performed.
- **Repository pin:** re-pinned at registration, a future act. No commit SHA in this document or its YAML projection is asserted as "registered" today.
- **`config_hash`:** recorded at registration.
- **New stop condition** (folded into §15 above): "reachable-status table not recorded."

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

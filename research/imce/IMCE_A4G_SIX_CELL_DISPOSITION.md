# IMCE-A4G — Final Six-Cell Disposition

**Wave:** A4G. Records-only. No outcome number, model fit, or trial-ledger write appears anywhere below.
**Authority:** amended contract V1.1 §1/§8/§9a (`IMCE_PREREGISTRATION_AND_EVALUATION_CONTRACT_V1.md`), as amended by `IMCE_A4G_AMENDMENT_LOG.md`.
**Purpose:** the mandatory Sol deliverable (c) — for each of the 6 registered historical cells: target, block basis, LEN membership, NVR stratum handling, predetermined status, and the lane-2 §8 six elections settled or marked settled-by-ruling.

---

## 0. Cell budget (unchanged — frozen at 6, one BH partition)

Per contract §1 (A5/A6, unamended by A4G): **6 historical cells**, one BH-FDR partition `imce_hist_v0` at q=0.10. A4G settles the statistical unit and evidentiary scope those 6 cells run under; it does not add, remove, or resize any cell.

| Trial family | Cells | Cell definition |
|---|---|---|
| `rf.cycle_pattern.imce_phase_v0` | 3 | 3 state targets × pooled homebuilder stratum × contrast [M vs family/age prior] |
| `rf.cycle_pattern.imce_sync_v0` | 2 | targets {`next_local_state_1rp`, `forward_63d_drawdown_tail`} × contrast [M+R vs M] |
| `rf.cycle_pattern.imce_risk_v0` | 1 | `forward_63d_drawdown_tail` × [M vs family/stratum prior] |

---

## 1. Per-cell disposition

### Cell 1 — `rf.cycle_pattern.imce_phase_v0`, target: next family-local state at 1 reporting period

| Field | Value |
|---|---|
| Target | next family-local state, 1 reporting period (D5 mechanism-local state transition) |
| Block basis | **B ≤ 5** (general cell — AG5) — GFC bust, GFC recovery, 2014–2019 grind, pandemic boom, 2022–2023 rate shock. Taper (2013) and 2018 air-pocket are subepisodes, zero N (AG7); affordability era is `OPEN_ACCRUING`, zero N (AG8). |
| LEN membership | Roster member (issuer-level). Cancellation-rate exclusion does not bind this cell's `M_t` construction unless a cancellation-rate feature is drawn in; per contract §2(b) confirmation note, exclusion is feature-level, universal across all 6 cells where the feature is used. |
| NVR stratum handling | Separate stratum, never pooled to raise n (AG13, reaffirmed unchanged). A transfer test is a future registered cell, not this one. |
| Predetermined status | `underpowered_accruing` (mechanical, §12 zero-pass rule — all 6 historical cells pre-labeled) |
| State-vector observability (AG14) | **Depends on which D5 state this target tracks — open A4 registration item (AG14).** If it tracks `order_softness`: full cohort. If `completed_inventory_build`: named 3-issuer subset (DHI/LEN/PHM) only, not a cohort claim. If `incentive_support` or `pace_recovery`: **may not run as a cohort cell at all** under AG14 — descriptive only. This ambiguity is not resolved by A4G; it is an explicit open item (see §3 below). |
| Six elections touched | E2 (partial, via AG14) |

### Cell 2 — `rf.cycle_pattern.imce_phase_v0`, target: next family-local state at 3 reporting periods

| Field | Value |
|---|---|
| Target | next family-local state, 3 reporting periods |
| Block basis | **B ≤ 5** (general cell — AG5), same composition as Cell 1 |
| LEN membership | Same as Cell 1 |
| NVR stratum handling | Same as Cell 1 |
| Predetermined status | `underpowered_accruing` |
| State-vector observability (AG14) | Same open item as Cell 1 — target-to-D5-state mapping not registered by A4G |
| Six elections touched | E2 (partial, via AG14) |

### Cell 3 — `rf.cycle_pattern.imce_phase_v0`, target: false repair/relapse within 3 reporting periods

| Field | Value |
|---|---|
| Target | false repair / relapse within 3 reporting periods |
| Block basis | **B ≤ 5** (general cell — AG5), same composition as Cell 1 |
| LEN membership | Same as Cell 1 |
| NVR stratum handling | Same as Cell 1 |
| Predetermined status | `underpowered_accruing` |
| State-vector observability (AG14) | Same open item as Cell 1 |
| Six elections touched | E2 (partial, via AG14) |

### Cell 4 — `rf.cycle_pattern.imce_sync_v0`, target: `next_local_state_1rp` (M+R vs M)

| Field | Value |
|---|---|
| Target | `next_local_state_1rp`, contrast [M+R vs M] |
| Block basis | **B ≤ 5** (general cell — AG5) unless the mechanism vector's feature set draws a cancellation-rate input, in which case the cancellation-scoped B ≤ 3 (AG6) applies to that feature's contribution — feature-level scoping, contract §2(b) note |
| LEN membership | Roster member; cancellation-rate feature exclusion applies at feature level if drawn |
| NVR stratum handling | Separate stratum, never pooled |
| Predetermined status | `underpowered_accruing` |
| State-vector observability (AG14) | `next_local_state_1rp` is the same D5 next-state target family as Cells 1–3; same open target-to-state mapping item |
| Six elections touched | E2 (partial) |

### Cell 5 — `rf.cycle_pattern.imce_sync_v0`, target: `forward_63d_drawdown_tail` (M+R vs M)

| Field | Value |
|---|---|
| Target | `forward_63d_drawdown_tail`, contrast [M+R vs M] |
| Block basis | **B ≤ 5** (general cell — AG5); a market/risk target, not itself a cancellation-denominator construction, so the general cap applies unless a cancellation-rate feature enters `M_t` |
| LEN membership | Roster member; feature-level exclusion if a cancellation feature is drawn |
| NVR stratum handling | Separate stratum, never pooled |
| Predetermined status | `underpowered_accruing` |
| State-vector observability (AG14) | Not directly D5-state-keyed (this is a market drawdown target, not a next-mechanism-state target) — AG14's scoping bears on `M_t`'s input features, not this cell's target itself |
| Six elections touched | none directly; E2 bears on feature construction only |

### Cell 6 — `rf.cycle_pattern.imce_risk_v0`, target: `forward_63_trading_day_drawdown_tail` (M vs family/stratum prior)

| Field | Value |
|---|---|
| Target | `forward_63_trading_day_drawdown_tail`, [M vs family/stratum prior] |
| Block basis | **B ≤ 5** (general cell — AG5); same feature-level cancellation scoping as Cell 5 if applicable |
| LEN membership | Roster member; feature-level exclusion if applicable |
| NVR stratum handling | Separate stratum, never pooled |
| Predetermined status | `underpowered_accruing` |
| State-vector observability (AG14) | Same as Cell 5 |
| Six elections touched | none directly |

---

## 2. Cross-cell summary

| Cell | Family | Block basis (B) | LEN | NVR | Status | Max ladder rung |
|---|---|---|---|---|---|---|
| 1 | `imce_phase_v0` | ≤5 (general) | member; feature-level cancellation exclusion if drawn | separate stratum | `underpowered_accruing` | `REGISTERED`→`REPLAYED`, never `DISPLAY`/`PROMOTE_ELIGIBLE` |
| 2 | `imce_phase_v0` | ≤5 (general) | same | separate stratum | `underpowered_accruing` | same |
| 3 | `imce_phase_v0` | ≤5 (general) | same | separate stratum | `underpowered_accruing` | same |
| 4 | `imce_sync_v0` | ≤5 general / ≤3 if cancellation feature drawn | same | separate stratum | `underpowered_accruing` | same |
| 5 | `imce_sync_v0` | ≤5 general / ≤3 if cancellation feature drawn | same | separate stratum | `underpowered_accruing` | same |
| 6 | `imce_risk_v0` | ≤5 general / ≤3 if cancellation feature drawn | same | separate stratum | `underpowered_accruing` | same |

**All 6 cells are pre-labeled `underpowered_accruing`, mechanically, invariant to any future outcome** (contract §12 zero-pass rule, unamended by A4G — the mechanism, not the label, is what A4G touches). Every cell fails the 40-block floor by roughly an order of magnitude on its stated block basis (5 or 3), whether measured against the general cap or the cancellation cap.

---

## 3. Lane-2 §8 six elections — final disposition

Source: `research/imce/hb0/IMCE_HB0_A4_CELL_BUDGET_INPUTS.md` §8.

| # | Election | Disposition | Ruling |
|---|---|---|---|
| E1 | TOL cancellation denominator: beginning-quarter backlog **or** signed contracts in quarter | **SETTLED.** Primary = signed contracts in quarter; beginning-quarter backlog = mandatory printed sensitivity, both printed either way. | AG12 |
| E2 | Cells keyed to `pace_recovery`/`completed_inventory_build`: re-scope to disclosing issuers (m=1–2, not cohort) **or** drop and re-declare budget | **PARTIALLY SETTLED.** `completed_inventory_build` → named 3-issuer subset (DHI/LEN/PHM), not dropped, not a cohort claim. `incentive_support`/`pace_recovery` → descriptive only, may not be imputed into any cohort cell (functionally the "cannot run as a cohort cell" branch, without literally re-declaring the frozen 6-cell budget). **Open:** which of the 3 declared `imce_phase_v0` targets maps to which D5 state is not registered by this amendment — see §4 below. | AG14 |
| E3 | `rho`/`rho_block` values: frozen pre-outcome, fit on train folds only | **MOOT for N-accounting** — AG3/AG4 remove ρ from the `n_effective_blocks` definition entirely. A future `rho_block` MAY still be registered at actual A4 registration, but only for the AG4 precision-diagnostic field, never for N. | AG3, AG4 |
| E4 | Whether block 2a (2013 taper) and 3a (2018 air-pocket) stay sub-episodes | **SETTLED: YES.** Both are named sub-episodes, contributing zero N, per AG7. | AG7 |
| E5 | MDC's admissibility, if the roster is ever widened | **MOOT** — AG16 forbids roster widening outright. Revisits only if AG16 itself is amended in a future gate. | AG16 |
| E6 | Whether to execute the Census NRS release-archive upgrade to `pit_pure` | **NOT EXECUTED.** Remains a costed, not-yet-executed A4 option — see `IMCE_A4G_SOURCE_BOUNDARY_TABLE.md` §3. This amendment does not execute it; NRS stays `revision_optimistic` today. | unchanged (no AG ruling executes E6) |

---

## 4. Explicit open item — phase-family target-to-D5-state mapping

**Not settled by this amendment, named honestly rather than silently picked (per FROZEN SPEC discipline):** the contract's `rf.cycle_pattern.imce_phase_v0` family declares "3 state targets" (§1) without naming which of the 4 D5 homebuilder mechanism-local states (`order_softness`, `completed_inventory_build`, `incentive_support`, `pace_recovery`) each of the 3 targets tracks. AG14 scopes the OBSERVABILITY of all 4 states (cohort-wide / named-3-subset / descriptive-only ×2) but does not itself assign which 3 of the 4 are the registered targets, nor which target-slot (1-period / 3-period / false-repair) maps to which state.

This matters materially: if any of the 3 declared targets is keyed to `incentive_support` or `pace_recovery`, that target-slot cannot run as a cohort cell at all under AG14 and would need to either re-scope to a single-issuer descriptive readout (not a cohort claim, and arguably outside what "state target" was meant to mean) or be replaced with a target keyed to `order_softness` or the named-subset `completed_inventory_build`. **This is left as an open A4 registration item.** A future A4 registration session must either (a) confirm the 3 targets were always intended as `order_softness`-family transitions only (in which case AG14 imposes no practical constraint), or (b) explicitly re-map or drop any target-slot that turns out to be keyed to a single-issuer-only state, with its own amendment-log entry.

---

**This document authorizes nothing. No cell, model, score, or outcome computation has started. The next authorized act on this family is actual A4 registration — see `IMCE_A4G_PROPOSED_A4_REGISTRATION_PACKET.md`.**

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

**Cell-level ruling applied throughout this section [MAJ-1, MAJ-2 — Fable adjudication of Opus red-team findings, A4G revision 2026-08-21]:** AG6's B≤3 cancellation cap binds a cell IN ITS ENTIRETY whenever that cell's registered input basis includes cancellation-rate data — never merely "a feature's contribution" inside an otherwise B≤5 cell. `order_softness` (contract §2, AG14) is the one D5 state whose registered basis today names cancellation-rate disclosure, so any cell targeting `order_softness` or a `next_local_state`-class target built from it is a **B≤3 cell as currently registered**, not a conditional B≤5-unless-drawn cell. Correspondingly, LEN's cancellation exclusion is **cell-level**: LEN is excluded entirely (issuer-level, not feature-level) from any B≤3 cell, and remains a full roster member in any B≤5 cell, where its cancellation-rate feature (if ever referenced non-primarily) is typed `missing` and never imputed (AG11 ban) rather than "excluded." (The prior draft's "contract §2(b) confirmation note" attribution for feature-level scoping was fabricated — no such note exists in the contract; that language was HB0 census evidence, not a contract clause — corrected here per the amended contract's `[AG10-clarif]` paragraph.) The 2014–2019 grind block, one of the three B≤3-contributing blocks, carries only **partial FY2016+ coverage** for PHM/NVR (AG6, M9-fix) — disclosed at every citation below.

### Cell 1 — `rf.cycle_pattern.imce_phase_v0`, target: next family-local state at 1 reporting period

| Field | Value |
|---|---|
| Target | next family-local state, 1 reporting period (D5 mechanism-local state transition) |
| Block basis | **B ≤ 3** (cancellation-scoped, AG6, MAJ-1) — 2014–2019 grind (**partial, FY2016+ PHM/NVR coverage**), 2020–2021 pandemic boom, 2022–2023 rate shock. GFC bust/recovery excluded (unstated early denominator convention); taper/air-pocket subepisodes zero N (AG7); affordability era `OPEN_ACCRUING` zero N (AG8). Applies because this cell's registered basis draws `order_softness`, which names cancellation-rate disclosure (AG14) — see the cell-level ruling above and §4's open item on the exact target-to-state mapping. |
| LEN membership | **EXCLUDED — cell-level** (AG10-clarif, MAJ-2). LEN is a B≤3-cell exclusion, issuer-level, matching its cancellation-rate-cell exclusion (contract §2 [A18]/AG10). |
| NVR stratum handling | Separate stratum, never pooled to raise n (AG13, reaffirmed unchanged). A transfer test is a future registered cell, not this one. |
| Predetermined status | `underpowered_accruing` (mechanical, §12 zero-pass rule — all 6 historical cells pre-labeled) |
| State-vector observability (AG14) | **Depends on which D5 state this target tracks — open A4 registration item (AG14), now BINDING at registration (§15/§15a, MAJ-5).** If it tracks `order_softness` (the working basis assumed for the B≤3 block-basis line above): full cohort, minus LEN. If `completed_inventory_build`: named 3-issuer subset (DHI/LEN/PHM — note LEN membership here would need reconciling against the cell-level cancellation exclusion if the two bases combine) only, not a cohort claim. If `incentive_support` or `pace_recovery`: **may not run as a cohort cell at all** under AG14 — descriptive only, and per the new binding stop condition, may not be registered unmapped. This ambiguity is not resolved by A4G; it is an explicit open item (see §3 below). |
| Six elections touched | E2 (partial, via AG14) |

### Cell 2 — `rf.cycle_pattern.imce_phase_v0`, target: next family-local state at 3 reporting periods

| Field | Value |
|---|---|
| Target | next family-local state, 3 reporting periods |
| Block basis | **B ≤ 3** (cancellation-scoped, AG6, MAJ-1), same composition and grind-block partial-coverage caveat as Cell 1 |
| LEN membership | **EXCLUDED — cell-level**, same as Cell 1 |
| NVR stratum handling | Same as Cell 1 |
| Predetermined status | `underpowered_accruing` |
| State-vector observability (AG14) | Same open item as Cell 1 — target-to-D5-state mapping not registered by A4G, now binding at registration |
| Six elections touched | E2 (partial, via AG14) |

### Cell 3 — `rf.cycle_pattern.imce_phase_v0`, target: false repair/relapse within 3 reporting periods

| Field | Value |
|---|---|
| Target | false repair / relapse within 3 reporting periods |
| Block basis | **B ≤ 3** (cancellation-scoped, AG6, MAJ-1), same composition and grind-block partial-coverage caveat as Cell 1 |
| LEN membership | **EXCLUDED — cell-level**, same as Cell 1 |
| NVR stratum handling | Same as Cell 1 |
| Predetermined status | `underpowered_accruing` |
| State-vector observability (AG14) | Same open item as Cell 1 |
| Six elections touched | E2 (partial, via AG14) |

### Cell 4 — `rf.cycle_pattern.imce_sync_v0`, target: `next_local_state_1rp` (M+R vs M)

| Field | Value |
|---|---|
| Target | `next_local_state_1rp`, contrast [M+R vs M] |
| Block basis | **B ≤ 3** (cancellation-scoped, AG6, MAJ-1) — same D5 next-state target class as Cells 1–3, so the same cell-level cancellation basis applies; same grind-block partial-coverage caveat |
| LEN membership | **EXCLUDED — cell-level**, same as Cell 1 |
| NVR stratum handling | Separate stratum, never pooled |
| Predetermined status | `underpowered_accruing` |
| State-vector observability (AG14) | `next_local_state_1rp` is the same D5 next-state target family as Cells 1–3; same open target-to-state mapping item, now binding at registration |
| Six elections touched | E2 (partial) |

### Cell 5 — `rf.cycle_pattern.imce_sync_v0`, target: `forward_63d_drawdown_tail` (M+R vs M)

| Field | Value |
|---|---|
| Target | `forward_63d_drawdown_tail`, contrast [M+R vs M] |
| Block basis | **Not yet settled to a single cap.** This is a market/risk target, not itself a `next_local_state`/D5 target — its `M_t` feature composition (and specifically whether it draws cancellation-rate data) is not finalized in the contract. Per the cell-level ruling (MAJ-1): **if** cancellation-rate is included in this cell's registered `M_t` basis at actual A4 registration, **B ≤ 3 applies to the cell entire**; **if** excluded, **B ≤ 5** (general cap, AG5) applies. This is a registration-time decision with its own review, not an open election of this gate (MAJ-1 explicitly removes the "open election" framing for the cap-scoping question itself — what remains open is only the underlying feature-composition fact, a separate, ordinary registration-time detail). |
| LEN membership | Conditional on the same basis: EXCLUDED (cell-level) if this cell registers as B≤3; roster member (cancellation feature typed missing, never imputed, AG11) if B≤5. |
| NVR stratum handling | Separate stratum, never pooled |
| Predetermined status | `underpowered_accruing` (invariant to which basis this cell resolves to — both B≤3 and B≤5 fail the 40-block floor by a wide margin) |
| State-vector observability (AG14) | Not directly D5-state-keyed (this is a market drawdown target, not a next-mechanism-state target) — AG14's scoping bears on `M_t`'s input features, not this cell's target itself |
| Six elections touched | none directly; E2 bears on feature construction only |

### Cell 6 — `rf.cycle_pattern.imce_risk_v0`, target: `forward_63_trading_day_drawdown_tail` (M vs family/stratum prior)

| Field | Value |
|---|---|
| Target | `forward_63_trading_day_drawdown_tail`, [M vs family/stratum prior] |
| Block basis | Same not-yet-settled conditional as Cell 5 — B≤3 entire if cancellation-rate is in the registered `M_t` basis, B≤5 if not; a registration-time decision, not an open election |
| LEN membership | Same conditional as Cell 5 |
| NVR stratum handling | Separate stratum, never pooled |
| Predetermined status | `underpowered_accruing` |
| State-vector observability (AG14) | Same as Cell 5 |
| Six elections touched | none directly |

---

## 2. Cross-cell summary

| Cell | Family | Block basis (B) | LEN | NVR | Status | Max ladder rung |
|---|---|---|---|---|---|---|
| 1 | `imce_phase_v0` | **≤3 entire** (cancellation-scoped, order_softness basis — AG6, MAJ-1) | **EXCLUDED — cell-level** | separate stratum | `underpowered_accruing` | `REGISTERED`→`REPLAYED`, never `DISPLAY`/`PROMOTE_ELIGIBLE` |
| 2 | `imce_phase_v0` | **≤3 entire** | **EXCLUDED — cell-level** | separate stratum | `underpowered_accruing` | same |
| 3 | `imce_phase_v0` | **≤3 entire** | **EXCLUDED — cell-level** | separate stratum | `underpowered_accruing` | same |
| 4 | `imce_sync_v0` | **≤3 entire** (same D5 next-state class) | **EXCLUDED — cell-level** | separate stratum | `underpowered_accruing` | same |
| 5 | `imce_sync_v0` | ≤3 entire if cancellation in registered basis, else ≤5 entire (registration-time decision, MAJ-1) | conditional on basis (excluded if ≤3, roster member with missing-typed feature if ≤5) | separate stratum | `underpowered_accruing` | same |
| 6 | `imce_risk_v0` | same conditional as Cell 5 | conditional, same as Cell 5 | separate stratum | `underpowered_accruing` | same |

**All 6 cells are pre-labeled `underpowered_accruing`, mechanically, invariant to any future outcome** (contract §12 zero-pass rule, unamended by A4G — the mechanism, not the label, is what A4G touches). Every cell fails the 40-block floor by roughly an order of magnitude on its stated block basis (3 or 5), whether measured against the cancellation cap or the general cap. **Cells 1–4 are settled at B≤3 entire under the cell-level ruling (MAJ-1); only Cells 5–6's basis remains conditional on a registration-time feature-composition fact, not on any open scoping election.**

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

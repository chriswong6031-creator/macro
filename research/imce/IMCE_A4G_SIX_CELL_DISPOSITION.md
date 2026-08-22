# IMCE-A4G / A4P — Final Six-Cell Disposition

**Wave:** A4G, updated by A4P (2026-08-21). Records-only. No outcome number, model fit, or trial-ledger write appears anywhere below.
**Authority:** amended contract V1.2 §1/§8/§9a (`IMCE_PREREGISTRATION_AND_EVALUATION_CONTRACT_V1.md`), as amended by `IMCE_A4G_AMENDMENT_LOG.md` (AG1–AG18, AP1–AP8).
**Purpose:** the mandatory Sol deliverable (c) — for each of the 6 registered historical cells: target, block basis, LEN membership, NVR stratum handling, predetermined status, and the lane-2 §8 six elections settled or marked settled-by-ruling. **This is a living A4G/A4P artifact, updated in place to the current law (not an append-only ledger); every material change is logged in `IMCE_A4G_AMENDMENT_LOG.md`.** A4P (AP1, AP2) settles the two items A4G left open: the phase-family target-to-D5-state mapping (§4 below, was open, now closed) and Cells 5–6's conditional block basis (§1 below, was conditional, now uniform B≤3 like Cells 1–4).

---

## 0. Cell budget (unchanged — frozen at 6, one BH partition)

Per contract §1 (A5/A6, unamended by A4G): **6 historical cells**, one BH-FDR partition `imce_hist_v0` at q=0.10. A4G settles the statistical unit and evidentiary scope those 6 cells run under; it does not add, remove, or resize any cell.

| Trial family | Cells | Cell definition |
|---|---|---|
| `rf.cycle_pattern.imce_phase_v0` | 3 | 3 state targets × pooled homebuilder stratum × contrast [M vs family/age prior] |
| `rf.cycle_pattern.imce_sync_v0` | 2 | targets {`next_local_state_1rp`, `forward_63d_drawdown_tail`} × contrast [M+R vs M] |
| `rf.cycle_pattern.imce_risk_v0` | 1 | `forward_63d_drawdown_tail` × [M vs family/stratum prior] |

**Six cell IDs — minted and frozen [AP8, M2, A4P binding; presented to Sol for ratification], the canonical
source is contract §11 and YAML `six_cell_ids_union`; this table uses them, it does not itself define them:**

| Cell | ID |
|---|---|
| 1 | `imce_phase_v0.next_order_softness_1rp` |
| 2 | `imce_phase_v0.next_order_softness_3rp` |
| 3 | `imce_phase_v0.order_softness_false_repair_3rp` |
| 4 | `imce_sync_v0.next_order_softness_1rp` |
| 5 | `imce_sync_v0.forward_63d_drawdown_tail` |
| 6 | `imce_risk_v0.forward_63_trading_day_drawdown_tail` |

---

## 1. Per-cell disposition

**Cell-level ruling applied throughout this section [MAJ-1, MAJ-2 — Fable adjudication of Opus red-team findings, A4G revision 2026-08-21]:** AG6's B≤3 cancellation cap binds a cell IN ITS ENTIRETY whenever that cell's registered input basis includes cancellation-rate data — never merely "a feature's contribution" inside an otherwise B≤5 cell. `order_softness` (contract §2, AG14) is the one D5 state whose registered basis today names cancellation-rate disclosure, so any cell targeting `order_softness` or a `next_local_state`-class target built from it is a **B≤3 cell as currently registered**, not a conditional B≤5-unless-drawn cell. Correspondingly, LEN's cancellation exclusion is **cell-level**: LEN is excluded entirely (issuer-level, not feature-level) from any B≤3 cell, and remains a full roster member in any B≤5 cell, where its cancellation-rate feature (if ever referenced non-primarily) is typed `missing` and never imputed (AG11 ban) rather than "excluded." (The prior draft's "contract §2(b) confirmation note" attribution for feature-level scoping was fabricated — no such note exists in the contract; that language was HB0 census evidence, not a contract clause — corrected here per the amended contract's `[AG10-clarif]` paragraph.) The 2014–2019 grind block, one of the three B≤3-contributing blocks, carries only **partial FY2016+ coverage** for PHM/NVR (AG6, M9-fix) — disclosed at every citation below.

**Uniform basis ruling, closes the Cell 5/6 conditional [AP2, A4P binding, 2026-08-21]:** A4G left Cells 5 and 6 conditional on an undetermined `M_t` feature composition. **AP2 settles it: all six registered v0 historical cells — not only Cells 1–4 — share the `order_softness` mechanism basis** (AP1's target mapping, `IMCE_A4P_ORDER_SOFTNESS_STATE_CONSTRUCTION_V1.md`), and that basis names cancellation-rate disclosure. **Cells 5 and 6 are therefore B≤3-entire, LEN-excluded, on the same footing as Cells 1–4 — the "B≤5 if cancellation excluded" branch is retired for these six cells; it never applies to any of them.** This basis may never be relaxed to B=5 merely to obtain a larger nominal N (AP2).

**Coverage impact — honestly recorded, not silently assumed [AP8, M7 fix].** The `order_softness`
construction's pooled roster is nominally {DHI, PHM, KBH, TOL} (§3.1 of the construction file), but the hb0
evidence census (`research/imce/hb0/evidence/`) has NOT positively receipted DHI's or TOL's net-orders
disclosure format for the 2014–2023 window that matters to all six cells — only PHM and KBH carry a
`[VERIFIED]`-grade receipt covering that window (construction file §1a, full citation trail there). Under the
construction's fail-closed rule, **DHI and TOL currently contribute `NOT_RECONSTRUCTABLE` on the orders-side
input for the entire 2014–2023 window**, so the roster actually eligible to mint a cohort state in that window
is **{PHM, KBH} — exactly the §3.1 ≥2-issuer floor, not comfortably above it.** This affects every cell below
that keys on the pooled `order_softness` cohort state (Cells 1–4 directly; Cells 5–6 via their `M_t` input
basis) — it does not change any cell's B≤3 block-basis or predetermined `underpowered_accruing` status
(§9a/§12 already predetermine that mechanically, independent of realized coverage), but it does mean the
realized episode population within the admissible blocks is thinner than the nominal four-issuer roster
implies. **Escalated to Sol** (this wave's return packet GAPS) as an open item for a future census pass to
receipt DHI's and TOL's pre-FY2025 order-disclosure format, which would restore them as contributors.

**Labelling consequence [AP8, F2(a)]:** because the historically-eligible roster is {PHM, KBH} — a strict
subset of the nominal four-issuer roster — every HISTORICAL `order_softness` read below (Cells 1–4 directly;
Cells 5–6 via their `M_t` basis) carries `named_subset_basis: [PHM, KBH]` and is a named-subset claim, never a
full-cohort claim, until DHI/TOL receipts exist (contract §2, AG14 scope note; construction §1a/§3.1). The
PROSPECTIVE arm is unaffected — genuine cohort basis there. **Whether a ≥2-contributor read may ever carry the
cohort label is Sol's open call (contract §2, F2(d)) — until ruled, named-subset labelling governs.**

**Unstated consequences, named for Sol's ratification review [AP8, F3, full detail: construction §1a]:** (1)
composing the orders-side gate with the cancellation-rate eras (PHM FY2016+, KBH FY2008+), **the grind block
(Cells 1–4's B≤3 basis includes it) yields ZERO cohort states before FY2016** — before then, PHM's
cancellation input is `missing`, leaving KBH as the sole contributor, below the ≥2 floor; the grind block's
genuinely usable window is **FY2016–2019, not the full 2014–2019 span.** (2) **With exactly two eligible
historical contributors, every non-null, non-`MIXED` cohort state is definitionally a PHM–KBH agreement
indicator** — there is no historical reading broader than "did PHM and KBH independently report the same
direction." Neither consequence changes any cell's predetermined `underpowered_accruing` status; both sharpen
what "thin historical read" concretely means for these cells.

### Cell 1 — `imce_phase_v0.next_order_softness_1rp` — `rf.cycle_pattern.imce_phase_v0`, target: next family-local state at 1 reporting period

| Field | Value |
|---|---|
| Target | next family-local state, 1 reporting period (D5 mechanism-local state transition) |
| Block basis | **B ≤ 3** (cancellation-scoped, AG6, MAJ-1) — 2014–2019 grind (**partial, FY2016+ PHM/NVR coverage**), 2020–2021 pandemic boom, 2022–2023 rate shock. GFC bust/recovery excluded (unstated early denominator convention); taper/air-pocket subepisodes zero N (AG7); affordability era `OPEN_ACCRUING` zero N (AG8). Applies because this cell's registered basis draws `order_softness`, which names cancellation-rate disclosure (AG14) — see the cell-level ruling above and §4 (**[AP8, m6 fix] CLOSED, not an open item** — the exact target-to-state mapping is settled by AP1). |
| LEN membership | **EXCLUDED — cell-level** (AG10-clarif, MAJ-2). LEN is a B≤3-cell exclusion, issuer-level, matching its cancellation-rate-cell exclusion (contract §2 [A18]/AG10). |
| NVR stratum handling | Separate stratum, never pooled to raise n (AG13, reaffirmed unchanged). A transfer test is a future registered cell, not this one. |
| Predetermined status | `underpowered_accruing` (mechanical, §12 zero-pass rule — all 6 historical cells pre-labeled) |
| State-vector observability (AG14/AP1) | **SETTLED [AP1, A4P binding].** Tracks `order_softness`. **Nominal** pooled population {DHI, PHM, KBH, TOL} (LEN excluded, NVR held out) — **currently-eligible HISTORICAL contributors {PHM, KBH} only** (construction §1a; every historical read below is `named_subset_basis: [PHM, KBH]`, not a full-cohort claim — see the labelling-consequence paragraph above). Prospectively the full nominal roster is eligible. Deterministic construction: `IMCE_A4P_ORDER_SOFTNESS_STATE_CONSTRUCTION_V1.md`. `completed_inventory_build` and `incentive_support`/`pace_recovery` are explicitly NOT the tracked state for this target (AP1). |
| Six elections touched | E2 (fully settled via AP1) |

### Cell 2 — `imce_phase_v0.next_order_softness_3rp` — `rf.cycle_pattern.imce_phase_v0`, target: next family-local state at 3 reporting periods

| Field | Value |
|---|---|
| Target | next family-local state, 3 reporting periods |
| Block basis | **B ≤ 3** (cancellation-scoped, AG6, MAJ-1), same composition and grind-block partial-coverage caveat as Cell 1 |
| LEN membership | **EXCLUDED — cell-level**, same as Cell 1 |
| NVR stratum handling | Same as Cell 1 |
| Predetermined status | `underpowered_accruing` |
| State-vector observability (AG14/AP1) | **SETTLED [AP1].** Same as Cell 1 — tracks `order_softness`; nominal pooled population {DHI, PHM, KBH, TOL}, NVR held out; **currently-eligible historical contributors {PHM, KBH} only** (construction §1a, `named_subset_basis: [PHM, KBH]`, see the labelling-consequence paragraph above). |
| Six elections touched | E2 (fully settled via AP1) |

### Cell 3 — `imce_phase_v0.order_softness_false_repair_3rp` — `rf.cycle_pattern.imce_phase_v0`, target: false repair/relapse within 3 reporting periods

| Field | Value |
|---|---|
| Target | false repair / relapse within 3 reporting periods |
| Block basis | **B ≤ 3** (cancellation-scoped, AG6, MAJ-1), same composition and grind-block partial-coverage caveat as Cell 1 |
| LEN membership | **EXCLUDED — cell-level**, same as Cell 1 |
| NVR stratum handling | Same as Cell 1 |
| Predetermined status | `underpowered_accruing` |
| State-vector observability (AG14/AP1) | **SETTLED [AP1].** Same as Cell 1 — tracks `order_softness`, false-repair/relapse defined as a `SOFTENING → TIGHTENING` cohort transition (a "repair") that reverts to `SOFTENING` within 3 reporting periods (`IMCE_A4P_ORDER_SOFTNESS_STATE_CONSTRUCTION_V1.md` §4). |
| Six elections touched | E2 (fully settled via AP1) |

### Cell 4 — `imce_sync_v0.next_order_softness_1rp` — `rf.cycle_pattern.imce_sync_v0`, target: `next_local_state_1rp` (M+R vs M)

| Field | Value |
|---|---|
| Target | `next_local_state_1rp`, contrast [M+R vs M] |
| Block basis | **B ≤ 3** (cancellation-scoped, AG6, MAJ-1) — same D5 next-state target class as Cells 1–3, so the same cell-level cancellation basis applies; same grind-block partial-coverage caveat |
| LEN membership | **EXCLUDED — cell-level**, same as Cell 1 |
| NVR stratum handling | Separate stratum, never pooled |
| Predetermined status | `underpowered_accruing` |
| State-vector observability (AG14/AP1) | **SETTLED [AP1].** `next_local_state_1rp` tracks the same `order_softness` next-period cohort state as Cell 1 — not an independently-defined state. |
| Six elections touched | E2 (fully settled via AP1) |

### Cell 5 — `imce_sync_v0.forward_63d_drawdown_tail` — `rf.cycle_pattern.imce_sync_v0`, target: `forward_63d_drawdown_tail` (M+R vs M)

| Field | Value |
|---|---|
| Target | `forward_63d_drawdown_tail`, contrast [M+R vs M] |
| Block basis | **SETTLED — B ≤ 3, cell-level [AP2, A4P binding — was conditional at A4G, resolved here].** This is a market/risk target, not itself a `next_local_state`/D5 target — but its `M_t` feature composition now includes `order_softness` (AP2: "all six v0 inferential historical cells use the same order-softness mechanism basis"), and `order_softness` names cancellation-rate disclosure. Per the cell-level ruling (MAJ-1), that makes this cell B≤3-entire, same composition and grind-block partial-coverage caveat as Cells 1–4 — **not** the B≤5 general basis; that branch is retired for this cell. |
| LEN membership | **EXCLUDED — cell-level [AP2]**, same as Cells 1–4 (was conditional at A4G, now settled). |
| NVR stratum handling | Separate stratum, never pooled |
| Predetermined status | `underpowered_accruing` |
| State-vector observability (AG14/AP1) | The cell's *target* (`forward_63d_drawdown_tail`) is a market drawdown outcome, not itself a D5-state target — AG14/AP1's target-to-state mapping governs the phase family and sync Cell 4 only. This cell's `M_t` **input basis** draws `order_softness` (AP2), which is why its block cap is now B≤3 rather than B≤5. |
| Six elections touched | E2 bears on feature construction (now settled — `order_softness` is the basis, AP2) |

### Cell 6 — `imce_risk_v0.forward_63_trading_day_drawdown_tail` — `rf.cycle_pattern.imce_risk_v0`, target: `forward_63_trading_day_drawdown_tail` (M vs family/stratum prior)

| Field | Value |
|---|---|
| Target | `forward_63_trading_day_drawdown_tail`, [M vs family/stratum prior] |
| Block basis | **SETTLED — B ≤ 3, cell-level [AP2, A4P binding]** — same reasoning and composition as Cell 5. |
| LEN membership | **EXCLUDED — cell-level [AP2]**, same as Cells 1–5. |
| NVR stratum handling | Separate stratum, never pooled |
| Predetermined status | `underpowered_accruing` |
| State-vector observability (AG14/AP1) | Same as Cell 5 — target is a market drawdown outcome, not a D5-state target; `M_t` input basis is `order_softness` (AP2). |
| Six elections touched | E2 bears on feature construction (now settled — `order_softness` is the basis, AP2) |

---

## 2. Cross-cell summary

| Cell | Family | Block basis (B) | LEN | NVR | Status | Max ladder rung |
|---|---|---|---|---|---|---|
| 1 | `imce_phase_v0` | **≤3 entire** (cancellation-scoped, order_softness basis — AG6, MAJ-1) | **EXCLUDED — cell-level** | separate stratum | `underpowered_accruing` | `REGISTERED`→`REPLAYED`, never `DISPLAY`/`PROMOTE_ELIGIBLE` |
| 2 | `imce_phase_v0` | **≤3 entire** | **EXCLUDED — cell-level** | separate stratum | `underpowered_accruing` | same |
| 3 | `imce_phase_v0` | **≤3 entire** | **EXCLUDED — cell-level** | separate stratum | `underpowered_accruing` | same |
| 4 | `imce_sync_v0` | **≤3 entire** (same D5 next-state class) | **EXCLUDED — cell-level** | separate stratum | `underpowered_accruing` | same |
| 5 | `imce_sync_v0` | **≤3 entire [AP2, settled — was conditional at A4G]** | **EXCLUDED — cell-level [AP2]** | separate stratum | `underpowered_accruing` | same |
| 6 | `imce_risk_v0` | **≤3 entire [AP2, settled — was conditional at A4G]** | **EXCLUDED — cell-level [AP2]** | separate stratum | `underpowered_accruing` | same |

**All 6 cells are pre-labeled `underpowered_accruing`, mechanically, invariant to any future outcome** (contract §12 zero-pass rule, unamended by A4G/A4P — the mechanism, not the label, is what A4G/A4P touches). Every cell fails the 40-block floor by roughly an order of magnitude on its B≤3 basis. **All six cells are now settled at B≤3 entire, uniformly, under the cell-level ruling (MAJ-1) plus the AP2 basis-uniformity ruling — no cell's basis is conditional any longer, and the B≤5 general basis describes no cell registered by this contract today.**

---

## 3. Lane-2 §8 six elections — final disposition

Source: `research/imce/hb0/IMCE_HB0_A4_CELL_BUDGET_INPUTS.md` §8.

| # | Election | Disposition | Ruling |
|---|---|---|---|
| E1 | TOL cancellation denominator: beginning-quarter backlog **or** signed contracts in quarter | **SETTLED.** Primary = signed contracts in quarter; beginning-quarter backlog = mandatory printed sensitivity, both printed either way. | AG12 |
| E2 | Cells keyed to `pace_recovery`/`completed_inventory_build`: re-scope to disclosing issuers (m=1–2, not cohort) **or** drop and re-declare budget | **FULLY SETTLED [AP1, A4P, 2026-08-21].** `completed_inventory_build` → named 3-issuer subset (DHI/LEN/PHM), never a v0 cohort inferential target. `incentive_support`/`pace_recovery` → descriptive only, may not be imputed into any cohort cell, mapped to nothing. **All 3 `imce_phase_v0` targets, and `imce_sync_v0` Cell 4, are mapped to `order_softness`** — see §4 below (formerly open, now closed) and `IMCE_A4P_ORDER_SOFTNESS_STATE_CONSTRUCTION_V1.md` for the deterministic construction. | AG14, AP1 |
| E3 | `rho`/`rho_block` values: frozen pre-outcome, fit on train folds only | **MOOT for N-accounting** — AG3/AG4 remove ρ from the `n_effective_blocks` definition entirely. A future `rho_block` MAY still be registered at actual A4 registration, but only for the AG4 precision-diagnostic field, never for N. | AG3, AG4 |
| E4 | Whether block 2a (2013 taper) and 3a (2018 air-pocket) stay sub-episodes | **SETTLED: YES.** Both are named sub-episodes, contributing zero N, per AG7. | AG7 |
| E5 | MDC's admissibility, if the roster is ever widened | **MOOT** — AG16 forbids roster widening outright. Revisits only if AG16 itself is amended in a future gate. | AG16 |
| E6 | Whether to execute the Census NRS release-archive upgrade to `pit_pure` | **NOT EXECUTED.** Remains a costed, not-yet-executed A4 option — see `IMCE_A4G_SOURCE_BOUNDARY_TABLE.md` §3. This amendment does not execute it; NRS stays `revision_optimistic` today. | unchanged (no AG ruling executes E6) |

---

## 4. Phase-family target-to-D5-state mapping — CLOSED [AP1, A4P, 2026-08-21]

**Formerly an explicit open item at A4G; settled by Sol's A4P ruling 1.** The contract's `rf.cycle_pattern.imce_phase_v0` family's 3 declared state targets, and `imce_sync_v0` Cell 4, are all mapped to the same D5 state, `order_softness` — confirming branch (a) of the two branches the A4G text named as the future resolution options ("confirm the 3 targets were always intended as `order_softness`-family transitions only"):

| Target slot | D5 state | Construction |
|---|---|---|
| next family-local state, 1 reporting period | `order_softness`, next-period cohort state | `IMCE_A4P_ORDER_SOFTNESS_STATE_CONSTRUCTION_V1.md` §2–§3 |
| next family-local state, 3 reporting periods | `order_softness`, +3-reporting-period cohort state | same |
| false repair / relapse within 3 reporting periods | `order_softness` `SOFTENING → TIGHTENING → SOFTENING` transition sequence | same, §4 |
| `imce_sync_v0` Cell 4 (`next_local_state_1rp`) | `order_softness`, next-period cohort state (same as the 1-reporting-period phase target) | same |

`completed_inventory_build` is explicitly **not** mapped to any of the 3 phase-family target slots — it remains a named DHI/LEN/PHM three-issuer descriptive/subset research object (AG14, unchanged), never a v0 cohort inferential target. `incentive_support` and `pace_recovery` remain descriptive only, mapped to nothing (AG14, unchanged). No target-slot required the "re-map or drop" branch — every slot resolves cleanly to `order_softness`, so AG14 imposes no practical constraint on the frozen 3-target/1-cell-4 set.

The construction itself (§1–§3 of the new file) is a **deterministic, outcome-independent, sign-only** rule — no grid search, no outcome-selected threshold, no issuer-specific tuning — pooled over exactly the population AP2 confirms as the cell-level roster for all six v0 historical cells: {DHI, PHM, KBH, TOL}, LEN excluded, NVR held out.

---

**This document authorizes nothing. No cell, model, score, or outcome computation has started. The next authorized act on this family is actual A4 registration — see `IMCE_A4G_PROPOSED_A4_REGISTRATION_PACKET.md`.**

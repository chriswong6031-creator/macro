# IMCE-HB-0 — Exact proposed A4 cell-budget inputs

**Wave:** A3 / IMCE-HB-0. Records-only. **This document proposes inputs; it registers nothing.**
A4 (IMCE-03) owns the `declared_budget` trial-ledger rows — the first `data/` write — and needs its
own wave approval. Nothing here is a registration, a fit, or an outcome.

**Authority:** contract §9a (reachable-status table), §3 (unit and effective-block law), §8
(promotion conjunction), §11 (multiplicity), D8 (trial-family reservation).

---

## 1. Inputs at a glance

| Input | Value | Source |
|---|---|---|
| Trial families (reserved, collision-free) | `rf.cycle_pattern.imce_phase_v0` · `rf.cycle_pattern.imce_sync_v0` · `rf.cycle_pattern.imce_risk_v0` | freeze D8 |
| Historical cells | **6** — phase 3, sync 2, risk 1 | contract §9a |
| BH-FDR partition | single, `imce_hist_v0`, **q = 0.10** | contract §9a |
| Roster | DHI, LEN, PHM, NVR, KBH, TOL | frozen; survivorship census §6 |
| Poolable issuers, general cell | **m = 5** (NVR held out as stratum) | freeze §7.2(2) |
| Poolable issuers, cancellation cell | **m = 4** (LEN excluded, NVR held out) | freeze §7.2(1)(2) |
| `n_blocks_hist` | **5** (hardened; frozen list resolved) | block list §4 |
| `n_blocks_prosp` | **0** (block 6 open, accruing) | block list §D2 |
| `n_effective_blocks`, general cell | **≈ 5.4 – 6.7** (ρ ∈ 0.7–0.9) — **an upper bound** | block list §8 |
| `n_effective_blocks`, cancellation cell | **≈ 3.2 – 3.9** | §4 below |
| Promotion floor | **40** | contract §8 item 5 |
| Predetermined status, every historical cell | **`underpowered_accruing`** | contract §9a |
| Max reachable rung on history | `REGISTERED` → `REPLAYED`, estimation-only; **never `DISPLAY`, never `PROMOTE_ELIGIBLE`** | contract §2 |

---

## 2. The finding A4 most needs — two of the four mechanism states are not measurable

The D5 homebuilder state vector is `order_softness` / `completed_inventory_build` /
`incentive_support` / `pace_recovery`. The definition crosswalk determines whether each has a
cohort-wide measurable basis. **It does not.**

| State | Primary metric | Cohort-wide measurable? | Why |
|---|---|---|---|
| **`order_softness`** | net orders, backlog, cancellation rate | **YES, with caveats** | Net orders and backlog are disclosed by all six from FY2005. Caveats: TOL's net-orders formula differs structurally (crosswalk X1), and the cancellation leg is denominator-limited to blocks 3–5 (§4). |
| **`completed_inventory_build`** | completed unsold inventory | **NO** | PHM splits it out (confirmed FY2024, earlier unconfirmed); **NVR does not separate it** from under-construction-unsold; **TOL: `missing`**; aged-completed inventory is disclosed by **nobody**. |
| **`incentive_support`** | incentives / concessions, rate buydowns | **NO — one issuer only** | **Only LEN tabulates a discrete average-incentive-per-home figure.** DHI is narrative-only; NVR uses "closing cost assistance" with no defining policy; PHM has a policy note but no isolated figure. Buydown cost is never isolated as its own number by anyone. |
| **`pace_recovery`** | cycle / construction time | **NO** | **Only KBH quantifies build time** (4–5 months construction; 6–7 months sale-to-delivery). PHM is qualitative. **NVR and TOL disclose no numeric figure at all** — both verified by full-text search, not assumed. |

**One of four states is well-measured across the cohort. Two are not measurable at all. One rests on a
single issuer.**

**Consequence for the 6-cell budget.** The budget was set before this census existed. A cell keyed to
`pace_recovery` or `completed_inventory_build` has no cohort-wide input series to compute from — it
would be measuring one issuer's disclosure practice, or an imputation. **A4 must either re-scope those
cells to the issuers that actually disclose the input (accepting m = 1–2, which is not a cohort claim),
or drop them and re-declare the budget.**

Silently populating them by imputing across non-disclosing issuers would violate contract §10
("Missing is never zero", `not_reconstructable` is distinct from `missing`) and the ordinal-sensor
rule (a directional or absent field entering a cardinal model is a missingness event, never an
imputation).

---

## 3. Effective-block arithmetic per cell class

`DEFF = 1 + (m − 1)·ρ` · `n_eff = (B × m) / DEFF`. **ρ is not estimated here** — A4 freezes it
pre-outcome and fits it on train folds only. This is a pre-registered sensitivity grid.

| Cell class | B | m | n_eff @ρ=0.7 | @ρ=0.8 | @ρ=0.9 | vs. floor 40 |
|---|---|---|---|---|---|---|
| General (all-issuer) | 5 | 6 | 6.7 | 6.0 | 5.5 | **~7× short** |
| General (NVR held out) | 5 | 5 | 6.6 | 6.0 | 5.4 | **~7× short** |
| **Cancellation** | **3** | **4** | **3.9** | **3.5** | **3.2** | **~11× short** |

**No cell reaches the floor. No choice available to A4 changes that.** Adding issuers barely moves
`n_eff` once ρ is high — which is the DEFF rule working as designed.

---

## 4. Why the cancellation cell gets B = 3, not 5

Stated denominators are a late-era artifact (crosswalk §4):

- PHM's and NVR's cancellation formulas are confirmed only from **FY2016**; their FY2005 filings give
  bare percentages with no denominator. NVR's FY2005 gives **two different bare rates** (12% in a
  backlog context, 25% in a mortgage-pipeline context) with neither denominator stated.
- KBH is gross-denominated from **FY2008**, but its FY2008 10-K **contradicts itself** — "based on net
  orders" in narrative, "based on gross orders" in a segment-table caption, both verified in the same
  filing.
- LEN states no formula, ever.

Blocks 1 (`hb_gfc_bust`) and 2 (`hb_gfc_recovery`) therefore predate the stated-denominator era for
most of the roster. Freezing a canonical denominator there requires **assuming** the unstated early
convention matched the later stated one — unverified, and precisely the flattening the census exists
to prevent.

**Denominator-verifiable blocks: 3, 4, 5 only.**

This is the census's sharpest structural cost: **the GFC bust and recovery — the two most
mechanism-informative episodes in the window — are the two where the signature homebuilder metric has
no verifiable denominator.**

---

## 5. Mandatory conditions A4 must carry into every cell

1. **Survivorship disclosure**, verbatim from survivorship census §8, on every readout. No cohort mean,
   dispersion statistic, or trough-severity claim without it.
2. **`pit_class` per macro leg**, via the §0 crosswalk in the source matrix. Only Treasury CMT is
   confirmed `pit_pure`. **No NAR series may be stored at all**; no Case-Shiller without a licence;
   Freddie Mac PMMS is HELD pending a rights determination.
3. **Affordability is a house construction** (Census price + Treasury rate + Census/BLS income), never
   "the NAR/NAHB affordability index."
4. **Alternate-convention sensitivity re-run** on every cancellation cell; a result that flips is not a
   pass. NVR and TOL publish both conventions in-source; DHI/PHM/KBH need a constructed alternate.
5. **TOL requires an explicit denominator election** between its two published rates, with both printed.
6. **NVR never pooled to raise n** — separate stratum or designated transfer test.
7. **Missing-indicator ban [A18] extended** to every era-correlated metric in crosswalk §5, not only
   LEN's cancellation rate.
8. **Epoch boundaries re-derived on the recognition clock** before partitioning any recognition-outcome
   statistic [G8-M2]. The block list's dates are operating-clock.
9. **`available_at` is metric-level, not period-level** (fiscal map §5.1) — headline KPIs at the 8-K,
   footnote/balance-sheet detail only at the 10-Q/10-K.
10. **`n_effective_blocks` is an upper bound** until `rho_block` exists (block list §D4); print raw,
    issuer-DEFF, and serial-adjusted counts separately.

---

## 6. Predetermined statuses (fixed pre-outcome, invariant to the data)

| Cell class | Cells | Predetermined status | Max rung |
|---|---|---|---|
| phase | 3 | `underpowered_accruing` | `REGISTERED`→`REPLAYED` |
| sync | 2 | `underpowered_accruing` | `REGISTERED`→`REPLAYED` |
| risk | 1 | `underpowered_accruing` | `REGISTERED`→`REPLAYED` |

Every historical cell's status is fixed **now**, before any number exists. Three guards from the
freeze are re-stated because this document is where a future reader will look for them:

- A sub-floor nominal "pass" **can never reach display or a truth statement**, and its point estimate
  **carries no prior into any prospective cell** [G8-B7] — the carry-path was deliberately deleted.
- `underpowered_accruing` is a **Research-Factory/trial-ledger status only**. It is **not** a CPI truth
  status (`truth_schema.md` enum: candidate/display/confirmer/scored/promoted_null/retired/superseded)
  and may not enter the CPI registry without an explicit schema + consumer-matrix amendment [G8-M7].
- At n_eff ≈ 6 the BH-FDR machinery is **statistically inoperative** on the historical arm. It is
  registered for the prospective arm and disclosed as inoperative here [G8-M9] — harmless only because
  the statuses are predetermined.

---

## 7. Come-back arithmetic, reproduced at the hardened count

| Basis | Years/block | 40-block floor reached |
|---|---|---|
| **B = 5 (hardened)** | 3.40 | **~2146** |
| B = 6 | 2.83 | ~2123 |
| B = 7 (frozen list read literally) | 2.95 | ~2124 |

The freeze's published headline — homebuilders reach the floor "around **~2145**" — **reproduces only
at B = 5**. The freeze's own arithmetic was already on a closed-blocks basis; this census makes that
explicit and confirms it independently.

**The honest headline is unchanged and this wave strengthens it:** the historical arm is instrumentation
and design validation, never a promotion path.

---

## 8. Open elections A4 must make (this census does not make them)

| # | Election | Options |
|---|---|---|
| E1 | TOL cancellation denominator | beginning-quarter backlog **or** signed contracts in quarter; both printed either way |
| E2 | Cells keyed to `pace_recovery` / `completed_inventory_build` | re-scope to disclosing issuers (m = 1–2, not a cohort claim) **or** drop and re-declare the budget (§2) |
| E3 | `rho` and `rho_block` values | frozen pre-outcome, fit on train folds only |
| E4 | Whether block 2a (2013 taper) and 3a (2018 air-pocket) stay sub-episodes | block list D1 recommends yes |
| E5 | MDC's admissibility, if the roster is ever widened | operating clock continuous; recognition clock ends 2024-04-19 |
| E6 | Whether to execute the Census NRS release-archive upgrade to `pit_pure` | source matrix §3; costed, not executed |

---

## 9. What A4 must NOT do

- Must not raise `n_effective_blocks` by counting issuers, rows, targets, horizons, directions, or
  overlapping windows (contract §3).
- Must not widen the roster to raise power. Widening improves **representativeness**, not **power**
  (survivorship census F-4) — more issuers inside the same shocks are correlated rows, not new draws.
- Must not re-key the fiscal→calendar crosswalk after outcome access [A17].
- Must not impute a non-disclosed metric across issuers (§2).
- Must not file a 126d claim in the live QLedger ladder — `GRADE_HORIZONS` is fenced at 63d [G8-m6].
- Must not access any outcome before the criteria commit. **Two-commit discipline** [G8-B1].

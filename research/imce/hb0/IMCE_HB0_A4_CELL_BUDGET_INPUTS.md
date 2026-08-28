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

## 2. The finding A4 most needs — mechanism-state coverage is uneven, and two states rest on one issuer

The D5 homebuilder state vector is `order_softness` / `completed_inventory_build` /
`incentive_support` / `pace_recovery`. The definition crosswalk determines how many issuers actually
disclose a usable input for each.

> **Corrected under adversarial review.** An earlier draft of this section claimed
> `completed_inventory_build` had **no** cohort-wide basis and that aged completed inventory was
> "disclosed by nobody". Both were wrong, and contradicted by this census's own evidence packet:
> **DHI discloses ~9,300 completed unsold homes and LEN ~5,000** (plus a per-community ratio), and
> **DHI does disclose an aged cut** — "approximately 800 homes had been completed for more than six
> months". The corrected table below is materially more permissive for that state, and A4 must act on
> this version. The error would have driven A4 to drop a cell it should keep.

| State | Primary metric | Issuers with a usable disclosed input | Verdict |
|---|---|---|---|
| **`order_softness`** | net orders, backlog, cancellation rate | **6 of 6** | **Cohort-measurable, with caveats** — TOL's net-orders formula differs structurally (crosswalk X1), and the cancellation leg is denominator-limited to blocks 3–5 (§4). |
| **`completed_inventory_build`** | completed unsold inventory | **3 of 6 quantified** — DHI (~9,300), LEN (~5,000 + per-community ratio), PHM (unit-level Unsold split). KBH qualitative only; NVR combined dollar bucket only; TOL `missing`. Aged-completed: **DHI alone**, one >6-month threshold. | **Partial** — constructible on a named 3-issuer subset; **not cohort-complete**, and the aged cut is single-issuer. |
| **`incentive_support`** | incentives / concessions, rate buydowns | **1 of 6 discrete** — only LEN tabulates an average-incentive-per-home figure. DHI narrative-only; NVR "closing cost assistance" with no defining policy; PHM has a policy note but no isolated figure. Buydown cost is isolated by nobody. | **Single-issuer** — not a cohort claim. |
| **`pace_recovery`** | cycle / construction time | **1 of 6 quantified** — only KBH (4–5 months build; 6–7 months sale-to-delivery). PHM qualitative. NVR and TOL not found in the FY2024/FY2025 10-K full text; **earlier years unsearched**. | **Single-issuer** — not a cohort claim. |

**One state is cohort-measurable; one is measurable on a 3-issuer subset; two rest on a single
issuer each.**

**Consequence for the 6-cell budget.** The budget was set before this census existed.

- A cell keyed to **`completed_inventory_build`** is constructible, but on **m = 3** (DHI, LEN, PHM)
  — a named-subset claim, not a cohort claim, and it must be labelled as such.
- A cell keyed to **`incentive_support`** or **`pace_recovery`** would measure one issuer's disclosure
  practice. **A4 must either re-scope to that issuer explicitly (m = 1, not a cohort claim) or drop the
  cell and re-declare the budget.**

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
| **General (poolable: NVR held out)** | 5 | **5** | 6.6 | 6.0 | 5.4 | **~7× short** |
| **Cancellation** (LEN excluded, NVR held out) | **3** | **4** | **3.9** | **3.5** | **3.2** | **~11× short** |
| *(reference only — m=6 pooling NVR is **barred** by freeze §7.2(2))* | *5* | *6* | *6.7* | *6.0* | *5.5* | *not an admissible cell* |

**No cell reaches the floor. No choice available to A4 changes that.** Adding issuers barely moves
`n_eff` once ρ is high — which is the DEFF rule working as designed.

> **[SUPERSEDED BY AG3 + A4P.1 R1 (2026-08-22): the DEFF formula and the `n_eff @ρ=0.7/0.8/0.9` table above
> compute a candidate `n_effective_blocks` estimator that is NOT the A4 registration law.** The DEFF/`rho`
> construction is STRUCK as the `n_effective_blocks` definition (AG3, 2026-08-21) — `n_effective_blocks` is
> capped at the raw closed-block count B (general cells ≤5, cancellation cells ≤3, AG5/AG6), never derived
> upward from an issuer-correlation parameter. A4 will not register any `rho` value and will not print an
> issuer-DEFF `n_eff` figure. This section's own bottom line — no cell class reaches the 40-block floor, ~7–11×
> short — is UNCHANGED and independently confirmed on the AG3-capped basis (contract §3, §8 item 5).]**
> Additive annotation only — the table and text above are the original A3 lane-2 text, unmodified, per Sol's
> bar on reopening A3 work. `IMCE_A4G_AMENDMENT_LOG.md`'s AG3/AG5/AG6 entries and this wave's `AP9.R1` entry
> carry the full ruling.

---

## 4. Why the cancellation cell gets B = 3, not 5

Stated denominators are a late-era artifact (crosswalk §4):

- PHM's and NVR's cancellation formulas are confirmed only from **FY2016**; their FY2005 filings give
  bare percentages with no denominator. NVR's FY2005 gives **two different bare rates** (12% in a
  backlog context, 25% in a mortgage-pipeline context) with neither denominator stated.
- KBH is gross-denominated from **FY2008**, but its FY2008 10-K **contradicts itself** — "based on net
  orders" in narrative, "based on gross orders" in a segment-table caption, both verified in the same
  filing.
- LEN states no formula anywhere the census could find (the search perimeter is recorded as gap G1 in
  `evidence/L2_defs_DHI_LEN.md`; pre-2010 10-Ks were not swept).

Blocks 1 (`hb_gfc_bust`) and 2 (`hb_gfc_recovery`) therefore predate the stated-denominator era for
most of the roster. Freezing a canonical denominator there requires **assuming** the unstated early
convention matched the later stated one — unverified, and precisely the flattening the census exists
to prevent.

**Denominator-verifiable blocks: the `hb_grind` (from FY2016), `hb_pandemic_boom` and `hb_rate_shock`
blocks only** — three of the five closed blocks.

**One caveat on m = 4 for this cell.** It assumes DHI, PHM, KBH and TOL each carry a usable
cancellation rate across all three. TOL's dual-denominator format is confirmed in Q1 FY2026 and (by
its comparative column) Q1 FY2025; **the first year TOL published it is unverified**, so TOL's
coverage of the earlier two blocks is not established. If TOL drops out, m = 3 and n_eff falls to
≈ 2.6–3.1 at ρ = 0.7–0.9.

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

> **[SUPERSEDED BY AG3 + A4P.1 R1 (2026-08-22): item 10 above conditions "upper bound" status on a `rho_block`
> parameter that does not exist, and recommends printing an issuer-DEFF count. This is NOT the A4 registration
> law.** The DEFF/`rho` construction is STRUCK as the `n_effective_blocks` definition (AG3, 2026-08-21) —
> `n_effective_blocks` is capped at the raw closed-block count B unconditionally (AG5/AG6), an upper bound by
> construction regardless of whether any `rho_block` is ever registered; A4 will not register `rho_block` and
> will not print an issuer-DEFF count. `raw_block_count` is printed alongside the effective count (contract §3)
> — that discipline is preserved without the DEFF construction.]**
> Additive annotation only — the list above is the original A3 lane-2 text, unmodified, per Sol's bar on
> reopening A3 work. `IMCE_A4G_AMENDMENT_LOG.md`'s AG3/AG5/AG6 entries and this wave's `AP9.R1` entry carry the
> full ruling.

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

## 7. Come-back arithmetic

| Basis | Span | Years/block | 40-block floor |
|---|---|---|---|
| **B = 5 (hardened)** — closed blocks only | 2006-01 → 2023-12 (18.0y) | 3.60 | **~2153** |
| B = 6 — taper split, closed only | 2006-01 → 2023-12 (18.0y) | 3.00 | ~2129 |
| B = 6 — counts the open era | 2006-01 → 2026-08 (20.6y) | 3.44 | ~2144 |
| B = 7 — literal list, counts the open era | 2006-01 → 2026-08 (20.6y) | 2.95 | ~2124 |

**Corrected under review.** An earlier draft claimed the freeze's ~2145 headline reproduced *only* at
B=5 and offered that as corroboration. It does not: B=6 counting the open era lands at ~2144, closer
than B=5. The arithmetic corroborates the **magnitude** — a century-plus on every basis, ~2124 to
~2153 — and does not identify a block count. B=5 rests on the block list's D1 and D2, not on this.

**The honest headline is unchanged:** on every basis the floor is a century-plus away, so the
historical arm is instrumentation and design validation, never a promotion path.

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

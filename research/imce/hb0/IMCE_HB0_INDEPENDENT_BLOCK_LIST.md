# IMCE-HB-0 — Frozen independent-block list (homebuilder family)

**Wave:** A3 / IMCE-HB-0, homebuilder source & definition census. Records-only.
**Authority:** merged IMCE-00 architecture freeze (`ec44ae7d1659`, PR #6127) and
`research/imce/IMCE_PREREGISTRATION_AND_EVALUATION_CONTRACT_V1.md` §3 (unit of observation,
frozen block list [A8], effective-block-count law [A9]).
**Status of this document:** a census + hardening proposal. It **does not amend** the frozen
block list. §3 requires an amendment-log entry for any change; the dispositions below are
submitted to Fable/Sol for adjudication and would be recorded as amendments in A4.

**Non-goal fence honoured in this file:** no model, no fit, no outcome, no return, no p-value.
No market-derived or price-derived block boundary appears anywhere below. Every boundary here is
drawn from documented macro/housing events, never from any issuer's or index's price behaviour.

---

## 1. What a block IS (the unit, stated before any count)

From contract §3, restated so the count below can be audited:

> The effective block count is the number of **independent shock realizations**. It may never be
> increased by counting issuers, rows, targets, horizons, directions, or overlapping windows.

An admissible block must therefore satisfy **all five** of these. The census below tests each
frozen-list entry against them, and this is the first time the list has been tested rather than asserted.

| # | Admissibility condition | Why it exists |
|---|---|---|
| B-1 | **Non-overlapping.** No block may be contained in, or share years with, another block. | §3 bans raising the count via overlapping windows. |
| B-2 | **Closed.** The episode has a terminal disposition — the shock has fully realized. | An open episode has no realized outcome; counting it is a unit violation. Precedent is on the record: the memory cohort's open HBM/AI episode is explicitly *not* a unit (freeze §7.3). |
| B-3 | **Clock-stamped.** Boundaries carry an explicit clock and explicit dates. | Epoch-clock rule [G8-M2]: a partition of a recognition-outcome statistic must use recognition-clock (`available_at`) boundaries, not operating-clock ones. A bare year label is neither. |
| B-4 | **A distinct shock, not a phase of the prior one.** | "Independent shock realization" requires independent draws, not sequential phases of one process. |
| B-5 | **Issuer-spanned.** Named roster issuers actually report through the block on a comparable basis. | A block no issuer spans contributes nothing; a block spanned only across a structural break contributes a break, not an observation. |

---

## 2. Audit of the frozen list against those conditions

The frozen list [A8], verbatim from contract §3, with this census's verdict appended:

| # | Frozen entry | B-1 non-overlap | B-2 closed | B-3 clocked | B-4 distinct shock | Verdict |
|---|---|---|---|---|---|---|
| 1 | GFC bust: 2006–2009 | pass | pass | **fail** (year labels only) | pass | **ADMISSIBLE**, needs dates |
| 2 | GFC recovery / land-light era: 2010–2013 | **fail** (contains #3) | pass | **fail** | conditional (see §4) | **ADMISSIBLE**, needs dates + overlap fix |
| 3 | 2013 taper (partial) | **fail** (inside #2) | pass | **fail** | **fail** — same rate/credit process as #2 | **NOT AN INDEPENDENT BLOCK** — see D1 |
| 4 | 2014–2019 grind, incl. the 2018 air-pocket | pass | pass | **fail** | pass | **ADMISSIBLE**, needs dates |
| 5 | 2020–2021 pandemic boom | pass | pass | **fail** | pass | **ADMISSIBLE**, needs dates |
| 6 | 2022–2023 rate shock / cancellation spike | pass | pass | **fail** | pass | **ADMISSIBLE**, needs dates |
| 7 | 2024–2026 affordability/incentive era | pass | **FAIL — OPEN** | **fail** | pass | **NOT A UNIT YET** — see D2 |

The list's own parenthetical — "(partial)" on entry 3 — is the only place the defect was
previously visible. It is now typed.

---

## 3. Defects found, with proposed dispositions

### D1 — Entry 3 (2013 taper) overlaps entry 2 and is not an independent draw

`2013 taper` lies wholly inside `2010–2013`. Two windows sharing a year cannot both increment a
count that §3 forbids raising "by … overlapping windows". Beyond the arithmetic, the taper fails
B-4 on substance: it is a movement in the **same** rate/credit transmission channel that defines
the recovery era, not a second, independent shock.

**Proposed disposition:** the 2013 taper is recorded as a **named sub-episode of block 2**, with its
own dates, available for descriptive and diagnostic use, and **contributing zero** to
`n_effective_blocks`. It is not deleted — it is re-typed.

**Alternative considered and rejected:** splitting block 2 at the taper into `2010–H1 2013` and
`H2 2013`. Rejected because it manufactures a ~6-month block out of one continuous process, which is
the precise inflation mechanism §3 exists to prevent, and because it would *raise* the count — the
direction of travel a census must be most suspicious of in its own output.

### D2 — Entry 7 (2024–2026) is an OPEN episode and may not be counted

As of the census date **2026-08-21** the affordability/incentive era has no terminal disposition.
The identical situation was already adjudicated for a sibling cohort in this same freeze:

> the open HBM/AI episode has no closing disposition and is not a unit — counting it is a unit
> violation (freeze §7.3, memory cohort)

The homebuilder family gets the same law or the freeze is inconsistent across its own cohorts.

**Proposed disposition:** block 7 is registered as `OPEN_ACCRUING`. It contributes **zero** to
`n_blocks_hist` and is the first block to enter `n_blocks_prosp` when it closes. Contract §13 already
mandates the two separate counters (`n_blocks_hist`, `n_blocks_prosp`) [A24]; this is the first
concrete assignment into them.

### D3 — Every boundary is a bare year, on no stated clock

All seven entries are year labels. B-3 fails universally. This matters *more* for homebuilders than
for any other cohort in the program, because the six roster issuers have four different fiscal
year-ends (Sept 30, Oct 31, Nov 30 ×2, Dec 31 ×2). A boundary written as "2013" resolves to a
**different fiscal quarter for each issuer**, so an unclocked boundary silently assigns different
amounts of each issuer's history to each side of the split.

**Proposed disposition:** every boundary is re-expressed as an explicit **calendar month** on a
**named clock**, per contract §2(a) (episodes re-key on calendar month) and the fiscal→calendar
crosswalk frozen by this wave (`IMCE_HB0_FISCAL_CALENDAR_MAP.md`). Boundaries used to partition any
recognition-outcome statistic must additionally be stated on the recognition clock (`available_at`),
per [G8-M2]. Proposed dates are in §5; they are **proposals**, and freezing them is an A4 act.

### D4 — Block-to-block dependence is unaddressed by the DEFF rule (contract hole)

This is the most consequential finding in this document.

The §3 DEFF rule governs one direction of dependence only: it collapses correlated **issuer**-episodes
*within* a block down to an effective count. It says nothing about correlation **between blocks**.
But the frozen list is not seven independent draws from a population of housing shocks — it is a
**sequence of phases of one national housing-cycle process**, driven substantially by one rate and
credit transmission channel over one twenty-year span. The 2010–2013 recovery is not an independent
event from the 2006–2009 bust; it is mechanically the clearing of that bust's inventory overhang.

The consequence is directional and unflattering: `n_effective_blocks` computed by the DEFF rule as
written is an **upper bound**, not an estimate. Serial dependence between adjacent blocks can only
reduce it further.

**Proposed disposition:** A4 registers a block-level dependence parameter (`rho_block`) alongside the
issuer-level `rho`, frozen pre-outcome under the same discipline (fit on train folds only, never on
the evaluation sample), and prints the raw count, the issuer-DEFF count, and the
serial-dependence-adjusted count as three separate numbers. Until that exists, every homebuilder
readout states that its `n_effective_blocks` is an upper bound.

### D5 — Structural breaks sit ON block boundaries and inside blocks

Block membership is not the same as comparable membership (B-5). Three known events collide with the
block grid, so a "spanning" issuer is not automatically a comparable one:

Block numbers below are the **proposed §5 renumbering**, used consistently throughout this document.

| Event | Date | Collides with | Consequence |
|---|---|---|---|
| PulteGroup / Centex merger | closed Aug 2009 | the block 1 → block 2 boundary | PHM's block-1 entity and block-2 entity are not the same business. PHM does not cleanly span that boundary. |
| Lennar / CalAtlantic | closed Feb 2018 | inside block 3 (`hb_grind`) | LEN's block-3 series contains a mid-block composition change. |
| Lennar / Millrose spin-off | Feb 2025 | inside block 6 (`hb_affordability_era`, OPEN) | LEN's land-holding metrics break inside the open era. |

Detail and citations: `IMCE_HB0_STRUCTURAL_BREAK_LEDGER.md`. The point for *this* document is that
per-block issuer counts must be taken from the break ledger, not from "was the ticker listed".

---

## 4. The hardened count

Reproducing the freeze's stated **5–7 honest blocks** and resolving it:

| Basis | Raw block count | What it counts |
|---|---|---|
| Frozen list read literally | **7** | includes the overlapping taper AND the open era — inadmissible on two independent grounds |
| Taper re-typed as sub-episode (D1 applied) | **6** | still counts the open era |
| **Hardened: D1 + D2 applied** | **5** | closed, non-overlapping, distinct-shock blocks only |

**The honest historical block count is B = 5.** The freeze's "5–7" range is therefore correct and this
census resolves it to its **lower bound**. The resolution direction matters: both corrections *reduce*
the count. A census that hardened its way to a larger N would be the one to distrust.

**Come-back arithmetic — and a corroboration this census withdrew under review.**

An earlier draft claimed the freeze's published come-back headline (the 40-block `PROMOTE_ELIGIBLE`
floor reached "around ~2145") reproduced **only** at B=5, and offered that as independent support for
the hardening. **Adversarial review falsified the claim and it is withdrawn.** The draft had used a
different span for the B=7 row than for the others, and measured 2006→2023 as 17 years by
year-label subtraction rather than 18.0 elapsed years.

Recomputed on one consistent convention (elapsed years from block-1 start; a basis that counts the
open era runs its span to the census date, since the counted block is still accruing):

| Basis | Span | Years per block | 40-block floor reached |
|---|---|---|---|
| **B=5 (hardened)** — closed blocks only | 2006-01 → 2023-12 (18.0y) | 3.60 | **~2153** |
| B=6 — taper split out, closed only | 2006-01 → 2023-12 (18.0y) | 3.00 | ~2129 |
| B=6 — counts the open era | 2006-01 → 2026-08 (20.6y) | 3.44 | **~2144** |
| B=7 — literal list, counts the open era | 2006-01 → 2026-08 (20.6y) | 2.95 | ~2124 |

**What this actually shows.** The freeze's ~2145 sits inside the range but does **not** uniquely
identify B=5 — B=6 counting the open era lands at ~2144, closer than B=5 does. The come-back
arithmetic corroborates the **magnitude** (the floor is a century-plus away on every basis, from
~2124 to ~2153) and says nothing about which block count is right.

**The hardening argument does not depend on this.** B=5 rests on D1 (the taper overlaps block 2) and
D2 (block 7 is open), each of which stands on its own reading of the frozen list and the freeze's own
treatment of the memory cohort. Removing a spurious corroboration leaves that reasoning untouched —
and the corroboration is removed precisely because it was spurious.

---

## 5. Proposed frozen block list (dated, clocked) — for A4 adjudication

Boundaries are **calendar months**, stated on the **operating clock** (housing-activity events).
Per [G8-M2], any partition of a recognition-outcome statistic must re-derive these on the recognition
clock; the recognition-clock offsets are issuer-specific and come from the fiscal/calendar map.

| Block | Key | Proposed start | Proposed end | Regime label | State | Counts toward |
|---|---|---|---|---|---|---|
| 1 | `hb_gfc_bust` | 2006-01 | 2009-12 | national housing bust; credit withdrawal; sector mortality event | CLOSED | `n_blocks_hist` |
| 2 | `hb_gfc_recovery` | 2010-01 | 2013-12 | recovery; land-light balance-sheet era | CLOSED | `n_blocks_hist` |
| 2a | `hb_2013_taper` | 2013-05 | 2013-12 | taper rate move | **SUB-EPISODE of block 2** | **nothing** |
| 3 | `hb_grind` | 2014-01 | 2019-12 | slow-growth grind; contains the 2018 rate air-pocket | CLOSED | `n_blocks_hist` |
| 3a | `hb_2018_airpocket` | 2018-07 | 2018-12 | 2018 rate air-pocket | **SUB-EPISODE of block 3** | **nothing** |
| 4 | `hb_pandemic_boom` | 2020-03 | 2021-12 | pandemic demand boom; supply-chain cycle-time blowout | CLOSED | `n_blocks_hist` |
| 5 | `hb_rate_shock` | 2022-01 | 2023-12 | rate shock; cancellation spike | CLOSED | `n_blocks_hist` |
| 6 | `hb_affordability_era` | 2024-01 | **open** | affordability constraint; incentive/buydown support | **OPEN_ACCRUING** | `n_blocks_prosp` on close |

`n_blocks_hist = 5` · `n_blocks_prosp = 0` (block 6 accrues; it closes into the prospective counter).

Note the 2018 air-pocket receives the **same** treatment as the 2013 taper (sub-episode, counts
nothing). The frozen list already nested it inside entry 4 — "including the 2018 air-pocket" — so this
is consistency, not a new rule: a named sub-shock inside a block is a sub-episode either way.

---

## 6. Issuer span per block

All six roster issuers were public and filing across the whole window, so *listing* spans every closed
block. Comparable span is narrower. `S` = spans comparably; `S*` = spans, but a structural break falls
on or inside the block (see D5); `strat` = present but held in a separate stratum by rule.

| Block | DHI | LEN | PHM | NVR | KBH | TOL | m (poolable) |
|---|---|---|---|---|---|---|---|
| 1 `hb_gfc_bust` | S | S | **S\*** (Centex Aug-2009 on the boundary) | strat | S | S | 5 |
| 2 `hb_gfc_recovery` | S | S | **S\*** (post-Centex entity) | strat | S | S | 5 |
| 3 `hb_grind` | S | **S\*** (CalAtlantic Feb-2018) | S | strat | S | S | 5 |
| 4 `hb_pandemic_boom` | S | S | S | strat | S | S | 5 |
| 5 `hb_rate_shock` | S | S | S | strat | S | S | 5 |
| 6 `hb_affordability_era` (OPEN) | S | **S\*** (Millrose Feb-2025) | S | strat | S | S | — |

NVR is `strat` in every row by rule, not by evidence: it is a designated mechanism outlier
(~100%-option land model) and "never pooled to raise n" (freeze §7.2 condition 2).

**Cancellation-rate cells are narrower still.** LEN is excluded from cancellation cells by rule
(freeze §7.2 condition 1 — no press-release cancellation rate, era-correlated missingness), and NVR
remains a separate stratum, so **m = 4** (DHI, PHM, KBH, TOL) for every cancellation cell.

**Survivorship stamp on this whole table.** Every issuer above is a 2026 survivor. The window opens
inside a sector mortality event, and the builders that died in blocks 1–2 appear in *no* row of this
table. The per-block `m` values are therefore counts of **survivors present**, never counts of the
population that was exposed. See `IMCE_HB0_SURVIVORSHIP_CENSUS.md`; the mandatory disclosure in §8
applies to every number on this page.

---

## 7. Why hundreds of issuer-quarter rows are not hundreds of observations

This is the specific inflation the acceptance criteria require be made impossible.

| Quantity | Value |
|---|---|
| Calendar quarters in the **census window** 2005-01-01 → 2026-08-21 | 87 |
| Naive issuer-quarter rows at 6 issuers | **522** |
| Calendar quarters in the **block-covered window** 2006-01 → 2026-08 (block 1 opens 2006-01) | 83 |
| Naive issuer-quarter rows on that window | **498** |
| Honest `n_effective_blocks` (§8) | **≈ 5.2 – 6.7** |
| Inflation factor if rows were used as N | **≈ 78× – 100×** |

The window distinction is stated rather than smoothed: the census roster is documented from 2005-01,
but block 1 opens 2006-01, so the row count on the block-covered window is 498, not 522. Either way
the inflation factor is two orders of magnitude, and the point does not turn on which window is used.

Four independent mechanisms each defeat the row count, and they compound:

1. **Within-episode rows are not trials.** Contract §3: "Issuer-quarter rows inside one episode are
   not independent trials." A block of 4 years contributes ~16 quarters per issuer and **one** shock.
2. **Within-block issuers share the shock.** A national rate move hits all six builders in the same
   quarter. Cross-issuer correlation inside a block is high by construction — this is what the DEFF
   rule discounts, and at ρ≈0.8 six issuers are worth ~1.2 independent observations, not six.
3. **The series are autocorrelated by construction.** Backlog at *t* mechanically contains orders from
   *t−1 … t−k*; a closing is a prior order realized. Consecutive quarters of backlog are near-restatements
   of each other, not fresh draws.
4. **Blocks themselves are serially dependent** (D4) — so even the block count is an upper bound.

**The load-bearing rule:** `n_rows` and `n_issuers` are printed for transparency; **promotion uses
`n_effective_blocks` and nothing else** (contract §3). No horizon count, no target count, no
direction split, and no overlapping-window construction may raise it.

---

## 8. Effective-block arithmetic (pre-registered sensitivity, NOT a fit)

ρ is **not estimated here** — estimating it would require touching the evaluation sample, which this
wave is fenced from. What follows is the pre-registered sensitivity grid over a ρ that A4 must freeze,
so the arithmetic cannot be chosen after seeing an answer.

`DEFF = 1 + (m − 1)·ρ` · `n_eff = (B × m) / DEFF`

At the hardened **B = 5**:

| ρ | m=6 (all-issuer) | m=5 (NVR held out) | m=4 (cancellation cell) |
|---|---|---|---|
| 0.50 | 8.6 | 8.3 | 8.0 |
| 0.60 | 7.5 | 7.4 | 7.1 |
| 0.70 | 6.7 | 6.6 | 6.5 |
| 0.80 | **6.0** | **6.0** | **5.9** |
| 0.90 | 5.5 | 5.4 | 5.4 |
| 0.95 | 5.2 | 5.2 | 5.2 |

**Reading.** For homebuilders — six issuers selling the same product into the same national rate and
affordability environment — a defensible ρ is high, 0.7–0.9. Across that range `n_eff ≈ 5.4–6.7`, and
it barely moves with `m`: adding issuers to a cell buys almost nothing once ρ is high, which is the
whole point of the DEFF rule. The freeze's stated `n_eff ≈ 6–10` is reproduced at its **lower end**,
and D4's serial dependence would push it lower still.

**Against the 40-block `PROMOTE_ELIGIBLE` floor: n_eff ≈ 6 versus a floor of 40.** The historical arm
is short by a factor of ~7 and no analytic choice available to A4 closes that gap. Every historical
cell's status is therefore predetermined `underpowered_accruing`, invariant to the data — exactly as
the freeze fixed pre-outcome. This census confirms that determination on its own arithmetic rather
than inheriting it.

---

## 9. What this document does NOT establish

Stated so a later reader cannot over-read it:

- It does **not** amend the frozen block list. D1–D5 are proposals for A4 amendment entries.
- It does **not** estimate ρ or `rho_block`. §8 is a sensitivity grid, not a fit.
- It does **not** inspect any outcome, return, or price. No block boundary here is market-derived.
- It does **not** establish that five blocks are *sufficient* for anything. It establishes the opposite.
- The per-block `m` values are **survivor counts** and carry the §6 survivorship stamp.

---

## 10. Falsifiers for this census

Concrete conditions that would overturn the counts above:

| # | Falsifier | Effect if true |
|---|---|---|
| F-1 | A documented housing shock in the window is found that is genuinely independent of the rate/credit channel and is absent from the frozen list. | B rises by one; the list is incomplete. |
| F-2 | Block 6 (2024–) is shown to have closed before 2026-08-21 on a documented, pre-registered closing rule. | B becomes 6; `n_blocks_hist` rises by one. |
| F-3 | The 2013 taper is shown to be a distinct shock in a different transmission channel from the 2010–2013 recovery. | D1 is wrong; B becomes 6. |
| F-4 | Cross-issuer correlation within a block is shown to be low (ρ < 0.5) on train-fold data. | `n_eff` rises toward 8–9. Still ≪ 40. |
| F-5 | The survivorship census shows enough surviving source documents for dead builders to reconstitute an exposure-complete cohort. | Per-block `m` rises; the §6 disclosure weakens (the block *count* does not change). |

F-4 and F-5 are the only two that could move the numbers materially, and **neither reaches the 40-block
floor**. That conclusion is invariant across every falsifier on this list.

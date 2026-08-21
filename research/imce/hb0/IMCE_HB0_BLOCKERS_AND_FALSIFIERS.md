# IMCE-HB-0 — Unresolved blockers and falsifiers

**Wave:** A3 / IMCE-HB-0. Records-only. Consolidated from all seven evidence lanes.

A **blocker** stops a specific downstream construction until resolved. A **falsifier** is a concrete,
checkable condition that would overturn a census conclusion. Both are named so that a later wave
inherits an honest account of what this census did and did not establish.

---

## 1. Hard blockers — these stop a named A4 construction

| # | Blocker | What it stops | What resolves it |
|---|---|---|---|
| **B1** | **Two of four D5 mechanism states have no cohort-wide measurable basis.** `completed_inventory_build` (NVR does not split it; TOL `missing`; nobody discloses aged completed inventory) and `pace_recovery` (only KBH quantifies build time; NVR and TOL disclose none). `incentive_support` rests on LEN alone. | Any cell keyed to those states. The 6-cell budget cannot be populated as currently scoped. | A4 elects: re-scope to disclosing issuers (m = 1–2, not a cohort claim) or drop and re-declare. Imputation is barred. |
| **B2** | **No verifiable cancellation-rate denominator in blocks 1–2.** PHM/NVR formulas confirmed only FY2016+; KBH FY2008+ **and self-contradictory in that filing**; LEN never. | A cancellation-rate cell spanning the GFC bust or recovery. | Locating pre-2016 filings that state the formula (falsifier F-2). Otherwise blocks 1–2 stay out. |
| **B3** | **LEN has no disclosed cancellation-rate denominator at all.** | Freezing a canonical LEN denominator under condition (4); any LEN cancellation cell. | A LEN filing stating a formula (F-1). Until then the exclusion stands — on the corrected ground. |
| **B4** | **NAR data may not be stored.** Verbatim: data may not be "reproduced, stored in a retrieval system, transmitted or redistributed… without NAR's prior written consent." | NAR Existing-Home Sales and the NAR Housing Affordability Index as stored context legs — permanently, not pending a workaround. Self-archival does not cure it; archiving *is* the prohibited act. | Written consent from NAR. |
| **B5** | **Terminal-year blind spot.** TOUSA, Orleans and Dominion Homes each never filed the annual report covering the period before failure. | Any complete survivorship correction. A corrected panel would hold the dead firms' healthy years and lose their dying years. | Non-EDGAR sources (bankruptcy court, state records) — outside this wave's source standard. |
| **B6** | **No denominator for a mortality/hazard rate.** The census supplies named deaths (numerator) and no population-by-date (denominator). | Any statement of what fraction of public homebuilders failed. | A separate, harder population census. Explicitly not attempted. |
| **B7** | **Block-to-block dependence is unaddressed by the DEFF rule.** It collapses issuer correlation *within* a block and says nothing about correlation *between* blocks — but the block list is a sequence of phases of one national housing-cycle process. | Treating `n_effective_blocks` as an estimate. It is an **upper bound**. | A4 registers `rho_block` pre-outcome and prints three counts (raw, issuer-DEFF, serial-adjusted). |

---

## 2. Soft blockers — resolvable with bounded further work

| # | Item | Effect |
|---|---|---|
| S1 | Earliest-coverage archaeology incomplete — a representative filing spine was opened, not all 22 years × 6 issuers | Field 12 is typed `missing`/`not_reconstructable` where unverified. Never interpolated. |
| S2 | Cannot distinguish "methodology changed" from "disclosure improved" for PHM/NVR pre-2016 | B2's severity is uncertain: the early convention may always have matched. |
| S3 | CalAtlantic restatement language unverified for LEN's orders/backlog/community count | The general acquisition-method rule implies no restatement; the specific filing was not opened. |
| S4 | Post-merger **segment-metric** continuity unchecked for every chain (CalAtlantic, Ryland, WCI, AV Homes) | Entity continuity is established; metric continuity is not. |
| S5 | Millrose restatement treatment `missing`; balance-sheet inventory delta not isolated | The largest single-metric break in the ledger is not fully characterized. |
| S6 | Six rights/revision claims rest on search summaries after HTTP 403 (MBA, S&P DJI, BLS CPI, NAHB terms) | Those verdicts are source claims, not verified. NAHB is **unverified, not cleared**. |
| S7 | Census NRS exact revision window unconfirmed — the freeze's rider states "three subsequent months plus annual benchmarking"; only general language was confirmed | The rider's *conclusion* (`revision_optimistic`) is adopted; its *stated mechanism* is carried as unverified. |
| S8 | Metric-level `available_at` spot-checked on 1 of 144 issuer-quarters | The two-knowledge-cutoff rule is a spot-check generalization for five of six issuers. |
| S9 | Fleet-wide accounting-standard adoptions VERIFIED for one or two issuers, INFERENCE for the rest | Strong inference (mandatory FASB windows) but not opened per issuer. |
| S10 | TOL JV-exclusion consistency verified for two periods only; City Living consolidation unresolved | X10's scope across the window is unconfirmed. |
| S11 | Hovnanian's 2021 Form 15-12G scope unresolved | A named trap, not a blocker for the frozen roster. |
| S12 | Two named PHM acquisitions (American West, John Wieland) not confirmed as SEC-filed events | Marked `missing` — not invented, not dropped. |

---

## 3. Falsifiers — what would overturn this census

Grouped by which conclusion they attack. **Every falsifier is checkable.**

### 3.1 Against the block count (B = 5)

| # | Falsifier | Effect |
|---|---|---|
| F-B1 | A documented housing shock in the window, independent of the rate/credit channel, absent from the frozen list | B rises by one |
| F-B2 | Block 6 (2024–) shown closed before 2026-08-21 on a pre-registered closing rule | B becomes 6 |
| F-B3 | The 2013 taper shown to be a distinct shock in a different transmission channel from the recovery | D1 wrong; B becomes 6 |
| F-B4 | Within-block cross-issuer correlation shown low (ρ < 0.5) on train folds | `n_eff` rises toward 8–9 |

**None reaches 40.** The `underpowered_accruing` determination is invariant across all four.

### 3.2 Against the definition crosswalk

| # | Falsifier | Effect |
|---|---|---|
| F-D1 | A LEN filing stating a cancellation formula | B3 clears; condition (1) may narrow |
| F-D2 | Pre-2016 PHM/NVR filings stating the formula | B2 clears; blocks 1–2 regain a denominator |
| F-D3 | KBH's FY2008 net-vs-gross contradiction resolved by a clarifying filing | KBH's early cancellation series becomes usable |
| F-D4 | TOL found to disclose a numeric cycle time | X9 narrows; `pace_recovery` gains a second issuer |
| F-D5 | An acquisition found to have restated prior-period operating metrics | The universal no-restatement rule breaks |

### 3.3 Against the source/PIT matrix

| # | Falsifier | Effect |
|---|---|---|
| F-S1 | NAR grants written consent, or the storage bar is superseded | B4 clears |
| F-S2 | Freddie Mac's terms determined to permit internal research storage | PMMS becomes a confirmed `pit_pure` mortgage-rate leg back to 1971 |
| F-S3 | Census NRS release archive proves incomplete or unparseable for 2005–2026 | The upgrade path to `pit_pure` closes permanently |
| F-S4 | NAHB terms located and permissive, and HMI confirmed non-revised | A sentiment leg opens |
| F-S5 | FHFA or BEA found to publish a true vintage archive | Those legs upgrade from `revision_optimistic` |

### 3.4 Against the survivorship census

| # | Falsifier | Effect |
|---|---|---|
| F-V1 | A failed builder's terminal-year financials found outside EDGAR | B5 weakens for that name |
| F-V2 | Post-merger segment disclosures found tracking legacy CalAtlantic/Ryland/WCI inside Lennar | S4 closes for the largest chain |
| F-V3 | A defensible public-homebuilder population-by-date constructed | B6 clears; a mortality rate becomes quotable |
| F-V4 | Roster widened at A4 to include MTH/MHO/BZH/HOV | Representativeness improves — **power does not** |
| F-V5 | Mercedes Homes / John Wieland found to have had SEC-registered public debt | Two `not_applicable` verdicts become closable gaps |

---

## 4. The three findings most likely to be misread

Recorded because each has an attractive wrong reading.

**4.1 "Five blocks is fine — we have 522 issuer-quarters."**
No. `n_rows` and `n_issuers` are printed for transparency; **promotion uses `n_effective_blocks` and
nothing else**. The inflation factor is **~87×**. Four independent mechanisms defeat the row count and
they compound (block list §7).

**4.2 "Add MTH, MHO, BZH and HOV and the sample gets stronger."**
It gets *more representative*, which is worth doing on its own merits — and it adds **no power**. Four
more issuers inside the same five shocks are correlated rows, not independent draws. At ρ ≈ 0.8,
going from m=6 to m=10 moves `n_eff` from ~6.0 to ~6.2. Representativeness and power are separate
problems and only the first is addressable by adding issuers.

**4.3 "TOL started building spec homes in 2023."**
No. TOL's *unhyphenated* "speculative homes" appears as early as the FY2006 10-K. What changed in
FY2023 is the **labelled terminology and disclosure emphasis**; TOL's own framing points to roughly
FY2022–23 as the *operational* inflection. **Disclosure onset ≠ behaviour onset.** Reading the
terminology change as a strategy change manufactures an event out of a disclosure choice — the
general form of the era-correlated-availability hazard in crosswalk §5.

---

## 5. Corrections this census owes upward

Two items where the census's evidence differs from a statement in the merged freeze. **Neither is
applied unilaterally** — both require an amendment-log entry and Fable/Sol adjudication.

| # | Freeze statement | What the census found | Proposed |
|---|---|---|---|
| **C1** | §7.2(1): LEN excluded — "**no press-release cancellation rate**; its missingness is era-correlated by construction" | Press-release absence **confirmed** (3 of 4 FY2025 quarters, zero hits). But LEN **does disclose 14% in its 10-K MD&A** — missing from a channel, not from the record. The stronger ground is that **LEN states no formula anywhere**, so condition (4) has nothing to freeze. | Keep the exclusion; **restate the reason**. The [A18] missing-indicator ban survives and is better supported. |
| **C2** | §3 frozen block list [A8] contains "2013 taper (partial)" inside "2010–2013", and "2024–2026" as a listed block | The taper **overlaps** block 2 and is the same transmission channel; the 2024–2026 era is **OPEN** and counting it repeats the unit violation the memory cohort was denied (§7.3). | Taper → sub-episode of block 2. 2024–2026 → `OPEN_ACCRUING`, counts toward `n_blocks_prosp` on close. **B = 5.** |

**Both corrections reduce the census's own numbers.** Neither creates headroom. That is the direction
a census's self-corrections should run, and it is offered as evidence of the census's posture rather
than as a claim of correctness.

---

## 6. What was deliberately not done

Fenced by the commission and confirmed clean by grep over every lane packet:

- **No model fitting.** No parameter was estimated. ρ appears only as a pre-registered sensitivity grid.
- **No outcome inspection.** No price, return, market-cap, or performance figure was fetched, computed
  or recorded — including deal values surfaced incidentally during survivorship research.
- **No p-values, no alpha claims, no cycle prediction.**
- **No Prophet/Radar connection, no UI, no runtime, no screener, no new data plane.**
- **No trial-ledger registration.** A4 owns the first `data/` write.
- **No source purchase.** No paid source was procured or recommended for procurement.
- **No FRED/ALFRED content fetched, quoted, cached or stored** — clause (q), all use classes.
- **No behavioural or market-derived epoch** anywhere in the structural-break ledger.

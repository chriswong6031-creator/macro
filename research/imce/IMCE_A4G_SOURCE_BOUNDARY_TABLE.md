# IMCE-A4G — Source / Boundary Table

**Wave:** A4G. Records-only. No outcome number, model fit, or trial-ledger write appears anywhere below.
**Authority:** amended contract V1.1 §2/§4 (`IMCE_PREREGISTRATION_AND_EVALUATION_CONTRACT_V1.md`), as amended by `IMCE_A4G_AMENDMENT_LOG.md` (AG15, AG17, AG18).
**Purpose:** the mandatory Sol deliverable (d) — per-source rights + `pit_class` (closed enum) + vintage verdict, the PMMS HELD row, and the receipted macro boundary dates with source citations (or `not_yet_receipted` markers — never invented dates).
**Primary source:** `research/imce/hb0/IMCE_HB0_SOURCE_PIT_VINTAGE_MATRIX.md` (17 series, 12 owning agencies, retrieved 2026-08-21) and `research/imce/IMCE_HB0_SOURCE_DEFINITION_CENSUS_V1.md` §7 (per-source vintage audit, SEC/Census/Freddie Mac/FHFA legs).

---

## 1. `pit_class` — closed enum [AG15]

`pit_class` is closed at exactly three values, taken verbatim from `config/cycle_pattern/truth_schema.md`:

| `pit_class` | Meaning |
|---|---|
| `pit_pure` | All features computed from tape ≤ t; no revision risk |
| `revision_optimistic` | Some features use revised macro/regime data without ALFRED vintages |
| `mixed` | PIT-pure for the primary signal; revision-optimistic for regime features |

No fourth or fifth token may be minted for this family (AG15). A3 lane-1's own five-way `source_vintage_class` census vocabulary (`pit_pure`, `revision_optimistic`, `current_revised_only`, `prospective_from_capture`, `rights_blocked`) is a strictly more granular **local diagnostic**, retained below for its own analytic value, and crosswalked down to the closed enum per this fixed rule:

| `source_vintage_class` (census-local) | → `pit_class` (registered) | Rationale |
|---|---|---|
| `pit_pure` | `pit_pure` | identical meaning |
| `revision_optimistic` | `revision_optimistic` | identical meaning |
| `current_revised_only` | `revision_optimistic` | a strictly worse case of the same failure — no vintages at all, rather than incomplete ones |
| `prospective_from_capture` | `pit_pure` from the capture date forward only | before capture the leg does not exist — typed absence, never a back-filled `revision_optimistic` |
| `rights_blocked` | **no `pit_class` at all** | rights gate precedes vintage gate — an unusable source has no PIT question |

---

## 2. Macro/context source table

`V` = agency page opened directly. `S` = search-summarized (403 or not located) — a source claim pending verification, never treated as verified.

| # | Series | Owning agency (never FRED) | Rights verdict | `source_vintage_class` (local) | `pit_class` (registered, via crosswalk) |
|---|---|---|---|---|---|
| 1 | New Residential Sales (sold/for-sale/months-supply/price) | Census (w/ HUD) | public domain | `revision_optimistic` (upgradeable — §3) | `revision_optimistic` |
| 2 | New Residential Construction (starts/permits/completions) | Census (w/ HUD) | public domain | `revision_optimistic` | `revision_optimistic` |
| 3 | Survey of Construction | Census | public domain | `current_revised_only` | `revision_optimistic` |
| 4 | Quarterly Starts & Completions by Purpose/Design | Census | public domain | `revision_optimistic` | `revision_optimistic` |
| 5 | Existing-Home Sales | NAR | **RIGHTS-BLOCKED** `V` | `current_revised_only` | **none — rights-blocked** |
| 6 | Housing Affordability Index | NAR | **RIGHTS-BLOCKED** | `current_revised_only` | **none — rights-blocked** |
| 7 | NAHB/Wells Fargo Housing Market Index (HMI) | NAHB | **UNVERIFIED**, not cleared `S` | `pit_pure` (tentative) | not usable until rights verified |
| 8 | NAHB/Wells Fargo Housing Opportunity Index (HOI) | NAHB | **UNVERIFIED**; discontinued after Q4 2023 | `current_revised_only`, then `not_applicable` | not usable |
| 9 | Weekly Applications Survey (incl. Purchase Index) | MBA | **not_licensed** for numeric series `S` | `current_revised_only` | **none — rights-blocked** |
| 10 | Primary Mortgage Market Survey, 30-yr fixed (PMMS) | Freddie Mac | **HELD** `V` — see §4 | `pit_pure` | `pit_pure` **once rights clear; HELD until then** |
| 11 | House Price Index | FHFA | freely available | `revision_optimistic` | `revision_optimistic` |
| 12 | S&P CoreLogic Case-Shiller HPI | S&P Dow Jones Indices | **RIGHTS-BLOCKED** `S` | `current_revised_only` | **none — rights-blocked** |
| 13 | Constant-maturity yields (Treasury CMT) | U.S. Treasury | public domain | `pit_pure` | `pit_pure` — **primary rate leg** |
| 14 | CPI shelter / owners' equivalent rent | BLS | public domain | `revision_optimistic` (SA layer) | `revision_optimistic` |
| 15 | Residential fixed investment | BEA | public domain | `revision_optimistic` | `revision_optimistic` |
| 16 | Construction spending (C30) | Census | public domain | `revision_optimistic` | `revision_optimistic` |
| 17 | PPI — lumber and wood products | BLS | public domain | `pit_pure` (provisional) | `pit_pure` (provisional) |
| — | SEC EDGAR (all 6 roster issuers' filings) | SEC | public domain | `pit_pure` (vintage-clean via filing immutability) | `pit_pure` |
| — | DHI_IR / PEER_BUILDER_IR (issuer 8-K exhibits) | issuers, via SEC EDGAR | public domain | `pit_pure` (vintage-clean via filing immutability) | `pit_pure` |
| — | FRED / ALFRED (all series) | St. Louis Fed | **`DO_NOT_INGEST`** — clause (q), binds all use classes incl. display tier | n/a — categorically excluded | **none — excluded, never a `pit_class` question [AG18]** |

**Tally (macro/context legs, `source_vintage_class`):** `pit_pure` 2 confirmed (#10 rights-pending, #13) + 2 tentative/provisional (#7 unverified, #17) · `revision_optimistic` 7 · `current_revised_only` 6 · `rights_blocked` 3 sources / 4 series (#5, #6, #12, plus #9 not_licensed) · rights unverified 2 (#7, #8).

---

## 3. The one genuine upgrade path available (not executed)

Census NRS maintains a first-print press-release archive back to **January 1995** (`census.gov/construction/nrs/data/releases.html`) — each monthly release is itself the vintage artifact, reconstructing a genuine point-in-time series across the full 2005–2026 study window, no self-archival lane needed, no rights obstacle (public domain). **Disposition (unchanged by A4G, election E6 not executed):** NRS is declared `revision_optimistic` today, with a recorded, costed upgrade path to `pit_pure` via the release archive. A4 may register that upgrade as an explicit, scoped task; until executed, the `revision_optimistic` declaration and its disclosure obligation stand.

---

## 4. PMMS HELD row — detail

**Freddie Mac Primary Mortgage Market Survey, 30-year fixed, is HELD [AG18].** Neither GO nor blocked by default.

- **PIT basis:** genuinely `pit_pure` — weekly published rate, archived back to 1971 (`freddiemac.com/pmms/pmms_archives`, retrieved 2026-08-21), not revised after publication.
- **Rights tension:** the PMMS page condones attribution-only use, but the site-wide Terms of Use bar redistributing, publishing, or commercially exploiting "Data" without a separate written licence (`freddiemac.com/terms/`, retrieved 2026-08-21). The two statements are in tension and not resolved by this document.
- **Construction break, independent of the rights question:** PMMS underwent a methodology change on **2022-11-17** — survey-of-lenders methodology replaced by applications submitted to Freddie Mac's Loan Product Advisor (LPA); the fees/points and 5/1 ARM series were discontinued at the same date. [Freddie Mac Economic & Housing Research Note, `freddiemac.com/research/pdf/202210-Note-PMMS-12.pdf`, retrieved 2026-08-21; corroborated by National Mortgage Professional, `nationalmortgageprofessional.com/news/freddie-mac-updates-its-mortgage-rate-survey`, retrieved 2026-08-21.] Any cell pooling PMMS observations across 2022-11-17 pools two different measurement instruments under one series name — a construction break, distinct from and in addition to the vintage/rights question.
- **Interim primary rate leg:** Treasury constant-maturity yields (#13) — confirmed `pit_pure`, public domain, full daily archive, no rights ambiguity.
- **Falsifier registered:** Freddie Mac's terms determined to permit internal research storage → PMMS becomes a confirmed `pit_pure` mortgage-rate leg back to 1971 (`IMCE_HB0_SOURCE_PIT_VINTAGE_MATRIX.md` §6, F-2).

---

## 5. No-NAR-storage rule — detail [AG18]

Verbatim from `nar.realtor` (retrieved 2026-08-21): *"No part of this data may be reproduced, stored in a retrieval system, transmitted or redistributed in any form or by any means…without NAR's prior written consent."* "Stored in a retrieval system" is the operative phrase — this bars ingestion itself, the same way FRED's clause (q) does. A self-archival lane does **not** cure it: archiving is the prohibited act.

**Consequence:** the affordability construct is assembled from clean underlying-owner legs, never adopted from an off-the-shelf index:

| Leg | Clean source | `pit_class` |
|---|---|---|
| Price | Census NRS median/average price (#1) | `revision_optimistic`, upgradeable (§3) |
| Rate | U.S. Treasury CMT (#13) | `pit_pure` |
| Rate (mortgage-specific, optional refinement) | Freddie Mac PMMS (#10) | `pit_pure` archive, but HELD pending rights (§4) |
| Income | Census / BLS income series | public domain |

Never presented as "the affordability index" — it is a house construction, disclosed as such in every readout.

---

## 6. Macro block boundary receipt status [AG17]

Per AG17, a block boundary used to partition an actual outcome run must carry a citation to a **dated macro-series or issuer-event source**, not a narrative news citation. The block list's year-level boundaries (contract §3 [A8]) and the A3 lane-2 proposed month-level boundaries (`IMCE_HB0_INDEPENDENT_BLOCK_LIST.md` §5) are recorded below with their current receipt status. **No date below is invented; every row is either receipted with a dated source or marked `not_yet_receipted`.**

| Block | Proposed month boundary | Receipt status | Detail |
|---|---|---|---|
| GFC bust | 2006-01 → 2009-12 | **not_yet_receipted** | Narrative-sourced only (e.g. NAHB HMI "all-time low of 8 in January 2009" — a level statement inside the block, not a boundary-dating citation for 2006-01 or 2009-12 specifically). |
| GFC recovery / land-light era | 2010-01 → 2013-12 | **not_yet_receipted** | Narrative-sourced only ("recovery... at a steady-but-very-slow pace"). |
| 2013 taper (sub-episode, zero N regardless) | 2013-05 → 2013-12 | **not_yet_receipted** | A dated macro fact exists nearby — "an almost one percentage point increase in the 30-year fixed mortgage rate between May and September of 2013" (St. Louis Fed blog post, `stlouisfed.org/on-the-economy/2017/march/housing-markets-face-taper-tantrum-moment`, retrieved 2026-08-21) — but this is a Fed Reserve Bank *blog* post citing a rate move, not a dated macro-series print pinned to the exact 2013-05/2013-12 boundary; and per AG7/AG17 this sub-episode's exact date does not need to be minted for N-accounting purposes regardless. |
| 2014–2019 grind, incl. 2018 air-pocket | 2014-01 → 2019-12 | **not_yet_receipted** | Narrative-sourced only (XHB ETF drawdown, builder-sentiment index level — level statements, not boundary-dating citations). |
| 2018 air-pocket (sub-episode, zero N regardless) | 2018-07 → 2018-12 | **not_yet_receipted** | Same as above — narrative only; sub-episode status (AG7) makes the exact date immaterial to N-accounting. |
| 2020–2021 pandemic boom | 2020-03 → 2021-12 | **not_yet_receipted** | Narrative-sourced only ("30-year fixed rate mortgage rates dropped to an historic low of 2.7 percent in December 2020" — a level statement, not a boundary citation for 2020-03 specifically). |
| 2022–2023 rate shock / cancellation spike | 2022-01 → 2023-12 | **not_yet_receipted for the block boundary itself** — **but a genuinely dated, receipted macro-series event falls inside this block:** Freddie Mac PMMS's construction break, **2022-11-17** (`freddiemac.com/research/pdf/202210-Note-PMMS-12.pdf`, retrieved 2026-08-21) — a real dated source event, but it dates a mid-block construction break, not the block's own start/end boundary. |
| 2024–2026 affordability era (`OPEN_ACCRUING`, zero N regardless) | 2024-01 → open | **not_yet_receipted for the start boundary** — **no end boundary exists (open, AG8).** A dated issuer event falls inside this block: LEN's Millrose spin-off, completed **2025-02-07** (LEN Form 8-K / press release, cited in `IMCE_HB0_SOURCE_DEFINITION_CENSUS_V1.md` §5a, retrieved 2026-08-21) — an issuer-structural event, not the block boundary. |

**Additional dated, receipted events on the record (issuer/source-structural, not block boundaries):**

| Event | Date | Source |
|---|---|---|
| PulteGroup / Centex merger closed | 2009-08-18 | SEC EDGAR PulteGroup 8-K/425, `sec.gov/Archives/edgar/data/822416/000119312509222939/dex991.htm`, retrieved 2026-08-21 |
| Lennar / CalAtlantic merger closed | 2018-02-12 | `prnewswire.com/news-releases/lennar-completes-strategic-combination-with-calatlantic-300597384.html`, retrieved 2026-08-21 |
| Lennar / Millrose spin-off completed | 2025-02-07 | cited in `IMCE_HB0_SOURCE_DEFINITION_CENSUS_V1.md` §5a |
| Freddie Mac PMMS construction break | 2022-11-17 | `freddiemac.com/research/pdf/202210-Note-PMMS-12.pdf`, retrieved 2026-08-21 |

**Governing rule (AG17, unchanged):** these issuer/source-structural events are receipted and usable for their own stated purpose (structural-break flags, construction-break disclosure). None of them is asserted here as a receipt for a BLOCK boundary — doing so would be exactly the M4-flagged circularity/narrative-substitution error this table exists to avoid. Until a systematic macro-series dating pass across all block boundaries is performed (lane-1 gap 11, still open), every block boundary above stays `not_yet_receipted` and may not be used to partition an actual outcome run (contract §15/§15a new stop condition).

---

**This document authorizes nothing. No outcome partition has run on any boundary above. The next authorized act is actual A4 registration and, separately, the macro-series boundary-dating pass named in lane-1 gap 11.**

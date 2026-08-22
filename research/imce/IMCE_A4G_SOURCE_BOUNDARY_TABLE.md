# IMCE-A4G / A4P — Source / Boundary Table

**Wave:** A4G, updated by A4P (2026-08-21, ruling 6). Records-only. No outcome number, model fit, or trial-ledger write appears anywhere below.
**Authority:** amended contract V1.2 §2/§4 (`IMCE_PREREGISTRATION_AND_EVALUATION_CONTRACT_V1.md`), as amended by `IMCE_A4G_AMENDMENT_LOG.md` (AG15, AG17, AG18, AP6).
**Purpose:** the mandatory Sol deliverable (d) — per-source rights + `pit_class` (closed enum) + vintage verdict, the PMMS HELD row, and the receipted macro boundary dates with source citations (or `not_yet_receipted` markers — never invented dates). **This is a living A4G/A4P artifact, updated in place to the current law; every material change is logged in `IMCE_A4G_AMENDMENT_LOG.md`.**
**Primary source:** `research/imce/hb0/IMCE_HB0_SOURCE_PIT_VINTAGE_MATRIX.md` (17 series, 12 owning agencies, retrieved 2026-08-21) and `research/imce/IMCE_HB0_SOURCE_DEFINITION_CENSUS_V1.md` §7 (per-source vintage audit, SEC/Census/Freddie Mac/FHFA legs). **A4P adds:** WebSearch/WebFetch receipts gathered 2026-08-21 (this session) — §2 row 13 (Treasury), §6 (rewritten), §7 (new).

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

`V` = agency page opened directly (this session or, where noted, a prior cited HB0 session). `S` = search-summarized or not independently re-verified this session — a source claim pending verification, never treated as verified. **[M4 fix, A4G revision]** The `pit_class` column below carries ONLY a closed-enum token (`pit_pure` / `revision_optimistic` / `mixed`) or `—` (no registrable `pit_class` — rights-blocked, unverified-rights, held, or categorically excluded); all qualifying prose ("not usable until…", "once rights clear", etc.) has moved to the Notes column.

| # | Series | Owning agency (never FRED) | Rights verdict | `source_vintage_class` (local) | `pit_class` (registered) | Notes |
|---|---|---|---|---|---|---|
| 1 | New Residential Sales (sold/for-sale/months-supply/price) | Census (w/ HUD) | public domain `V` | `revision_optimistic` | `revision_optimistic` | Upgradeable to `pit_pure` — §3 |
| 2 | New Residential Construction (starts/permits/completions) | Census (w/ HUD) | public domain `V` | `revision_optimistic` | `revision_optimistic` | — |
| 3 | Survey of Construction | Census | public domain `V` | `current_revised_only` | `revision_optimistic` | Crosswalked per §1 (strictly-worse case) |
| 4 | Quarterly Starts & Completions by Purpose/Design | Census | public domain `V` | `revision_optimistic` | `revision_optimistic` | — |
| 5 | Existing-Home Sales | NAR | **RIGHTS-BLOCKED** `V` | `current_revised_only` | **—** | Rights-blocked — no `pit_class` question (§1 crosswalk, rights gate precedes vintage gate) |
| 6 | Housing Affordability Index | NAR | **RIGHTS-BLOCKED** `V` | `current_revised_only` | **—** | Rights-blocked, same basis as #5 |
| 7 | NAHB/Wells Fargo Housing Market Index (HMI) | NAHB | **UNVERIFIED**, not cleared `S` | `pit_pure` (tentative) | **—** | Rights not yet verified — `pit_class` withheld pending rights; would be `pit_pure` if/when cleared |
| 8 | NAHB/Wells Fargo Housing Opportunity Index (HOI) | NAHB | **UNVERIFIED**; discontinued after Q4 2023 `S` | `current_revised_only`, then `not_applicable` | **—** | Discontinued + rights unverified — not usable regardless |
| 9 | Weekly Applications Survey (incl. Purchase Index) | MBA | **not_licensed** for numeric series `S` | `current_revised_only` | **—** | Not licensed — treated as rights-blocked for the numeric series |
| 10 | Primary Mortgage Market Survey, 30-yr fixed (PMMS) | Freddie Mac | **HELD** `V` — see §4 | `pit_pure` | **—** | Genuinely `pit_pure` by construction, but HELD pending rights determination — `pit_class` not assignable until rights clear (§1 crosswalk) |
| 11 | House Price Index | FHFA | freely available `V` | `revision_optimistic` | `revision_optimistic` | — |
| 12 | S&P CoreLogic Case-Shiller HPI | S&P Dow Jones Indices | **RIGHTS-BLOCKED** `S` | `current_revised_only` | **—** | Rights-blocked absent an S&P DJI licence |
| 13 | Constant-maturity yields (Treasury CMT) | U.S. Treasury | public domain **`S` — DOWNGRADED [MAJ-6]** | `pit_pure` | `pit_pure` | **Primary rate leg.** A4G session attempted owner-direct re-verification (`home.treasury.gov`, 3 WebFetch attempts across two URL paths) — every attempt timed out (60s), while a control fetch to `example.com` succeeded in the same session, ruling out a general tool failure. **A4P session (2026-08-21) repeated the attempt** — 3 more `WebFetch` calls (TextView query page, `interest-rates-data-csv-archive` alias, `daily-treasury-rate-archives` index) — **all 3 again timed out**, confirming the failure is structural to this domain via this tool, not incidental. Sol's A4P commissioning message independently asserts Treasury publishes the Daily Treasury Par Yield Curve Rates with CSV/XML export and archived historical files — **recorded as Sol-attested (CEO-level, authoritative for the fact of availability)**, corroborated by a `WebSearch` pass this session (not owner-direct) locating the archive index (`.../daily-treasury-rate-archives`) and a dedicated XML files page (`.../interest-rate-xml-files`) reporting CSV/XML/raw-XML availability — see §7. **Grade remains `S`** (search-summarized / Sol-attested, not independently page-opened by any session to date) — **not upgraded to `V`.** The reuse/storage basis (redistribution/persistence rights) is explicitly **NOT settled** by either session's record; no persistent ingestion has occurred or occurs in this wave. **Unresolved at A4: both candidate rate legs — Treasury CMT (this row, `S`) and PMMS (HELD, row 10) — currently lack a session-verified `V`-grade citation; a future A4 registration or ingestion-design session must complete owner-direct verification of at least the primary leg (Treasury CMT) AND settle its storage basis before relying on it in a registered, persisted cell.** |
| 14 | CPI shelter / owners' equivalent rent | BLS | public domain `V` | `revision_optimistic` (SA layer) | `revision_optimistic` | — |
| 15 | Residential fixed investment | BEA | public domain `V` | `revision_optimistic` | `revision_optimistic` | — |
| 16 | Construction spending (C30) | Census | public domain `V` | `revision_optimistic` | `revision_optimistic` | — |
| 17 | PPI — lumber and wood products | BLS | public domain `V` | `pit_pure` (provisional) | `pit_pure` | Provisional — revision policy unconfirmed |
| — | SEC EDGAR (all 6 roster issuers' filings) | SEC | public domain `V` | `pit_pure` (vintage-clean via filing immutability) | `pit_pure` | — |
| — | DHI_IR / PEER_BUILDER_IR (issuer 8-K exhibits) | issuers, via SEC EDGAR | public domain `V` | `pit_pure` (vintage-clean via filing immutability) | `pit_pure` | — |
| — | FRED / ALFRED (all series) | St. Louis Fed | **`DO_NOT_INGEST`** — clause (q), binds all use classes incl. display tier | n/a — categorically excluded | **—** | Excluded categorically [AG18] — never a `pit_class` question |

**Tally — row-derivable directly from the table above [M4 fix]:** 20 total rows (17 numbered series + SEC EDGAR + DHI_IR/PEER_BUILDER_IR + FRED/ALFRED). `pit_class = pit_pure`: 4 rows (#13, #17, SEC EDGAR, DHI_IR/PEER_BUILDER_IR). `pit_class = revision_optimistic`: 8 rows (#1, #2, #3, #4, #11, #14, #15, #16). `pit_class = —` (no registrable `pit_class`): 8 rows (#5, #6, #7, #8, #9, #10, #12, FRED/ALFRED) — of which rights-blocked: 3 (#5, #6, #12); not-licensed: 1 (#9); rights-unverified: 2 (#7, #8); HELD: 1 (#10); categorically excluded: 1 (FRED/ALFRED). `4 + 8 + 8 = 20` — identity check against the row total.

---

## 3. The one genuine upgrade path available (not executed)

Census NRS maintains a first-print press-release archive back to **January 1995** (`census.gov/construction/nrs/data/releases.html`) — each monthly release is itself the vintage artifact, reconstructing a genuine point-in-time series across the full 2005–2026 study window, no self-archival lane needed, no rights obstacle (public domain). **Disposition (unchanged by A4G, election E6 not executed):** NRS is declared `revision_optimistic` today, with a recorded, costed upgrade path to `pit_pure` via the release archive. A4 may register that upgrade as an explicit, scoped task; until executed, the `revision_optimistic` declaration and its disclosure obligation stand.

---

## 4. PMMS HELD row — detail

**Freddie Mac Primary Mortgage Market Survey, 30-year fixed, is HELD [AG18].** Neither GO nor blocked by default.

- **PIT basis:** genuinely `pit_pure` in construction — weekly published rate, archived back to 1971 (`freddiemac.com/pmms/pmms_archives`, retrieved 2026-08-21), not revised after publication. **Registered `pit_class` today is `—`** (§2, M4 fix), not `pit_pure` — rights gate precedes vintage gate (§1 crosswalk), so a HELD source carries no registrable `pit_class` until its rights question resolves, even though its vintage properties are known and clean.
- **Rights tension:** the PMMS page condones attribution-only use, but the site-wide Terms of Use bar redistributing, publishing, or commercially exploiting "Data" without a separate written licence (`freddiemac.com/terms/`, retrieved 2026-08-21). The two statements are in tension and not resolved by this document.
- **Construction break, independent of the rights question:** PMMS underwent a methodology change on **2022-11-17** — survey-of-lenders methodology replaced by applications submitted to Freddie Mac's Loan Product Advisor (LPA); the fees/points and 5/1 ARM series were discontinued at the same date. [Freddie Mac Economic & Housing Research Note, `freddiemac.com/research/pdf/202210-Note-PMMS-12.pdf`, retrieved 2026-08-21; corroborated by National Mortgage Professional, `nationalmortgageprofessional.com/news/freddie-mac-updates-its-mortgage-rate-survey`, retrieved 2026-08-21.] Any cell pooling PMMS observations across 2022-11-17 pools two different measurement instruments under one series name — a construction break, distinct from and in addition to the vintage/rights question.
- **Interim primary rate leg:** Treasury constant-maturity yields (#13) — `pit_pure`, public domain, no known rights ambiguity, but **downgraded to `S` this session [MAJ-6]**: three owner-direct verification attempts (`home.treasury.gov`) timed out and were not completed. Both candidate rate legs (PMMS here, Treasury CMT at #13) are therefore currently unresolved-at-`V` in different ways — PMMS on rights, Treasury CMT on this session's failed re-verification — and a future A4 registration session should complete owner-direct verification of at least Treasury CMT before relying on it in a registered cell.
- **Falsifier registered:** Freddie Mac's terms determined to permit internal research storage → PMMS becomes a confirmed `pit_pure` mortgage-rate leg back to 1971 (`IMCE_HB0_SOURCE_PIT_VINTAGE_MATRIX.md` §6, F-2).

---

## 5. No-NAR-storage rule — detail [AG18]

Verbatim from `nar.realtor` (retrieved 2026-08-21): *"No part of this data may be reproduced, stored in a retrieval system, transmitted or redistributed in any form or by any means…without NAR's prior written consent."* "Stored in a retrieval system" is the operative phrase — this bars ingestion itself, the same way FRED's clause (q) does. A self-archival lane does **not** cure it: archiving is the prohibited act.

**Consequence:** the affordability construct is assembled from clean underlying-owner legs, never adopted from an off-the-shelf index:

| Leg | Clean source | `pit_class` |
|---|---|---|
| Price | Census NRS median/average price (#1) | `revision_optimistic`, upgradeable (§3) |
| Rate | U.S. Treasury CMT (#13) | `pit_pure`, but graded `S` this session pending owner-direct re-verification (§2, MAJ-6) |
| Rate (mortgage-specific, optional refinement) | Freddie Mac PMMS (#10) | `pit_pure` in construction, but registered `pit_class` is `—` — HELD pending rights (§4) |
| Income | Census / BLS income series | public domain |

Never presented as "the affordability index" — it is a house construction, disclosed as such in every readout.

---

## 6. Macro block boundary receipt status [AG17, updated AP6]

Per AG17, a block boundary used to partition an actual outcome run must carry a citation to a **dated macro-series or issuer-event source**, not a narrative news citation. The block list's year-level boundaries (contract §3 [A8]) and the A3 lane-2 proposed month-level boundaries (`IMCE_HB0_INDEPENDENT_BLOCK_LIST.md` §5) are recorded below with their current receipt status. **No date below is invented; every row is either receipted with a dated source or marked `not_yet_receipted`.**

**A4P research pass (2026-08-21, AP6):** this session performed a bounded, good-faith web-research pass for first-party, non-outcome, dated macro-series/monetary-policy sources bracketing the proposed month boundaries — priority given to the 3 blocks that actually matter for the six registered v0 historical cells' N-accounting under AP2 (grind/pandemic-boom/rate-shock; GFC bust/recovery no longer count toward any registered cell's N, though they remain in the named 7-entry taxonomy). **Three genuinely new dated, first-party, non-outcome receipts were found and are recorded below** — none of them redefines a block boundary; each is recorded as *corroborating/bracketing context*, per the scope discipline restated below. **No boundary is changed by AP6** — no evidence found this session contradicts any proposed month boundary; every boundary not newly bracketed below remains `not_yet_receipted`, unchanged from the A4G finding, and is not silently left un-researched — the research was performed and came up empty for those rows.

| Block | Proposed month boundary | Receipt status | Detail |
|---|---|---|---|
| GFC bust | 2006-01 → 2009-12 | **not_yet_receipted** | Narrative-sourced only (e.g. NAHB HMI "all-time low of 8 in January 2009" — a level statement inside the block, not a boundary-dating citation for 2006-01 or 2009-12 specifically). AP6 research pass did not target this block (deprioritized — GFC blocks carry zero N for all 6 registered cells under AP2). |
| GFC recovery / land-light era | 2010-01 → 2013-12 | **not_yet_receipted** | Narrative-sourced only ("recovery... at a steady-but-very-slow pace"). AP6 did not target this block (same deprioritization). |
| 2013 taper (sub-episode, zero N regardless) | 2013-05 → 2013-12 | **not_yet_receipted** | A dated macro fact exists nearby — "an almost one percentage point increase in the 30-year fixed mortgage rate between May and September of 2013" (St. Louis Fed blog post, `stlouisfed.org/on-the-economy/2017/march/housing-markets-face-taper-tantrum-moment`, retrieved 2026-08-21) — but this is a Fed Reserve Bank *blog* post citing a rate move, not a dated macro-series print pinned to the exact 2013-05/2013-12 boundary; and per AG7/AG17 this sub-episode's exact date does not need to be minted for N-accounting purposes regardless. |
| 2014–2019 grind, incl. 2018 air-pocket | 2014-01 → 2019-12 | **not_yet_receipted for the exact month boundary** | Narrative-sourced only (XHB ETF drawdown, builder-sentiment index level — level statements, not boundary-dating citations). AP6's research pass targeted this block (it is B≤3-contributing under AP2) but found no first-party, housing-specific, dated print pinned to 2014-01 or 2019-12 specifically — remains `not_yet_receipted`, honestly, rather than substituting a general-economy source. |
| 2018 air-pocket (sub-episode, zero N regardless) | 2018-07 → 2018-12 | **not_yet_receipted** | Same as above — narrative only; sub-episode status (AG7) makes the exact date immaterial to N-accounting. |
| 2020–2021 pandemic boom | 2020-03 → 2021-12 | **not_yet_receipted for the exact month boundary — but bracketed by 2 new `V`-grade first-party receipts [AP6]:** NBER Business Cycle Dating Committee, `nber.org` (owner page opened directly this session): peak in monthly U.S. economic activity **February 2020** (announced 2020-06-08, `nber.org/news/business-cycle-dating-committee-announcement-june-8-2020`, retrieved 2026-08-21); trough **April 2020** (announced 2021-07-19, `nber.org/news/business-cycle-dating-committee-announcement-july-19-2021`, retrieved 2026-08-21). **Scope discipline (unchanged from AG17/M4):** these are GENERAL U.S. business-cycle dates, not housing-sector-specific — housing did not bust during this recession, it boomed. Recorded as bracketing context only (the proposed 2020-03 start sits 1–2 months after the NBER peak/trough window) — **not** used to redefine the housing-specific boundary. A candidate housing-specific receipt (Freddie Mac PMMS record-low 30-year rate, 2.66% on 2020-12-24, `freddiemac.gcs-web.com/news-releases/news-release-details/mortgage-rates-hit-record-low-yearend`) was found via `WebSearch` but returned **HTTP 403** on direct `WebFetch` — recorded `S`-grade (search-summarized only), and it is a level statement (a record low reached *within* the block) not a boundary-dating citation, consistent with the A4G table's existing treatment of the prior "2.7% in December 2020" narrative citation. |
| 2022–2023 rate shock / cancellation spike | 2022-01 → 2023-12 | **not_yet_receipted for the exact month boundary — but bracketed by 1 new `V`-grade first-party receipt [AP6]:** Federal Reserve, `federalreserve.gov` press release (owner page opened directly this session): **2022-03-16**, FOMC raised the federal funds target range to 0.25%–0.50% from 0–0.25%, "the first hike of the tightening cycle that began in 2022" (`federalreserve.gov/newsevents/pressreleases/monetary20220316a1.htm`, retrieved 2026-08-21). This is a monetary-policy action (first-party, non-outcome, dated), not a housing-sector print — it brackets the proposed 2022-01 start within ~2.5 months and directly corroborates the block's own name ("rate shock") but is **not** used to redefine the month boundary. Also unchanged from A4G: Freddie Mac PMMS's construction break, **2022-11-17** (`freddiemac.com/research/pdf/202210-Note-PMMS-12.pdf`, retrieved 2026-08-21) — a real dated source event inside this block, dating a mid-block methodology change, not the block's own start/end boundary. |
| 2024–2026 affordability era (`OPEN_ACCRUING`, zero N regardless) | 2024-01 → open | **not_yet_receipted for the start boundary** — **no end boundary exists (open, AG8).** A dated issuer event falls inside this block: LEN's Millrose spin-off, completed **2025-02-07** (LEN Form 8-K / press release, cited in `IMCE_HB0_SOURCE_DEFINITION_CENSUS_V1.md` §5a, retrieved 2026-08-21) — an issuer-structural event, not the block boundary. AP6 did not target this block (zero N regardless of receipt status, AG8). |

**Additional dated, receipted events on the record (issuer/source-structural or general-macro, not block boundaries):**

| Event | Date | Source | Grade |
|---|---|---|---|
| PulteGroup / Centex merger closed | 2009-08-18 | SEC EDGAR PulteGroup 8-K/425, `sec.gov/Archives/edgar/data/822416/000119312509222939/dex991.htm`, retrieved 2026-08-21 | `S` (A4G) |
| Lennar / CalAtlantic merger closed | 2018-02-12 | `prnewswire.com/news-releases/lennar-completes-strategic-combination-with-calatlantic-300597384.html`, retrieved 2026-08-21 | `S` (A4G) |
| Lennar / Millrose spin-off completed | 2025-02-07 | cited in `IMCE_HB0_SOURCE_DEFINITION_CENSUS_V1.md` §5a | `S` (A4G) |
| Freddie Mac PMMS construction break | 2022-11-17 | `freddiemac.com/research/pdf/202210-Note-PMMS-12.pdf`, retrieved 2026-08-21 | `S` (A4G) |
| FOMC first 2022 rate hike | 2022-03-16 | `federalreserve.gov/newsevents/pressreleases/monetary20220316a1.htm`, retrieved 2026-08-21 | **`V`** (AP6, owner page opened directly) |
| NBER recession peak (COVID) | 2020-02 (announced 2020-06-08) | `nber.org/news/business-cycle-dating-committee-announcement-june-8-2020`, retrieved 2026-08-21 | **`V`** (AP6, owner page opened directly) |
| NBER recession trough (COVID) | 2020-04 (announced 2021-07-19) | `nber.org/news/business-cycle-dating-committee-announcement-july-19-2021`, retrieved 2026-08-21 | **`V`** (AP6, owner page opened directly) |
| Freddie Mac PMMS record-low 30yr rate | 2020-12-24, 2.66% | `freddiemac.gcs-web.com/news-releases/news-release-details/mortgage-rates-hit-record-low-yearend` (WebSearch summary; direct fetch returned HTTP 403) | `S` (AP6) |

**Governing rule (AG17, unchanged; restated per AP6):** these issuer/source-structural and general-macro events are receipted and usable for their own stated purpose (structural-break flags, construction-break disclosure, general-cycle bracketing context). **None of them is asserted here as a receipt for a BLOCK boundary** — doing so would be exactly the M4-flagged circularity/narrative-substitution error this table exists to avoid, and using a general-economy date (NBER, FOMC) to redefine a housing-sector-specific boundary would repeat the same category of error in a new direction. Until a systematic, housing-sector-specific macro-series dating pass across all block boundaries is performed (lane-1 gap 11, still open after both the A4G and A4P research passes), every block boundary marked `not_yet_receipted` above stays so and may not be used to partition an actual outcome run **on that boundary** (contract §15/§15a stop condition) — the year-level boundaries (frozen, not "proposed") remain fully usable without month-level receipting, per AG17's own escape clause.

---

## 7. Treasury CSV/XML archive — receipt detail [AP6, new]

**Sol's A4P commissioning message independently asserts:** "Treasury publishes Daily Treasury Par Yield Curve Rates with CSV/XML and archived files." This is recorded as a **Sol-attested (CEO-level) fact**, treated as authoritative for the *existence* of the archive/export capability, separate from and not requiring a session's own owner-direct page-open to be actionable as a governance record.

**This session's own verification attempt:** 3 `WebFetch` calls against `home.treasury.gov` — the `TextView` query page (`?type=daily_treasury_yield_curve&field_tdr_date_value=2026`), an `interest-rates-data-csv-archive` alias, and the `daily-treasury-rate-archives` index — **all 3 timed out at 60 seconds**, reproducing the identical failure the A4G wave recorded under MAJ-6 (3 different attempts, same outcome). This is now a **repeated, reproducible failure across two independent sessions and six total attempts** against this specific domain via `WebFetch` — recorded as a durable finding, not a one-off tool hiccup.

**A `WebSearch` pass (this session) corroborates, without opening the primary page directly:**
- Archive index: `home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rate-archives` — search-result summary: "provides access to select types of interest rate data including Daily Treasury Par Yield Curve Rates... can be downloaded as CSV files, viewed as XML feeds, or downloaded as raw XML."
- Dedicated XML files page: `home.treasury.gov/policy-issues/financing-the-government/interest-rate-statistics/interest-rate-xml-files`.

**Grade: `S`** (search-summarized / Sol-attested) — **not** `V`. No session to date has independently opened the Treasury archive page itself. This is disclosed, not hidden: the fact of CSV/XML availability is recorded with high confidence (Sol's direct assertion + independent search corroboration + Treasury's well-known public first-party status), but the specific grading discipline this table applies throughout (§1 legend: `V` = agency page opened directly) is held to consistently rather than relaxed for a high-confidence case.

**Storage/reuse basis — explicitly NOT settled, per the A4P ruling's own instruction ("do NOT ingest now"):** no persistent ingestion of Treasury CMT data occurs in this wave or any prior IMCE wave. A future A4 registration or ingestion-design session must (a) complete owner-direct `V`-grade verification of the archive page, and (b) determine and record Treasury's specific redistribution/persistence terms (distinct from the general "public domain, U.S. government work" presumption already noted at §2 row 13 — the presumption has not been independently checked against Treasury's own terms-of-use page this session, the way NAR's and Freddie Mac's terms were checked at §4–§5) before any `C_t`/`M_t` field is built on this series.

---

**This document authorizes nothing. No outcome partition has run on any boundary above. The next authorized act is actual A4 registration and, separately, the housing-sector-specific macro-series boundary-dating pass named in lane-1 gap 11 (still open after two research passes).**

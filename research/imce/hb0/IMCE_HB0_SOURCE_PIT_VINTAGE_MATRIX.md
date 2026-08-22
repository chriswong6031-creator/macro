# IMCE-HB-0 — Source, PIT and vintage matrix (macro/context legs)

**Wave:** A3 / IMCE-HB-0. Records-only. This is the **vintage rider** owed by the merged freeze [G8-M6]:

> IMCE-HB-0 must add a per-source vintage audit for every GO macro/homebuilder source; any leg
> without retrievable vintages is declared `revision_optimistic` in the contract's `pit_class` and
> disclosed in every readout that uses it.

**Evidence lane:** research/sonnet, 17 series across 12 owning agencies, 2026-08-21.
**Fence honoured:** no FRED or ALFRED content was fetched, quoted, or stored at any point — FRED terms
clause (q) bars storing, caching, archiving, or database incorporation, and binds all use classes
including display tier (freeze §8, `DO_NOT_INGEST`). Every series commonly reached via FRED carries a
named underlying-agency replacement path below. No price, return, or outcome data appears here.

---

## 0. Vocabulary adjudication — the five census classes are NOT the CPI enum

**Defect found, and deliberately not papered over.** The commission names five vintage classes
(`pit_pure`, `revision_optimistic`, `current_revised_only`, `prospective_from_capture`,
`rights_blocked`). The canonical CPI truth schema — `config/cycle_pattern/truth_schema.md:61` — admits
exactly **three** `pit_class` values:

| CPI `pit_class` | Meaning (verbatim from the schema table) |
|---|---|
| `pit_pure` | All features computed from tape ≤ t; no revision risk |
| `revision_optimistic` | Some features use revised macro/regime data without ALFRED vintages |
| `mixed` | PIT-pure for the primary signal; revision-optimistic for regime features |

Minting a fourth or fifth CPI enum value from this wave would recreate the exact defect the A2 audit
exists to heal — the freeze found **at least four coexisting consumer vocabularies** including orphan
tokens registered in no authority, and an unknown status "would fence no surface" [G8-M1, G8-M7].

**Ruling.** The five classes are an **HB-0-local source-census vocabulary** named
`source_vintage_class`. They are strictly more granular than `pit_class` and **never substitute for
it**. Any future truth row carries a `pit_class` from the three-value CPI enum, derived through this
fixed crosswalk:

| `source_vintage_class` (census) | → CPI `pit_class` | Rationale |
|---|---|---|
| `pit_pure` | `pit_pure` | identical meaning |
| `revision_optimistic` | `revision_optimistic` | identical meaning |
| `current_revised_only` | `revision_optimistic` | a strictly worse case of the same failure — no vintages at all, rather than incomplete ones. It must not map to anything softer. |
| `prospective_from_capture` | `pit_pure` **from the capture date forward only** | before the capture date the leg **does not exist** and is a typed absence, never a back-filled `revision_optimistic` value |
| `rights_blocked` | **no `pit_class` at all** | the leg may not be ingested, so it never becomes a truth row. **Rights gate precedes vintage gate** — an unusable source has no PIT question. |

Adopting this crosswalk requires no schema amendment. Proposing a new CPI enum value would; none is
proposed.

---

## 1. The matrix

`V` = agency page opened directly. `S` = search-summarized, agency page returned 403 or was not
located — treated as a **source claim pending verification**, never as verified.

| # | Series | Owning agency (never FRED) | Canonical access path | Vintage archive? | Revision policy | `source_vintage_class` | Rights verdict |
|---|---|---|---|---|---|---|---|
| 1 | New Residential Sales — sold, for-sale, months supply, median/avg price | Census (w/ HUD) | census.gov/construction/nrs/ ; releases archive `…/nrs/data/releases.html` | **YES** — first-print press-release archive back to **Jan 1995** `V` | preliminary revised in subsequent months; exact month-count **unconfirmed** `S` | `revision_optimistic` (**upgradeable** — see §3) | public domain |
| 2 | New Residential Construction — starts, permits, under construction, completions | Census (w/ HUD) | census.gov/construction/nrc/ | partial — no dedicated release index located `S` | imputed-data replacement; prior-year re-benchmark with the April release `S` | `revision_optimistic` | public domain |
| 3 | Survey of Construction — completion times, characteristics | Census | census.gov/construction/soc/about.html | **no** | inherits NRS/NRC cadence | `current_revised_only` | public domain |
| 4 | Quarterly Starts & Completions by Purpose and Design | Census | census.gov/construction/nrc/quarterly.html | **no** index located | inherits NRC | `revision_optimistic` | public domain |
| 5 | Existing-Home Sales | NAR | nar.realtor/…/existing-home-sales | **no** | periodic deed-record benchmarking; no published window | `current_revised_only` | **RIGHTS-BLOCKED** `V` — see §2 |
| 6 | Housing Affordability Index | NAR | nar.realtor/…/housing-affordability-index | **no** | inherits median-price + rate inputs | `current_revised_only` | **RIGHTS-BLOCKED** — see §2 |
| 7 | NAHB/Wells Fargo Housing Market Index (HMI) | NAHB | nahb.org/…/indices/housing-market-index | press releases only | fresh monthly diffusion index; **no revision policy located** | `pit_pure` **(tentative)** | **UNVERIFIED** — no terms page located `S` |
| 8 | NAHB/Wells Fargo Housing Opportunity Index (HOI) | NAHB | nahbclassic.org legacy archive | legacy only | **DISCONTINUED after Q4 2023**, superseded by the Cost of Housing Index | `current_revised_only`, then `not_applicable` | **UNVERIFIED** (as #7) |
| 9 | Weekly Applications Survey incl. Purchase Index | MBA | mba.org/…/weekly-applications-survey | licensed product | no ex-post revision process located | `current_revised_only` (free layer is headline % change only) | **not_licensed** for the numeric series `S` |
| 10 | Primary Mortgage Market Survey, 30-yr fixed | Freddie Mac | freddiemac.com/pmms ; `…/pmms_archives` | **YES — weekly, back to 1971** `V` | fresh weekly survey print; not revised | **`pit_pure`** | **CONSTRAINED** `V` — see §2 |
| 11 | House Price Index | FHFA | fhfa.gov/data/hpi | **no** distinct vintage product located | open-ended: two-month origination lag "lead to revisions of the index for previous periods" `V` | `revision_optimistic` | freely available |
| 12 | S&P CoreLogic Case-Shiller HPI | S&P Dow Jones Indices | spglobal.com/spdji/… | registration-gated | 3-month moving-average construction | `current_revised_only` | **RIGHTS-BLOCKED** `S` — see §2 |
| 13 | Constant-maturity yields | U.S. Treasury | home.treasury.gov/…/interest-rates ; daily rate archives | **YES — full daily archive** | same-day market snapshot; not revised | **`pit_pure`** | public domain |
| 14 | CPI shelter / owners' equivalent rent | BLS | bls.gov/cpi/ | News-Release PDF archive is the vintage source | SA series carries a rolling ~5-year seasonal-factor revision window `S`; NSA levels not revised | `revision_optimistic` (SA layer) | public domain |
| 15 | Residential fixed investment | BEA | bea.gov NIPA tables 1.1.5 / 5.3.5 | likely, exact path unconfirmed | Advance → Second → Third, plus annual and ~5-yearly benchmark revisions `S` | `revision_optimistic` | public domain |
| 16 | Construction spending (C30) | Census | census.gov/construction/c30/ | monthly PDFs; no index confirmed | **most concretely documented:** two months revised each release; 88 months of seasonal factors refreshed annually; ACES benchmarks in 1992/1994/1998/2003/2008/2012/2017 `V` | `revision_optimistic` | public domain |
| 17 | PPI — lumber and wood products | BLS | data.bls.gov WPU08 family | unconfirmed | commodity PPI typically final at release; **unconfirmed** | `pit_pure` **(provisional)** | public domain |

**Tally:** `pit_pure` **2 confirmed** (#10, #13) + 2 tentative/provisional (#7, #17) ·
`revision_optimistic` **7** · `current_revised_only` **6** · `rights_blocked` **3 sources / 4 series**
(#5, #6, #12, plus #9 not_licensed) · rights **unverified** 2 (#7, #8).

---

## 2. The rights finding — the affordability leg cannot be taken off the shelf

This is the most consequential result in this document and it changes what A4 may build.

**NAR bars storage, not merely redistribution.** Verbatim from `nar.realtor` (`V`):

> "No part of this data may be reproduced, stored in a retrieval system, transmitted or redistributed
> in any form or by any means…without NAR's prior written consent"

"Stored in a retrieval system" is the operative phrase. This is not a redistribution clause that a
private research database escapes — it bars the ingestion itself, the same way FRED's clause (q) does.
**NAR Existing-Home Sales and the NAR Housing Affordability Index are therefore `rights_blocked` for
this program**, and a self-archival lane does not cure it: archiving *is* the prohibited act.

The commission asked for "affordability/rate context from rights-safe canonical sources." The audit's
answer is that **the two most obvious affordability indices are not rights-safe**:

| Off-the-shelf affordability source | Status |
|---|---|
| NAR Housing Affordability Index | `rights_blocked` — storage barred `V` |
| NAHB/Wells Fargo Housing Opportunity Index | **discontinued after Q4 2023**, and NAHB rights unverified |

**Consequence — the affordability construct must be assembled from clean legs, not adopted.** An
affordability measure is a function of price, mortgage rate, and income. Each has a clean underlying
owner:

| Leg | Clean source | Class |
|---|---|---|
| Price | Census New Residential Sales median/average price (#1) | `revision_optimistic`, upgradeable (§3) |
| Rate | **U.S. Treasury constant-maturity yields (#13)** | **`pit_pure`, public domain, full archive** |
| Rate (mortgage-specific) | Freddie Mac PMMS (#10) | `pit_pure` archive back to 1971, but rights-**constrained** — see below |
| Income | Census / BLS income series | public domain |

This is a **house-constructed** affordability context leg, declared as such, and never presented as
"the affordability index". It is also strictly better on PIT grounds than either blocked index, both
of which are `current_revised_only`.

**Freddie Mac PMMS is the ambiguous case and must not be waved through.** Its 1971→present weekly
archive is genuinely `pit_pure` and openly downloadable, and the PMMS page condones attribution-only
use — but the site-wide Terms of Use bar redistributing, publishing, or commercially exploiting "Data"
without a separate written licence (`V`, `freddiemac.com/terms/`). The two statements are in tension.
**Disposition: PMMS is HELD pending a rights determination.** It is not cleared by default, and it is
not blocked by default. Treasury CMT (#13) carries no such ambiguity and is the primary rate leg;
PMMS is a mortgage-spread refinement to be added only if the rights question resolves.

**Rights precedes vintage.** #12 Case-Shiller is the cleanest illustration: whether it is
`current_revised_only` is moot while its redistribution bar stands. It gets no `pit_class` at all
(§0 crosswalk).

---

## 3. The one genuine upgrade available — Census NRS first-print archive

The freeze's rider anticipated that Census NRS would be `revision_optimistic` because the mandated
FRED replacement removes ALFRED-style vintage access. That is correct *as the series is normally
consumed*, but the audit found a mitigation the rider flagged only in passing:

> Census maintains a first-print press-release archive back to **January 1995** (text 1995–2000,
> PDF 2001+) `V` — `census.gov/construction/nrs/data/releases.html`

Each monthly release **is** the vintage artifact. Parsing that archive reconstructs a genuine
point-in-time NRS series covering the entire 2005–2026 study window — no self-archival lane needed,
no rights obstacle (public domain).

**Disposition:** NRS is declared `revision_optimistic` **today**, as the rider requires, with a
recorded and costed upgrade path to `pit_pure` via the release archive. A4 may register that upgrade
as an explicit, scoped task. Until it is executed, the `revision_optimistic` declaration and its
disclosure obligation stand — **the availability of an upgrade is not the upgrade.**

---

## 4. What every homebuilder readout must disclose

Binding until each condition is cleared:

1. **Macro/context legs are `revision_optimistic` unless individually named otherwise.** Only
   Treasury CMT (#13) is confirmed `pit_pure`, public-domain, and archive-complete.
2. **No NAR series may be stored or used.** Not Existing-Home Sales, not the Affordability Index.
3. **No Case-Shiller series may be stored or redistributed** absent an S&P DJI licence.
4. **The affordability leg is a house construction** from Census price + Treasury rate + Census/BLS
   income — never "the NAR/NAHB affordability index".
5. **Freddie Mac PMMS is HELD** pending a rights determination; Treasury CMT is the primary rate leg.
6. **NAHB is unverified, not cleared.** HMI's tentative `pit_pure` rests on an unlocated revision
   policy and an unlocated terms page. It may not be used until both are opened directly.

---

## 5. Gaps — what is not verified, and what would verify it

Six load-bearing claims rest on search summaries because the agency page returned HTTP 403 or was not
located. These are **not** verified and are flagged in place above.

| Gap | What would verify it |
|---|---|
| NAHB terms of use — no working page located (guess 404'd) | Open the nahb.org footer Terms of Use via a browser session or sitemap |
| NAHB HMI revision policy — "not revised" is inferred from the diffusion-index pattern | Open the HMI methodology PDF and check for a restatement clause |
| MBA licence language — mba.org 403'd | Retry from an unrestricted path, or request the subscription terms PDF |
| S&P DJI redistribution bar — canonical governance page 403'd; quote came from a third-party-hosted PDF | Re-open `spglobal.com/spdji/en/governance/terms-of-use/` directly |
| BLS CPI 5-year seasonal-factor window — FAQ page 403'd | Open the CPI Handbook of Methods revisions chapter |
| **Census NRS exact revision window** — the freeze's rider states "three subsequent months plus annual benchmarking"; only general "subsequent months" language was confirmed | Open the NRS Reliability of Estimates / technical documentation PDF and extract the month count |
| FHFA HPI — whether a true vintage archive exists apart from the current-revised dataset | Check `fhfa.gov/data/hpi/datasets` for dated file series |
| BEA RFI vintage-table path outside FRED/ALFRED | Open BEA's archived NIPA release tables directly |
| BLS PPI lumber revision policy — `pit_pure` is provisional | Open the bls.gov/ppi technical notes revision section |

**Note on the last-but-one row.** The freeze's own rider asserted a specific NRS revision window
("three subsequent months plus annual benchmarking"). This audit could not confirm that figure against
a page-opened Census source. The rider's *conclusion* — NRS is `revision_optimistic` — is unaffected
and is adopted. Its *stated mechanism* is carried forward as unverified rather than repeated as fact.

---

## 6. Falsifiers

| # | Falsifier | Effect if true |
|---|---|---|
| F-1 | NAR grants written consent, or the quoted storage bar is superseded. | #5/#6 leave `rights_blocked`; the NAR affordability index becomes usable. |
| F-2 | Freddie Mac's terms are determined to permit internal research storage. | PMMS becomes a confirmed `pit_pure` mortgage-rate leg back to 1971. |
| F-3 | The Census NRS release archive proves incomplete or unparseable for 2005–2026. | The §3 upgrade path closes; NRS stays `revision_optimistic` permanently. |
| F-4 | NAHB's terms are located and permit use, and HMI is confirmed non-revised. | HMI's tentative `pit_pure` is confirmed and a sentiment leg opens. |
| F-5 | FHFA or BEA is found to publish a true vintage archive. | Those legs upgrade from `revision_optimistic`. |

None of these changes the §4 disclosure obligation for any leg not individually cleared.

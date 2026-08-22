---
key: NAR-TERMS-BAR-STORAGE-NOT-ONLY-REDISTRIBUTION
claim: >
  National Association of REALTORS data (Existing-Home Sales, Housing Affordability Index)
  may not be STORED, not merely not redistributed. The operative language on nar.realtor
  is that no part of the data may be "reproduced, stored in a retrieval system, transmitted
  or redistributed in any form or by any means...without NAR's prior written consent" -
  "stored in a retrieval system" bars the ingestion itself, the same structural prohibition
  as FRED's clause (q), so a private internal research database is NOT an escape and a
  self-archival lane does not cure it because archiving IS the prohibited act. Adjacent
  audit findings: S&P CoreLogic Case-Shiller bars redistribution without express S&P DJI
  consent; MBA's full Weekly Applications numeric series is paywalled under a single-user
  licence; Freddie Mac PMMS is openly archived to 1971 but its site Terms of Use still bar
  redistributing "Data" without a written licence (ambiguous, HELD); NAHB's terms page could
  not be located at all, so NAHB is UNVERIFIED, not cleared.
falsifier: >
  Open nar.realtor/research-and-statistics/housing-statistics/existing-home-sales and find
  the quoted restriction absent, narrowed to redistribution only, or superseded. Or obtain
  written consent from NAR, which by its own terms lifts the bar.
so_what: >
  Do not plan any housing/affordability context leg around NAR or Case-Shiller series -
  the rights gate precedes the vintage gate, and a rights-blocked source never reaches a
  pit_class question at all. Build an affordability construct from clean underlying legs
  instead (Census New Residential Sales price + U.S. Treasury constant-maturity yields +
  Census/BLS income) and declare it as a house construction, never as "the affordability
  index". Treasury CMT is the only leg in the 17-series audit confirmed pit_pure,
  public-domain AND archive-complete, so it is the default rate leg; PMMS is a
  mortgage-spread refinement to add only if its rights ambiguity resolves.
kind: constraint
verified_at: 2026-08-21
verified_by: "research/imce/hb0/evidence/L7_source_pit_vintage.md rows 5,6,10,12; nar.realtor terms opened directly"
scope:
  - macro
  - research/imce/
  - engine/cycle_pattern/
confidence: verified
---

# NAR bars storage, not only redistribution

Rights verdicts from the 17-series HB-0 vintage audit, for the five commonly-reached
housing/affordability sources:

| Source | Verdict | Basis |
|---|---|---|
| **NAR** (Existing-Home Sales, Affordability Index) | **rights_blocked for storage** | quoted terms, page opened directly |
| **S&P CoreLogic Case-Shiller** | rights_blocked without licence | source claim; canonical S&P DJI terms page returned 403 |
| **MBA** Weekly Applications (numeric series) | not_licensed | source claim; mba.org returned 403 |
| **Freddie Mac PMMS** | **HELD** - archive open to 1971, but site terms bar redistributing "Data" | terms page opened directly |
| **NAHB** (HMI, HOI/CHI) | **UNVERIFIED, not cleared** | no working terms page located |

The pattern worth carrying: a trade association's "free" data page and its terms page
frequently disagree, and the terms page wins. Check the terms page before designing a leg
around a series, not after.

Rights gate precedes vintage gate: an unusable source has no PIT question, so it gets no
`pit_class` at all. Full matrix and the vintage-vocabulary adjudication:
`research/imce/hb0/IMCE_HB0_SOURCE_PIT_VINTAGE_MATRIX.md`.

Related: [[failing-issuers-stop-filing-before-collapse]].

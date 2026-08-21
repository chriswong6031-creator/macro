---
key: HOMEBUILDER-CANCELLATION-DENOMINATORS-ALL-DIVERGE
claim: >
  The six IMCE homebuilder issuers have six mutually incompatible cancellation-rate
  disclosure regimes and no two share a denominator. DHI states "cancelled sales orders
  divided by gross sales orders" in both 10-K and press release; PHM states "canceled orders
  for the period divided by gross new orders for the period" (confirmed FY2016+); NVR states
  a gross-sales denominator AND separately discloses a second opening-backlog measure
  alongside it; KBH footnotes a gross-orders formula (FY2008+) but its FY2008 10-K
  contradicts itself, using "based on net orders" in narrative and "based on gross orders"
  in a segment-table caption in the same filing; TOL publishes NO cancellation rate or
  formula in its 10-K at all and instead prints TWO rates side by side in the quarterly press
  release (percent of beginning-quarter backlog AND percent of signed contracts in quarter,
  2.8% vs 5.4% in Q1 FY2026); LEN discloses a bare 14% in its 10-K MD&A with no formula
  anywhere and omits the rate entirely from its press releases. Critically the stated formulas
  are a LATE-ERA artifact - PHM and NVR only from FY2016, KBH from FY2008 - so the 2006-2013
  blocks have no verifiable denominator for most of the roster.
falsifier: >
  Full-text search PHM or NVR 10-Ks for fiscal years 2006-2015 (efts.sec.gov, forms=10-K)
  for "divided by" or "percentage of gross sales" and find the formula sentence present
  earlier than FY2016; or find any Lennar filing stating a cancellation-rate formula; or
  find a KBH filing after FY2008 that resolves the net-vs-gross contradiction.
so_what: >
  Never build a single cross-issuer "cancellation rate" column for this cohort - it would
  silently mix a ratio to gross orders, a ratio to gross sales, a ratio to opening backlog,
  a press-release-only dual measure, and one number whose denominator nobody has stated.
  Freeze ONE canonical denominator per issuer with a printed conversion, elect between TOL's
  two published rates explicitly, and exclude LEN because nothing is freezable rather than
  because the rate is "missing" (it is disclosed, just undefined). NVR and TOL publish both
  conventions themselves, so the mandated alternate-convention sensitivity re-run is directly
  executable for those two instead of requiring reconstruction. Restrict any cancellation
  cell to blocks 3-5; the GFC bust and recovery blocks are not denominator-verifiable.
kind: data
verified_at: 2026-08-21
verified_by: "research/imce/hb0/evidence/L2_defs_DHI_LEN.md, L3_defs_PHM_NVR.md, L4_defs_KBH_TOL.md; FY2024/FY2025 10-Ks and 8-K EX-99.1 per issuer"
scope:
  - macro
  - research/imce/
  - cycle-pattern-issuer-mechanism
confidence: verified
---

# Six homebuilders, six cancellation-rate regimes

| Issuer | Where | Formula stated? | Denominator |
|---|---|---|---|
| DHI | 10-K + press release | yes | gross orders in period |
| PHM | 10-K (FY2016+) | yes | gross new orders in period |
| NVR | 10-K (FY2016+) | yes, **plus a second backlog-based measure** | gross sales; opening backlog |
| KBH | 10-K, footnoted (FY2008+) | yes, but **self-contradictory in FY2008** | gross orders |
| TOL | **press release only** | two rates simultaneously | beginning-quarter backlog AND signed contracts in quarter |
| LEN | 10-K MD&A only, bare 14% | **no** | **unknown** |

This is the concrete case for the house rule "build a denominator crosswalk, not a false
standardized column." The metric most diagnostic of homebuilder demand stress is the one
where cross-issuer comparability is weakest, and the incomparability is invisible in any
data vendor's normalized field.

The era finding compounds it: stated denominators appear FY2008-FY2016 depending on issuer,
so the two most mechanism-informative episodes in the window - the GFC bust and recovery -
are exactly where the denominators are unverifiable. Treating the later stated convention as
retroactively true is an assumption, not a reading.

Full crosswalk including 14 named cross-issuer incompatibilities:
`research/imce/hb0/IMCE_HB0_METRIC_DEFINITION_CROSSWALK.md`.

Related: [[edgar-structured-issuer-metadata-is-untrustworthy]].

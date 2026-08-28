---
key: FAILING-ISSUERS-STOP-FILING-BEFORE-COLLAPSE
claim: >
  Survivorship bias in a public-issuer panel has a SECOND form that adding the dead
  companies back does not fix: a failing issuer stops filing before its terminal annual
  report, so its collapse period is absent from EDGAR entirely. Measured on the 2006-2011
  homebuilder mortality event: TOUSA's last annual period is 2007-12-31 and it filed
  Chapter 11 on 2008-01-29 with NO FY2008 10-K ever filed; Orleans Homebuilders' last
  annual period is 2008-06-30 against a 2010-03-01 Chapter 11 with NO FY2009 10-K;
  Dominion Homes' filings stop mid-2008 while its reported wind-down runs to ~2013. A
  "survivorship-corrected" panel built from EDGAR therefore contains the dead firms'
  HEALTHY years and loses their DYING years, so it understates distress in the SAME
  direction as excluding them outright.
falsifier: >
  Open data.sec.gov/submissions/CIK0001046578.json (TOUSA), CIK0000038570.json (Orleans)
  or CIK0000917857.json (Dominion Homes) and find a 10-K whose reportDate covers the
  fiscal year of or after the terminal event. Alternatively, locate terminal-year
  financials for any of the three in a non-EDGAR source (bankruptcy court, state records),
  which would make the correction constructible from outside EDGAR.
so_what: >
  Never describe an issuer panel as "survivorship-corrected" merely because delisted names
  were added back - the correction is partial by construction and the residual bias runs
  the same direction as the original. Any trough-severity, cross-issuer dispersion, or
  cohort-mean claim over a mortality window must disclose the terminal-year censoring
  separately from the roster-exclusion problem. Budget non-EDGAR sourcing (bankruptcy
  dockets) if terminal-period detail is actually required, and expect the identity and
  timeline to be reconstructible when the financials are not.
kind: landmine
verified_at: 2026-08-21
verified_by: "research/imce/hb0/evidence/L1_cohort_survivorship.md Part 2; EDGAR submissions JSON per CIK"
scope:
  - macro
  - research/imce/
  - cycle-pattern-issuer-mechanism
confidence: verified
---

# Failing issuers stop filing before the collapse year

The obvious survivorship problem is "the dead are missing from the roster." This record is
about the second one, which no roster change fixes.

| Entity | CIK | Last annual period on EDGAR | Terminal event | Missing |
|---|---|---|---|---|
| TOUSA | 1046578 | 2007-12-31 | Chapter 11, 2008-01-29 | **FY2008 10-K never filed** |
| Orleans Homebuilders | 38570 | 2008-06-30 | Chapter 11, 2010-03-01 | **FY2009 10-K never filed** |
| Dominion Homes | 917857 | filings stop mid-2008 | wind-down ~2013 | ~5 years `not_reconstructable` |

Companies stop reporting exactly when the collapse they are undergoing becomes the
interesting observation. The mechanism is mundane - a company in Chapter 11 has neither
the obligation nor the resources to complete an audit - which is why it recurs and why it
should be assumed present in any mortality window rather than discovered per-study.

Consequence: identity and timeline are reconstructible for most dead issuers (14 of 16 in
the homebuilder census); terminal-year OPERATING DETAIL is not, for at least the
bankruptcy cases. Those are different availability questions and a census must answer them
separately.

Related: [[nar-terms-bar-storage]] is a different constraint on the same census;
`research/imce/hb0/IMCE_HB0_SURVIVORSHIP_CENSUS.md` §3 carries the full treatment.

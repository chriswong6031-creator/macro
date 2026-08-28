---
key: EDGAR-STRUCTURED-ISSUER-METADATA-IS-UNTRUSTWORTHY
claim: >
  EDGAR's structured issuer metadata cannot be trusted without opening the underlying
  document, and two distinct failure modes were measured on the homebuilder roster.
  (1) CORRUPTED PERIOD-OF-REPORT: Lennar's FY2005 10-K (accession 0001193125-06-025438)
  carries reportDate 2005-01-30 in EDGAR metadata while the document's own cover page reads
  "For the fiscal year ended November 30, 2005" - a pipeline keyed on raw reportDate
  mis-keys a full fiscal year by ten months. (2) FORM 15 SCOPE: a Form 15 deregisters a
  SECURITY CLASS, not necessarily a REGISTRANT - Hovnanian filed a Form 15-12G on
  2021-11-04 and has filed 10-Ks, 10-Qs and 8-Ks continuously through 2026, and MDC
  Holdings' equity was acquired 2024-04-19 with two Form 15s on record while the registrant
  keeps filing under a public-debt Section 15(d) obligation.
falsifier: >
  Open sec.gov/Archives/edgar/data/920760/000119312506025438/d10k.htm and find a cover page
  agreeing with the 2005-01-30 reportDate. Or open data.sec.gov/submissions/CIK0000357294.json
  (Hovnanian) or CIK0000773141.json (MDC/Sekisui House) and find filing activity ending at
  the Form 15 date.
so_what: >
  Sanity-check reportDate against the issuer's known fiscal-year-end month before keying any
  time series on it, and reconcile against the cover page when the month disagrees - a
  silent ten-month mis-key inside a crisis window is the failure this prevents. Never treat
  a Form 15 as an issuer terminal event: resolve which security class it covers and check
  whether filing activity actually stopped, because equity termination and registrant
  termination are different dates and the gap can run years. For any market-recognition
  construct the equity date governs; for an operating-mechanism construct the filing series
  governs.
kind: landmine
verified_at: 2026-08-21
verified_by: "research/imce/hb0/evidence/L5_fiscal_calendar_clocks.md gaps table; L1_cohort_survivorship.md Part 2 row 16, Part 4"
scope:
  - macro
  - research/imce/
  - engine/institutional_census/
confidence: verified
---

# EDGAR structured issuer metadata is untrustworthy

Two independent failure modes, both measured on the six-name homebuilder roster during
IMCE-HB-0, both of which would corrupt an automated ingest silently.

**1. Corrupted period-of-report.** One filing in ~500 examined carried a reportDate ten
months off its own cover page. The tell is cheap: Lennar's fiscal year ends November 30, so
a reportDate in January is impossible on its face. A month-vs-known-FYE assertion catches
this class without opening any document.

**2. Form 15 scope.** Both Hovnanian and MDC Holdings have Form 15s on record and both are
still filing. A Form 15 answers "did a security class deregister", never "did this issuer
stop existing". The homebuilder census resolved MDC by clock: operating clock continuous to
the present, recognition clock ends at the 2024-04-19 equity acquisition.

The general lesson is that EDGAR's structured fields are a convenience index over documents,
not an authority about them. They are excellent for bulk discovery - one submissions JSON
per issuer yields form types, periods and filing dates for the entire history - and must be
validated at the point where a value becomes load-bearing.

Related: [[failing-issuers-stop-filing-before-collapse]] is the availability question;
this record is the metadata-accuracy question.

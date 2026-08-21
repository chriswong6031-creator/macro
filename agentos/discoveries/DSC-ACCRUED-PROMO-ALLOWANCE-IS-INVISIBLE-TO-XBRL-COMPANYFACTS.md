---
key: ACCRUED-PROMO-ALLOWANCE-IS-INVISIBLE-TO-XBRL-COMPANYFACTS
claim: >
  The SEC XBRL `companyfacts` API is NOT a complete read of a filed balance sheet, and
  the gap is not random - it falls on issuer-custom line items, which for a consumer
  brand is exactly where trade/promotional investment lives. For CELH (CIK 0001341766)
  the `companyfacts` payload exposes only the `dei`, `us-gaap`, `srt` and `ecd`
  namespaces; no `celh` custom namespace is published. The "Accrued promotional
  allowance" line - which runs 99.787 -> 453.043 USD millions between 2023-12-31 and
  2026-06-30, reaching 55.4% of quarterly revenue - is therefore absent from the API
  while being plainly present in every filed balance sheet. The nearest us-gaap concept
  that IS exposed, `AccruedMarketingCostsCurrent`, is a DIFFERENT and much smaller line
  (72.8M at 2025-12-31 against 307.9M for the promotional allowance) and silently
  substituting it understates the field by ~4x. A second, related trap: CELH tags
  `us-gaap:SellingAndMarketingExpense` for exactly three quarters (2022 Q1-Q3) and never
  again, so a same-name expense series built from the API breaks at 2022-09-30 with no
  error. CELH also tags no standalone Q4 duration fact - Q4 must be derived as FY minus
  Q1..Q3, which moves its honest `available_at` to the 10-K filing date.
falsifier: >
  `curl -H "User-Agent: <org> <contact>" https://data.sec.gov/api/xbrl/companyfacts/CIK0001341766.json`
  then `python3 -c "import json;d=json.load(open(...));print(list(d['facts']))"` - if a
  `celh` namespace appears, or if any exposed concept reproduces the 453.043M value at
  2026-06-30, the claim is broken. Cross-check the true values against the EX-99.1
  balance sheet in accession 0001341766-26-000047.
so_what: >
  Any issuer-mechanism pipeline that sources accounting facts from `companyfacts` alone
  will silently miss the trade-investment stock - the single best-performing
  under-instrumented sensor found in the CELH autopsy, and the one that stepped up
  BEFORE the reported brand decline. Capture plans must include statement-level parsing
  of the 10-Q/10-K or the EX-99.1 press-release balance sheet for custom lines, and must
  record the concept name actually used per issuer rather than assuming a us-gaap tag.
  Never substitute a same-sounding us-gaap concept for a missing custom line: type it
  `not_available_for_date` and parse the statement. Check namespace coverage per issuer
  before promising a field in any census or contract - coverage is an issuer-by-issuer
  fact, not a property of the API.
kind: data
verified_at: 2026-08-21
verified_by: >
  https://data.sec.gov/api/xbrl/companyfacts/CIK0001341766.json (namespaces observed:
  dei, us-gaap, srt, ecd); EX-99.1 balance sheets in accessions 0001341766-24-000031,
  0001341766-24-000095, 0001341766-25-000018, 0001341766-25-000099,
  0001341766-26-000017, 0001341766-26-000047; ledger rows S005/S006/S004 in
  research/imce/celh/celh_source_rights_missingness.csv; full first-disclosure ledger in
  research/imce/celh/celh_xbrl_original_disclosures.csv (655 rows, 60 flagged restated).
scope:
  - macro
  - research/imce/
  - WS:CYCLE-PATTERN-ISSUER-MECHANISM
confidence: verified
---

# Scope note

The CELH-specific values are verified. The GENERAL claim — that `companyfacts` omits
issuer-custom lines — follows from how the API is built (it serves the filer's own
taxonomy extensions only when the filer publishes them) and should be treated as a
standing check to run per issuer, not as an assumption that every issuer has the same
hole.

Related: [[DSC-ISSUER-EPOCH-BOUNDARY-LAG-SPLITS-BY-BOUNDARY-CLASS]].
Parent: `DEC:CPI-ISSUER-MECHANISM-RESEARCH-EXTENSION-NOT-NEW-ENGINE`.

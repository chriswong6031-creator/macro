---
key: XBRL-DUPLICATE-LAW-IS-INTRA-INSTANCE
claim: >
  XBRL 2.1 section 4.10 defines duplicate items only when they are P-Equal
  (children of the identical parent) as well as C-Equal and U-Equal, so the
  duplicate/accuracy predicate cannot relate facts in two separate SEC
  instance documents.
falsifier: >
  Open the XBRL 2.1 rec+errata 2013-02-20 section 4.10 duplicate-item row and
  find a definition that omits P-Equal or that explicitly binds facts across
  instance documents.
so_what: >
  Do not cite within-document duplicate guidance, EDGAR Guide section 9.10, or
  _duplicates_agree as proof that a later 10-Q revises a 10-K. Cross-filing
  equality is a Mastermind lineage-evidence interpretation, default NO_RELATION.
kind: constraint
verified_at: 2026-08-24
verified_by: >
  Opened XBRL 2.1 rec+errata 2013-02-20 section 4.10 this session; duplicate
  item row requires P-Equal, C-Equal, and U-Equal. Opened EDGAR XBRL Guide
  August 2026 section 9.10, which scopes consistency to an instance.
scope:
  - macro
  - engine/fundamental_forensics/raw_ledger.py
  - engine/fundamental_forensics/query.py
  - research/financial_intelligence_fabric/FIF_3A4R_CROSS_FILING_LINEAGE_PROTOCOL.md
  - WS:FINANCIAL-INTELLIGENCE-FABRIC
confidence: verified
---

Within-document consistency remains the job of `_duplicates_agree`.
Cross-filing confirmation is not that job.

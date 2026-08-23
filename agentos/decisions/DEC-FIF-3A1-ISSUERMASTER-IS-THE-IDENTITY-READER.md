---
key: FIF-3A1-ISSUERMASTER-IS-THE-IDENTITY-READER
question: >
  May FIF-3A1 independently pick a security for an issuer from raw
  issuer/security tables, or must it use the canonical Data OS reader?
answer: >
  Use lib.dataos.identity.IssuerMaster for current issuer→security
  membership. Raw issuer/security tables may supply metadata only after
  IssuerMaster.securities_of_issuer returns the active roster.
  SUPERSEDED_DUPLICATE_MINT rows are not current membership.
rationale: >
  Sol REQUEST_CHANGES on PR #6268 head
  c0ced14a4270f73b0d62bc986851f9fbe0e9e217. Data OS already owns current
  membership, including exclusion of superseded duplicate mints. An
  independent FIF first-row or parquet filter would revive a tombstone
  as a live listing.
alternatives:
  - option: Keep FIF's independent parquet issuer/security join
    why_not: It reimplements membership and can select SUPERSEDED_DUPLICATE_MINT.
  - option: Treat listing_key uniqueness as identity
    why_not: Duplicate mints can share an issuer; state, not key order, is canonical.
evidence:
  - "lib/dataos/identity.py IssuerMaster.securities_of_issuer excludes security_state tombstones"
  - "tests/fixtures/fundamental_forensics/issuer_master_adversarial_duplicate_mint.json lists DUP first"
  - "tests/test_fundamental_forensics_financial_statement_service.py::test_issuer_master_selects_active_membership_not_superseded_duplicate"
affects:
  - WS:FINANCIAL-INTELLIGENCE-FABRIC
  - engine/fundamental_forensics/statement_service.py
  - lib/dataos/identity.py
confidence: high
reversibility: costly
decided_by: ceo-sol
decided_at: 2026-08-23
---

FIF-3A1 identity binding is a reader of IssuerMaster, not a second allocator.

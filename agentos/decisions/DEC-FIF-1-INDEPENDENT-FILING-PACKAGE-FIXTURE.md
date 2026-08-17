---
key: FIF-1-INDEPENDENT-FILING-PACKAGE-FIXTURE
question: >
  How may FIF-1 obtain governed metric cells that prove the 1050/1060 temporal
  laws without using Company Facts rows as if they were filing-package facts?
answer: >
  Create an independent, explicitly synthetic, canonical raw-ledger fixture of
  filing-package-authoritative facts (source=sec-edgar, dimensions_known=true,
  typed restatement lineage constructed at birth). Keep
  tests/fixtures/fundamental_forensics/companyfacts_versions.json as a separate
  occurrence-inventory witness. Never manufacture the filing-authority fixture
  by flipping dimensions_known or injecting revision_of onto Company Facts rows.
rationale: >
  DSC:COMPANYFACTS-CANNOT-FEED-CORE-METRIC-QUERY showed the core catalog
  refuses Company Facts rows as unknown_dimension_scope. Mutating those rows
  into consolidated facts would launder an occurrence inventory into a filing
  package and hide the seam the kernel exists to preserve. An independent
  synthetic ledger can still prove the same numeric/temporal laws through the
  existing query kernel without a second semantic model.
alternatives:
  - option: Flip dimensions_known=true on converted Company Facts rows
    why_not: Operator-forbidden. It would claim consolidated filing-package
      authority the Company Facts conversion deliberately withholds.
  - option: Inject revision_of onto converted Company Facts rows
    why_not: Operator-forbidden. Typed lineage must be born with the filing
      package fixture, not inferred from later accessions.
  - option: Monkeypatch _fact_dimensions_allowed in the packet builder
    why_not: Work-around of the kernel safety fence; same as B4's test-local
      overlay, illegal as a product adapter.
  - option: Relabel attested_occurrence as revenue
    why_not: GovernanceBundle validation hard-fails that relabel.
evidence:
  - DSC:COMPANYFACTS-CANNOT-FEED-CORE-METRIC-QUERY
  - operator instruction 2026-08-16: independent synthetic filing-package fixture; Company Facts remains a separate witness
  - tests/test_fundamental_forensics_attested_occurrence_governance.py::test_evidence_bundle_selects_unknown_dimensions_but_core_rejects_them
affects:
  - WS:FINANCIAL-INTELLIGENCE-FABRIC
  - tests/fixtures/fundamental_forensics/
  - engine/fundamental_forensics/financial_intelligence_packet.py
confidence: high
reversibility: easy
decided_by: chairman
decided_at: 2026-08-16
---

FIF-1 code consumes the new filing-package fixture as the query-authoritative
ledger. The Company Facts fixture may appear only as a hashed inventory
witness in packet receipts. It is not a query input.

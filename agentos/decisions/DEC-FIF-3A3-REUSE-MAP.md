---
key: FIF-3A3-REUSE-MAP
question: >
  How must FIF-3A3 convert accepted AAPL iXBRL occurrences into the
  canonical RawFactLedger and activate the existing financial query
  route without creating a second kernel?
answer: >
  One deterministic parser-result adapter in
  engine/fundamental_forensics/ixbrl_raw_ledger.py consumes
  parse_sec_filing_document output plus admitted golden package
  metadata. Reuse TAXONOMY_NAMESPACE_POLICY for US GAAP/DEI QNames,
  UNIT_POLICY for USD/shares/pure, sec_document_id for primary-document
  identity, RawFactLedger as the occurrence kernel, and
  BitemporalMetricQueryEngine as the resolver. Activate only
  GoldenAaplFinancialQueryProvider on POST /api/forensics/v1/financial/query.
  Optional delivery metadata on FinancialQueryDataset stays absent for FIP1.
rationale: >
  A1/A2 proved as-reported statement truth. FIF-2 proved governed query
  against synthetic facts. Those were parallel islands. A3 closes the
  gap by converting every representable numeric iXBRL occurrence from
  the accepted golden bytes into the existing ledger rather than
  reconstructing query logic beside the statement path.
alternatives:
  - option: Patch query.py to accept Clark-notation concept QNames
    why_not: Sol forbade widening the kernel unless archaeology proved an unavoidable contract defect. TAXONOMY_NAMESPACE_POLICY already exists.
  - option: Convert only statement totals needed to green tests
    why_not: A core-relevant numeric source fact may not disappear without a typed exclusion.
  - option: Infer us-gaap from a local name or treat the 10-Q as revision_of the 10-K
    why_not: Custom namespaces must remain ungoverned. Duplicate roots without typed lineage must stay NOT_EVALUABLE.
evidence:
  - "engine/fundamental_forensics/filing_attestation.py TAXONOMY_NAMESPACE_POLICY maps fasb.org/us-gaap/2009-2026 and xbrl.sec.gov/dei/2009-2026"
  - "sec_document_id exports stable_id('sec_document', cik, accession, role, name)"
  - "research/financial_intelligence_fabric/FIF_3A3_REUSE_MAP.md"
affects:
  - WS:FINANCIAL-INTELLIGENCE-FABRIC
  - engine/fundamental_forensics/ixbrl_raw_ledger.py
  - engine/fundamental_forensics/query_service.py
  - app/forensics.py
confidence: high
reversibility: costly
decided_by: coo-fable
decided_at: 2026-08-23
---

FIF-3A3 reuses the frozen FIF-1/FIF-2 kernels and accepted A1/A2 golden
bytes. It does not mint a second ledger, registry, query kernel, or API.

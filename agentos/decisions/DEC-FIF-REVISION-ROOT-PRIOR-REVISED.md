---
key: FIF-REVISION-ROOT-PRIOR-REVISED
question: >
  What vocabulary should financial_intelligence_packet.v1 use for multi-hop
  reported-revision rows?
answer: >
  Separate lineage root from immediate predecessor. Each hop stores
  root_value/root_accession/root_occurrence_id, prior_value/prior_accession/
  parent_occurrence_id, and revised_value/revised_accession/
  revised_occurrence_id. Deltas are prior → revised. uses_later_restatement
  is renamed uses_later_reported_revision to cover amendment, comparative
  recast, restatement, source correction, and withdrawal.
rationale: >
  FIF-1R2 mixed parent parsed_value into original_value while original_*
  identity fields pointed at the lineage root. A hop-2 row could say
  original_value=1060 with original_accession of the 1050 filing. That
  violates source-reversibility. v1 is not frozen, so the names are changed
  now rather than carried forever.
alternatives:
  - option: Keep original_* exclusively for root and compute deltas from root
    why_not: >
      Absolute/relative delta from an immediate predecessor is the useful
      hop-local change; root identity is still stored separately.
  - option: Keep uses_later_restatement
    why_not: The extractor already emits amendment, recast, correction, and
      withdrawal, not merely restatements.
evidence:
  - Sol FIF-1R2 source review 2026-08-18: blocker 2
  - tests/test_fundamental_forensics_financial_intelligence_packet_r3.py::test_multihop_revision_separates_root_prior_and_revised
affects:
  - WS:FINANCIAL-INTELLIGENCE-FABRIC
  - contracts/financial_intelligence_packet.schema.json
  - engine/fundamental_forensics/financial_intelligence_packet.py
confidence: high
reversibility: costly
decided_by: ceo-sol
decided_at: 2026-08-18
---

Revision rows now name root, prior, and revised as distinct source nodes.
Lineage IDs run root through current. The flag follows the query kernel's
reported-revision vocabulary rather than restatement-only naming.

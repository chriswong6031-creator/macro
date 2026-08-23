---
key: FIF-3A1-AUTHORITY-IS-CONTEXT-ONLY-OBJECT
question: >
  Which authority vocabulary may the FIF-3A1 statement response use?
answer: >
  Reuse the canonical FIF object authority={"class":"context_only","display_only":true}
  at the top level. Remove delivery.authority. delivery remains only
  source/promotion truth: committed golden fixture, attested=false,
  production_issuer_service=false. No second authority vocabulary.
rationale: >
  Sol REQUEST_CHANGES on PR #6268. delivery.authority="context_display_only"
  invented a string that the rest of FIF does not use. Query and packet
  envelopes already carry the object form.
alternatives:
  - option: Keep delivery.authority as a display-only string
    why_not: That is a second vocabulary beside context_only/display_only.
evidence:
  - "engine/fundamental_forensics/query_service.py authority object"
  - "engine/fundamental_forensics/financial_intelligence_packet.py packet authority must remain context_only/display_only"
affects:
  - WS:FINANCIAL-INTELLIGENCE-FABRIC
  - engine/fundamental_forensics/statement_service.py
  - contracts/statement_cell.v1.md
confidence: high
reversibility: easy
decided_by: ceo-sol
decided_at: 2026-08-23
---

One authority object. Delivery does not restate it.

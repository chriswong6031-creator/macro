---
key: FIF-ENTITY-ID-IS-NOT-CIK
question: >
  Before freezing financial_intelligence_packet.v1, must Mastermind
  entity_id equal the SEC CIK?
answer: >
  No. entity_id is canonical issuer identity; cik is the SEC identifier.
  They may be equal in synthetic FIP1, but equality is not contract law.
  FIF-1R3 removes the EntityInput equality constraint introduced in FIF-1R2.
  Source Registry is not built in this wave.
rationale: >
  Sol's source review of merged #5837 found that FIF-1R2 accidentally froze
  entity_id == cik because the synthetic fixture used CIK for both. The FIF
  masterplan treats issuer identity and CIK as different dimensions so later
  waves can represent ticker changes, ADRs, multiple listed securities, LEIs,
  mergers, and non-US filings. Making CIK the forever internal issuer ID would
  be a product architecture freeze, not a fixture convenience.
alternatives:
  - option: Keep entity_id == cik as packet-contract law
    why_not: >
      It silently makes an SEC identifier Mastermind's canonical issuer ID.
      The masterplan already anticipates a separate identity plane.
  - option: Build Source Registry in FIF-1R3
    why_not: Sol explicitly scoped R3 to remove the equality constraint, not
      to land the identity plane.
  - option: Defer the question until after v1 freeze
    why_not: Frozen packet field semantics are costly to rename later.
evidence:
  - Sol FIF-1R2 source review 2026-08-18: blocker 3, entity_id == cik
  - engine/fundamental_forensics/financial_intelligence_packet.py EntityInput
  - tests/test_fundamental_forensics_financial_intelligence_packet_r3.py::test_entity_id_need_not_equal_cik_and_does_not_leak
affects:
  - WS:FINANCIAL-INTELLIGENCE-FABRIC
  - engine/fundamental_forensics/financial_intelligence_packet.py
  - contracts/financial_intelligence_packet.schema.json
confidence: high
reversibility: costly
decided_by: ceo-sol
decided_at: 2026-08-18
---

Canonical issuer identity and CIK stay independent packet fields. Synthetic
FIP1 may still set them equal. Isolation continues to key on entity_id, so a
CIK-only occurrence is foreign to a non-CIK canonical entity.

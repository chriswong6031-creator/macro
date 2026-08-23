---
key: FIF-3A2-RELATED-EVENT-REF-OMITS-GENERATION
question: >
  How may FIF statements reference the existing AAPL FY2026 Q3 Earnings
  event without copying the workspace or minting generation identity?
answer: >
  Optional top-level related_event_ref with plane, event_id, relation
  same_fiscal_results_period, and source_filing_distinction between
  8-K 0000320193-26-000018 and 10-Q 0000320193-26-000020. Omit the key
  entirely when the golden package has no event (A1 10-K). Never include
  generation_id. Never copy Revenue, guidance, transcript, or Q&A.
  Request path stays offline; acceptance tests may call read_event_workspace.
rationale: >
  Live generation moved from f709a0a6ec514282d5769e7d to
  d7b994675fe59d0181643b8b while event_id stayed constant. Statement bytes
  must not change when Earnings republishes.
alternatives:
  - option: Reuse market_memory source_event_ref
    why_not: That contract is pre-decision replay geometry, not a filing↔event pointer.
  - option: Store generation_id as truth
    why_not: Sol forbade minting a second generation as statement identity.
evidence:
  - "engine/neuralweb/company_intelligence_reader.py read_event_workspace"
  - "engine/company_intelligence/event_workspace.py FLAGSHIP_EVENT_ID"
  - "A1 envelope omits related_event_ref and keeps SHA 25e5562e81cb80bd42d0feb544c212c4471e11736601aaee418a60981a457184"
affects:
  - WS:FINANCIAL-INTELLIGENCE-FABRIC
  - engine/fundamental_forensics/statement_service.py
  - contracts/statement_cell.v1.md
confidence: high
reversibility: costly
decided_by: coo-fable
decided_at: 2026-08-23
---

The event link is a stable event_id plus distinct SEC accessions, not a
copied workspace and not a generation.

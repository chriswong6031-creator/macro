---
key: FIF-3A2-REUSE-MAP
question: >
  What existing FIF-3A1 machinery must FIF-3A2 reuse to serve AAPL's
  FY2026 Q3 10-Q and a stable Earnings event reference, and what may
  it newly bind?
answer: >
  Reuse the accepted statement route, GoldenAaplStatementProvider family,
  package-admission law, HTML-table composition, iXBRL parse, consolidated_only
  mapping, duplicate adjudication, presentation-occurrence split, role-local
  calculations, IssuerMaster identity, and context_only authority. Generalize
  the provider from one accession to the exact AAPL golden set
  (0000320193-25-000079 and 0000320193-26-000020). Bind Q3 columns by
  complete filing period from same-column facts. Add optional related_event_ref
  omitted on A1. Do not create a second route, provider family, event
  workspace, or FIP.
rationale: >
  A1 proved one annual filing. A2 must prove the same architecture survives
  quarterly reporting and converges with the already-live event
  evt_cik0000320193_2026q3_results. statement_cell.v1 already distinguishes
  shared-end-date durations via start+end, so this is not a contract STOP.
  The A1 10-K SHA must remain byte-identical.
alternatives:
  - option: Invent Three Months Ended labels as column identity
    why_not: Sol forbade label heuristics. Complete period is already on the column object.
  - option: Fetch the live Earnings workspace on the statements path
    why_not: No request-time network. A changing generation must not change statement bytes.
  - option: Treat 8-K 0000320193-26-000018 as the 10-Q
    why_not: Distinct form, accession, and acceptance clock.
evidence:
  - "data.sec.gov submissions accession 0000320193-26-000020 acceptanceDateTime 2026-07-31T10:01:02.000Z"
  - "www.sec.gov archive index SHA-256 3e5dde4c0403da2358df715608c679d66223c8d716a75fe1136d9257ba812fdc / 6311 bytes / 65 members"
  - "A1 execute SHA 25e5562e81cb80bd42d0feb544c212c4471e11736601aaee418a60981a457184 unchanged"
  - "research/financial_intelligence_fabric/FIF_3A2_REUSE_MAP.md"
affects:
  - WS:FINANCIAL-INTELLIGENCE-FABRIC
  - engine/fundamental_forensics/statement_graph.py
  - engine/fundamental_forensics/statement_service.py
confidence: high
reversibility: costly
decided_by: coo-fable
decided_at: 2026-08-23
---

FIF-3A2 reuses the accepted A1 statement architecture and extends the
golden AAPL filing set. It does not mint a second statements stack.

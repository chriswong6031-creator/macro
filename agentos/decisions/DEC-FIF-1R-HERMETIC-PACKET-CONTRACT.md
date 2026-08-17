---
key: FIF-1R-HERMETIC-PACKET-CONTRACT
question: >
  How should FIF-1R freeze financial_intelligence_packet.v1 so assembly is a
  pure function of its arguments, formula evidence is recursively auditable,
  and a cell cannot be both-null?
answer: >
  Split I/O into the repo/CLI adapter. assemble_financial_intelligence_packet
  receives PacketBuildContext (injected schema + builder digest) and
  PacketEvidenceDigests; it must not read the checkout. Unrequested formula
  dependencies live in evidence_cells, not in the user cells array. Every
  formula dependency_cell_id must resolve inside the packet down to a direct
  source fact. The schema uses an exact oneOf for valued vs non-valued cells
  and requires provenance receipts on valued direct and formula cells.
rationale: >
  Operator review of PR #5809 at 674f3a07 found three contract defects: the
  builder hashed Path(__file__) and loaded the schema internally; FY2023
  gross_margin referenced a gross_profit cell that was absent from the packet;
  and value=null plus non_value_state=null was schema-valid. Filing Forensics,
  Terminal, Neural Web, and export workers must call one assembler from
  already-loaded inputs. Silently adding gross_profit to user cells would
  diverge requested metrics from returned metrics. A dedicated evidence plane
  keeps that split while making the packet self-contained.
alternatives:
  - option: Keep filesystem reads inside build_financial_intelligence_packet
    why_not: >
      Every future consumer would inherit checkout discovery. The FIF-1
      boundary was that the kernel is a pure reusable function.
  - option: Silently add formula dependencies to the user cells array
    why_not: >
      Requested metrics and returned user metrics would diverge. Downstream
      consumers could not tell a asked-for metric from scaffolding.
  - option: Nest dependency_evidence only under formula provenance
    why_not: >
      A recursive evidence_cells map is reusable across formulas, deduplicates
      shared leaves, and is simpler to index by cell_id.
  - option: Keep the existing if/then value vs non-value schema
    why_not: >
      Neither branch fires when both fields are null, which is the ambiguity
      the packet exists to eliminate.
evidence:
  - operator FIF-1R review of PR #5809 head 674f3a07bf786a9f2ac345c9a22014159fd6eef3
  - tests/test_fundamental_forensics_financial_intelligence_packet.py Laws 9-10 plus nested net_debt, schema-negative, and pure-kernel I/O denial
affects:
  - WS:FINANCIAL-INTELLIGENCE-FABRIC
  - contracts/financial_intelligence_packet.schema.json
  - engine/fundamental_forensics/financial_intelligence_packet.py
  - scripts/build_financial_intelligence_packet.py
confidence: high
reversibility: costly
decided_by: chairman
decided_at: 2026-08-16
---

FIF-1R closes the packet contract on PR #5809 without starting FIF-2. The
synthetic filing-package ledger and bitemporal query kernel are unchanged in
role: Company Facts remains a hashed witness, and user-requested cells stay
exactly the requested metric set.

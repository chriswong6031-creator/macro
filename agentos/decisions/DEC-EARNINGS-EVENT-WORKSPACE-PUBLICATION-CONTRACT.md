---
key: EARNINGS-EVENT-WORKSPACE-PUBLICATION-CONTRACT
question: >
  What exact production publication and read path does E1 write event_workspace.v1
  to, and what counts as the real consumer that must observe generation and
  correction?
answer: >
  Publish event_workspace.v1 as a sibling object under the existing Company
  Intelligence product prefix at company_intelligence/event_workspaces/, using
  the same marker-last immutable generation discipline as write_generation.
  The real consumer is
  engine.neuralweb.company_intelligence_reader.read_event_workspace, which
  follows marker → immutable generation → hash-verified workspace object.
  The closed v1 teaser (validate_context / GET /api/company-intelligence/{ticker}
  / read_company_intelligence) is not the consumer. A golden JSON fixture may
  pin bytes and does not count. Terminal Brief + dossier glance is E1+E2 arc
  success, not E1.
rationale: >
  company_intelligence_context.v1 is a closed public wire: unknown keys are
  refused and the v1 manifest files map accepts only companies/{TICKER}.json.
  Stuffing the workspace into that object would either break the teaser or
  invent a silent schema. Binding E2 to the teaser would also contradict the
  freeze that E2 may not fetch CI v1 overlay as the glance. Nesting under the
  same product prefix reuses the existing origin, fetch, and hash-verify family
  without a second R2 product or a mutation of the closed v1 maps.
alternatives:
  - option: Embed event_workspace.v1 inside the v1 company context JSON
    why_not: >
      validate_context requires exact keys. Additive fields are an
      input-boundary violation on a model-facing public wire.
  - option: Add workspaces/*.json into the existing v1 manifest files map
    why_not: >
      company_count must equal len(files) and every file must start with
      companies/. Changing that reopens the closed teaser contract.
  - option: Treat a golden JSON fixture as the E1 consumer
    why_not: >
      A fixture cannot observe a published generation_id advance. CEO review
      required a real reader / private API / production adapter.
  - option: Call Terminal Brief + dossier E1 success
    why_not: >
      E1 is no-UI and must not touch Terminal or dossier JS. Brief + dossier is
      the E1+E2 arc.
evidence:
  - "engine/company_intelligence/contracts.py validate_context exact-keys; validate_manifest companies/*.json only"
  - "engine/company_intelligence/views.py write_generation marker-last"
  - "engine/neuralweb/company_intelligence_reader.py read_company_intelligence is the bounded teaser projector"
  - "research/earnings_intelligence/E0_E1_E2_CONTRACT_FREEZE.md §4.1"
affects:
  - "WS:EARNINGS-INTELLIGENCE-OS"
  - earnings-intelligence
  - engine/company_intelligence/**
  - engine/neuralweb/company_intelligence_reader.py
confidence: high
reversibility: costly
decided_by: session-e0-freeze
decided_at: 2026-08-16
---

E1 that cannot publish onto this nest without inventing a second product
prefix or mutating the closed v1 maps must stop and escalate rather than
fork the store.

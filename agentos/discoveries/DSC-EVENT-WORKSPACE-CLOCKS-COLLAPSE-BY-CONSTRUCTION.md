---
key: EVENT-WORKSPACE-CLOCKS-COLLAPSE-BY-CONSTRUCTION
claim: >
  The event_workspace.v1 two-clock collapse observed on the live AAPL generation
  (observed_at == source_available_at == generated_at) is structural, not an
  accident of one build: event_workspace_build.py derives the build clock from
  observed_at and emits generated_at from that same clock, and the sole
  production caller seeds BOTH observed_at and source_available_at from the SEC
  filing acceptance_datetime. Direction matters: source_available_at is the one
  CORRECT clock (a genuine legal source time); observed_at and generated_at are
  the derived fields carrying no independent information. The US G0 census's
  remediation ("do not stamp source_available_at = generated_at", spec draft §3)
  points at the wrong field, and any frontier built "from lifecycle pairs"
  (the #5953-embedded draft adjudication's recipe) is degenerate — the pair
  carries one instant. The real build surface is per-source clock projection:
  live sources[] carry no clock fields while SourceDocument already defines
  fetched_at/published_at/available_at.
falsifier: >
  Read engine/company_intelligence/event_workspace_build.py:150 and :449 — if
  generated_at is minted independently of observed_at, the derivation claim is
  dead. Read scripts/refresh_event_workspaces.py:352,362-363 — if observed_at is
  seeded from a genuine consumer-observation clock distinct from the filing
  acceptance_datetime, the direction claim is dead. A live generation whose
  lifecycle carries two distinct instants kills the "structural" claim.
so_what: >
  Any K4-G / Earnings E-wave clock fix must target observed_at/generated_at
  semantics and per-source clock projection, and must never "repair"
  source_available_at — reversing that direction (as the accepted census's spec
  draft prescribes as written) would corrupt the only correct clock in the
  contract. Binding condition §2.a-b of the c0g seat adjudication.
kind: architecture
verified_at: 2026-08-19
verified_by:
  - "engine/company_intelligence/event_workspace_build.py:150 (clock = _utc(observed_at, ...))"
  - "engine/company_intelligence/event_workspace_build.py:449 (generated_at emitted from that clock)"
  - "scripts/refresh_event_workspaces.py:352,362-363 (observed_at=source_clock, source_available_at=source_clock, source_clock=filing acceptance_datetime)"
  - "live R2 generation f709a0a6ec514282d5769e7d lifecycle triple-equality (workspace sha256 dbd50e5c…81197 matches manifest)"
  - "engine/company_intelligence/documents.py:162-164 (SourceDocument clock fields exist; live sources[] carry none)"
scope:
  - "engine/company_intelligence/"
  - "research/earnings_intelligence/g0/"
  - "research/alpha_intelligence/"
confidence: verified
---

Found during the c0g audit of PR #5955 (US G0 census): the census reported the
collapse honestly but tagged it INFERRED and diagnosed the causal direction
backwards; the opus audit upgraded it to code-verified and reversed the arrow.
Both rival G0 documents missed the lifecycle-pair degeneracy.

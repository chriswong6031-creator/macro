---
key: FIF-PACKET-GOVERNANCE-IS-CUTOFF-VISIBLE
question: >
  What identifies the governance of a historical financial_intelligence_packet.v1
  — today's full metric registry digest, or the governance visible at the
  requested system-recorded cutoff?
answer: >
  Historical packet identity is governed by the cutoff-visible
  GovernanceBundle, never by the mutable latest registry digest. Packet
  governance carries governance_bundle_id (the bundle content_id) and
  governance_recorded_at. Receipts identify the same cutoff-visible bundle.
  A rule with available_at after the requested cutoff must not rewrite the
  bytes, hash, or packet_id of a historical packet whose visible financial
  semantics did not change.
rationale: >
  The query kernel already projects GovernanceBundle at recorded_at. FIF-1R3
  still copied live catalog_version / catalog_content_sha256 into packet
  governance, so appending a future mapping changed old packet hashes. That
  is historical instability, not a new projection model. Reuse the existing
  bundle identity; do not invent a second governance system.
alternatives:
  - option: Keep metric_registry_digest as load-bearing packet identity
    why_not: Adding a future rule rewrites historical packets whose visible rules did not change.
  - option: Invent a FIF-specific registry projection
    why_not: The query kernel already owns cutoff-visible governance.
  - option: Defer until after v1 freeze
    why_not: Frozen packet identity that drifts under future rules cannot be a freeze.
evidence:
  - Sol FIF-1R3 source review of PR #5889: cutoff-visible governance identity
  - engine/fundamental_forensics/metric_registry.py MetricRegistry.governance_bundle_at
  - tests/test_fundamental_forensics_financial_intelligence_packet_r3.py::test_future_rule_does_not_rewrite_historical_packet_identity
affects:
  - WS:FINANCIAL-INTELLIGENCE-FABRIC
  - engine/fundamental_forensics/financial_intelligence_packet.py
  - contracts/financial_intelligence_packet.schema.json
confidence: high
reversibility: costly
decided_by: ceo-sol
decided_at: 2026-08-18
---

A historical Financial Intelligence Packet is identified by the governance
bundle visible at its requested system-recorded cutoff, not by today's
mutable complete registry digest.

---
key: FIF-3A4R-CROSS-FILING-LINEAGE-ACCEPTED-ON-MAIN
question: >
  What is the durable architecture and program state of FIF-3A4R after Sol's
  final exact-head adjudication and the landing of research PR #6382?
answer: >
  FIF-3A4R is ACCEPTED_ARCHITECTURE / ON_MAIN / NOT_BUILT. The accepted v1
  architecture preserves the accepted A1/A2 FILED RawFactOccurrences unchanged,
  records only immutable cutoff-visible positive lineage evidence, and performs
  effective-root unification inside the existing BitemporalMetricQueryEngine.
  The lineage relation is xbrl_confirmation; it is not
  FactEventType.XBRL_CONFIRMATION and it does not remint or append a
  RawFactOccurrence. Confirmation may affect LATEST_KNOWN_AS_OF only.
  AS_REPORTED retains the original A1 FILED root; LATEST_RESTATED and FIF
  revisions[] ignore confirmations. Runtime lineage_evidence may contain only
  accepted positive immutable relations; the A4R census JSON and replay are
  research evidence, never a runtime provider or second truth plane.
rationale: >
  FIF-3A3 proved the real A1/A2 filing occurrences converge into the canonical
  RawFactLedger and existing query kernel, but also proved same-economic-fact
  comparative instants remain NOT_EVALUABLE while the two filing roots are
  unlinked. A4R freezes the narrow source law by which a later filing can confirm
  an earlier fact without falsely calling the later filing a revision/restatement
  or rewriting accepted source identity. Sol source-reviewed exact research head
  07755cb557a53af1341d8b6323a412631af8d83e after protected Skillpack bootstrap
  mastermindx-market-intelligence/Mastermind@068125e3524eb1b327721f1e79a2338f3d367554,
  released HOLD-FOR-SOL, and PR #6382 squash-merged as
  fe8caca04b634686fc8d8707a188ea1a8477c31c.
confirmation_v1:
  default: NO_RELATION
  positive_requires:
    - FILED -> FILED
    - distinct accessions
    - same filer/source family
    - parent accepted before child
    - same canonical economic logical_key
    - dimensions_known=true
    - duplicate groups individually adjudicated
    - exact parsed numeric value
    - exact decimals/precision semantics
    - approved standard source taxonomy
    - exact original source taxonomy namespace/version
  exclusions:
    - Nil/nil facts have no v1 confirmation contract.
    - _duplicates_agree is intra-instance evidence and does not widen cross-filing confirmation.
    - Precision-consistent values that are not exactly equal remain unconfirmed.
    - Changed values do not become a typed revision without separate auditable evidence.
clock_law:
  source_known_at: max(parent.accepted_at, child.accepted_at)
  system_available_at: >
    No earlier than parent recorded_at, child recorded_at, accepted A4R
    lineage-rule availability, and immutable lineage-evidence receipt recording.
    The research-census timestamp does not authorize runtime lineage.
  historical_states:
    - Before A2 is knowable, A1 remains VALUE.
    - With A1+A2 visible but no cutoff-visible lineage receipt, preserve FIF-3A3 NOT_EVALUABLE.
    - After positive lineage evidence is cutoff-visible, LATEST_KNOWN_AS_OF may resolve through A2 FILED.
census_v1_1:
  schema: fif3a4r.aapl_overlap_census/v1.1
  a1_occurrences: 964
  a2_occurrences: 758
  overlap_logical_keys: 133
  duration_overlap: 0
  exact_numeric_confirmation_candidates: 130
  empty_dimension_exact: 37
  dimensioned_exact: 93
  query_relevant_empty_dim_core_mapped_non_nil: 15
  nil_confirmation_unspecified: 1
  precision_consistent_unconfirmed: 1
  changed_value: 1
  source_taxonomy_namespace_version_mismatch: 0
  payload_sha256: b1577b04f553c56ba278d2057ecc07a0d23159a1d20a41339b39da4ed24c12a9
  file_sha256: f1481fffa18720209ba98d463c25a52b4e497bff89b2159cfa3b2d74ea63ab58
  accepted_a3_ledger_sha: ba149bd55d929d843f353e91bbf68147791fb8b4a20c258426ea2eb7527019d8
alternatives:
  - option: Reclassify A2 FILED as FactEventType.XBRL_CONFIRMATION
    why_not: Rewrites occurrence identity and the accepted A3 ledger; confirmation is lineage, not a source event type.
  - option: Append a third confirmation RawFactOccurrence
    why_not: Creates duplicate identity/truth and still needs suppression semantics; one occurrence plane is frozen.
  - option: Use _duplicates_agree or precision intervals as confirmation
    why_not: Consistent is not confirmed. v1 is intentionally exact and cross-filing.
  - option: Load the research census JSON as runtime lineage
    why_not: Research evidence cannot become a provider dependency or authorize historical system availability.
evidence:
  - "Research PR #6382 accepted head 07755cb557a53af1341d8b6323a412631af8d83e; squash merge fe8caca04b634686fc8d8707a188ea1a8477c31c"
  - "Exact-head ci run 32897588352 SUCCESS and fences run 32897588374 SUCCESS; fresh ci-authority/main after Sol release SUCCESS"
  - "research/financial_intelligence_fabric/FIF_3A4R_CROSS_FILING_LINEAGE_PROTOCOL.md"
  - "research/financial_intelligence_fabric/FIF_3A4R_AAPL_OVERLAP_CENSUS.json"
  - "DSC:AAPL-A1-A2-CROSS-FILING-OVERLAP-CENSUS"
  - "DSC:XBRL-DUPLICATE-LAW-IS-INTRA-INSTANCE"
affects:
  - WS:FINANCIAL-INTELLIGENCE-FABRIC
  - research/financial_intelligence_fabric/FIF_3A4R_CROSS_FILING_LINEAGE_PROTOCOL.md
  - engine/fundamental_forensics/query.py
  - engine/fundamental_forensics/query_service.py
confidence: high
reversibility: costly
decided_by: ceo-sol
decided_at: 2026-08-25
related:
  - "DEC:FIF-3A3-ACCEPTED-GOLDEN-QUERY-ON-MAIN"
  - "DSC:AAPL-UNLINKED-VINTAGES-REQUIRE-TYPED-REVISION-LINEAGE"
  - "DSC:AAPL-A1-A2-CROSS-FILING-OVERLAP-CENSUS"
  - "DSC:XBRL-DUPLICATE-LAW-IS-INTRA-INSTANCE"
---

This decision accepts architecture and source law only. FIF-3A4 runtime
implementation has not started and remains NOT_BUILT. FIF-3 remains IN_PROGRESS.
Production attested issuer service remains NOT_BUILT. Historical FIF-3A3 replay
must remain reproducible forever.

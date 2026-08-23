# Dislocation P0-S1F source-only model and independent audit commission

**Scope:** the frozen S1F exact seventy only, transported in seven predetermined
ten-packet batches. This is a price-blind source-feasibility experiment. It has no
ranking, gating, sizing, execution, signal-originating, or P0-S2 authority.

The coordinator supplies canonical SEC source packets as exact document identities,
hashes, roles, a batch-level unique-document store, and readable evidence-catalog
excerpts that replay to raw bytes. Every textual exact FTS match and additive primary
document appears once in the batch store as exact `source_utf8`; a non-UTF-8 binary
document appears as exact base64 with its encoding declared. The catalog is a citation
aid, not a substitute for reviewing the complete supplied documents. Packet inventories
preserve whether a document is an exact FTS match, additive primary context, or both,
and preserve the canonical owner role. Evidence may cite any supplied exact or additive
document. The retrieval stratum, query family, and query phrase are provenance only.
They are not semantic labels and must never determine an event family.

## Fresh Grok proposal pass — repeat for each frozen batch

Review every one of the ten attached packets. Use no external source and no prior A1R
semantic output. Return one JSON object with:

- `schema = mastermind.dislocation_p0.s1f_grok_proposal_batch.v1`;
- the exact attached `batch_number`, `batch_id`, `source_manifest_sha256`, and
  `batch_plan_sha256`;
- `input_bundle_sha256` exactly as supplied by the coordinator;
- `proposer = {provider: xAI, model: <exact runtime model shown by the web UI>,
  role: GROK_SOURCE_ONLY, fresh_source_only: true}`;
- ten `proposals` in the exact attached packet order;
- `relationship_hypotheses = []` because final linkage is deferred to all seventy.

Each proposal has the exact `packet_id`, `proposer_role = GROK_SOURCE_ONLY`, and a
`semantic` object containing exactly:

`event_family`, `affected_scope`, `adverse_information_state`,
`duration_uncertainty`, `recoverability_evidence`,
`structural_impairment_evidence`, `quantified_impact`,
`mitigation_resolution_transition`, and `episode_relationship`.

Each field is either `{value, evidence}` or `{state}`. A value is non-null and its
evidence is an exact catalog mapping `{document_sha256,start,end,excerpt}`. Do not
normalize or rewrite the excerpt. Typed states are `UNKNOWN`, `UNAVAILABLE`,
`RIGHTS_BLOCKED`, `NOT_APPLICABLE`, `EXPLICIT_NONE`, `CORRECTED`, and `QUARANTINED`.
The last three are affirmative source claims and require evidence. Review the complete
document store, then cite an exact catalog segment. If a binary or table region has no
readable exact segment, use a typed state; never invent an offset.

## Independent Opus 5 Max audit — repeat for each frozen batch

Audit all ten proposals from source, independently. The shadow-triage result and prior
A1R semantics are deliberately absent. Return:

- `schema = mastermind.dislocation_p0.s1f_opus_audit_batch.v1`;
- exact batch/source/proposal/input hashes supplied by the coordinator;
- `auditor = {provider: Anthropic, model: Opus 5 Max, role: OPUS,
  independent_source_only: true}`;
- ten `audits` in exact packet order;
- `relationships = []`; cross-batch edges are deferred to the all-seventy pass.

Every audit has `packet_id`, `auditor_role = OPUS`, a verdict `ACCEPT`, `REPAIR`, or
`REJECT`, explicit `disagreements`, and a complete packet-local
`relationship_assessment` for `duplicate`, `amendment`, `pulse`, `mitigation`,
`resolution`, and `episode`. `ACCEPT` has no disagreements or `final_semantic`.
`REPAIR` has at least one terminal disagreement and a complete `final_semantic` with
all nine fields under the same span law. `REJECT` has at least one terminal
disagreement, a typed `typed_refusal`, and no final semantic.

At batch scope, use a typed relationship state when the relationship cannot yet be
established. Do not guess a cross-batch edge.

## Final Opus 5 Max all-seventy relationship reconciliation

The coordinator supplies a compact all-seventy file after all seven audits. It carries
global packet identity/order, form and clocks, lineage, document hashes/roles, final
proposal/audit semantics and the exact spans those artifacts already cited. It carries
no raw price/outcome data and no shadow-triage verdict.

Return one object with:

- `schema = mastermind.dislocation_p0.s1f_all70_relationship_reconciliation.v1`;
- exact source, batch-plan, proposal-bundle, and audit-bundle hashes;
- `reconciler = {provider: Anthropic, model: Opus 5 Max, role: OPUS,
  independent_source_only: true}`;
- `reviewed_packet_ids` containing all seventy IDs in exact global slot order;
- `all70_complete = true`, `unresolved_count = 0`;
- `resolution_matrix`, one `{packet_id, resolution: RESOLVED}` per packet in exact
  global order;
- `final_relationship_assessments`, one row per packet in exact global order, with a
  terminal six-kind `relationship_assessment` under the same assertion/evidence law;
- explicit resolved `relationships` across the panel.

This pass may repair only the relationship assessments that were necessarily blind to
other batches. It may not alter any semantic field, audit verdict, disagreement, or
typed refusal. Every affirmative relationship assertion and edge must reuse an exact
evidence span already present in the compact input; do not invent a new offset.

An edge names one of `duplicate`, `amendment`, `pulse`, `mitigation`, `resolution`, or
`episode`; has unique valid `packet_ids`; includes replayable evidence from its first
packet; carries `auditor_role = OPUS`, the first packet's final `audit_verdict`, and a
terminal `resolution` of `RESOLVED` or `NOT_APPLICABLE`.

## Episode admission law

An accession is not an episode. A resolved episode edge is admissible only if at least
one linked packet is independently `ACCEPT` or `REPAIR` and its final audited semantic
has exact evidence for one of:

- `adverse_information_state = P0_ADVERSE_INFORMATION`;
- `structural_impairment_evidence = P0_STRUCTURAL_IMPAIRMENT_CONTROL`;
- `mitigation_resolution_transition = P0_RESOLVED_BEFORE_DISCLOSURE_CONTROL`.

Typed nulls/refusals and `REJECT` admit no episode. Ordinary dividend, offering,
buyback, agreement, joint-venture, or results disclosures with no controlled P0 state
admit no episode. Zero episodes is an honest result. No top-ups.

## Stop

Return the requested JSON only. Do not browse, access prices/outcomes/counterfactuals,
start P0-S2, or make a feasibility/promotion decision.

---
key: D5-OWNER-IS-GOVREV-ONTOLOGY-PLUS-COMPOSED-DOSSIER
question: >
  Where does reviewed defense program / mission / capability / product truth
  canonically live, and how are economic/supplier relationships composed with
  it without creating a second identity graph, second theme/economic graph,
  second budget plane, or defense-specific parallel truth store?
answer: >
  Option D. D5 owns exactly one new canonical record class in the GovRev
  defense plane — government_program_ontology.v1 (reviewed acquisition
  program / capability / platform identity plus source-bound role assertions
  and milestones, propose→curate admission, display-tier authority, temporal
  quadruple known_at/valid_from/valid_to/evidence_refs) — and the user-facing
  Program Dossier is a composed read model
  (government_program_dossier.v1) joining, at read time: D5 ontology +
  defense21 recipient identity + GovRev award events (via the reviewed
  program_event_links pointer relation, D5R.2 — exact event_id +
  source-identity hash + canonical_award_identity agreement, zero copied
  event truth)
  + the budget owner (projection_missing until it produces) + Stock Identity
  via the identity atlas + GMI economic relationships (reserved-null today,
  rendered not_asserted). No new global supergraph, no defense supplier graph,
  no automatic (official-tier) rows inside D5 v1 — every D5 record is
  human-admitted.
rationale: >
  The recipient graph rejects extension by construction (closed 13-key
  contract, additionalProperties:false everywhere, const-pinned version,
  producer docstring naming closure as the anti-drift device). GMI's
  policy_program is a never-emitted enum literal, GMI is context_only with
  does_not_own bounding it away from acquisition identity, and the
  three-graph separation map routes GovRev INTO GMI as an input ramp — owner
  inversion. An independent graph is the forbidden fourth spine; the
  economic_propagation ownership census §2.5 already assigns
  program/mission/capability/product to government-revenue-foresight. The
  budget graph's program nodes are budget-exhibit-native (dod-program:* keys
  closed at procurement_line_item/rdte_program_element) and its artifact is
  hard-disabled pending D6 (its program-node kinds closed at
  procurement_line_item/rdte_program_element) — tenanting acquisition
  identity there inverts the dependency and conflates exhibit-line identity
  with acquisition-program identity. The estate has ratified the chosen two-artifact shape twice
  (recipient graph + identity atlas; budget graph + workspace rails), and
  government_budget_edge.v1 already codifies the reviewed_documentary
  dual-evidence pattern D5 role assertions adopt.
alternatives: >
  (A) Extend government_recipient_entity_graph.v1 — rejected: contract closed
  by design; identity-specific per its own schema language. (B) House D5
  objects in GMI Theme Graph — rejected: unused policy_program literal is not
  ownership; context_only thematic plane; blocked TRANSMISSION lane coupling;
  separation map makes GovRev an input ramp, not a tenant. (C) Independent
  Defense Program Graph — rejected: duplicate graph infrastructure; census
  forbids a fourth spine and already assigns the truth category to GovRev.
  (E, surfaced by census) Extend government_budget_program_graph.v1 —
  rejected: exhibit-native identity, hard-disabled production, D6-scoped
  acquisition; acquisition programs span exhibits and decades.
evidence: >
  research/defense_intelligence/DEFENSE_D5_PROGRAM_GRAPH_ARCHITECTURE_FREEZE.md
  §1-§4 (census with file:line citations);
  contracts/government_revenue/government_recipient_entity_graph.v1.schema.json;
  contracts/theme_graph/nodes.v1.schema.json:26 + edges.v1.schema.json;
  research/economic_propagation/D0_OWNERSHIP_AND_GRAPH_CENSUS.md §1, §2.5, §4;
  research/economic_propagation/D0_THREE_GRAPH_SEPARATION_MAP.md §6;
  contracts/government_revenue/government_budget_program_graph.v1.schema.json;
  contracts/government_revenue/government_budget_edge.v1.schema.json;
  engine/government_revenue/budget_program.py:139-268;
  collectors/dod_budget.py:37; scripts/build_government_revenue.py:715-718.
affects: ["research/defense_intelligence/", "contracts/government_revenue/", "engine/government_revenue/"]
confidence: high
reversibility: costly
decided_by: coo-fable
decided_at: 2026-08-21
---

Scope note: D5 role assertions are program-participation facts (procurement
domain), not the census's missing customer/supplier economic object —
economic_weight is REQUIRED and const null on every v1 role assertion (it
names the absence of an earned economic share and may never be made
non-null), and GMI W4 remains the owner of any future
SUPPLIES/ENABLES/BOTTLENECK_OF economics, free to consume D5 records as an
input ramp. On any conflict, the architecture freeze document governs over
this record. D5 implementation itself remains unauthorized until Sol accepts
D5R and authorizes the build.

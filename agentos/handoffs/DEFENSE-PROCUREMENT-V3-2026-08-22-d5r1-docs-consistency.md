---
workstream: WS:DEFENSE-PROCUREMENT-V3
session: claude/d5r1-docs-consistency
model: fable
ended_because: complete
prs: []
decisions: []
discoveries: []

mission: >
  Sol D5R.1 directive: docs-consistency close ONLY. D5R core architecture
  passed review; final acceptance held on six source-law contradictions.
  Repair them so a cold builder never chooses between two contradictory
  instructions. Owner adjudication and Virginia pilot stay frozen. No
  production schema/code. D5 and D6+ remain unauthorized.

state_before: >
  D5R merged as PR 6209 (780b669ec87d, 2026-08-22T04:32Z) with post-merge
  proof green. Sol review found six contradictions: bare capability id in
  the composition; economic_weight freeze/handoff conflict; role-assertion
  key optionality ambiguous; issuer-disclosure host authority unassigned;
  the realized Block VI award required as a "milestone"; AUKUS forward item
  unclassified in the evidence registry. Branch cut from fresh origin/main
  dc7c2e9f4da8 (2026-08-22T05:15Z); no open lane touched D5-owned paths.

changed:
  - path: research/defense_intelligence/evidence/compositions/d5-program-dossier-virginia.html
    what: >
      capability:undersea-warfare -> acq-capability:undersea-warfare;
      inspector milestone row re-pointed to the AUKUS Pillar-1 forward
      window (delivery_event, 2030-2033) with an explicit line that the
      2026-07-29 Block VI award is a GovRev/D3 changed-event, never a D5
      milestone.
  - path: research/defense_intelligence/DEFENSE_D5_PROGRAM_GRAPH_ARCHITECTURE_FREEZE.md
    what: >
      §3.1 role_assertion: program_id REQUIRED, platform_id OPTIONAL with
      loader-enforced referential + program-match + temporal-compatibility
      rules; platform-only assertions invalid in v1; economic_weight
      REQUIRED const null ("names the absence of an earned economic share";
      do not derive/estimate/populate/rank or otherwise make it non-null).
      §3.1 milestone: FORWARD-ONLY law — realized procurement events are
      GovRev/D3 truth, never duplicated as milestones; passed milestones
      close out via valid_to. §3.1a: issuer-disclosure host authority
      frozen after a bounded census (no canonical issuer→IR-host owner
      exists in the estate — issuer_master has no website field, earnings
      plane ingests no first-party releases, biocatalyst registry is
      per-dataset): schema-enforced shape (source_url/retrieved_from_url/
      pinned_issuer_host), curator-pinned per-row host with recorded basis,
      loader-refused mismatch/missing pin; NO global issuer→host table, no
      second company-source registry; read-only rejoin via version bump if
      an owner later exists. §7.1: Block VI award reclassified as the
      changed-event; AUKUS Pillar-1 window named as the forward-milestone
      candidate with source CRS RL32418 classified SOURCE CLAIM;
      not_reviewed/reviewed_none frozen as valid production outcomes. T13
      re-stated to assert only per-row-pin authority; T14 extended with
      platform referential-integrity refusals.
  - path: research/defense_intelligence/DEFENSE_D5_PROGRAM_GRAPH_IMPLEMENTATION_HANDOFF.md
    what: >
      Gate 3: milestones rail required in a VALID state (reviewed forward
      milestone or honest not_reviewed/reviewed_none); the July-29 award
      removed as a mandatory milestone admission. do_not_redo:
      economic_weight sentence rewritten to the const-null form. §3
      registry: AUKUS/CRS RL32418 row added with verification level and
      re-fetch + receipt + review requirement.
  - path: agentos/decisions/DEC-D5-PILOT-IS-VIRGINIA-CLASS-SSN.md
    what: >
      Answer text updated: milestones rail forward-only with the AUKUS
      candidate; Block VI award named as the changed-event, never a D5
      milestone.

verified:
  - claim: no bare D5 `capability:` id remains in the D5R artifact set (only acq-capability)
    command: >
      grep -rn "capability:undersea|`capability:<" research/defense_intelligence/
      agentos/decisions/DEC-D5-*.md agentos/handoffs/DEFENSE-PROCUREMENT-V3-2026-08-21*
      agentos/workstreams/WS-DEFENSE-PROCUREMENT-V3.md | grep -v acq-capability -> empty
  - claim: no canonical issuer→IR-host owner exists in the estate (census, file:line receipts)
    command: routed scout census packet (build_security_master.py:188-197; earnings_story_promotion.yml:11-16; biocatalyst_sources.yml; edgar collectors)
  - claim: AgentOS store validates clean after edits
    command: python3 scripts/agentos.py validate

unverified:
  - claim: the AUKUS Pillar-1 window survives document review as an admissible forward milestone
    what_would_verify: re-fetch CRS RL32418, receipt, human review at D5 time (registry row carries the rule)

unresolved:
  - >
    Final D5R acceptance — held by Sol pending this consistency close; D5
    implementation and D6+ remain unauthorized.

next_actions:
  - Return to Sol with the D5R.1 PR for final D5R acceptance.
  - >
    If accepted and D5 authorized: cold builder starts from the handoff §0
    gates on fresh origin/main; every instruction now has exactly one
    binding form (fresh adversarial consistency review run this session).

do_not_redo:
  - Do not reopen the owner adjudication or the Virginia pilot (frozen; Sol D5R.1 order).
  - Do not re-run the issuer→IR-host census — result is frozen into freeze §3.1a with receipts (none exists; per-row worksheet pins are the only authority).
  - Do not re-admit the 2026-07-29 Block VI award as a D5 milestone in any future wave — it is the GovRev/D3 changed-event.

danger_areas:
  - >
    The issuer-host authority is deliberately per-row worksheet pins — any
    implementation that "helpfully" adds a global issuer→host table or a
    company-source registry violates the frozen census ruling.
  - >
    Milestones are forward-only; wiring the changed-event tape into the
    milestones rail re-introduces the exact duplication Sol rejected.
---

Docs/AgentOS/reference-composition changes only; zero production surface
touched. D5R = in_progress, D5 = todo/unauthorized, D6+ = unauthorized.

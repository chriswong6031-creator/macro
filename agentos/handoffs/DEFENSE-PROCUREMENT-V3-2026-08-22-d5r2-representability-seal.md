---
workstream: WS:DEFENSE-PROCUREMENT-V3
session: claude/d5r2-contract-representability
model: fable
ended_because: complete
prs: []
decisions: []
discoveries: []

mission: >
  Sol D5R.2 directive: contract-representability seal ONLY. Make every D5
  canonical truth and read-model state machine-representable so the
  implementation worker writes code, not architecture. No research waves,
  no production schema/code. D5 and D6+ remain unauthorized; owner
  adjudication and Virginia pilot stay frozen.

state_before: >
  D5R.1 merged as PR 6219 (aef397478a02); Sol passed the six repairs and
  the owner/pilot rulings but held final D5R acceptance because several
  canonical objects still required the implementation worker to invent
  their physical schema (no enumerated top-level key set, no
  program-capability or program-event representation, review states not
  derivable from the artifact, milestone preimage collidable on window.to,
  logical-id-vs-revision law unstated, dossier bundle and program_link
  shapes unfrozen). Branch cut from fresh origin/main 7e00f8746ce5.

changed:
  - path: research/defense_intelligence/DEFENSE_D5_PROGRAM_GRAPH_ARCHITECTURE_FREEZE.md
    what: >
      NEW §3.0: seventeen-key closed top-level skeleton (contract,
      schema_version const 1.0.0, graph_id grammar
      program-ontology:<status>:<YYYY-MM-DD>:<batch-slug>, graph clocks)
      with a complete machine-readable reference JSON whose
      content-addressed ids recompute under the sha12 law. §3.1: universal
      revision law; relationship-representation law (program→capability
      ONLY via program_capability_links[] with the relation's own claim
      scope; platform fields; cross-plane only via program_event_links[]);
      milestone temporal_kind date/window XOR. §3.1a: frozen evidence-row
      shape (ev:<sha12>); claim_scopes + per-kind coverage extended with
      the two relation scopes; exhaustive preimage registry — milestone
      preimage now carries temporal_kind + window.to (collision repair).
      NEW §3.1b program_event_links: pointer-only relation at
      government_procurement_event.v2 (event_id +
      award_change.source_identity id/content_sha256 + canonical award
      identity agreement, loader fail-closed, no name/description/ticker/
      fuzzy matching, zero copied event truth) + census honesty (NO
      Virginia Block VI v2 event on main 7e00f874; no DoD announcements
      collector in D5). NEW §3.1c review_coverage[]: audit rows
      (rev-cov:<sha12>, scope, subject, worksheet_ref/sha256,
      admitted_count) + the four-state derivation law making
      reviewed_none artifact-derivable. §4: dossier bundle contract frozen
      (nine keys, content_id per the shipped dossier law); awards rail
      split into source_state × link_state axes; the three exact five-key
      program_link shapes. §5: logical-id + revision law (rename = same id
      revision+1; identity break = new id + predecessor_id, restructured;
      variant_added removed; succession_reason re-closed as
      renamed|attribute_revision|superseded_evidence|restructured);
      D5-scoped conflicts/overrides row shapes. §6: new-mint inventory
      extended. §7.1/§9: changed-event claims conditioned on the census
      (no fabricated tape truth; contract-type/quantity elements gap
      honestly without a reviewed link). §8: T1 exact-shape rewrite, T2
      fully executable (rename vs identity break vs refusals), T14(c)
      milestone window collision, NEW T15 (event-link exact identity),
      T16 (relation evidence), T17 (artifact-only coverage derivation).
  - path: research/defense_intelligence/evidence/fixtures/d5-representability-fixtures.json
    what: >
      NEW — fixtures A-I (Sol §8 A-H + a conflict-lifecycle fixture I minted
      during review): Virginia program+capability relation,
      three role assertions, healthy-source+unreviewed-link event state
      with census receipt, IRDM reviewed_none (real committed event
      identity govws-a6c70850a9cbdce9fa3e7f3b + coverage row), rename
      same-logical-id, identity-break restructure, milestone window
      collision pair (cd326e9ef033 ≠ f9d504cf169e), zero-admission review
      pass, and fixture I (conflict declared → conflicted → cleared via
      conflicts-row retirement → both surfaces re-derive, replayed at two
      analysis cuts). All content-addressed ids computed under the frozen
      sha12 law; placeholder preimages published so every sha256 is
      reproducible.
  - path: research/defense_intelligence/DEFENSE_D5_PROGRAM_GRAPH_IMPLEMENTATION_HANDOFF.md
    what: >
      Gates 1/2/3/4 re-frozen (seventeen-key skeleton, T1-T17, program-
      event-linkage honesty at D5 start, exact five-key IRDM shape); §3
      registry census row added (VERIFIED, re-run at D5 start); do_not_redo
      rewritten: program_event_links[] is the ONLY cross-plane award
      reference, no DoD announcements collector, review states only from
      review_coverage rows.
  - path: research/defense_intelligence/evidence/compositions/d5-program-dossier-virginia.html
    what: >
      "tape current" fabrication repaired: changed card renders source
      current + link not_reviewed; contract-type and quantity elements gap
      honestly; inspector row records the census state.
  - path: agentos/decisions/DEC-D5-OWNER-IS-GOVREV-ONTOLOGY-PLUS-COMPOSED-DOSSIER.md
    what: award-events join wording aligned to the program_event_links relation.
  - path: agentos/decisions/DEC-D5-PILOT-IS-VIRGINIA-CLASS-SSN.md
    what: >
      Block VI phrasing aligned: changed-event-plane truth, no tape event
      row yet per the D5R.2 census.
  - path: agentos/workstreams/WS-DEFENSE-PROCUREMENT-V3.md
    what: D5R wave next_action records D5R.2 as the final representability seal.

verified:
  - claim: no government_procurement_event.v2 row for the Block VI award exists on origin/main 7e00f874
    command: >
      routed scout census 2026-08-22 — git show origin/main parquet+JSON
      sweep (awards.parquet 3,807 rows, award_actions.parquet 35,284 rows,
      award_snapshots/award_event_snapshots, dossiers/latest/workspace
      JSON); 13 Electric Boat awards all pre-2026; corpus newest known_at
      2026-08-21T23:22:35Z
  - claim: event identity/hash field names are the real producer fields
    command: >
      award_events.py:1844-1848 (award_change.source_identity id/version/
      content_sha256), :1907 (event_id), point_in_time.py:148
      (canonical_award_identity grammar)
  - claim: the IRDM fixture uses the real committed event identity
    command: >
      git show origin/main:data/government_revenue/workspace.json →
      event_id govws-a6c70850a9cbdce9fa3e7f3b, source_identity.id
      action:CONT_TX_9700_-NONE-_HC101319C0006_P00032_-NONE-_0
  - claim: milestone window-collision fixture ids are distinct and recomputable
    command: python3 fixture generator (scratchpad) — cd326e9ef033 != f9d504cf169e
  - claim: AgentOS store validates clean after edits
    command: python3 scripts/agentos.py validate
  - claim: >
      the commissioned adversarial mutation review concluded YES — zero
      blocker/high/medium representability findings
    command: >
      NINE fresh cold opus reviewer rounds (each a new agent, re-deriving
      everything): rounds 1-8 found and repaired 2 blocker / 15 high / 33
      medium / 33 low findings in total; round 9 at 8c986a457426 rendered
      YES (0/0/0, 2 low — both folded post-verdict as one-clause
      clarifications: award_change-only event links, DISTINCT-refs =
      distinct evidence_ids + uniqueItems). Round 9 independently
      recomputed 20/20 content-addressed ids, verified all 8 placeholder
      hashes, ran the coverage walk and the fixture-I two-cut replay, and
      closed 12 mutation attacks including the round-8 timestamp-spelling
      attack.

unverified: []

unresolved:
  - >
    Final D5R acceptance — held by Sol; D5R.2 is the last commissioned
    close. D5 implementation and D6+ remain unauthorized.

next_actions:
  - Return to Sol with the D5R.2 PR for final D5R acceptance.
  - >
    If accepted and D5 authorized: the cold builder constructs every byte
    of government_program_ontology.v1, government_program_dossier.v1 and
    workspace.program_link from freeze §3.0-§3.1c/§4/§5 + the fixtures
    file without inventing a key, relationship, versioning rule,
    review-state source, or join; re-run the Virginia event census against
    fresh main first (handoff §3).

do_not_redo:
  - Do not reopen the owner adjudication, the Virginia pilot, the IRDM null control, or the issuer-host census (all frozen; Sol D5R.2 order).
  - Do not re-run the Block VI event census for D5R purposes — frozen with receipts into freeze §3.1b/handoff §3; it is re-run only at D5 implementation start against fresh main.
  - Do not re-admit the 2026-07-29 Block VI award as a D5 milestone, and do not call it a GovRev event while no v2 row exists on main.
  - Do not reintroduce variant_added — platform variants are new logical records with variant_of, never successions.

danger_areas:
  - >
    The milestone preimage changed in D5R.2 (temporal_kind + window.to
    slots added). Nothing was ever produced under the D5R.1 preimage, but
    any cached copy of the old five-slot preimage is now wrong — the
    freeze §3.1a registry is the only authority.
  - >
    program_event_links verification reads the event's NESTED
    award_change.source_identity block — not a top-level field. Asserting
    top-level source_identity keys will refuse every row.
  - >
    review_coverage rows are curate-only. A propose script or composer
    that emits one silently manufactures review acts.
---

Docs/AgentOS/reference-fixture changes only; zero production surface
touched. D5R = in_progress (acceptance held), D5 = todo/unauthorized,
D6+ = unauthorized.

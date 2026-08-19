---
key: CS-V2-SIX-QUESTION-ONTOLOGY
question: >
  The current page is an Observed Filing State desk. Competitors collapse
  shelf, EFFECT, ATM, warrants, and guessed dilution into scores and badges.
  What canonical questions must capital_structure_state.v2 separate so V2
  cannot ship another opaque dilution product?
answer: >
  Six questions, never collapsed: Authorization (what exists on paper);
  Execution eligibility (what can be used now); Remaining capacity (how much
  under named constraints); Economic supply (shares that could hit the market
  under named price scenarios); Funding need (cash/debt/catalyst pressure);
  Observed issuance (what was actually sold/exercised/converted). A shelf is
  never expected dilution. EFFECT is never active executable capacity. Missing
  is never zero. A model probability is never a filing fact. prophet_authority
  stays false. No overall CS score.
rationale: >
  The 2026-08-01 docket already named authorization-versus-issuance as the
  product. PR #5792 recovered ingestion into an event projection that still
  lists eight UNAVAILABLE_CAPABILITIES on every issuer, then presents a filing
  list. Blending those eight into a badge would copy the competitor failure
  mode the original program existed to avoid. Neural Web and Prophet can only
  consume typed facts and individually gauntleted features.
alternatives:
  - option: Ship a single dilution / financing-risk score for the dossier hero
    why_not: REJECTED_BY_DESIGN. Opaque, not PIT, not gauntleted, violates A7
      if an LLM originates it.
  - option: Treat EFFECT as active ATM/shelf capacity
    why_not: Effectiveness is not remaining capacity and not a sale (CFI 116.22
      measures offered amount at takedown).
  - option: Keep event-state as the product and call V2 done after live-tail
    why_not: Recovers freshness of a filing browser, not the capital twin the
      Chairman asked for.
evidence:
  - "docs/CAPITAL_STRUCTURE_INTELLIGENCE_CONTRACT.md UNAVAILABLE_CAPABILITIES and context-only ruling"
  - "research/CAPITAL_STRUCTURE_INTELLIGENCE_COMPETITIVE_TEARDOWN_AND_BUILD_DOCKET_2026-08-01.md §0"
  - "research/CAPITAL_STRUCTURE_ISSUER_STATE_W3_BUILD_DOCKET.md non-negotiable operating rules"
  - "projection.json unavailable list identical on AIR, CLNN, QNCX, WHK, LPTH, EDBL at freeze"
  - "research/CAPITAL_STRUCTURE_INTELLIGENCE_V2_MASTERPLAN_2026-08-18.md §5 §11"
affects:
  - "WS:CAPITAL-STRUCTURE-INTELLIGENCE-V2"
  - "capital-structure-intelligence"
  - "templates/capital_structure.html.j2"
  - "engine/capital_structure/"
confidence: high
reversibility: costly
decided_by: cursor-grok-4.6
decided_at: 2026-08-18
review_by: 2026-08-25
---

Proposed by the Cursor Grok 4.6 W0 session, not Fable. Sol accepted this
ontology in the 2026-08-18 AMEND review of PR #5901; it is not reopened.
Program owner remains COO Fable. Later waves implement families; they may
not collapse the six questions.

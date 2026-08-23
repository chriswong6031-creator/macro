---
key: ALPHA-INTELLIGENCE-INTEGRATION
title: Mastermind Alpha Intelligence Expansion — program integration (COO lane)
objective: >
  Coordinate the A–J Alpha Intelligence Expansion responsibilities (Evidence Mesh,
  Institutional Intelligence, Specialist Adapters, Economic Propagation, Relative
  Opportunity, Path Survival, Post-Event Reinterpretation, OpportunityCase, Prophet
  V4 Integration, Evaluation/Expert Learning) across their existing canonical
  owners without duplicating any store, ranker, grader, identity plane, lifecycle,
  or publication truth. Done means every K1–K7 keystone packet has shipped with
  contracts frozen by the canonical owners and zero forbidden duplicates built.
status: active
program: mastermind-semantic-system-map
repos: [macro]
owner: fable
class: adjudication
blast_radius: reversible
ambiguity: scoped
owns_paths:
  - research/alpha_intelligence/
  - research/evidence_mesh/
  - contracts/evidence_foundation/
  - lib/evidence_foundation.py
  - tests/fixtures/evidence_foundation/
  - tests/test_evidence_foundation_contract.py
depends_on:
  - WS:PROPHET-US-V4-RECOVERY
  - WS:PROPHET-CONDITIONAL-FUSION
  - WS:GMI-THEME-GRAPH
  - WS:EARNINGS-INTELLIGENCE-OS
  - WS:EVAL-OS-MEASUREMENT-LAW
  - WS:STOCK-IDENTITY
  - WS:FINANCIAL-INTELLIGENCE-FABRIC
  - WS:FUNDAMENTAL-FORENSICS
  - WS:LIVE-ENTRY-RADAR
  - WS:DEFENSE-PROCUREMENT-V3
artifacts:
  - research/alpha_intelligence/MASTERMIND_ALPHA_INTELLIGENCE_EXPANSION_PASS0_2026-08-18.md
  - research/alpha_intelligence/C0_WAVE0_ADJUDICATION_2026-08-19.md
  - research/alpha_intelligence/C0G_G0_SEAT_ADJUDICATION_2026-08-19.md
  - research/evidence_mesh/K1_EVIDENCE_FOUNDATION_CONTRACT_FREEZE_2026-08-23.md
  - contracts/evidence_foundation/reference.v1.schema.json
  - contracts/evidence_foundation/vocabulary.v1.json
landmines:
  - "Runtime authority of this workstream is NONE, permanently. It coordinates and
    adjudicates; it never gates, dispatches, ranks, or owns production state. Its
    ownership matrix is a dated snapshot — canonical ownership stays in
    config/mastermind_programs.yml, sibling WS records, and DNR."
  - "CRITICAL FIREWALL: OpportunityCase prose never feeds Prophet ranking. Prophet
    consumes structured governed families only (via the conditional-fusion arena +
    Eval OS gauntlet)."
  - "The c0 FIF/FF stop prose is historical, not current state: #5889 merged as
    f4183edade53603fad7a97f702eb4c6e5eabff5d, #5898 merged as
    21f51a1ecfed778a738b048bd7e5efd30b1d9336, and #6285 merged as
    1e7d9f5030fd7c7c06fb03f022857510c5d0f9ed. Merge never implies unrelated
    production acceptance; current FIF-3A2 #6302 remains DRAFT / HOLD-FOR-SOL and
    K1 neither modifies nor routes around it."
  - "PR #5894 (V4-D2A GMI→Data OS bridge) MERGED 2026-08-18 — the theme-graph/
    identity occupation cleared by its own terms (c0 delta). Radar/Prophet-Lab
    surfaces are now the occupied territory: #5925/#5928/#5929 open post-#5924
    B5A/B5B recut (DEC:PROPHET-LAB-B5A-RECUT) — F-lane contact stays read-only."
  - "D-lane territory carries score-tier kills: DNR:KILL-PSS-SR2-PEER-DIFFUSION,
    DNR:KILL-PSS-SR3-PARTICIPATION, DNR:KILL-CN-SUPPLY-ABSORPTION,
    DNR:KILL-CAUSAL-DAG-ALPHA. Kills close constructions, not the search space:
    display/research tier is lawful, score tier needs the gauntlet."
  - "A0's boring-baseline verdict is BINDING on any physical mesh store: the
    pointer log must lose to 'call the owner reader' unless a funded consumer
    needs a cross-store pointer index over >=3 owner_stores for one subject
    (A0_MINIMAL_EVIDENCE_MESH_RECOMMENDATION.md §8 flip condition). FABLE-A
    freezes contracts; it does not build the store until that condition is met."
  - "US G0 canonical copy is MERGED PR #5955 (research/earnings_intelligence/g0/,
    inside the Earnings owner's owns_paths); CN-G0 is MERGED PR #5943
    (research/alpha_intelligence/censuses/CN-G0/). The #5822->#5953 rival
    censuses/G0/ set plus its embedded non-seat C0G_G0_ADJUDICATION was
    WITHDRAWN from #5953 before it merged — no rival copy exists on main.
    C0G_G0_SEAT_ADJUDICATION_2026-08-19.md remains the governing record of
    G0 canonicity (final merged-object pins in its §7); never adjudicate
    from any resurrected rival copy."
  - "K4-G preconditions are frozen in the seat packet §6: clock-direction fix
    targets observed_at/generated_at, NEVER source_available_at
    (DSC:EVENT-WORKSPACE-CLOCKS-COLLAPSE-BY-CONSTRUCTION); frontier = derived
    read-only view, no EVENT_STATES edit; FIF-7 'event workspace packet' /
    'market reaction' two-owner overlap must be adjudicated at K4-G commission
    time; CN adapter is an Earnings-owner identity-plane wave post-E2
    (DEC:ALPHA-INTEL-EARNINGS-EVENT-TRUTH-IS-VENUE-NEUTRAL)."
do_not_redo:
  - "Do not build: a second financial truth store (engine/stock_fundamentals.py +
    engine/fundamental_forensics/ exist); a second Earnings store
    (engine/earnings_release, event_workspace.v1); a second theme truth store
    (engine/theme_graph/, bitemporal belief_time); a second forward
    grader/scoreboard (engine/cycle_forward_log.py + board/track/trial/qledger
    family); a second cross-family ranker (engine/us_prophet_fusion.py is
    canonical, Chairman override 2026-08-15 #5753); a second identity plane
    (engine/stock_identity/ + engine/theme_graph/identity.py); a second Prophet
    candidate lifecycle (expansion/signal/promotion gates + us_candidate_lanes); a
    second publication truth (per-surface scripts/build_*.py); a universal
    evidence warehouse (the mesh is a REFERENCE layer; config/synapse.yml is the
    governance catalog)."
  - "Do not re-derive settled discoveries: DSC:13F-ATOM-POLL-BUDGET-IS-700-FILINGS;
    DSC:NO-QLEDGER-CLAIM-EVER-CARRIED-A-CONTROL-LEG."
waves:
  - id: p0
    title: PASS-0 architecture reconciliation (ownership matrix, collisions, lane gating)
    status: done
  - id: c0
    title: Wave-0 census adjudication (GROK A0/B0/D0/E0/F0 returns; FABLE-A dispatch decision)
    status: done
    depends_on: [p0]
  - id: c0g
    title: G0 return adjudication (post-event reinterpretation census — outstanding at c0)
    status: done
    depends_on: [c0]
  - id: k1
    title: K1 Evidence Foundation — mesh contract freeze (FABLE-A)
    status: in_progress
    depends_on: [c0]
    next_action: Sol accepts or returns exact amendments on the v1.0.0 contract-only packet; no dependent wave starts before that ruling.
  - id: k2
    title: K2 Institutional Intelligence — manager ontology + intent contract (B), adapter pilots (C)
    status: todo
    depends_on: [k1]
  - id: k3
    title: K3 Opportunity Semantics — propagation contract (D), opportunity evidence vector (E)
    status: todo
    depends_on: [k1]
  - id: k4
    title: K4 Path/Event Intelligence — holdability extension (F), earnings event-clock waves (G)
    status: todo
    depends_on: [k1]
  - id: k5
    title: K5 OpportunityCase + Prophet integration (H, I) — governed families into the fusion arena
    status: todo
    depends_on: [k2, k3]
  - id: k6
    title: K6 Forward learning — prospective expert/complementarity ledgers (J)
    status: todo
    depends_on: [k5]
  - id: k7
    title: K7 Chairman final experience acceptance
    status: todo
    depends_on: [k6]
next_action: >
  Sol reviews the exact K1 Evidence Foundation v1.0.0 return packet at
  research/evidence_mesh/K1_EVIDENCE_FOUNDATION_CONTRACT_FREEZE_2026-08-23.md
  and rules ACCEPT or names exact amendments. The physical-store flip condition
  is adverse: no named committed >=3-owner single-query consumer exists, so owner
  readers remain direct and no store/index was built. Do not start K2, K3, K4,
  B1, K2-B, D5-EARNINGS, or any dependent wave before Sol accepts K1.
---

# Alpha Intelligence Expansion — integration workstream

This is the program-control lane for the Mastermind Alpha Intelligence Expansion
(operator fanout pack, 2026-08-18). It exists to keep ten responsibilities (A–J)
reconciled against their canonical owners; it builds nothing itself.

The PASS-0 packet — ownership matrix, collision map, capability-adoption map,
safe/wait lane rulings, perishability verdict, and the K1–K7 merge/dependency
graph — is `research/alpha_intelligence/MASTERMIND_ALPHA_INTELLIGENCE_EXPANSION_PASS0_2026-08-18.md`
(reconciliation pin `47aaa6036846`, 2026-08-18). Read it before adjudicating any
lane; re-derive its live-state claims (open PRs, CI health) rather than trusting
the snapshot after ~1 week.

Keystone packets K1–K7 go to Sol in the K-PACKET format defined by the
commission; ordinary PRs are never escalated. If a K packet's "CEO DECISIONS
NEEDED" is empty, the program continues automatically.

---
key: PROPHET-US-V4-RECOVERY
title: Prophet US V4 — recovery, early discovery & intelligence graph OS
objective: >
  Migrate Prophet US from a late-confirmation board to an early-discovery,
  present-entry, intelligence-ranked research OS. Done means the Chairman opens
  Prophet V4 in production and sees: every owed session settled (or explicitly
  unavailable), early expert evidence before slow confirmation, deterministic
  server-authoritative entry availability where green means only ENTRY_OPEN, an
  explainable missing-aware intelligence rank inside availability lanes, a
  complete searchable All Candidates field with no producer cap, cohort-honest
  grading of every episode, and the frozen V3 algorithm accruing as
  us_prophet_v3_legacy_shadow on the same tape.
status: active
program: prophet-us
p0: US_PROPHET_ENTRY_TIMING
repos: [macro]
owner: fable
class: build
blast_radius: user_facing
ambiguity: scoped
owns_paths:
  - research/prophet_v4/
  - engine/us_turn_watch.py
  - scripts/build_turn_watch.py
  - site/turn_watch/
depends_on:
  - WS:PROPHET-US-AVAILABILITY
  - WS:LIVE-ENTRY-RADAR
  - WS:PROPHET-CONDITIONAL-FUSION
  - WS:GMI-THEME-GRAPH
  - WS:EARNINGS-INTELLIGENCE-OS
  - WS:STOCK-IDENTITY
  - WS:PROPHET-US-ENTRY-TIMING
  - WS:EVAL-OS-MEASUREMENT-LAW
decisions:
  - DEC:PROPHET-V4-THEIA-SOURCE-RIGHTS
landmines:
  - "THE OUTAGE was LIVE at 0A (2026-08-17) and STILL UNRESOLVED on the reader at the
    0B pin (2026-08-18T00Z: source_asof=2026-08-13, 206 plans): #5742 open; sibling
    sessions + operator own recovery (triage: push-freeze ruleset GH013, theta-m1
    label pin, runner saturation; overlapping bakes at 23:56Z). The candidate store
    data/us_prophet_rank/candidates/ + legacy-shadow parts remain stalled with it.
    V4 does NOT implement — a1 is acceptance-by-adoption. Current deltas:
    research/prophet_v4/POST_0A_RECONCILIATION_2026-08-17.md."
  - "Prophet index top-level asof is WALL-CLOCK (DSC:PROPHET-ASOF-IS-WALL-CLOCK);
    freshness = source_asof + per-plan cohorts. Run conclusions decouple from Prophet
    delivery in both directions (DSC:CANCELLED-DAILY-RUN-CAN-STILL-DELIVER-PROPHET)."
  - "Pages can diverge from git in BOTH directions: designed conservatism
    (daily.yml:5046-5092, Pages lags one cycle) AND the measured 08-16 violation
    (run 31913143619 — Pages served the first v3 board git never got; mechanics
    unresolved from source). Production is the VPS, not Pages."
  - "The served board and the plan book have different gates: build_stock_library.py
    writes us_standouts.json directly; prophet_bridge.select_candidates() is a
    downstream consumer that refuses buy_soon. FOUR stage derivations disagree on the
    page (CURRENT_STATE §8). One server contract is B3's job."
  - "PAID BOUNDARY (scoped, 0B): #5840 merged the ranked-board server-side split
    (free shell + premium remainder; PROVEN_LIVE at the 0B pin — VPS premiumdata 401,
    3-row anonymous shell, render receipt 5232c4c4). Per #5840's OWN scope, Act-Now,
    .topsetups, ran, and theme-tape member names REMAIN DOM-gated — residual
    commercial-boundary debt. Do not write 'all Prophet anonymous leakage fixed'."
  - "Vocabulary collisions: Radar G0/C1-C5 vs Fusion arena rungs C1-C5 vs
    prophet_arena C0-C7 execution policies vs audit C0-C4; two same-named 'arena'
    systems; _v2 paths are SCHEMA versions, not the v2 ranker era; two 'board history'
    stores. Disambiguation table: CURRENT_STATE §9 — binding on every handoff."
  - "TURN WATCH is an orphan desk this WS now owns: artifact stale (data_session
    2026-08-13), page never built, engine copy has zero template consumers."
  - "MP-1 (research/migration_packets/MP-1-prophet-board.md) is design-ratified with
    all spawn gates satisfied and NOT executed — B5/E2 build against it; its
    population re-source must be checked against DNR:KILL-PROPHET-POP-MERGE first."
  - "QLedger's control leg has never been populated on any of 46,630 claims
    (DSC:NO-QLEDGER-CLAIM-EVER-CARRIED-A-CONTROL-LEG); the plan ledger has no
    benchmark column. Do not describe V4 grading as control-matched until wired."
  - "Radar W4 activation proof is structurally owed (operator arm of
    ENTRY_RADAR_LIVE_ENABLE); B-15..B-19 dispositions post-#5370-heal are UNKNOWN —
    B2 opens with the matrix, do not assume the heal closed them."
do_not_redo:
  - "Do not spend a PR removing the bridge candidate cap: N_CANDIDATES=12 survives
    only as an OVERRIDDEN DEFAULT (prophet_bridge.py:146,1147) — production passes
    n=None (:4127; daily.yml:2270). A grep hitting the constant does not contradict
    this; observed narrow boards come from the admission gate chain, not a cap."
  - "Do not widen Conditional Fusion PR-3B (outcome-blind LOFO + member census, its
    own fresh session) into availability/Radar/lifecycle/V4-UI work — V4-E1 consumes
    the ACCEPTED registry after PR-3D."
  - "Do not build a second cross-family ranker, second theme graph, second earnings
    store, second forward grader, second publication truth, or a rival identity
    stack (masterplan §6.4 reject list; canonical owners in
    research/prophet_v4/CONTRACT_AND_OWNER_MAP.md)."
  - "Do not flatten Radar expert identities (G0/C1-C5) into one entry_signal boolean;
    entry-detector fusion is Radar's reserved F1_FUSION slot."
  - "Do not synthesize the missed Aug-14 session from later knowledge — exact
    reconstruction from Aug-14-knowable data or an explicit unrecoverable receipt."
artifacts:
  - research/prophet_v4/PROPHET_US_V4_RECOVERY_AND_INTELLIGENCE_GRAPH_OS_MASTERPLAN_BY_SOL_2026-08-17.md
  - research/prophet_v4/FABLE_HANDOFF_PROPHET_US_V4_0A_2026-08-17.md
  - research/prophet_v4/CURRENT_STATE_2026-08-17.md
  - research/prophet_v4/CAPABILITY_LEDGER.md
  - research/prophet_v4/ARCHITECTURE_FREEZE.md
  - research/prophet_v4/CONTRACT_AND_OWNER_MAP.md
  - research/prophet_v4/SOURCE_RIGHTS_AND_COVERAGE_REGISTRY.md
  - research/prophet_v4/EXPERIENCE_REFERENCE_COMPOSITIONS.md
  - research/prophet_v4/WAVE_GRAPH_AND_MERGE_ORDER.md
  - research/prophet_v4/V4_A1_AVAILABILITY_RECOVERY_HANDOFF.md
waves:
  - id: 0a
    title: "V4-0A — estate archaeology + architecture freeze. Merged #5832
      (squash ebce73b97288, 2026-08-17T13:18:55Z)."
    status: done
    pr: 5832
  - id: 0b
    depends_on: [0a]
    title: "V4-0B — post-0A records reconciliation (records only; scope narrowed by
      the 2026-08-17 Sol 0B handoff — no sibling record edits). Evidence:
      research/prophet_v4/POST_0A_RECONCILIATION_2026-08-17.md."
    status: done
    pr: 5847
  - id: a1
    depends_on: [0a]
    title: "V4-A1 — owed-session settlement recovery. DO NOT SPAWN: implementation is
      owned by the active Availability/outage sessions (incident receipt #5742);
      V4_A1_AVAILABILITY_RECOVERY_HANDOFF.md is the ACCEPTANCE CONTRACT Sol reviews
      the sibling return against — never a command to launch a competing session."
    status: todo
    next_action: >
      Acceptance-by-adoption only: when the Availability/outage return arrives, map it
      to the A1 gates and route to Sol for acceptance. A fresh board or a green run
      alone does not close this wave.
  - id: a2
    depends_on: [a1]
    title: "V4-A2 — canonical settlement manifest (prophet.settlement_manifest/v1)"
    status: todo
    next_action: >
      ADOPT FIRST: before any spawn, map the accepted Availability/outage return onto
      this capability; if the sibling durable fix already satisfies it, close by
      reference — only the unresolved delta may become a V4 wave.
  - id: a3
    depends_on: [a1]
    title: "V4-A3 — atomic publication + split-brain fence"
    status: todo
    next_action: >
      ADOPT FIRST: same rule as a2 — map the sibling return (and #5840's premium-plane
      split) before spawning; only the unresolved delta becomes a V4 wave.
  - id: a4
    depends_on: [a2, a3]
    title: "V4-A4 — availability fire-drill week"
    status: todo
  - id: b1
    depends_on: [a1]
    title: "V4-B1 — canonical candidate episode registry (prophet.candidate_episode/v1)"
    status: todo
  - id: b2
    depends_on: [b1]
    title: "V4-B2 — entry-event correction hardening (B-15..B-19)"
    status: todo
  - id: b3
    depends_on: [b1]
    title: "V4-B3 — orthogonal lifecycle contract (4 independent state fields)"
    status: todo
  - id: b4
    depends_on: [b2, b3]
    title: "V4-B4 — deterministic buyability/chase firewall (prophet.entry_availability/v1)"
    status: todo
  - id: b5
    depends_on: [b3, b4]
    title: "V4-B5 — Early Entry Desk MVP (TURN WATCH finally visible)"
    status: todo
  - id: b6
    depends_on: [b2]
    title: "V4-B6 — Radar observation-only activation (full-RTH-session proof)"
    status: todo
  - id: b7
    depends_on: [b6]
    title: "V4-B7 — Radar production UI + Prophet integration (executes Radar W9 under
      Radar ownership). 0B note: Radar W6 code merged (#5834, research_priority.v1 —
      ACCRUING attention ordering, commissioning owed, zero Prophet authority); W8
      (#5737) still open/reference-only; W9 absent. b7 inherits Radar's W9 deps."
    status: todo
  - id: c1
    depends_on: [b1]
    title: "V4-C1 — cohort-separated all-candidate ledger"
    status: todo
  - id: c2
    depends_on: [c1]
    title: "V4-C2 — us_prophet_v3_legacy_shadow (activates at cutover)"
    status: todo
  - id: c3
    depends_on: [b5]
    title: "V4-C3 — operator decision instrumentation"
    status: todo
  - id: d1
    depends_on: [0a]
    title: "V4-D1 — theme-source and identity census. DONE 2026-08-18: master census
      research/prophet_v4/D1_THEME_SOURCE_AND_IDENTITY_CENSUS_2026-08-18.md + 9
      machine artifacts in research/prophet_v4/d1/. Headlines: C6 thematic gap =
      2,368/3,253 (73%); graph company plane is ticker-string-keyed (D2's repair);
      two live graph data defects (GOLD reused-ticker, IBIT ETF-as-company); Citrini
      OPERATOR_HELD_ONLY; Theia DEC stands; 5 rights decisions routed."
    status: done
    pr: 5859
  - id: d2
    depends_on: [d1]
    title: "V4-D2 — canonical ontology + probation mapping, executing INSIDE/WITH the
      GMI lane. Spawn handoff ready:
      research/prophet_v4/V4_D2_ONTOLOGY_AND_PROBATION_HANDOFF.md (identity-grain
      repair via stock_identity, probation-only mapping breadth for 312 THS + 268
      finviz + 20 proxy baskets, forward-only PIT vintages, defect corrections
      through graph lineage). Commissioning = Sol adjudication with GMI."
    status: todo
  - id: d3
    depends_on: [d2]
    title: "V4-D3 — ThemeState consumption contract. D1's merge-order RECOMMENDATION
      (research/prophet_v4/D1_D3_W3B_MERGE_ORDER_RECOMMENDATION.md, pending Sol+GMI
      adjudication): GMI W3B builds theme_state/v1 AFTER d2; d3 becomes the
      Prophet-side consumption/join wave; W3B's charter must reconcile the
      pre-existing neuralweb thematic_state lineage; Finviz/THS-derived state stays
      internal-only pending the routed rights decision."
    status: todo
  - id: d4
    depends_on: [d3]
    title: "V4-D4 — peer and transmission features"
    status: todo
  - id: d5
    depends_on: [d1]
    title: "V4-D5 — V4 intelligence-vector contract (prophet.intelligence_vector/v1).
      D1 ruling (research/prophet_v4/D1_D5_READINESS_RULING.md):
      D5_CONTRACT_READY_AFTER_D1 — may run in parallel with d2/W3B on disjoint
      paths; theme family stays ACCRUING (null_reason theme_state_not_built) until
      d3; no ticker-string joins in the contract; SPARSE coverage band is the honest
      scan-tier default."
    status: todo
  - id: d6
    depends_on: [d5]
    title: "V4-D6 — earnings adapter. Premise updated 0B: EIOS E1P is LIVE for the
      golden AAPL FY2026 Q3 event workspace (#5842) and E2 is unblocked — but ONE
      golden event is not broad issuer coverage; d6 still waits on d5 and must not
      infer coverage from it."
    status: todo
  - id: d7
    depends_on: [d5]
    title: "V4-D7 — alt-data family adapters (one per family)"
    status: todo
  - id: e1
    depends_on: [b4, c1, d5]
    title: "V4-E1 — explainable deterministic V4 priority (extends Fusion registry
      post-3D). 0B note: Fusion PR-3B AND PR-3C (#5839) are merged; PR-3D remains the
      sibling acceptance boundary; V4 does not read/tune from the W3 forward race."
    status: todo
  - id: e2
    depends_on: [e1, b7, c2, a4]
    title: "V4-E2 — Prophet V4 primary experience + cutover"
    status: todo
  - id: e3
    depends_on: [c1, e1]
    title: "V4-E3 — listwise ranker challenger (shadow only)"
    status: todo
  - id: e4
    depends_on: [e3]
    title: "V4-E4 — conditional router/multi-head challenger (shadow only)"
    status: todo
  - id: e5
    depends_on: [d4, e3]
    title: "V4-E5 — temporal heterogeneous graph challenger (shadow only)"
    status: todo
  - id: e6
    depends_on: [e3, e4, e5]
    title: "V4-E6 — promotion gauntlet + V3 retirement ruling"
    status: todo
next_action: >
  V4-D1 complete. Route to Sol for three adjudications: (1) commission d2 with GMI
  per research/prophet_v4/V4_D2_ONTOLOGY_AND_PROBATION_HANDOFF.md; (2) ratify the
  D3/W3B merge-order recommendation with GMI; (3) optionally commission the d5
  contract-only lane in parallel (D1_D5_READINESS_RULING.md). Rights decisions
  routed in the census §7 await Chairman/Sol. A-lane unchanged: DO NOT SPAWN A1 —
  sibling-owned, acceptance-by-adoption (#5742); a2/a3 adopt-first.
---

## Context

Chairman-commissioned P0 (2026-08-17): Sol's masterplan
(`research/prophet_v4/PROPHET_US_V4_RECOVERY_AND_INTELLIGENCE_GRAPH_OS_MASTERPLAN_BY_SOL_2026-08-17.md`)
freezes the V4 thesis — surface by emergence, gate by the trade available now, rank by
intelligence, explain the evidence, let the Chairman decide. This workstream is the
INTEGRATION umbrella: it owns candidate-episode intake, board lifecycle, deterministic
entry availability, product projection, and operator workflow. It consumes — and never
duplicates — the sibling owners: Radar (expert events), Stock Identity (identity
epochs/routing), GMI (theme graph/state), EIOS (earnings), Conditional Fusion
(cross-family ranking machinery), Availability (rescue plane), Evaluation OS/QLedger
(outcome labels).

## Scope boundary

Wave definitions and acceptance live in masterplan §21; dependencies, merge order, and
path ownership in `research/prophet_v4/WAVE_GRAPH_AND_MERGE_ORDER.md` (its §4 rulings
govern every path shared with a registered sibling owner — engine/prophet_*.py belongs
to WS:PROPHET-US-ENTRY-TIMING and B2/B3/B4 execute jointly under it); nine numbered
architecture decisions in `research/prophet_v4/ARCHITECTURE_FREEZE.md` with the tenth
(wave dependencies/file ownership) frozen in the wave-graph doc. As each wave starts,
its owned paths are PROMOTED into this record's owns_paths (or the partner
workstream's) so the AgentOS collision detector can see them. Sibling wave
IDs (Radar W0-W9, Fusion PR-3x, GMI W3x, EIOS E0-E2) are never renamed by this program.
Future stores (candidate episode registry, availability artifacts, V4 rank projection)
enter `owns_paths:` when their waves create them — not before.

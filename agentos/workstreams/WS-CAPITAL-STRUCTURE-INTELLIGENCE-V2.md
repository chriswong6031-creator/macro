---
key: CAPITAL-STRUCTURE-INTELLIGENCE-V2
title: Capital Structure Intelligence V2 — issuer capital twin
objective: >
  Freeze and then build a point-in-time issuer financing state machine and
  capital-supply intelligence system that answers what an issuer can issue now,
  what it needs to fund, what supply can hit shareholders, what changed, and
  what that implies for catalysts, Neural Web, and later Prophet — without an
  SEC filing browser, an opaque dilution score, or a second canonical plane.
  Done for W0 = Sol/Chairman accept the 2026-08-18 masterplan as amended.
  Done for the program = deterministic twin families live, prophet_authority
  still false until per-feature gauntlet.
status: active
program: capital-structure-intelligence
repos: [macro]
owner: coo-fable
class: research
blast_radius: user_facing
ambiguity: scoped
owns_paths:
  - engine/capital_structure/
  - collectors/sec_capital_structure.py
  - collectors/sec_capital_structure_companyfacts.py
  - scripts/compile_capital_structure_events.py
  - scripts/compile_capital_structure_document_terms.py
  - scripts/compile_capital_structure_instrument_candidate_terms.py
  - scripts/compile_capital_structure_registration_lifecycles.py
  - scripts/build_capital_structure_projection.py
  - scripts/check_capital_structure_health.py
  - scripts/materialize_capital_structure_share_counts.py
  - contracts/capital_structure_source_manifest.schema.json
  - app/capital_structure.py
  - data/capital_structure/
  - docs/CAPITAL_STRUCTURE_INTELLIGENCE_CONTRACT.md
  - research/CAPITAL_STRUCTURE_INTELLIGENCE_V2_MASTERPLAN_2026-08-18.md
  - templates/capital_structure.html.j2
decisions:
  - DEC:CS-V2-EVIDENCE-IDENTITY-OCCURRENCE-BYTES
  - DEC:CS-V2-FIRST-KNOWN-AT-IS-CANONICAL-RETENTION-CLOCK
  - DEC:CS-V2-CLOSED-BUNDLE-ATOMIC-PERSISTENCE
  - DEC:CS-V2-WHOLE-GENERATION-APPEND-ONLY-FENCE
  - DEC:CS-V2-LIVE-TAIL-SEPARATE-FROM-BACKLOG
  - DEC:CS-V2-SIX-QUESTION-ONTOLOGY
  - DEC:CS-V2-W1B-SOL-ACCEPTED-NATURAL-PROOF-GATE
  - DEC:CS-V2-W1-IDENTITY-PUBLICATION-PROVEN-LIVE
  - DEC:CS-V2-W2A-CLASS-RESERVES-AND-HORIZON-FRESHNESS
  - DEC:CS-V2-W2B-500-LIVE-ENVELOPE
  - DEC:CS-V2-W2C-EXACT-DEPENDENCY-INCREMENTAL-DOCUMENT-TERMS
  - DEC:CS-V2-W2D-DUAL-DISCOVERY-CLOCK
discoveries:
  - DSC:CS-MANIFEST-ID-HASHES-RETRIEVAL-CLOCKS
  - DSC:CS-SOURCE-MANIFEST-UNSPECIFIED-MERGE
  - DSC:CS-THROUGHPUT-HEALTHY-HORIZON-STALE
  - DSC:CS-INSTRUMENT-AND-LIFECYCLE-COMPILERS-NOT-NIGHTLY
  - DSC:CS-EVENT-EDGES-NEAR-ZERO
  - DSC:CS-V2-W1B-NATURAL-CHAIN-PROVEN-LIVE
  - DSC:CS-V2-W2A-NATURAL-CHAIN-PROVEN-LIVE
  - DSC:CS-V2-W2B-NATURAL-CHAIN-PROVEN-LIVE
  - DSC:CS-V2-W2C-DOCUMENT-TERM-ESTATE-SCALING
  - DSC:CS-V2-W2D-DAILY-INDEX-READINESS
do_not_redo:
  - "Reopen PR #5792 ingestion freeze (AccessDenied / zero-progress health) without new evidence"
  - "Solve concurrent collect with an et_gate mutex (DEC:COLLECT-MUTEX-CANNOT-LIVE-IN-ET-GATE)"
  - "Rewrite historical manifest_id strings or PIT receipts"
  - "Add merge=union on data/capital_structure/source_manifest.jsonl"
  - "Push-time content-aware merge of source_manifest.jsonl (Sol AMEND 2026-08-18)"
  - "Create a BioCatalyst-specific or Prophet-specific capital ledger"
  - "Silently claim company_event.v1"
  - "Ship an opaque Capital Structure or dilution score"
  - "Encode Release 33-11418 as current law"
  - "Mint legacy:{source_id} as a new child occurrence key"
  - "Hash source.manifest_ids or PIT clocks into post-W1 event identity"
  - "Shortcut re-observation on the complete row alone"
  - "Persist only the changed members of an N+1 closed bundle"
  - "Treat a deselected/removed current member as re-observation when remaining members are unchanged"
  - "Re-review whether Sol accepted W1B #6044; the accepted PR body records PASS and the merge is on main"
  - "Dispatch a second daily run merely to accelerate the W1B production receipt"
  - "Reopen the proven-live W2A/W2B capacity, spill, lane, pacing, or carrier law for the W2C runtime repair"
  - "Create a document-term cache or second compiled-root truth store"
  - "Dispatch or rerun daily.yml to manufacture W2C/W2D proof; wait for the first natural scheduled chain containing both merges"
landmines:
  - "manifest_id_for hashes retrieval clocks (DSC:CS-MANIFEST-ID-HASHES-RETRIEVAL-CLOCKS)"
  - "Partial N+1 persist drops unchanged children from _current_manifest_bundle"
  - "Candidate-only classify_bundle_against_published misses deselected current members"
  - "Subset-hashing v2 manifest_id fights validate_manifest_ledger one-id-one-body"
  - "Concurrent daily.yml collect is still possible; CS must be idempotent"
  - "Share-count v2 and Company Facts are default-off / unprovisioned — not live"
  - "Incremental reuse is legal only for an exact closed manifest/content/parser dependency; --rebuild remains the whole-ledger retained-byte audit"
  - "W2C/W2D merged does not close W2; only the required first natural chain can promote the joint repair from BUILT_NOT_PROVEN"
artifacts:
  - research/CAPITAL_STRUCTURE_INTELLIGENCE_V2_MASTERPLAN_2026-08-18.md
  - research/CAPITAL_STRUCTURE_W2A_QUEUE_CENSUS_2026-08-21.md
  - research/CAPITAL_STRUCTURE_W2B_CAPACITY_QUALIFICATION_2026-08-23.md
  - research/CAPITAL_STRUCTURE_W2C_INCREMENTAL_DOCUMENT_TERMS_QUALIFICATION_2026-08-25.md
  - research/CAPITAL_STRUCTURE_W2D_SEC_DISCOVERY_QUALIFICATION_2026-08-25.md
  - docs/CAPITAL_STRUCTURE_INTELLIGENCE_CONTRACT.md
  - research/CAPITAL_STRUCTURE_ISSUER_STATE_W3_BUILD_DOCKET.md
  - research/CAPITAL_STRUCTURE_INTELLIGENCE_COMPETITIVE_TEARDOWN_AND_BUILD_DOCKET_2026-08-01.md
  - agentos/handoffs/CAPITAL-STRUCTURE-INTELLIGENCE-V2-2026-08-20.md
  - agentos/handoffs/CAPITAL-STRUCTURE-INTELLIGENCE-V2-2026-08-20-w1b-sol-acceptance-reconciliation.md
  - agentos/handoffs/CAPITAL-STRUCTURE-INTELLIGENCE-V2-2026-08-21.md
  - agentos/handoffs/CAPITAL-STRUCTURE-INTELLIGENCE-V2-2026-08-21-w2a.md
  - agentos/handoffs/CAPITAL-STRUCTURE-INTELLIGENCE-V2-2026-08-23-w2a-closeout.md
  - agentos/handoffs/CAPITAL-STRUCTURE-INTELLIGENCE-V2-2026-08-23-w2b.md
  - agentos/handoffs/CAPITAL-STRUCTURE-INTELLIGENCE-V2-2026-08-24-w2b-natural-proof.md
  - agentos/handoffs/CAPITAL-STRUCTURE-INTELLIGENCE-V2-2026-08-25-w2c.md
  - agentos/handoffs/CAPITAL-STRUCTURE-INTELLIGENCE-V2-2026-08-25-w2d.md
next_action: >
  W2A and W2B are PROVEN_LIVE. W2C PR #6415 merged as
  5bc31a700406c2a90771d0ce86d230d28c73c86c and W2D PR #6424 merged as
  cadfa403033f9de338e9f490abac05eb08cbb293 after exact-head Sol release;
  both repairs are BUILT_NOT_PROVEN. Do not dispatch a proof run. Observe only
  the first natural scheduled collector -> Capital Structure chain whose
  checkout contains both merges. Only that chain can close W2 if it proves
  healthy same-day discovery/reconciliation, zero unserved LIVE work, and
  Capital Structure runtime below the unchanged warning. W3 and W4 remain held.
waves:
  - id: W0
    title: Architecture freeze, estate audit, competitor/regulatory refresh
    status: done
    pr: 5901
    next_action: >
      Accepted by Sol/Chairman. W1 authorized.
  - id: W1
    title: Evidence identity + whole-generation append-only fence
    status: done
    depends_on: [W0]
    pr: 5959
    next_action: >
      Merged as #5959 / b7004b132509. W1 identity/publication foundation is
      PROVEN_LIVE after W1A #6012, W1B #6044, and natural chain
      32426513915 / generation 3ba28993b741.
  - id: W1A
    title: Clock-independent event identity, no new legacy occurrence, bundle re-obs
    status: done
    depends_on: [W1]
    pr: 6012
    next_action: >
      Merged as #6012. Identity accepted; W1B closes closed-bundle persist.
  - id: W1B
    title: Accession-wide closed-bundle atomic persistence
    status: done
    depends_on: [W1A]
    pr: 6044
    next_action: >
      Done. Merged as #6044 / ec388d963190. Natural collect→CS proof is
      daily run 32426513915 (collect 96609474282, capital_structure
      96637756516) publishing generation 3ba28993b741.
      DSC:CS-V2-W1B-NATURAL-CHAIN-PROVEN-LIVE. Do not start W2 here.
  - id: W2
    title: Capacity-separated retrieval and current-horizon closure gate
    status: in_progress
    depends_on: [W1B]
    next_action: >
      W2A/W2B are PROVEN_LIVE and inherited LIVE debt reached zero in natural
      run 32786919396. W2C #6415 / 5bc31a700406 and W2D #6424 /
      cadfa403033f are merged but BUILT_NOT_PROVEN. Use only the first natural
      scheduled chain containing both merges to prove runtime below warning,
      healthy current discovery/reconciliation, zero unserved LIVE work, and
      the frozen W1/W2 invariants. W3/W4 remain held until that proof closes W2.
  - id: W2A
    title: LIVE_TAIL / RECOVERY / HISTORICAL_BACKFILL plus horizon health
    status: done
    depends_on: [W1B]
    pr: [6220, 6282]
    next_action: >
      Done and proven live by run 32603557988 and generation 73d9810fe3f9.
      Preserve its scheduling, truth, identity, and projection laws in W2B.
  - id: W2B
    title: Existing-carrier capacity envelope 540 = 500 / 20 / 20
    status: done
    depends_on: [W2A]
    pr: [6287, 6349]
    next_action: >
      Done and proven live by natural run 32671784885, collect job 97273624140,
      Capital Structure job 97292842139, and generation 8a3628f1c2bb. Preserve
      the 500/20/20 law through W2C/W2D and final natural proof.
  - id: W2C
    title: Exact-dependency incremental document-term runtime
    status: in_progress
    depends_on: [W2B]
    pr: 6415
    next_action: >
      Sol-released implementation merged as #6415 /
      5bc31a700406c2a90771d0ce86d230d28c73c86c. Capability state is
      BUILT_NOT_PROVEN pending the joint first natural W2C/W2D chain; preserve
      full --rebuild audit authority and all W2B scheduling/runtime boundaries.
  - id: W2D
    title: SEC/New York discovery readiness and same-day accession observation
    status: in_progress
    depends_on: [W2B]
    pr: 6424
    next_action: >
      Sol released exact head 3bc96bbdaf7512f4136af224bce1be26618050a9
      in PR #6424 comment 5422154666; it squash-merged as
      cadfa403033f9de338e9f490abac05eb08cbb293. Capability state is
      BUILT_NOT_PROVEN pending the same first natural chain. Do not dispatch or
      rerun daily.yml solely for proof.
  - id: W3
    title: Capital Changes Desk and issuer Capital Twin UX on honest states
    status: todo
    depends_on: [W2]
  - id: W4
    title: Registration and remaining-capacity state machine (I.B.6, ATM, ELOC)
    status: todo
    depends_on: [W2]
  - id: W5
    title: Instrument overhang and disclosed toxic-term facts
    status: todo
    depends_on: [W4]
  - id: W6
    title: Share basis, corporate actions, cash and funding need
    status: todo
    depends_on: [W4]
  - id: W7
    title: Neural Web typed change events and Prophet shadow features
    status: todo
    depends_on: [W4, W5, W6]
---

Capital Structure V2 recovers the 2026-08-01 product thesis after PR #5792
fixed ingestion. Destination is a PIT issuer capital twin. W0 research and
this AMEND were executed by Cursor Grok 4.6; COO Fable remains the program
owner. W1/W1A/W1B are PROVEN_LIVE. W2A and W2B are DONE and PROVEN_LIVE.
Natural run 32786919396 drained inherited LIVE debt from 337 to zero. W2C
(#6415 / 5bc31a700406) and W2D (#6424 / cadfa403033f) are now merged but
BUILT_NOT_PROVEN; W2 remains in progress until the first natural scheduled
chain containing both proves the runtime and discovery falsifiers closed.
W3/W4 remain unstarted and held behind W2.

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
discoveries:
  - DSC:CS-MANIFEST-ID-HASHES-RETRIEVAL-CLOCKS
  - DSC:CS-SOURCE-MANIFEST-UNSPECIFIED-MERGE
  - DSC:CS-THROUGHPUT-HEALTHY-HORIZON-STALE
  - DSC:CS-INSTRUMENT-AND-LIFECYCLE-COMPILERS-NOT-NIGHTLY
  - DSC:CS-EVENT-EDGES-NEAR-ZERO
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
landmines:
  - "manifest_id_for hashes retrieval clocks (DSC:CS-MANIFEST-ID-HASHES-RETRIEVAL-CLOCKS)"
  - "Partial N+1 persist drops unchanged children from _current_manifest_bundle"
  - "Candidate-only classify_bundle_against_published misses deselected current members"
  - "Subset-hashing v2 manifest_id fights validate_manifest_ledger one-id-one-body"
  - "Concurrent daily.yml collect is still possible; CS must be idempotent"
  - "Projection freshness is compiler age, not information horizon"
  - "Share-count v2 and Company Facts are default-off / unprovisioned — not live"
artifacts:
  - research/CAPITAL_STRUCTURE_INTELLIGENCE_V2_MASTERPLAN_2026-08-18.md
  - docs/CAPITAL_STRUCTURE_INTELLIGENCE_CONTRACT.md
  - research/CAPITAL_STRUCTURE_ISSUER_STATE_W3_BUILD_DOCKET.md
  - research/CAPITAL_STRUCTURE_INTELLIGENCE_COMPETITIVE_TEARDOWN_AND_BUILD_DOCKET_2026-08-01.md
needs_ceo:
  question: >
    Accept W1B membership-subtraction amend on #6044 so a deselected
    current member forces a whole-candidate-bundle revision, after the
    original W1B persist law? Hold W2 until W1B merges and the first
    natural collector → Capital Structure chain containing W1B is
    production-proven.
  options:
    - Accept the W1B amend; authorize Wave 2 only after merge and natural CS-path proof
    - Accept with further named amendments
    - Reject; name which closed-bundle ruling to reopen
  recommendation: >
    Accept the W1B amend. Do not start Wave 2 in this PR. Do not rewrite
    historical event_ids or v1 manifests. Do not dispatch a second daily run.
  by_when: 2026-08-25
next_action: >
  Sol review of the W1B membership-subtraction amend on #6044; do not
  merge until accepted; do not start W2; do not create W1C.
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
      Merged as #5959 / b7004b132509. Identity defects closed by W1A.
  - id: W1A
    title: Clock-independent event identity, no new legacy occurrence, bundle re-obs
    status: done
    depends_on: [W1]
    pr: 6012
    next_action: >
      Merged as #6012. Identity accepted; W1B closes closed-bundle persist.
  - id: W1B
    title: Accession-wide closed-bundle atomic persistence
    status: in_progress
    depends_on: [W1A]
    branch: claude/cs-v2-w1b-closed-bundle
    pr: 6044
    next_action: >
      Sol review of the W1B membership-subtraction amend on #6044.
      Do not merge until accepted. Do not start W2. Do not create W1C.
  - id: W2
    title: LIVE_TAIL / RECOVERY / HISTORICAL_BACKFILL plus horizon health
    status: todo
    depends_on: [W1B]
    next_action: >
      Start only after W1B merge and the first natural post-W1B CS chain is proven.
  - id: W3
    title: Capital Changes Desk and issuer Capital Twin UX on honest states
    status: todo
    depends_on: [W1B]
  - id: W4
    title: Registration and remaining-capacity state machine (I.B.6, ATM, ELOC)
    status: todo
    depends_on: [W1B]
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
owner, not the executor of this freeze. Implementation starts at W1 only
after Sol/Chairman acceptance.

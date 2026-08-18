---
key: CAPITAL-STRUCTURE-INTELLIGENCE-V2
title: Capital Structure Intelligence V2 — issuer capital twin
objective: >
  Freeze and then build a point-in-time issuer financing state machine and
  capital-supply intelligence system that answers what an issuer can issue now,
  what it needs to fund, what supply can hit shareholders, what changed, and
  what that implies for catalysts, Neural Web, and later Prophet — without an
  SEC filing browser, an opaque dilution score, or a second canonical plane.
  Done for W0 = Sol/Chairman accept the 2026-08-18 masterplan. Done for the
  program = deterministic twin families live, prophet_authority still false
  until per-feature gauntlet.
status: awaiting_review
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
  - DEC:CS-V2-IDENTITY-DUAL-READ
  - DEC:CS-V2-GIT-REMAINS-GENERATION-SELECTOR
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
  - "Create a BioCatalyst-specific or Prophet-specific capital ledger"
  - "Silently claim company_event.v1"
  - "Ship an opaque Capital Structure or dilution score"
  - "Encode Release 33-11418 as current law"
  - "Start W1 identity implementation before Sol/Chairman accept W0"
landmines:
  - "manifest_id_for hashes retrieval clocks (DSC:CS-MANIFEST-ID-HASHES-RETRIEVAL-CLOCKS)"
  - "CS push uses git pull -X theirs on unspecified-merge source_manifest.jsonl"
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
    Accept the Capital Structure Intelligence V2 architecture freeze
    (research/CAPITAL_STRUCTURE_INTELLIGENCE_V2_MASTERPLAN_2026-08-18.md)
    and authorize only Wave 1 identity/idempotency work after this PR merges?
  options:
    - Accept freeze; authorize Wave 1 only after merge
    - Accept freeze with named amendments
    - Reject; name which ruling to reopen
  recommendation: >
    Accept freeze. Do not start Wave 1 in this PR. Do not drain the historical
    backlog as a substitute for live-tail. Identity is the first implementation
    wave because the source-identity audit proved a DNR violation.
  by_when: 2026-08-25
next_action: >
  Sol/Chairman review this architecture PR; do not merge until accepted; do not
  start Wave 1 identity implementation.
waves:
  - id: W0
    title: Architecture freeze, estate audit, competitor/regulatory refresh
    status: in_progress
    next_action: >
      This research PR. Stop when CI is green and the PR is handed to
      Sol/Chairman. Do not merge. Do not start W1.
  - id: W1
    title: Identity dual-read, observation log, concurrent-safe ledger merge
    status: todo
    depends_on: [W0]
    next_action: >
      Execute only after W0 is accepted. Masterplan §19 is the bounded handoff.
  - id: W2
    title: LIVE_TAIL / RECOVERY / HISTORICAL_BACKFILL plus horizon health
    status: todo
    depends_on: [W1]
  - id: W3
    title: Capital Changes Desk and issuer Capital Twin UX on honest states
    status: todo
    depends_on: [W1]
  - id: W4
    title: Registration and remaining-capacity state machine (I.B.6, ATM, ELOC)
    status: todo
    depends_on: [W1]
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
fixed ingestion. The destination is a PIT issuer capital twin, not a filing
browser. W0 is docs-only. Implementation starts at W1 only after acceptance.

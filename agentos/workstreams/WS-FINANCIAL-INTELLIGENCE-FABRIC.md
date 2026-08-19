---
key: FINANCIAL-INTELLIGENCE-FABRIC
title: Mastermind Financial Intelligence Fabric
objective: >
  Build one governed Financial Intelligence Fabric that turns filings and earnings
  events into reversible financial facts, statements, disclosure changes, forensic
  findings, peer context, and receipt-bearing packets, served through Filing
  Forensics, Fundamental Forensics, Earnings Intelligence, Terminal, dossiers,
  Neural Web, API, and exports. Done means the FIF-0..FIF-11 waves in the 2026-08-16
  masterplan are merged and live, with display/context authority at birth and no
  second semantic model.
status: active
program: fundamental-forensics
repos: [macro, terminal]
owner: coo-fable
class: build
blast_radius: reversible
ambiguity: scoped
owns_paths:
  - research/MASTERMIND_FINANCIAL_INTELLIGENCE_FABRIC_MASTERPLAN_2026-08-16.md
  - research/financial_intelligence_fabric/
  - contracts/financial_intelligence_packet.schema.json
  - engine/fundamental_forensics/financial_intelligence_packet.py
  - engine/fundamental_forensics/synthetic_filing_package.py
  - scripts/build_financial_intelligence_packet.py
  - tests/test_fundamental_forensics_financial_intelligence_packet.py
  - tests/test_fundamental_forensics_financial_intelligence_packet_r2.py
  - tests/test_fundamental_forensics_financial_intelligence_packet_r3.py
  - tests/fixtures/fundamental_forensics/filing_package_raw_ledger_v1.json
  - tests/fixtures/fundamental_forensics/expected_financial_intelligence_packet_v1.json
  - engine/fundamental_forensics/query_service.py
  - tests/test_fundamental_forensics_financial_query_service.py
  - tests/test_fundamental_forensics_financial_query_api.py
depends_on: []
discoveries:
  - DSC:COMPANYFACTS-CANNOT-FEED-CORE-METRIC-QUERY
  - DSC:PR-HOLD-REQUIRES-NATIVE-AUTOMERGE-DISARM
  - DSC:REVIEW-HOLD-PROSE-IS-NOT-FAIL-CLOSED
decisions:
  - DEC:FIF-1-INDEPENDENT-FILING-PACKAGE-FIXTURE
  - DEC:FIF-1R-HERMETIC-PACKET-CONTRACT
  - DEC:FIF-ENTITY-ID-IS-NOT-CIK
  - DEC:FIF-REVISION-ROOT-PRIOR-REVISED
  - DEC:FIF-PACKET-GOVERNANCE-IS-CUTOFF-VISIBLE
  - DEC:FIF-1-V1-FROZEN
next_action: >
  FIF-2A is fixture_proven on PR #5983 and held for Sol review. Do not
  merge until that review accepts. Do not start FIF-2B. Do not claim a
  production issuer query service. Native auto-merge stays disarmed.
landmines:
  - >
    Core catalog is consolidated_only. Company Facts conversion sets
    dimensions_known=false. Querying companyfacts_versions.json through
    load_core_metric_registry yields unknown_dimension_scope, never 1050/1060.
    See DSC:COMPANYFACTS-CANNOT-FEED-CORE-METRIC-QUERY and
    DEC:FIF-1-INDEPENDENT-FILING-PACKAGE-FIXTURE.
  - >
    Relabeling the B4 attested_occurrence evidence bridge as revenue is a hard
    registry error. Monkeypatching _fact_dimensions_allowed is a workaround the
    kernel exists to prevent.
  - >
    PR #5799 owns Earnings Intelligence E0/E1/E2 documents. FIF must not edit them.
  - >
    Legacy attested-history completion remains WS:CALCBENCH-FILING-FORENSICS-PARITY
    and is blocked on the protected writer credential. That gate still binds
    production issuer admission (FIF-3+). It does not block synthetic/semantic
    FIF-1 packet-contract work.
  - >
    Removing merge-on-green does not disable GitHub native auto-merge.
    See DSC:PR-HOLD-REQUIRES-NATIVE-AUTOMERGE-DISARM. Even both disarmed plus
    PR-body prose is not fail-closed; see DSC:REVIEW-HOLD-PROSE-IS-NOT-FAIL-CLOSED.
do_not_redo:
  - Do not create a second semantic model, query kernel, or metric registry.
  - Do not fetch SEC data, write R2, add an API, page, detector, peer engine, LLM, or score in FIF-1.
  - Do not debug or replace the attested-history Wave 0B credential path.
  - Do not reopen frozen financial_intelligence_packet.v1 semantics; FIF-1 is DONE (DEC:FIF-1-V1-FROZEN).
  - FIF-2A is the authenticated canonical query bridge only; do not start FIF-2B (statements, revisions, trace, packet-read, bulk).
  - Do not claim production issuer coverage; FIF-2A is fixture-proven against FIP1. FIF-3 wires admitted issuer packages.
  - Do not manufacture a filing-authority fixture by flipping dimensions_known or injecting revision_of onto Company Facts rows.
  - Do not put filesystem, schema, or digest discovery inside assemble_financial_intelligence_packet.
  - Do not silently add unrequested metrics to the user cells array.
  - Do not treat removal of merge-on-green as a merge hold; disable GitHub native auto-merge too.
  - Do not treat PR-body "do not merge" prose as a fail-closed Sol-review gate.
  - Do not mix a CI-control-plane / sol-review-required queue into a FIF packet PR.
  - Do not rewrite source-native SEC/XBRL identity to mint a Mastermind issuer ID.
  - Do not use the live full-registry digest as historical packet identity.
waves:
  - id: FIF-0
    title: Program reset — land masterplan, naming, and collision map
    status: done
    next_action: Masterplan and FIF-1 handoff remain the program source of truth.
  - id: FIF-1
    title: Golden financial_intelligence_packet.v1 hermetic vertical slice
    status: done
    depends_on: [FIF-0]
    pr: 5889
    next_action: >
      FROZEN on main at f4183edade53603fad7a97f702eb4c6e5eabff5d.
      packet_id fip_18e2f725f6ba20678d0612bb. Do not reopen. Do not create FIF-1R4.
  - id: FIF-2
    title: Read-only financial query API
    status: in_progress
    depends_on: [FIF-1]
    next_action: >
      FIF-2A fixture_proven on PR #5983, held for Sol review. FIF-2 remains
      in_progress. Do not start FIF-2B. Production issuer coverage is FIF-3.
  - id: FIF-3
    title: Golden five-issuer vertical slice
    status: todo
    depends_on: [FIF-2]
  - id: FIF-4
    title: Filing Forensics V2 product MVP
    status: todo
    depends_on: [FIF-3]
  - id: FIF-5
    title: Cross-universe discovery
    status: todo
    depends_on: [FIF-4]
  - id: FIF-6
    title: Peer Lab and semantic scale
    status: todo
    depends_on: [FIF-5]
  - id: FIF-7
    title: Earnings, non-GAAP, KPI, and guidance convergence
    status: todo
    depends_on: [FIF-3]
  - id: FIF-8
    title: Specialist accounting and disclosure packs
    status: todo
    depends_on: [FIF-6]
  - id: FIF-9
    title: API, exports, and Excel
    status: todo
    depends_on: [FIF-2]
  - id: FIF-10
    title: Neural Web, outcomes, and Prophet shadow
    status: todo
    depends_on: [FIF-4]
  - id: FIF-11
    title: Broad scale and independent closure
    status: todo
    depends_on: [FIF-7, FIF-8, FIF-9, FIF-10]
---

# Financial Intelligence Fabric

Program reset for Filing Forensics / Fundamental Forensics. The Calcbench-parity
effort is reclassified as an external capability ledger, not the product name.

Canonical documents:

- `research/MASTERMIND_FINANCIAL_INTELLIGENCE_FABRIC_MASTERPLAN_2026-08-16.md`
- `research/financial_intelligence_fabric/FIF_1_GOLDEN_FINANCIAL_INTELLIGENCE_PACKET_HANDOFF_2026-08-16.md`

Legacy attested-history completion remains `WS:CALCBENCH-FILING-FORENSICS-PARITY`
and is blocked on the protected writer credential. This workstream does not
replace that credential path. Synthetic/semantic FIF-1 work is not blocked on
that gate; production issuer promotion still is.

FIF-1 preflight found no existing packet contract. The operator chose
`DEC:FIF-1-INDEPENDENT-FILING-PACKAGE-FIXTURE`. Operator review of PR #5809
then required FIF-1R (`DEC:FIF-1R-HERMETIC-PACKET-CONTRACT`) and FIF-1R2
contract closure. #5837 merged those R2 foundations prematurely on
2026-08-17. Sol's source review accepted the R2 architecture but rejected
v1 freeze over against-input numeric proof, mixed multi-hop revision
semantics, accidental entity_id==CIK law, and unbounded reconvergent graph
validation. FIF-1R3 closed those defects on PR #5889. Sol freeze-reviewed accepted head
`e2a584496b08e68ca6054954142050db9e2c587b` as PASS / ACCEPTED_FOR_LANDING.
#5889 squash-merged as `f4183edade53603fad7a97f702eb4c6e5eabff5d`.
`financial_intelligence_packet.v1` is FROZEN. FIF-1 is DONE. FIF-2A is
the authenticated HTTP adapter over that frozen kernel
(`POST /api/forensics/v1/financial/query`). It is fixture-proven, not a
production issuer service, and is held for Sol review. Do not start
FIF-2B. Do not create FIF-1R4. Do not reopen accepted packet semantics.

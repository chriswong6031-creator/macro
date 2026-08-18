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
next_action: >
  Sol reviews the FIF-1R3 semantic-closure PR. Do not merge until that review
  accepts. Do not start FIF-2. Do not mix a CI-control-plane redesign into this
  packet PR.
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
  - Do not start FIF-2 until FIF-1 is accepted.
  - Do not manufacture a filing-authority fixture by flipping dimensions_known or injecting revision_of onto Company Facts rows.
  - Do not put filesystem, schema, or digest discovery inside assemble_financial_intelligence_packet.
  - Do not silently add unrequested metrics to the user cells array.
  - Do not treat removal of merge-on-green as a merge hold; disable GitHub native auto-merge too.
  - Do not treat PR-body "do not merge" prose as a fail-closed Sol-review gate.
  - Do not mix a CI-control-plane / sol-review-required queue into a FIF packet PR.
waves:
  - id: FIF-0
    title: Program reset — land masterplan, naming, and collision map
    status: done
    next_action: Masterplan and FIF-1 handoff remain the program source of truth.
  - id: FIF-1
    title: Golden financial_intelligence_packet.v1 hermetic vertical slice
    status: in_progress
    depends_on: [FIF-0]
    next_action: >
      Sol reviews FIF-1R3 semantic closure. Against-input must prove numbers
      against the query kernel; revision rows separate root/prior/revised;
      entity_id is not CIK; graph validation is O(V+E). v1 freeze waits on
      that review. Do not start FIF-2.
  - id: FIF-2
    title: Read-only financial query API
    status: todo
    depends_on: [FIF-1]
    next_action: Wait for FIF-1 acceptance. Do not start FIF-2.
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
validation. FIF-1R3 closes those defects. FIF-1 stays in progress until Sol
accepts. FIF-2 is still stopped.

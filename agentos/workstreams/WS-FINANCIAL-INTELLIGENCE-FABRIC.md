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
depends_on:
  - WS:CALCBENCH-FILING-FORENSICS-PARITY
discoveries:
  - DSC:COMPANYFACTS-CANNOT-FEED-CORE-METRIC-QUERY
next_action: >
  Operator decides how FIF-1 may obtain governed metric cells from
  tests/fixtures/fundamental_forensics/companyfacts_versions.json. Do not implement
  the packet until that decision is recorded. Recommended default: re-spec FIF-1
  onto filing-package-shaped facts (dimensions_known=true, typed revision_of) and
  keep Company Facts as occurrence-inventory receipts only.
landmines:
  - >
    PR #5794 still owns app/forensics.py, private_state, health, Filing Forensics
    UI/site, and CI registration files. FIF-1 must not touch those files.
  - >
    PR #5799 owns Earnings Intelligence E0/E1/E2 documents. FIF must not edit them.
  - >
    Core catalog is consolidated_only. Company Facts conversion sets
    dimensions_known=false. Querying the fixture through load_core_metric_registry
    yields unknown_dimension_scope, never 1050/1060. See
    DSC:COMPANYFACTS-CANNOT-FEED-CORE-METRIC-QUERY.
  - >
    Relabeling the B4 attested_occurrence evidence bridge as revenue is a hard
    registry error. Monkeypatching _fact_dimensions_allowed is a workaround the
    kernel exists to prevent.
do_not_redo:
  - Do not create a second semantic model, query kernel, or metric registry.
  - Do not fetch SEC data, write R2, add an API, page, detector, peer engine, LLM, or score in FIF-1.
  - Do not debug or replace the attested-history Wave 0B credential path.
  - Do not start FIF-2 until FIF-1 is accepted and PR #5794 no longer owns app routes.
waves:
  - id: FIF-0
    title: Program reset — land masterplan, naming, and collision map
    status: in_progress
    next_action: >
      Keep the 2026-08-16 masterplan and FIF-1 execution handoff as the program
      source of truth. Do not expand FIF-0 into a capability-ledger build in the
      same PR as the FIF-1 stop.
  - id: FIF-1
    title: Golden financial_intelligence_packet.v1 hermetic vertical slice
    status: in_progress
    depends_on: [FIF-0]
    next_action: >
      Stopped on preflight. Operator must choose the query input shape before any
      packet code is written.
  - id: FIF-2
    title: Read-only financial query API
    status: todo
    depends_on: [FIF-1]
    next_action: Wait for FIF-1 acceptance and PR #5794 route-conflict clearance.
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
    depends_on: [FIF-9, FIF-10]
---

# Financial Intelligence Fabric

Program reset for Filing Forensics / Fundamental Forensics. The Calcbench-parity
effort is reclassified as an external capability ledger, not the product name.

Canonical documents:

- `research/MASTERMIND_FINANCIAL_INTELLIGENCE_FABRIC_MASTERPLAN_2026-08-16.md`
- `research/financial_intelligence_fabric/FIF_1_GOLDEN_FINANCIAL_INTELLIGENCE_PACKET_HANDOFF_2026-08-16.md`

Legacy attested-history completion remains `WS:CALCBENCH-FILING-FORENSICS-PARITY`
and is blocked on the protected writer credential. This workstream does not
replace that credential path.

FIF-1 preflight on `origin/main` `3b0c7dbbcc4d` found no existing
`financial_intelligence_packet` contract. The first code PR is blocked on
`DSC:COMPANYFACTS-CANNOT-FEED-CORE-METRIC-QUERY`.

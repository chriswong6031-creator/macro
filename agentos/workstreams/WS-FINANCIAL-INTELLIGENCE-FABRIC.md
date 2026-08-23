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
  - engine/fundamental_forensics/revision_service.py
  - tests/test_fundamental_forensics_financial_query_service.py
  - tests/test_fundamental_forensics_financial_query_api.py
  - tests/test_fundamental_forensics_financial_revision_service.py
  - tests/test_fundamental_forensics_financial_revision_api.py
  - engine/fundamental_forensics/packet_service.py
  - tests/test_fundamental_forensics_financial_packet_service.py
  - tests/test_fundamental_forensics_financial_packet_api.py
  - engine/fundamental_forensics/statement_graph.py
  - engine/fundamental_forensics/statement_service.py
  - tests/test_fundamental_forensics_financial_statement_service.py
  - tests/test_fundamental_forensics_financial_statement_api.py
  - tests/fixtures/fundamental_forensics/aapl_10k_2025/
  - research/financial_intelligence_fabric/FIF_3A1_REUSE_MAP.md
  - contracts/statement_cell.v1.md
  - scripts/capture_fif3a1_aapl_package.py
depends_on: []
discoveries:
  - DSC:COMPANYFACTS-CANNOT-FEED-CORE-METRIC-QUERY
  - DSC:PR-HOLD-REQUIRES-NATIVE-AUTOMERGE-DISARM
  - DSC:REVIEW-HOLD-PROSE-IS-NOT-FAIL-CLOSED
  - DSC:AAPL-LABEL-RESOURCES-SHARE-XLINK-LABEL
  - DSC:AAPL-PRODUCT-SERVICE-HYPERCUBE-PRECEDES-LINE-ITEMS
  - DSC:AAPL-CF-BEGINNING-CASH-IS-INSTANT-IN-DURATION-COLUMNS
decisions:
  - DEC:FIF-1-INDEPENDENT-FILING-PACKAGE-FIXTURE
  - DEC:FIF-1R-HERMETIC-PACKET-CONTRACT
  - DEC:FIF-ENTITY-ID-IS-NOT-CIK
  - DEC:FIF-REVISION-ROOT-PRIOR-REVISED
  - DEC:FIF-PACKET-GOVERNANCE-IS-CUTOFF-VISIBLE
  - DEC:FIF-1-V1-FROZEN
  - DEC:FIF-2-DONE-STATEMENTS-MOVE-TO-FIF-3
  - DEC:FIF-3A1-REUSE-MAP
  - DEC:FIF-3A1-ISSUERMASTER-IS-THE-IDENTITY-READER
  - DEC:FIF-3A1-DISPLAYED-TABLE-IS-THE-COMPOSITION
  - DEC:FIF-3A1-PACKAGE-WITNESS-ADMISSION
  - DEC:FIF-3A1-CALC-NETWORKS-ARE-ROLE-LOCAL
next_action: >
  FIF-1 is DONE / FROZEN. FIF-2 is DONE / FIXTURE_PROVEN SERVICE
  SUBSTRATE (DEC:FIF-2-DONE-STATEMENTS-MOVE-TO-FIF-3). FIF-2A/B/C remain
  ACCEPTED / FIXTURE_PROVEN / ON_MAIN. A dedicated FIF-2D fixture-only
  trace route is rejected; company statements moved into FIF-3. FIF-3 is
  IN_PROGRESS. FIF-3A1 is BUILT_NOT_ACCEPTED (AAPL 2025 10-K as-reported
  statements). Do not reopen FIF-2A/2B/2C. Do not claim production issuer
  coverage. Do not start the next AAPL slice.
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
    Apple FY2025 10-K presentation prefixes the Product/Service hypercube
    before line items while HTML nests Products/Services under Net sales.
    Reconstruct the captured tables. See DSC:AAPL-PRODUCT-SERVICE-HYPERCUBE-PRECEDES-LINE-ITEMS
    and DEC:FIF-3A1-DISPLAYED-TABLE-IS-THE-COMPOSITION.
  - >
    Cash-flow beginning cash is an instant fact in duration columns.
    See DSC:AAPL-CF-BEGINNING-CASH-IS-INSTANT-IN-DURATION-COLUMNS.
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
    PR-body prose is not fail-closed; see DSC:REVIEW-HOLD-PROSE-IS-NOT-FAIL-CLOSED
    (additional evidence: PR #6157 merged 2026-08-21T16:08:36Z while HOLD FOR SOL
    remained in the body and comments).
do_not_redo:
  - Do not create a second semantic model, query kernel, or metric registry.
  - Do not fetch SEC data, write R2, add an API, page, detector, peer engine, LLM, or score in FIF-1.
  - Do not debug or replace the attested-history Wave 0B credential path.
  - Do not reopen frozen financial_intelligence_packet.v1 semantics; FIF-1 is DONE (DEC:FIF-1-V1-FROZEN).
  - FIF-2A is ACCEPTED / FIXTURE_PROVEN; do not reopen A–D or add FIF-2A hardening.
  - FIF-2B is ACCEPTED / FIXTURE_PROVEN; do not reopen revision projection, packet identity, or add FIF-2B hardening.
  - FIF-2C is ACCEPTED / FIXTURE_PROVEN; do not reopen packet HTTP identity, unsupported-cell 200 vs query/revision 400, or add FIF-2C hardening.
  - FIF-2D dedicated fixture-only trace is rejected (DEC:FIF-2-DONE-STATEMENTS-MOVE-TO-FIF-3); do not build it.
  - Do not claim production issuer coverage; FIF-2A/FIF-2B/FIF-2C are fixture-proven against FIP1. FIF-3A1 is a golden AAPL fixture vertical, not attested admission.
  - Do not manufacture a filing-authority fixture by flipping dimensions_known or injecting revision_of onto Company Facts rows.
  - Do not put filesystem, schema, or digest discovery inside assemble_financial_intelligence_packet.
  - Do not silently add unrequested metrics to the user cells array.
  - Do not treat removal of merge-on-green as a merge hold; disable GitHub native auto-merge too.
  - Do not treat PR-body "do not merge" prose as a fail-closed Sol-review gate.
  - Do not mix a CI-control-plane / sol-review-required queue into a FIF packet PR.
  - Do not treat raw presentation order as AAPL as-reported composition.
  - Do not build a generic segment/dimension engine from the AAPL Product/Service table.
  - Do not independently resolve issuer→security; use IssuerMaster.
  - Do not call this a production issuer service.
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
    status: done
    depends_on: [FIF-1]
    pr: [5983, 6157, 6235, 6254]
    next_action: >
      DONE / FIXTURE_PROVEN SERVICE SUBSTRATE. FIF-2A #5983, FIF-2B #6157,
      FIF-2C #6235, records #6254. FIF-2D fixture-only trace rejected;
      statements moved to FIF-3 (DEC:FIF-2-DONE-STATEMENTS-MOVE-TO-FIF-3).
      Default query/revision/packet providers remain unavailable/503.
  - id: FIF-3
    title: Golden five issuer vertical slice
    status: in_progress
    depends_on: [FIF-2]
    next_action: >
      FIF-3A1 AAPL as-reported primary statements, accession
      0000320193-25-000079, issuer ISS:US-XNAS-AAPL. BUILT_NOT_ACCEPTED
      pending Sol. Do not add SNOW/CAT/BAC/GOOGL. Do not start the next
      AAPL slice. Production attested issuer service remains NOT_BUILT.
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
(`POST /api/forensics/v1/financial/query`). Sol source-reviewed amended
head `1b7a65be23bc683706eb660c92f8fc26e81cc80e` as PASS /
ACCEPTED_FOR_LANDING. A–D (mixed duration+instant, cutoff-governed
unsupported metric, bounded streaming ingress, fail-closed
canonical→source binding) are accepted. FIF-2A is ACCEPTED /
FIXTURE_PROVEN / ON_MAIN via PR #5983. FIF-2B is the authenticated HTTP
adapter over the frozen packet revision plane
(`POST /api/forensics/v1/financial/revisions`). Sol source-reviewed
amended head `55663277a32c12251dbeb80945d0abcf36570b58` as PASS /
ACCEPTED. GitHub squash-merged PR #6157 as
`56d1a36caa43ca2a8ea4570808edca75ca2fc334` on 2026-08-21T16:08:36Z
while the explicit Sol hold was still in force; the accepted product
was not reverted. Canonical packet identity is bound; arbitrary
synthetic fixtures cannot claim committed FIP1 receipts; packet request
validation precedes provider opening; B-visible/C-hidden and delayed-
mapping PIT laws are proven; #5983 hashes remain unchanged. Production
default provider remains unavailable/503. FIF-2B is ACCEPTED /
FIXTURE_PROVEN / ON_MAIN. FIF-2C is the authenticated HTTP adapter
over the frozen assembler (`POST /api/forensics/v1/financial/packet`).
Sol source-reviewed accepted head
`27c04ca0750f6346670b26ae97b5ec3e0da1faac` as PASS /
ACCEPTED_FOR_LANDING. Landing head
`ba244971456738e0778dde6224d1f0fe25303cb2` integrated current-main
`d62c0a7b3f38013648e45c5a12fcdd710d55483b`. PR #6235 squash-merged as
`2ba752ddd0302b50f27913df22bc12fb548754b9` on 2026-08-22T19:27:18Z.
Rich FIP1 identity is packet_id `fip_49718dcaf4c6855592b6ba0a`,
content_sha256 `49718dcaf4c6855592b6ba0a160851c608b4733b44f8ac9a6cf7d907df7565e5`,
X-FIF-Response-SHA256 `310f6579ab0014e6af16a3341f005078eab3fdcc70ebe67ec83cf138b9e6c23a`,
18270 HTTP bytes. `CustomerCount` remains packet 200 with unsupported
cells; FIF-2A/FIF-2B keep their accepted unsupported-metric 400.
FIF-2C is ACCEPTED / FIXTURE_PROVEN / ON_MAIN. FIF-2 is DONE /
FIXTURE_PROVEN SERVICE SUBSTRATE (`DEC:FIF-2-DONE-STATEMENTS-MOVE-TO-FIF-3`).
A dedicated FIF-2D fixture-only trace route is rejected; company
statements moved into FIF-3. FIF-3 is IN_PROGRESS. FIF-3A1 reconstructs
AAPL FY2025 10-K accession `0000320193-25-000079` as filing-native
statement trees for issuer `ISS:US-XNAS-AAPL`. Do not create FIF-1R4.
Do not reopen accepted packet, query, or revision semantics. Do not
claim production issuer coverage; attested admission remains blocked.

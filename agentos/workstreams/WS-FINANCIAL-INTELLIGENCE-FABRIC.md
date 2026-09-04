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
  - tests/test_fundamental_forensics_ixbrl_raw_ledger.py
  - tests/fixtures/fundamental_forensics/aapl_10k_2025/
  - tests/fixtures/fundamental_forensics/aapl_10q_2026q3/
  - engine/fundamental_forensics/ixbrl_raw_ledger.py
  - engine/fundamental_forensics/sec_document_spine.py
  - tests/test_sec_document_spine.py
  - research/financial_intelligence_fabric/FIF_3A1_REUSE_MAP.md
  - research/financial_intelligence_fabric/FIF_3A2_REUSE_MAP.md
  - research/financial_intelligence_fabric/FIF_3A3_REUSE_MAP.md
  - research/financial_intelligence_fabric/FIF_3A4R_CROSS_FILING_LINEAGE_PROTOCOL.md
  - research/financial_intelligence_fabric/FIF_3A4R_AAPL_OVERLAP_CENSUS.json
  - research/financial_intelligence_fabric/replay_fif3a4r_aapl_overlap_census.py
  - research/financial_intelligence_fabric/FIF_3A2_AAPL_GOLDEN_REVIEW.md
  - contracts/statement_cell.v1.md
  - scripts/capture_fif3a1_aapl_package.py
  - scripts/capture_fif3a2_aapl_package.py
depends_on: []
discoveries:
  - DSC:COMPANYFACTS-CANNOT-FEED-CORE-METRIC-QUERY
  - DSC:PR-HOLD-REQUIRES-NATIVE-AUTOMERGE-DISARM
  - DSC:REVIEW-HOLD-PROSE-IS-NOT-FAIL-CLOSED
  - DSC:AAPL-LABEL-RESOURCES-SHARE-XLINK-LABEL
  - DSC:AAPL-PRODUCT-SERVICE-HYPERCUBE-PRECEDES-LINE-ITEMS
  - DSC:AAPL-CF-BEGINNING-CASH-IS-INSTANT-IN-DURATION-COLUMNS
  - DSC:AAPL-CF-CASH-CONCEPT-OCCURS-TWICE
  - DSC:AAPL-Q3-DURATION-FAMILIES-SHARE-END-DATE
  - DSC:AAPL-UNLINKED-VINTAGES-REQUIRE-TYPED-REVISION-LINEAGE
  - DSC:XBRL-DUPLICATE-LAW-IS-INTRA-INSTANCE
  - DSC:AAPL-A1-A2-CROSS-FILING-OVERLAP-CENSUS
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
  - DEC:FIF-3A1-MAPPING-RESPECTS-DIMENSIONAL-PROFILE
  - DEC:FIF-3A1-DUPLICATES-REACH-CELL-ADJUDICATION
  - DEC:FIF-3A1-PRESENTATION-OCCURRENCES-ARE-NOT-COLLAPSED
  - DEC:FIF-3A1-AUTHORITY-IS-CONTEXT-ONLY-OBJECT
  - DEC:FIF-3A1-ACCEPTED-GOLDEN-ON-MAIN
  - DEC:FIF-3A2-REUSE-MAP
  - DEC:FIF-3A2-COLUMNS-BIND-COMPLETE-PERIOD
  - DEC:FIF-3A2-RELATED-EVENT-REF-OMITS-GENERATION
  - DEC:FIF-3A2-ACCEPTED-GOLDEN-ON-MAIN
  - DEC:FIF-3A3-REUSE-MAP
  - DEC:FIF-3A3-ACCEPTED-GOLDEN-QUERY-ON-MAIN
  - DEC:FIF-3A4R-CROSS-FILING-LINEAGE-ACCEPTED-ON-MAIN
next_action: >
  FIF-3A4R is ACCEPTED_ARCHITECTURE / ON_MAIN / NOT_BUILT via PR #6382
  (accepted head 07755cb557a53af1341d8b6323a412631af8d83e; squash merge
  fe8caca04b634686fc8d8707a188ea1a8477c31c;
  DEC:FIF-3A4R-CROSS-FILING-LINEAGE-ACCEPTED-ON-MAIN). Sol has closed the
  A4R research gate. Do not implement FIF-3A4 from this records closeout;
  implementation requires a separate Sol commission. FIF-1 remains DONE /
  FROZEN. FIF-2 remains DONE / FIXTURE_PROVEN SERVICE SUBSTRATE. FIF-3
  remains IN_PROGRESS. FIF-3A1/A2 remain ACCEPTED / GOLDEN FIXTURE PROVEN /
  ON_MAIN. FIF-3A3 remains ACCEPTED / GOLDEN QUERY CONVERGENCE PROVEN /
  ON_MAIN. Production attested issuer service remains NOT_BUILT. Do not call
  FIF-3 done, do not claim production issuer coverage, and do not start another
  issuer from the A4R closeout.
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
    Apple FY2026 Q3 10-Q operations has four duration columns whose end
    dates are shared by 3M and 9M families. Bind by complete period.
    See DSC:AAPL-Q3-DURATION-FAMILIES-SHARE-END-DATE and
    DEC:FIF-3A2-COLUMNS-BIND-COMPLETE-PERIOD.
  - >
    After both AAPL golden filings are visible, comparative instants such
    as total_assets at 2025-09-27 are NOT_EVALUABLE because the 10-K and
    10-Q are unlinked duplicate roots. Do not invent revision_of. Accepted
    A4R architecture does not retroactively repair this state: only a future
    cutoff-visible positive lineage receipt may make LATEST_KNOWN_AS_OF resolve.
    See DSC:AAPL-UNLINKED-VINTAGES-REQUIRE-TYPED-REVISION-LINEAGE and
    DEC:FIF-3A4R-CROSS-FILING-LINEAGE-ACCEPTED-ON-MAIN.
  - >
    FIF-3A4R is ACCEPTED_ARCHITECTURE / ON_MAIN / NOT_BUILT. Do not remint A2
    FILED as FactEventType.XBRL_CONFIRMATION, append a third confirmation
    occurrence, widen v1 to _duplicates_agree, discard dimensioned lineage,
    treat the research census timestamp or JSON as runtime authority, or load
    the census into a production/query provider. Confirmation is source lineage,
    not a reported revision, and its system_available_at must be no earlier than
    all accepted rule/recording prerequisites. See
    DEC:FIF-3A4R-CROSS-FILING-LINEAGE-ACCEPTED-ON-MAIN,
    DSC:XBRL-DUPLICATE-LAW-IS-INTRA-INSTANCE, and
    DSC:AAPL-A1-A2-CROSS-FILING-OVERLAP-CENSUS.
  - >
    FIF-3A3 query source set is frozen to A1 0000320193-25-000079 and A2
    0000320193-26-000020. Iterating GOLDEN_AAPL_FIXTURES silently admits
    later statement packages into the A3 ledger.
  - >
    Non-null FinancialQueryDataset.delivery is exact committed_golden_fixture
    / attested=false / production_issuer_service=false. Extra keys, true
    flags, or non-booleans are private 503, not a new authority vocabulary.
  - >
    sec_document_id owns canonical CIK plus accession, existing SEC document
    role vocabulary, and document-spine member-path validation. 320193 and
    0000320193 mint one identity.
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
  - Do not invent a second authority vocabulary; reuse {"class":"context_only","display_only":true}.
  - Do not enrich dimensioned ProductMember/ServiceMember rows as consolidated revenue/cost_of_revenue.
  - Do not collapse repeated presentation occurrences into one concept → row.
  - Do not pre-filter duplicate facts to agreeing values before _cell_from_facts.
  - Do not recast an iXBRL-sourced cell as calculated merely because a calc arc exists.
  - FIF-3A1 is ACCEPTED / GOLDEN FIXTURE PROVEN / ON_MAIN (DEC:FIF-3A1-ACCEPTED-GOLDEN-ON-MAIN); do not reopen accepted AAPL composition, mapping, duplicate, presentation-occurrence, or authority laws, and do not add FIF-3A1 hardening.
  - Do not call FIF-3 done; the golden five-issuer slice is still IN_PROGRESS.
  - FIF-3A2 is ACCEPTED / GOLDEN FIXTURE PROVEN / ON_MAIN (DEC:FIF-3A2-ACCEPTED-GOLDEN-ON-MAIN); do not reopen accepted Q3 composition, complete-period column law, related_event_ref, or SHA b98602a299996ff7ea58b842364031547df795d1458b51134eef0e37159b7918, and do not add FIF-3A2 hardening.
  - FIF-3A3 is ACCEPTED / GOLDEN QUERY CONVERGENCE PROVEN / ON_MAIN (DEC:FIF-3A3-ACCEPTED-GOLDEN-QUERY-ON-MAIN); do not reopen the A1+A2 source freeze, delivery fail-closed law, canonical sec_document_id, unlinked-vintage N/E, or ledger/query identities, and do not add FIF-3A3 hardening.
  - >
    FIF-3A4R is ACCEPTED_ARCHITECTURE / ON_MAIN / NOT_BUILT
    (DEC:FIF-3A4R-CROSS-FILING-LINEAGE-ACCEPTED-ON-MAIN). Do not start
    FIF-3A4 implementation, activate AAPL revisions/packet, or alter accepted
    A3 historical replay from this records closeout. A future implementation
    requires a separate Sol commission.
  - Do not remint accepted A2 FILED occurrences as FactEventType.XBRL_CONFIRMATION.
  - Do not cite within-document duplicate law or _duplicates_agree as proof
    one filing revises or confirms another.
  - Do not confirm us-gaap OtherAssetsNoncurrent 83727M vs 72634M, do not
    treat us-gaap LongTermDebt 90678M vs 90700M as v1 exact confirmation,
    and do not mint v1 xbrl_confirmation for the CommitmentsAndContingencies
    nil pair.
  - Do not discard dimensioned exact confirmation candidates because the
    current core catalog is consolidated-only.
  - Do not iterate GOLDEN_AAPL_FIXTURES inside GoldenAaplFinancialQueryProvider.
  - Do not treat a non-null FinancialQueryDataset.delivery as a production-attestation authority.
  - Do not label frozen FIF-1 packet_id fip_18e2f725f6ba20678d0612bb as FIF-2C; FIF-2C rich HTTP proof is fip_49718dcaf4c6855592b6ba0a / content 49718dcaf4c6855592b6ba0a160851c608b4733b44f8ac9a6cf7d907df7565e5 / response 310f6579ab0014e6af16a3341f005078eab3fdcc70ebe67ec83cf138b9e6c23a.
  - Do not mint generation_id as financial-statement truth; related_event_ref is a stable event_id plus distinct SEC accessions.
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
    pr: [6268, 6302, 6352, 6382]
    next_action: >
      FIF-3A1 is ACCEPTED / GOLDEN FIXTURE PROVEN / ON_MAIN via PR #6268
      (accepted head 80d3da1e2ce6, merge 4ef15259f027). FIF-3A2 AAPL
      FY2026 Q3 10-Q accession 0000320193-26-000020 plus related_event_ref
      to evt_cik0000320193_2026q3_results is ACCEPTED / GOLDEN FIXTURE
      PROVEN / ON_MAIN via PR #6302 (accepted head 9598c5430c587b,
      merge e210a80d2bad). FIF-3A3 is ACCEPTED / GOLDEN QUERY
      CONVERGENCE PROVEN / ON_MAIN via PR #6352 (accepted head
      197f405758fd, merge 34ce48ec67a8). Query source set is exactly A1
      0000320193-25-000079 plus A2 0000320193-26-000020. Ledger SHA
      ba149bd55d929d843f353e91bbf68147791fb8b4a20c258426ea2eb7527019d8;
      AAPL response SHA 58972cb88f82483e86acc9d9fc3b1cbce046f466ff8665ae214909d90ab078b0.
      Unlinked A1/A2 comparatives remain NOT_EVALUABLE until a future
      cutoff-visible positive lineage receipt is present
      (DSC:AAPL-UNLINKED-VINTAGES-REQUIRE-TYPED-REVISION-LINEAGE).
      FIF-3A4R is ACCEPTED_ARCHITECTURE / ON_MAIN / NOT_BUILT via PR #6382
      (accepted head 07755cb557a53af1341d8b6323a412631af8d83e; merge
      fe8caca04b634686fc8d8707a188ea1a8477c31c;
      DEC:FIF-3A4R-CROSS-FILING-LINEAGE-ACCEPTED-ON-MAIN). The accepted
      census is v1.1 with 130 exact numeric candidates, 37 empty-dimension,
      93 dimensioned, 15 query-relevant, one nil refusal, one precision-
      consistent refusal, one changed-value refusal, zero namespace/version
      mismatches; payload SHA b1577b04f553c56ba278d2057ecc07a0d23159a1d20a41339b39da4ed24c12a9,
      file SHA f1481fffa18720209ba98d463c25a52b4e497bff89b2159cfa3b2d74ea63ab58.
      Do not implement FIF-3A4 until separately commissioned by Sol. FIF-3
      itself is not done. Do not add SNOW/CAT/BAC/GOOGL from this closeout.
      Production attested issuer service remains NOT_BUILT.
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
statement trees for issuer `ISS:US-XNAS-AAPL`. Sol source-reviewed
exact product head `80d3da1e2ce6f028a526520139d039692a324610` as PASS
/ ACCEPTED_FOR_LANDING. PR #6268 squash-merged as
`4ef15259f0273e48927dfd488502e57bfbb2dab5` on 2026-08-23T05:43:51Z.
Accepted response identity is SHA-256
`25e5562e81cb80bd42d0feb544c212c4471e11736601aaee418a60981a457184`,
196310 bytes, rows 24 / 35 / 35. FIF-3A1 is ACCEPTED / GOLDEN FIXTURE
PROVEN / ON_MAIN (`DEC:FIF-3A1-ACCEPTED-GOLDEN-ON-MAIN`). FIF-3A2
extends the same statements route to AAPL FY2026 Q3 10-Q accession
`0000320193-26-000020` (period of report 2026-06-27, SEC acceptance
`2026-07-31T10:01:02.000Z`). Sol source-reviewed exact product head
`9598c5430c587b2ec9d1f84d3fa6e2d704808bcc` as PASS /
ACCEPTED_FOR_LANDING. PR #6302 squash-merged as
`e210a80d2bad56b351d90ef82ddaa4ec114887b9` on 2026-08-23T11:57:16Z.
The captured package accounts for 65 SEC index members and retains 6
(primary HTML plus xsd/pre/cal/def/lab). Accepted Q3 response identity
is SHA-256
`b98602a299996ff7ea58b842364031547df795d1458b51134eef0e37159b7918`,
190019 bytes, rows 24 / 36 / 35. Operations columns bind complete
`{kind,start,end}` so 3M and 9M families that share an end date stay
distinct (`DEC:FIF-3A2-COLUMNS-BIND-COMPLETE-PERIOD`). Optional
`related_event_ref` points at existing event_id
`evt_cik0000320193_2026q3_results`, distinguishes results 8-K
`0000320193-26-000018` from periodic 10-Q `0000320193-26-000020`,
omits `generation_id`, copies no Earnings payload, and is absent on
the A1 10-K (`DEC:FIF-3A2-RELATED-EVENT-REF-OMITS-GENERATION`).
FIF-3A2 is ACCEPTED / GOLDEN FIXTURE PROVEN / ON_MAIN
(`DEC:FIF-3A2-ACCEPTED-GOLDEN-ON-MAIN`). FIF-3A3 converts the accepted
A1/A2 iXBRL bytes through the strict SEC parser and one
`ixbrl_raw_ledger.py` adapter into canonical `RawFactLedger`, then
serves governed values on the existing authenticated
`POST /api/forensics/v1/financial/query`. Sol source-reviewed exact
product head `197f405758fdfe19be7de739c1aabfc938272c40` as PASS /
ACCEPTED_FOR_LANDING. PR #6352 squash-merged as
`34ce48ec67a8697ddfbe439e9840e818c98eee70` on 2026-08-24T09:53:54Z.
Accepted identities remain ledger SHA
`ba149bd55d929d843f353e91bbf68147791fb8b4a20c258426ea2eb7527019d8`,
AAPL response SHA
`58972cb88f82483e86acc9d9fc3b1cbce046f466ff8665ae214909d90ab078b0`,
query hash
`f8f6dc3134592c817001738cbdefb09ee1b71798ef24a8e64dc75685a6f9c7a1`,
A1 statement SHA
`25e5562e81cb80bd42d0feb544c212c4471e11736601aaee418a60981a457184`,
A2 statement SHA
`b98602a299996ff7ea58b842364031547df795d1458b51134eef0e37159b7918`,
A1 document
`sec_document_d23a609841f9a32489dd7abc952d39622540f8a24905612bda1d43e5577860b8`,
A2 document
`sec_document_29a36fa46a0bc5309f17bd254c3061f20c4b3de7e05898a2fec9ee58f89e8760`.
The A3 source set is exactly A1+A2
(`DEC:FIF-3A3-ACCEPTED-GOLDEN-QUERY-ON-MAIN`). Non-null delivery is
exact committed-golden / non-attested / non-production.
`sec_document_id` owns canonical CIK plus accession, role, and
member-path validation. Unlinked A1/A2 comparatives remain
`NOT_EVALUABLE` (`DSC:AAPL-UNLINKED-VINTAGES-REQUIRE-TYPED-REVISION-LINEAGE`).
FIF-3A3 is ACCEPTED / GOLDEN QUERY CONVERGENCE PROVEN / ON_MAIN.
Predecessor-label law: frozen FIF-1 golden packet_id is
`fip_18e2f725f6ba20678d0612bb`; FIF-2C rich HTTP proof remains
packet_id `fip_49718dcaf4c6855592b6ba0a`,
content `49718dcaf4c6855592b6ba0a160851c608b4733b44f8ac9a6cf7d907df7565e5`,
response `310f6579ab0014e6af16a3341f005078eab3fdcc70ebe67ec83cf138b9e6c23a`.
This is not production coverage. Production attested issuer service
remains NOT_BUILT. Do not create FIF-1R4. Do not reopen accepted
packet, query, revision, FIF-3A1, FIF-3A2, or FIF-3A3 semantics. Do
not call FIF-3 done. FIF-3A4R is ACCEPTED_ARCHITECTURE / ON_MAIN /
NOT_BUILT via PR #6382 and
`DEC:FIF-3A4R-CROSS-FILING-LINEAGE-ACCEPTED-ON-MAIN`. This acceptance
freezes source law only; FIF-3A4 implementation requires a separate Sol
commission.

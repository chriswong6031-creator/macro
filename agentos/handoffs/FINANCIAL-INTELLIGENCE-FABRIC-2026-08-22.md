---
workstream: "WS:FINANCIAL-INTELLIGENCE-FABRIC"
session: claude/fif-3a1
model: local
ended_because: complete
prs: [6268]
mission: >
  FIF-3A1 AAPL real as-reported statement vertical: Data OS identity,
  bounded 10-K package, filing-native statement trees, authenticated
  Forensics consumer, human golden review. Stop for Sol. Do not start
  the next AAPL slice.
state_before: >
  Sol observed main 67e6e59734d9. Pickup fast-forwarded through
  bc0a9cd89640 to baf1a7070ce4. FIF-1 DONE/FROZEN. FIF-2A #5983, FIF-2B
  #6157, FIF-2C #6235, records #6254 on main. FIF-2 still recorded as
  in_progress until DEC:FIF-2-DONE-STATEMENTS-MOVE-TO-FIF-3. No
  statement_cell.v1 implementation. No AAPL filing-package bytes in repo.
changed:
  - path: agentos/decisions/DEC-FIF-2-DONE-STATEMENTS-MOVE-TO-FIF-3.md
    what: Narrow sequencing supersession; FIF-2 DONE/FIXTURE_PROVEN; statements move to FIF-3; FIF-2D rejected.
  - path: agentos/decisions/DEC-FIF-3A1-REUSE-MAP.md
    what: Frozen identity/package/XBRL reuse map before code.
  - path: agentos/discoveries/DSC-AAPL-LABEL-RESOURCES-SHARE-XLINK-LABEL.md
    what: Apple label resources share xlink:label across roles.
  - path: agentos/workstreams/WS-FINANCIAL-INTELLIGENCE-FABRIC.md
    what: FIF-2 done; FIF-3 in_progress; FIF-3A1 BUILT_NOT_ACCEPTED.
  - path: engine/fundamental_forensics/statement_graph.py
    what: Presentation/label/calculation walk and as-reported reconstruction.
  - path: engine/fundamental_forensics/statement_service.py
    what: Golden AAPL statement admission, Data OS bind, envelope.
  - path: app/forensics.py
    what: POST /api/forensics/v1/financial/statements on the existing private/auth boundary.
  - path: tests/fixtures/fundamental_forensics/aapl_10k_2025/
    what: Accession 0000320193-25-000079; 93 members; 6 stored XBRL members.
  - path: tests/test_fundamental_forensics_financial_statement_service.py
    what: Discriminating reconstruction, identity, ambiguity, predecessor, no-network proofs.
  - path: tests/test_fundamental_forensics_financial_statement_api.py
    what: Auth/private/405/golden HTTP proofs.
  - path: contracts/statement_cell.v1.md
    what: Minimal statement_cell.v1 / statement-tree contract.
  - path: research/financial_intelligence_fabric/FIF_3A1_AAPL_GOLDEN_REVIEW.md
    what: Human review vs captured AAPL 10-K primary document.
verified:
  - claim: Data OS binds CIK 0000320193 to ISS:US-XNAS-AAPL / SEC:US-XNAS-AAPL / US-XNAS-AAPL and not to the CIK as entity_id.
    command: python3 pandas filter of data/reference/issuer_master.parquet and security_master.parquet for cik==0000320193 and issuer_id==ISS:US-XNAS-AAPL
    result: one issuer row, one security row, issuer_id != cik
  - claim: Golden package is accession 0000320193-25-000079 with index sha256 d61dde83df2dde7d63041e443321eab963b245e4c0090ba6240ce1711329de83, 93 members, 6 stored.
    command: python3 -m pytest tests/test_fundamental_forensics_financial_statement_service.py::test_package_manifest_digest_and_member_counts
    result: passed
  - claim: Three statement trees reconstruct with filing-native titles and row counts 25/38/36.
    command: python3 -m pytest tests/test_fundamental_forensics_financial_statement_service.py::test_reconstruct_three_primary_statements_filing_native
    result: passed; roles apple.com CONSOLIDATEDSTATEMENTS OF OPERATIONS / BALANCESHEETS / CASHFLOWS
  - claim: Net sales FY2025 416161000000 reverses to ix:nonFraction f-78 scale 6 context c-1 containing 416,161.
    command: python3 -m pytest tests/test_fundamental_forensics_financial_statement_service.py::test_income_duration_reverses_to_aapl_xbrl_occurrence
    result: passed
  - claim: Accounts receivable instant 39777000000 reverses to ix:nonFraction f-163 containing 39,777.
    command: python3 -m pytest tests/test_fundamental_forensics_financial_statement_service.py::test_balance_sheet_instant_reverses
    result: passed
  - claim: Cash-flow beginning 29943000000 and ending 35934000000 are the same concept distinguished by preferredLabel.
    command: python3 -m pytest tests/test_fundamental_forensics_financial_statement_service.py::test_cash_flow_order_is_filing_native_and_splits_beginning_ending_cash
    result: passed
  - claim: SG&A stays unmapped and present at 27601000000.
    command: python3 -m pytest tests/test_fundamental_forensics_financial_statement_service.py::test_unmapped_sga_row_survives
    result: passed
  - claim: Disagreeing duplicate facts are quality_state=ambiguous with null value.
    command: python3 -m pytest tests/test_fundamental_forensics_financial_statement_service.py::test_duplicate_disagreeing_facts_are_ambiguous_not_first_row_wins
    result: passed
  - claim: Statement response SHA-256 is 853f2fd89e2dd2175152b089d0c80b2bc7777c103fefb5011433f0657057bda2 across repeated runs with no urllib and no Path.write_bytes.
    command: python3 -m pytest tests/test_fundamental_forensics_financial_statement_service.py::test_execute_is_deterministic_and_pinned tests/test_fundamental_forensics_financial_statement_service.py::test_no_request_time_network_or_attested_write tests/test_fundamental_forensics_financial_statement_api.py
    result: passed; paid POST 200 private no-store; anon 401; free 403; non-POST 405
  - claim: FIF-2A five query hashes, rich FIP1 packet identity, and frozen FIF-1 paths remain unchanged.
    command: python3 -m pytest tests/test_fundamental_forensics_financial_statement_service.py::test_fif2a_query_hashes_unchanged tests/test_fundamental_forensics_financial_statement_service.py::test_fif2b_and_fif2c_accepted_packet_behavior_unchanged tests/test_fundamental_forensics_financial_statement_service.py::test_frozen_fif1_paths_are_empty_diff tests/test_fundamental_forensics_financial_packet_service.py::test_fif2a_query_hashes_unchanged tests/test_fundamental_forensics_financial_packet_service.py::test_rich_packet_is_the_complete_research_artifact
    result: passed; rich packet_id fip_49718dcaf4c6855592b6ba0a; content_sha256 49718dcaf4c6855592b6ba0a160851c608b4733b44f8ac9a6cf7d907df7565e5; X-FIF-Response-SHA256 310f6579ab0014e6af16a3341f005078eab3fdcc70ebe67ec83cf138b9e6c23a; 18270 bytes
  - claim: AgentOS schema validate exits 0 on this worktree.
    command: python3 scripts/agentos.py validate
    result: 0 error(s), 16 warning(s) unrelated to FIF
unverified:
  - claim: Exact-head hosted ci.yml and fences.yml on the PR head
    what_would_verify: gh run view after push; packs and fences SUCCESS on the exact SHA
  - claim: Browser-rendered SEC HTML nesting of Products/Services under Net sales
    what_would_verify: Visual inspection of the live SEC viewer; presentation-tree hypercube prefix is already recorded in FIF_3A1_AAPL_GOLDEN_REVIEW.md
unresolved:
  - FIF-3A1 is BUILT_NOT_ACCEPTED pending Sol. Production attested issuer service remains NOT_BUILT.
  - Definition linkbase is retained and unused; reconstruction is undimensioned.
  - Income-statement presentation includes hypercube/axis/member abstracts before line items.
next_actions:
  - Sol source-reviews this PR. Do not merge until Sol releases the hold.
  - Do not start the next AAPL slice, SNOW/CAT/BAC/GOOGL, FIF-2D, or production admission.
  - Later AAPL event linkage must reuse Earnings Intelligence event_workspace.v1.
do_not_redo:
  - Do not mint mmx.issuer.aapl or treat ticker/CIK as canonical issuer identity.
  - Do not build a dedicated /financial/trace endpoint.
  - Do not reorder as-reported rows into the 50-metric registry.
  - Do not call SEC, write R2, or mutate attested history on the HTTP path.
  - Do not reopen frozen FIF-1 packet semantics or accepted FIF-2A/B/C hashes.
  - Do not claim production issuer coverage.
danger_areas:
  - Apple label resources share one xlink:label across roles (DSC:AAPL-LABEL-RESOURCES-SHARE-XLINK-LABEL).
  - JSONResponse would re-serialize and break X-FIF-Response-SHA256.
  - GoldenAaplStatementProvider must share forensics_api.REPO with Data OS parquet reads.
  - PR-body HOLD language is not a merge barrier; native auto-merge must stay null (DSC:REVIEW-HOLD-PROSE-IS-NOT-FAIL-CLOSED, DSC:PR-HOLD-REQUIRES-NATIVE-AUTOMERGE-DISARM).
---

FIF-3A1 built against golden AAPL FY2025 10-K accession
0000320193-25-000079. Entitled POST /api/forensics/v1/financial/statements
returns three as-reported primary statement trees with per-cell source
spans. FIF-2 is DONE / FIXTURE_PROVEN. Production issuer service is not
built. Stop for Sol. Do not start the next AAPL slice.

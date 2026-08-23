---
workstream: "WS:FINANCIAL-INTELLIGENCE-FABRIC"
session: claude/fif-3a1
model: local
ended_because: complete
prs: [6268]
decisions:
  - DEC:FIF-3A1-ISSUERMASTER-IS-THE-IDENTITY-READER
  - DEC:FIF-3A1-DISPLAYED-TABLE-IS-THE-COMPOSITION
  - DEC:FIF-3A1-PACKAGE-WITNESS-ADMISSION
  - DEC:FIF-3A1-CALC-NETWORKS-ARE-ROLE-LOCAL
discoveries:
  - DSC:AAPL-PRODUCT-SERVICE-HYPERCUBE-PRECEDES-LINE-ITEMS
  - DSC:AAPL-CF-BEGINNING-CASH-IS-INSTANT-IN-DURATION-COLUMNS
mission: >
  Amend PR #6268 in place for Sol REQUEST_CHANGES on FIF-3A1 exact head
  c0ced14a4270f73b0d62bc986851f9fbe0e9e217. Close four product blockers.
  Do not merge. Do not start the next AAPL slice.
state_before: >
  Architecture accepted. Exact-head hosted CI/fences green on c0ced14.
  Sol requested IssuerMaster membership, displayed-table composition,
  package/witness admission, and role-local calculation networks.
  Reviewed against main 21f51a1; current main later carried FF-1P2R.
changed:
  - path: engine/fundamental_forensics/statement_service.py
    what: IssuerMaster current-membership reader; delivery authority is committed golden fixture, non-attested, context/display-only.
  - path: engine/fundamental_forensics/statement_graph.py
    what: HTML displayed-table composition, strict package/witness admission, role-local calc networks.
  - path: tests/fixtures/fundamental_forensics/aapl_10k_2025/sec_submissions_witness.json
    what: Retained SEC submissions witness for acceptance/form/report/primary-document.
  - path: tests/fixtures/fundamental_forensics/issuer_master_adversarial_duplicate_mint.json
    what: Active plus SUPERSEDED_DUPLICATE_MINT under one issuer, duplicate listed first.
  - path: tests/test_fundamental_forensics_financial_statement_service.py
    what: Four-blocker proofs; new response SHA 1a489e46; row counts 24/35/35.
  - path: tests/test_fundamental_forensics_financial_statement_api.py
    what: HTTP identity and delivery authority against the new trees.
  - path: research/financial_intelligence_fabric/FIF_3A1_AAPL_GOLDEN_REVIEW.md
    what: Re-human-reviewed three statements including Product/Services dimensional rows.
  - path: scripts/capture_fif3a1_aapl_package.py
    what: Capture process mints fixture_recorded_at and writes the witness.
verified:
  - claim: IssuerMaster returns only SEC:US-XNAS-AAPL when a SUPERSEDED_DUPLICATE_MINT sibling is listed first.
    command: python3 -m pytest tests/test_fundamental_forensics_financial_statement_service.py::test_issuer_master_selects_active_membership_not_superseded_duplicate -q
    result: passed
  - claim: Products/Services display under Net sales with dimensioned FY2025 307003000000 reversing to 307,003.
    command: python3 -m pytest tests/test_fundamental_forensics_financial_statement_service.py::test_products_and_services_are_displayed_under_net_sales_with_dimensions tests/test_fundamental_forensics_financial_statement_service.py::test_reconstruct_three_primary_statements_filing_native -q
    result: passed; IS/BS/CF rows 24/35/35; hypercube labels absent
  - claim: Index SHA d61dde83, 93 members, witness SHA 6449489e 364 bytes, fixture_recorded_at 2026-08-23T00:32:31Z; hostile index/inventory/witness mutations fail.
    command: python3 -m pytest tests/test_fundamental_forensics_financial_statement_service.py::test_package_manifest_digest_and_member_counts tests/test_fundamental_forensics_financial_statement_service.py::test_hostile_index_digest_is_refused tests/test_fundamental_forensics_financial_statement_service.py::test_hostile_index_duplicate_member_is_refused tests/test_fundamental_forensics_financial_statement_service.py::test_hostile_inventory_extra_member_is_refused tests/test_fundamental_forensics_financial_statement_service.py::test_hostile_inventory_missing_member_is_refused tests/test_fundamental_forensics_financial_statement_service.py::test_hostile_inventory_duplicate_member_is_refused tests/test_fundamental_forensics_financial_statement_service.py::test_hostile_acceptance_witness_digest_is_refused tests/test_fundamental_forensics_financial_statement_service.py::test_hostile_acceptance_witness_unbind_is_refused tests/test_fundamental_forensics_financial_statement_service.py::test_capture_process_mints_fixture_recorded_at -q
    result: passed
  - claim: Calculation networks are role-local; same parent in two roles does not contaminate.
    command: python3 -m pytest tests/test_fundamental_forensics_financial_statement_service.py::test_calculation_relationships_are_role_local -q
    result: passed
  - claim: New canonical response identity is SHA-256 1a489e46698e99f83518f18def89c381a29f63960a979d9de82caa29bcc3198e / 196358 bytes, delivery committed_golden_fixture non-attested context_display_only.
    command: python3 -m pytest tests/test_fundamental_forensics_financial_statement_service.py::test_execute_is_deterministic_and_pinned tests/test_fundamental_forensics_financial_statement_api.py -q
    result: passed
  - claim: Five #5983 hashes and FIF-2C packet identity are unchanged; frozen FIF-1 paths empty vs origin/main.
    command: python3 -m pytest tests/test_fundamental_forensics_financial_statement_service.py::test_fif2a_query_hashes_unchanged tests/test_fundamental_forensics_financial_statement_service.py::test_fif2b_and_fif2c_accepted_packet_behavior_unchanged tests/test_fundamental_forensics_financial_statement_service.py::test_frozen_fif1_paths_are_empty_diff -q
    result: passed
unverified:
  - claim: Exact-head hosted ci.yml and fences.yml on the amended PR head
    what_would_verify: gh run view after push; packs and fences SUCCESS on the exact SHA
unresolved:
  - FIF-3A1 remains BUILT_NOT_ACCEPTED pending Sol. Production attested issuer service remains NOT_BUILT.
  - Do not start the next AAPL slice.
next_actions:
  - Sol source-reviews amended #6268. Do not merge until Sol releases the hold.
  - Do not start the next AAPL slice, SNOW/CAT/BAC/GOOGL, FIF-2D, or production admission.
do_not_redo:
  - Do not mint mmx.issuer.aapl or treat ticker/CIK as canonical issuer identity.
  - Do not independently resolve issuer→security; IssuerMaster is the reader.
  - Do not treat raw presentation order as AAPL composition or build a generic segment engine.
  - Do not call this a production issuer service.
  - Do not reopen frozen FIF-1 packet semantics or accepted FIF-2A/B/C hashes.
  - Do not edit the Prophet handoff; current main owns model: codex.
danger_areas:
  - Apple label resources share one xlink:label across roles (DSC:AAPL-LABEL-RESOURCES-SHARE-XLINK-LABEL).
  - Product/Service hypercube precedes line items (DSC:AAPL-PRODUCT-SERVICE-HYPERCUBE-PRECEDES-LINE-ITEMS).
  - CF beginning cash is instant in duration columns (DSC:AAPL-CF-BEGINNING-CASH-IS-INSTANT-IN-DURATION-COLUMNS).
  - JSONResponse would re-serialize and break X-FIF-Response-SHA256.
  - PR-body HOLD language is not a merge barrier; native auto-merge must stay null.
---

Sol REQUEST_CHANGES closed in place on PR #6268. FIF-3A1 is still
BUILT_NOT_ACCEPTED. FIF-1 DONE/FROZEN. FIF-2 DONE/FIXTURE_PROVEN.
FIF-3 IN_PROGRESS. Production attested issuer service NOT_BUILT.
Do not merge. Do not start the next AAPL slice.

---
workstream: "WS:FINANCIAL-INTELLIGENCE-FABRIC"
session: claude/fif-3a1
model: local
ended_because: complete
prs: [6268]
decisions:
  - DEC:FIF-3A1-MAPPING-RESPECTS-DIMENSIONAL-PROFILE
  - DEC:FIF-3A1-DUPLICATES-REACH-CELL-ADJUDICATION
  - DEC:FIF-3A1-PRESENTATION-OCCURRENCES-ARE-NOT-COLLAPSED
  - DEC:FIF-3A1-AUTHORITY-IS-CONTEXT-ONLY-OBJECT
discoveries:
  - DSC:AAPL-CF-CASH-CONCEPT-OCCURS-TWICE
mission: >
  Amend PR #6268 in place for Sol REQUEST_CHANGES on FIF-3A1 exact head
  747ff1bc6dc441c49e33003ebf1322f2f5b116e5. Close remaining issues A–D.
  Do not merge. Do not start the next AAPL slice.
state_before: >
  Identity, displayed-table composition, package admission, and role-local
  calculation blockers were accepted closed. Sol requested dimensional-profile
  mapping, duplicate identity reaching cell adjudication, uncollapsed
  presentation occurrences with direct iXBRL cells, and canonical
  authority={"class":"context_only","display_only":true}.
changed:
  - path: engine/fundamental_forensics/statement_graph.py
    what: consolidated_only mapping refuses dimensioned members; duplicate identity is concept/context/unit; presentation occurrences are not collapsed; reported iXBRL cells stay direct.
  - path: engine/fundamental_forensics/statement_service.py
    what: Top-level authority object; delivery no longer carries an authority string.
  - path: tests/test_fundamental_forensics_financial_statement_service.py
    what: Proofs for A–D; new response SHA 25e5562e / 196310 bytes.
  - path: tests/test_fundamental_forensics_financial_statement_api.py
    what: HTTP identity and canonical authority object.
  - path: contracts/statement_cell.v1.md
    what: Authority object, dimensional mapping, presentation occurrences, direct vs formula_dependencies.
  - path: research/financial_intelligence_fabric/FIF_3A1_AAPL_GOLDEN_REVIEW.md
    what: Mapping counts IS 13/11; periodStart/End cash; canonical authority object.
verified:
  - claim: Dimensioned Products/Services Net sales and Cost of sales stay unmapped; undimensioned totals map to revenue and cost_of_revenue.
    command: python3 -m pytest tests/test_fundamental_forensics_financial_statement_service.py::test_dimensional_product_service_rows_are_not_enriched_as_consolidated_metrics -q
    result: passed
  - claim: Conflicting Total net sales duplicate through reconstruct_primary_statements is ambiguous with competing receipts.
    command: python3 -m pytest tests/test_fundamental_forensics_financial_statement_service.py::test_conflicting_duplicate_total_net_sales_is_ambiguous_end_to_end -q
    result: passed
  - claim: Beginning cash is periodStartLabel and ending cash is periodEndLabel; Gross margin stays direct while formula_dependencies remain.
    command: python3 -m pytest tests/test_fundamental_forensics_financial_statement_service.py::test_cash_flow_order_is_filing_native_and_splits_beginning_ending_cash tests/test_fundamental_forensics_financial_statement_service.py::test_reported_ixbrl_fact_stays_direct_when_calc_network_exists -q
    result: passed
  - claim: Response authority is context_only/display_only; delivery has no authority field; SHA-256 25e5562e81cb80bd42d0feb544c212c4471e11736601aaee418a60981a457184 / 196310 bytes.
    command: python3 -m pytest tests/test_fundamental_forensics_financial_statement_service.py::test_execute_is_deterministic_and_pinned tests/test_fundamental_forensics_financial_statement_api.py::test_paid_golden_aapl_returns_three_statement_trees -q
    result: passed
  - claim: AgentOS validate exits 0 on the new DEC/DSC records.
    command: python3 scripts/agentos.py validate
    result: 0 error(s); pre-existing warnings only
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
  - Do not enrich dimensioned ProductMember/ServiceMember rows as consolidated revenue/cost_of_revenue.
  - Do not pre-filter duplicate facts to agreeing values before _cell_from_facts.
  - Do not collapse repeated presentation occurrences into one concept → row.
  - Do not invent a second authority vocabulary; reuse {"class":"context_only","display_only":true}.
  - Do not recast an iXBRL-sourced cell as calculated merely because a calc arc exists.
  - Do not independently resolve issuer→security; IssuerMaster is the reader.
  - Do not treat raw presentation order as AAPL composition or build a generic segment engine.
  - Do not call this a production issuer service.
  - Do not reopen frozen FIF-1 packet semantics or accepted FIF-2A/B/C hashes.
danger_areas:
  - Core catalog is consolidated_only; mapping must read dimensional_profile.
  - Apple cash concept occurs twice (DSC:AAPL-CF-CASH-CONCEPT-OCCURS-TWICE).
  - Product/Service hypercube precedes line items (DSC:AAPL-PRODUCT-SERVICE-HYPERCUBE-PRECEDES-LINE-ITEMS).
  - CF beginning cash is instant in duration columns (DSC:AAPL-CF-BEGINNING-CASH-IS-INSTANT-IN-DURATION-COLUMNS).
  - JSONResponse would re-serialize and break X-FIF-Response-SHA256.
  - PR-body HOLD language is not a merge barrier; native auto-merge must stay null.
---

Sol REQUEST_CHANGES A–D closed in place on PR #6268. FIF-3A1 is still
BUILT_NOT_ACCEPTED. FIF-1 DONE/FROZEN. FIF-2 DONE/FIXTURE_PROVEN.
FIF-3 IN_PROGRESS. Production attested issuer service NOT_BUILT.
Do not merge. Do not start the next AAPL slice.

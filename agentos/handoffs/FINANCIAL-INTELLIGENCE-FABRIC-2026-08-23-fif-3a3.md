---
workstream: "WS:FINANCIAL-INTELLIGENCE-FABRIC"
session: claude/fif-3a3
model: local
ended_because: complete
prs: ["https://github.com/mastermindx-market-intelligence/macro/pull/6352"]
mission: >
  FIF-3A3: convert accepted AAPL iXBRL occurrences into the canonical
  RawFactLedger and return governed normalized values on the existing
  authenticated financial query route. Do not start FIF-3A4. Do not
  call FIF-3 done. HOLD-FOR-SOL.
state_before: >
  FIF-3A1 accepted on main via PR #6268 merge 4ef15259f027. FIF-3A2
  accepted via PR #6302 merge e210a80d2bad. A2 records PR #6324 merge
  8c125a80bc8c. Pickup origin/main e96c3810eb46 after Sol-observed
  f69348e80d4b (fast-forwarded through skip-ci ticks). Query route
  defaulted to UnavailableFinancialQueryProvider.
changed:
  - path: engine/fundamental_forensics/ixbrl_raw_ledger.py
    what: Parser-result adapter plus GoldenAaplFinancialQueryProvider.
  - path: engine/fundamental_forensics/sec_document_spine.py
    what: Exported sec_document_id; production call sites now use it.
  - path: engine/fundamental_forensics/query_service.py
    what: Optional FinancialQueryDataset.delivery; omitted on FIP1.
  - path: app/forensics.py
    what: Default query provider is GoldenAaplFinancialQueryProvider.
  - path: tests/test_fundamental_forensics_ixbrl_raw_ledger.py
    what: Conversion, reconciliation, PIT, dimensions, duplicates, unlinked vintages.
decisions:
  - DEC:FIF-3A3-REUSE-MAP
  - DEC:FIF-1-V1-FROZEN
discoveries:
  - DSC:AAPL-UNLINKED-VINTAGES-REQUIRE-TYPED-REVISION-LINEAGE
verified:
  - claim: A1 FY2025 revenue 416161000000 and A2 Q3/YTD revenue, assets, CFO reconcile to statement fact_id via source_occurrence_key.
    command: python3 -m pytest tests/test_fundamental_forensics_ixbrl_raw_ledger.py::test_required_governed_aapl_values tests/test_fundamental_forensics_ixbrl_raw_ledger.py::test_statement_query_reconciliation_for_direct_metrics -q
    result: passed; AAPL query response SHA 58972cb88f82483e86acc9d9fc3b1cbce046f466ff8665ae214909d90ab078b0
  - claim: Conversion report A1 969 numeric/964 represented/5 unsupported_transform; A2 762/758/4; ledger SHA ba149bd55d929d843f353e91bbf68147791fb8b4a20c258426ea2eb7527019d8.
    command: python3 -m pytest tests/test_fundamental_forensics_ixbrl_raw_ledger.py::test_conversion_report_is_complete_and_deterministic -q
    result: passed
  - claim: Comparative total_assets at 2025-09-27 is NOT_EVALUABLE unlinked source vintages after both filings are visible.
    command: python3 -m pytest tests/test_fundamental_forensics_ixbrl_raw_ledger.py::test_unlinked_vintages_are_not_evaluable -q
    result: passed; reason unlinked source vintages require an explicit typed revision lineage
  - claim: A1/A2 statement SHAs, five #5983 query hashes, and FIF-2C packet pins remain unchanged; FIF-1 and query/raw_ledger/metric_registry are empty-diff versus origin/main.
    command: python3 -m pytest tests/test_fundamental_forensics_ixbrl_raw_ledger.py::test_five_5983_query_hashes_and_fif2c_pins tests/test_fundamental_forensics_ixbrl_raw_ledger.py::test_frozen_predecessor_paths_are_empty_diff -q
    result: passed
  - claim: AgentOS schema validates.
    command: python3 scripts/agentos.py validate
    result: 0 error(s)
unverified: []
unresolved:
  - FIF-3A3 is BUILT_NOT_ACCEPTED pending Sol.
  - FIF-3 remains IN_PROGRESS.
  - Production attested issuer service remains NOT_BUILT.
  - Comparative overlap across unlinked golden filings stays NOT_EVALUABLE until a later typed-revision wave.
next_actions:
  - Sol reviews this PR. Do not merge until released.
  - Do not start FIF-3A4 or another issuer from this wave.
do_not_redo:
  - Do not patch query.py to guess Clark-notation QNames.
  - Do not invent revision_of from 10-Q comparative overlap with the 10-K.
  - Do not convert only statement totals; retain every representable numeric occurrence.
  - Do not activate AAPL packet or revision providers.
  - Do not add delivery metadata to FIP1 datasets.
danger_areas:
  - Setting revision_of on A2 comparative facts would silently fuse unlinked vintages.
  - Flipping dimensions_known true on partial contexts would let Product/Service or incomplete parses become consolidated revenue.
  - Importing delivery onto FIP1 FinancialQueryDataset changes FIF-2A bytes.
  - Request-time SEC or current clock would violate golden PIT.
---

FIF-3A3 built the real AAPL occurrence ledger onto the existing query
route from accepted A1/A2 iXBRL bytes. HOLD-FOR-SOL.

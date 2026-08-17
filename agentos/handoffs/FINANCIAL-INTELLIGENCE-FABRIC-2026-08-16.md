---
workstream: "WS:FINANCIAL-INTELLIGENCE-FABRIC"
session: claude/fif-1-golden-financial-intelligence-packet
model: codex
ended_because: complete
mission: >
  FIF-1R only on PR #5809. Split I/O from packet assembly, close formula
  evidence recursively, repair the cell oneOf invariant, add adversarial
  contract tests, regenerate the golden packet, and identify the prior CI
  reds. Stop for operator re-review. Do not merge. Do not start FIF-2.
state_before: >
  Operator source-reviewed PR #5809 at 674f3a07. Three contract blockers:
  builder hashed Path(__file__) and loaded the schema internally; FY2023
  gross_margin referenced a missing gross_profit cell; schema allowed
  value=null and non_value_state=null. Hardening tests were missing. Pack 11
  was a FIF import-pinning miss later fixed on 60821a0c; pack 5 was inherited
  qledger and is green on this rebase. FIF-2 had not started.
changed:
  - path: engine/fundamental_forensics/financial_intelligence_packet.py
    what: Pure assemble kernel with injected PacketBuildContext/PacketEvidenceDigests; evidence_cells plane; recursive formula closure.
  - path: scripts/build_financial_intelligence_packet.py
    what: CLI now loads files/hashes/schema and calls the repo adapter.
  - path: contracts/financial_intelligence_packet.schema.json
    what: Exact oneOf valued vs non-valued cells; valued direct/formula provenance requirements; evidence_cells.
  - path: tests/test_fundamental_forensics_financial_intelligence_packet.py
    what: Laws 9-10 now resolve every dependency; nested net_debt; pure-kernel I/O denial; schema-negative matrix; numeric edge cases.
  - path: tests/fixtures/fundamental_forensics/filing_package_raw_ledger_v1.json
    what: Added 2024-12-31 nested debt/cash facts for the net_debt acceptance test. Not requested in the golden metric set.
  - path: tests/fixtures/fundamental_forensics/expected_financial_intelligence_packet_v1.json
    what: Regenerated golden bytes after the contract freeze.
  - path: agentos/decisions/DEC-FIF-1R-HERMETIC-PACKET-CONTRACT.md
    what: Recorded the FIF-1R contract choices.
decisions:
  - DEC:FIF-1-INDEPENDENT-FILING-PACKAGE-FIXTURE
  - DEC:FIF-1R-HERMETIC-PACKET-CONTRACT
discoveries:
  - DSC:COMPANYFACTS-CANNOT-FEED-CORE-METRIC-QUERY
prs:
  - 5809
verified:
  - claim: >
      Focused FIF packet tests pass, including Laws 1-12, nested net_debt
      closure, pure-kernel I/O denial, schema negatives, and two-process
      golden byte identity.
    command: >
      project-venv python -m pytest tests/test_fundamental_forensics_financial_intelligence_packet.py -q
    result: 25 passed
  - claim: Query, registry, companyfacts ledger, and import-pinning regressions pass.
    command: >
      project-venv python -m pytest tests/test_fundamental_forensics_query.py
      tests/test_fundamental_forensics_metric_registry.py
      tests/test_fundamental_forensics_companyfacts_ledger.py
      tests/test_check_script_import_pinning.py::test_unpinned_entry_scripts_only_shrink -q
    result: 147 passed
  - claim: Agent OS records validate.
    command: python3 scripts/agentos.py validate
    result: 0 error(s), 11 unrelated pre-existing warnings
  - claim: FY2023 gross_margin dependencies all resolve; gross_profit is evidence-only.
    command: assemble golden packet and walk formula_leaves
    result: >
      evidence_cells=3 all gross_profit; requested cells do not include
      gross_profit; FY2023 gross_margin deps resolve to gross_profit + revenue
  - claim: Prior pack-5 qledger failure is not present on this head.
    command: >
      project-venv python -m pytest
      tests/test_qledger_desk_adapter.py::test_demand_chain_control_leg_resolves_through_membership_and_aliases
      tests/test_check_script_import_pinning.py::test_unpinned_entry_scripts_only_shrink -q
    result: 2 passed
unverified:
  - claim: PR #5809 required CI packs conclude green on the FIF-1R head.
    what_would_verify: gh pr checks 5809 after push, wait for concluded packs
  - claim: Production Company Facts still cannot feed core-catalog revenue.
    what_would_verify: Convert a live attested AAPL capture and query revenue through load_core_metric_registry without monkeypatch
unresolved:
  - Operator re-review of FIF-1R before merge and before any FIF-2 work
next_actions:
  - Re-review PR https://github.com/mastermindx-market-intelligence/macro/pull/5809
  - Merge only after that review; do not start FIF-2 in this PR
do_not_redo:
  - Do not convert companyfacts_versions.json into the packet query ledger
  - Do not flip dimensions_known or inject revision_of onto Company Facts rows
  - Do not monkeypatch _fact_dimensions_allowed or relabel attested_occurrence as revenue
  - Do not add a second metric registry, query kernel, API, page, detector, score, or SEC fetch
  - Do not put filesystem/schema/digest discovery inside assemble_financial_intelligence_packet
  - Do not silently add unrequested metrics to the user cells array
danger_areas:
  - engine/fundamental_forensics/query.py consolidated_only / _fact_dimensions_allowed
  - Golden packet bytes include packet_builder_digest of financial_intelligence_packet.py; regenerating is required after any builder edit
  - tests/fixtures/fundamental_forensics/companyfacts_versions.json remains an inventory witness only
  - assemble_financial_intelligence_packet must keep receiving injected schema and digests; a default Path(__file__) read reopens blocker 1
---

FIF-1R is ready for operator re-review on PR #5809. The packet is still
display/context only. FIF-2 is not started. Do not merge in this session.

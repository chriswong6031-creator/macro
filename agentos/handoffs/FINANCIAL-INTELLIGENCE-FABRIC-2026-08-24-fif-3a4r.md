---
workstream: "WS:FINANCIAL-INTELLIGENCE-FABRIC"
session: claude/fif-3a4r
model: fable
ended_because: complete
mission: >
  FIF-3A4R SPEC_ONLY research freeze. Determine and freeze one lawful
  Mastermind contract for relating the same economic XBRL fact across
  separate SEC filings, with a deterministic AAPL A1/A2 overlap census,
  without changing runtime query behavior or implementing FIF-3A4.
state_before: >
  Sol commissioned FIF-3A4R against observed main
  cda4bd5e9fa7e7dc69eb8e0ebe55185b5efa9208. FIF-3A1/A2/A3 were already
  accepted on main. Comparative total_assets instant 2025-09-27 after both
  golden filings are visible remains NOT_EVALUABLE unlinked source vintages.
  No accepted cross-filing confirmation architecture existed.
changed:
  - path: research/financial_intelligence_fabric/FIF_3A4R_CROSS_FILING_LINEAGE_PROTOCOL.md
    what: >
      Candidate lineage protocol for Sol. Winner is a cutoff-visible
      lineage-evidence overlay over unchanged FILED occurrences. Not an
      accepted DEC.
  - path: research/financial_intelligence_fabric/FIF_3A4R_AAPL_OVERLAP_CENSUS.json
    what: Deterministic A1/A2 logical-key overlap census receipt. Research evidence only.
  - path: research/financial_intelligence_fabric/replay_fif3a4r_aapl_overlap_census.py
    what: Replay tool that rebuilds the census from accepted golden packages.
  - path: agentos/discoveries/DSC-XBRL-DUPLICATE-LAW-IS-INTRA-INSTANCE.md
    what: Duplicate/accuracy law is intra-instance because P-Equal requires one XML parent.
  - path: agentos/discoveries/DSC-AAPL-A1-A2-CROSS-FILING-OVERLAP-CENSUS.md
    what: Exact AAPL overlap class counts against accepted A3 ledger SHA.
  - path: agentos/workstreams/WS-FINANCIAL-INTELLIGENCE-FABRIC.md
    what: >
      FIF-3A4R recorded as SPEC_ONLY / CANDIDATE FOR SOL. FIF-3 stays
      IN_PROGRESS. FIF-3A1/A2/A3 remain accepted. Do not start FIF-3A4.
  - path: agentos/handoffs/FINANCIAL-INTELLIGENCE-FABRIC-2026-08-24-fif-3a4r.md
    what: Continuation handoff returning the candidate to Sol.
decisions:
  - DEC:FIF-3A1-ACCEPTED-GOLDEN-ON-MAIN
  - DEC:FIF-3A2-ACCEPTED-GOLDEN-ON-MAIN
  - DEC:FIF-3A3-REUSE-MAP
  - DEC:FIF-3A3-ACCEPTED-GOLDEN-QUERY-ON-MAIN
discoveries:
  - DSC:AAPL-UNLINKED-VINTAGES-REQUIRE-TYPED-REVISION-LINEAGE
  - DSC:COMPANYFACTS-CANNOT-FEED-CORE-METRIC-QUERY
  - DSC:XBRL-DUPLICATE-LAW-IS-INTRA-INSTANCE
  - DSC:AAPL-A1-A2-CROSS-FILING-OVERLAP-CENSUS
verified:
  - claim: origin/main at research closeout is 2df738a154acc6feae96e2ad0a6d289d3ab0f4a7 and is a descendant of Sol-observed cda4bd5e9fa7e7dc69eb8e0ebe55185b5efa9208.
    command: git fetch origin; git rev-parse origin/main; git merge-base --is-ancestor cda4bd5e9fa7e7dc69eb8e0ebe55185b5efa9208 origin/main
    result: origin/main 2df738a154acc6feae96e2ad0a6d289d3ab0f4a7; ancestor check exit 0
  - claim: STOP files that own A3 identity have empty diff versus origin/main.
    command: git diff --stat origin/main -- engine/fundamental_forensics/ixbrl_raw_ledger.py engine/fundamental_forensics/query_service.py engine/fundamental_forensics/sec_document_spine.py engine/fundamental_forensics/query.py engine/fundamental_forensics/raw_ledger.py engine/fundamental_forensics/metric_registry.py app/forensics.py tests/fixtures/fundamental_forensics/aapl_10k_2025 tests/fixtures/fundamental_forensics/aapl_10q_2026q3
    result: empty
  - claim: Replay census class_counts are exact 131 exact confirmation candidates, 1 precision-consistent LongTermDebt, 1 changed OtherAssetsNoncurrent, 1291 no_relation, 15 query-relevant consolidated mapped rows, duration overlap 0, ledger SHA ba149bd55d929d843f353e91bbf68147791fb8b4a20c258426ea2eb7527019d8.
    command: python3 research/financial_intelligence_fabric/replay_fif3a4r_aapl_overlap_census.py
    result: class_counts match committed JSON; census payload SHA d705de0dddab9761441aa9649b973dcd2f7ac2c265282658446b8bba6a8d4be0; written file SHA e405b4094e8905a9384fb1aef3c694c2e6b7244eabd7164ba3f73082822d0018
  - claim: Comparative total_assets instant 2025-09-27 remains NOT_EVALUABLE unlinked source vintages on current HEAD.
    command: python3 -m pytest tests/test_fundamental_forensics_ixbrl_raw_ledger.py::test_unlinked_vintages_are_not_evaluable -q
    result: passed
  - claim: Engine code does not import the A4R census JSON or replay tool.
    command: rg -n "FIF_3A4R_AAPL_OVERLAP_CENSUS|replay_fif3a4r" engine app
    result: no matches
  - claim: python3 scripts/agentos.py validate exits 0 on the A4R records.
    command: python3 scripts/agentos.py validate
    result: exit 0
unverified:
  - claim: FASB ASC 250 primary text for restatement presentation.
    what_would_verify: Open the FASB ASC 250 page and quote the error-correction restatement requirement independently of secondary summaries.
unresolved:
  - Sol has not accepted or rejected the cutoff-visible lineage-evidence overlay.
  - v1 exact-token confirmation versus widening to _duplicates_agree for the one LongTermDebt row is an open Sol question.
  - system_available_at pin for the first AAPL receipts is unchosen.
  - FIF-3 remains IN_PROGRESS. Production attested issuer service remains NOT_BUILT.
  - Default FIF-2 revision/packet providers remain unavailable.
next_actions:
  - Sol reviews FIF_3A4R_CROSS_FILING_LINEAGE_PROTOCOL.md and either accepts, amends, or returns LINEAGE_ARCHITECTURE_BLOCKED.
  - Do not code FIF-3A4, remint A2 FILED, activate AAPL revisions/packet, or start SNOW/CAT/BAC/GOOGL from this freeze.
  - Do not mint an accepted AgentOS DEC for this architecture until Sol rules.
  - Keep A3 historical N/E reproducible; do not append lineage events into the accepted A3 ledger object.
do_not_redo:
  - Do not reopen accepted FIF-3A1/A2/A3 identities, hashes, or source freeze.
  - Do not treat research census JSON as a runtime provider input.
  - Do not remint accepted A2 FILED occurrences as XBRL_CONFIRMATION.
  - Do not append a third confirmation occurrence while keeping A2 FILED.
  - Do not cite within-document duplicate law as proof one filing revises another.
  - Do not confirm us-gaap OtherAssetsNoncurrent 83727M versus 72634M.
  - Do not treat us-gaap LongTermDebt 90678M versus 90700M as v1 exact confirmation.
  - Do not invent revision_of from 10-Q comparative overlap with the 10-K.
danger_areas:
  - Encoding confirmation by changing occurrence event_type rewrites occurrence_id and A3 ledger SHA ba149bd55d929d843f353e91bbf68147791fb8b4a20c258426ea2eb7527019d8.
  - An overlay without system_available_at repairs A3 N/E as soon as A2 is visible.
  - Company Facts RevisionEvidence remints at birth and must not feed AAPL core metric truth.
  - Calling FIF-3 done after this research freeze would close the five-issuer slice without SNOW/CAT/BAC/GOOGL.
---

FIF-3A4R is SPEC_ONLY and candidate-for-Sol, not shipped architecture.
FIF-3A1/A2/A3 remain accepted on main. FIF-3 remains in progress.
Production attested issuer service remains NOT_BUILT.

Safe v1 confirmation candidates are the 131 exact complete logical-key
overlaps, of which 15 are empty-dimension core-mapped non-nil query
parents including total_assets 359241000000. The changed Other Assets
row is not a confirmation. The precision-different LongTermDebt row is
not v1 exact confirmation.

The candidate architecture is a cutoff-visible lineage-evidence overlay
on FinancialQueryDataset, selected by BitemporalMetricQueryEngine, pointing
at unchanged FILED occurrences. A3 datasets keep empty evidence so a
historical A3 cutoff still returns NOT_EVALUABLE. Confirmation receipts
must not enter LATEST_RESTATED or revisions[].

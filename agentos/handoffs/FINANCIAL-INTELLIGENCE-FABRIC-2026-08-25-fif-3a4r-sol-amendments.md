---
workstream: "WS:FINANCIAL-INTELLIGENCE-FABRIC"
session: claude/fif-3a4r
model: fable
ended_because: complete
prs: [6382]
mission: >
  Amend HOLD-FOR-SOL PR #6382 in place with Sol's 2026-08-25 bounded
  architecture rulings. Re-run the AAPL overlap census under tightened v1
  eligibility. Drop the unrelated board-shadow carrier. Do not merge. Do
  not code FIF-3A4. Do not mint an accepted DEC.
state_before: >
  PR #6382 was PARKED / HOLD-FOR-SOL at head 46d91240baa5 with a candidate
  protocol, a 131-row exact-confirmation census, and two unrelated
  board-shadow/_now_iso test pins. Sol ruled PASS WITH BOUNDED AMENDMENTS.
  Main had already landed the real board-shadow heal as PR #6386.
changed:
  - path: research/financial_intelligence_fabric/FIF_3A4R_CROSS_FILING_LINEAGE_PROTOCOL.md
    what: >
      Freeze Sol's seven bounded amendments. Architecture remains SPEC_ONLY,
      not an accepted DEC. HOLD-FOR-SOL remains.
  - path: research/financial_intelligence_fabric/replay_fif3a4r_aapl_overlap_census.py
    what: Tighten v1 positive guards; exclude nils; require exact original taxonomy URI/version.
  - path: research/financial_intelligence_fabric/FIF_3A4R_AAPL_OVERLAP_CENSUS.json
    what: Replayed v1.1 census after tightened eligibility. Research evidence only.
  - path: agentos/discoveries/DSC-AAPL-A1-A2-CROSS-FILING-OVERLAP-CENSUS.md
    what: Update exact counts to 130 numeric + 1 nil excluded + namespace-version proof.
  - path: agentos/workstreams/WS-FINANCIAL-INTELLIGENCE-FABRIC.md
    what: Record Sol PASS WITH BOUNDED AMENDMENTS and keep HOLD-FOR-SOL / SPEC_ONLY.
  - path: agentos/handoffs/FINANCIAL-INTELLIGENCE-FABRIC-2026-08-25-fif-3a4r-sol-amendments.md
    what: Continuation handoff after the Sol amendment freeze.
  - path: tests/test_board_shadow.py
    what: Carrier removed; file restored to origin/main (#6386 derived ASOF).
  - path: tests/test_hk_discovery_challenger.py
    what: Carrier removed; file restored to origin/main.
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
  - claim: Tightened census class_counts are 130 exact numeric confirmation candidates, 1 nil_confirmation_unspecified, 1 precision_consistent_unconfirmed, 1 changed_value, 1291 no_relation, 0 namespace mismatches, 15 query-relevant consolidated mapped rows, 93 dimensioned exact rows, ledger SHA ba149bd55d929d843f353e91bbf68147791fb8b4a20c258426ea2eb7527019d8.
    command: python3 research/financial_intelligence_fabric/replay_fif3a4r_aapl_overlap_census.py
    result: payload SHA b1577b04f553c56ba278d2057ecc07a0d23159a1d20a41339b39da4ed24c12a9; file SHA f1481fffa18720209ba98d463c25a52b4e497bff89b2159cfa3b2d74ea63ab58
  - claim: All 133 overlaps share original Clark URI http://fasb.org/us-gaap/2025 on both A1 and A2.
    command: python3 research/financial_intelligence_fabric/replay_fif3a4r_aapl_overlap_census.py
    result: source_namespace_version_proof.mismatch_count 0; overlap_concept_uri_pairs only 2025|2025 with count 133
  - claim: STOP files that own A3 identity have empty diff versus origin/main.
    command: git diff --stat origin/main -- engine/fundamental_forensics/ixbrl_raw_ledger.py engine/fundamental_forensics/query_service.py engine/fundamental_forensics/sec_document_spine.py engine/fundamental_forensics/query.py engine/fundamental_forensics/raw_ledger.py engine/fundamental_forensics/metric_registry.py app/forensics.py tests/fixtures/fundamental_forensics/aapl_10k_2025 tests/fixtures/fundamental_forensics/aapl_10q_2026q3
    result: empty
  - claim: Engine code does not import the A4R census JSON or replay tool.
    command: rg -n "FIF_3A4R_AAPL_OVERLAP_CENSUS|replay_fif3a4r" engine app
    result: no matches
  - claim: python3 scripts/agentos.py validate exits 0 on the A4R records.
    command: python3 scripts/agentos.py validate
    result: exit 0
  - claim: Carrier test files match origin/main.
    command: git diff origin/main -- tests/test_board_shadow.py tests/test_hk_discovery_challenger.py
    result: empty
unverified:
  - claim: FASB ASC 250 primary text for restatement presentation.
    what_would_verify: Open the FASB ASC 250 page and quote the error-correction restatement requirement independently of secondary summaries.
unresolved:
  - HOLD-FOR-SOL remains. Sol has not released merge or authorized FIF-3A4.
  - No accepted AgentOS DEC exists for this architecture.
  - First-implementation system_available_at is bounded but not yet a recorded receipt clock.
  - FIF-3 remains IN_PROGRESS. Production attested issuer service remains NOT_BUILT.
next_actions:
  - Keep PR #6382 draft, unarmed, HOLD-FOR-SOL.
  - Do not code FIF-3A4, remint A2 FILED, activate AAPL revisions/packet, or start SNOW/CAT/BAC/GOOGL.
  - Do not mint an accepted AgentOS DEC until Sol releases the hold.
  - Keep A3 historical N/E reproducible; do not append lineage events into the accepted A3 ledger object.
do_not_redo:
  - Do not reopen accepted FIF-3A1/A2/A3 identities, hashes, or source freeze.
  - Do not treat research census JSON as a runtime provider input.
  - Do not remint accepted A2 FILED occurrences as FactEventType.XBRL_CONFIRMATION.
  - Do not append a third confirmation occurrence while keeping A2 FILED.
  - Do not cite within-document duplicate law or _duplicates_agree as proof one filing revises or confirms another.
  - Do not confirm us-gaap OtherAssetsNoncurrent 83727M versus 72634M.
  - Do not treat us-gaap LongTermDebt 90678M versus 90700M as v1 exact confirmation.
  - Do not mint v1 xbrl_confirmation for the CommitmentsAndContingencies nil pair.
  - Do not discard the 93 dimensioned exact confirmation candidates.
  - Do not invent revision_of from 10-Q comparative overlap with the 10-K.
  - Do not re-land the board-shadow _now_iso pin on this research PR; #6386 already derived ASOF on main.
danger_areas:
  - Encoding confirmation by changing occurrence event_type rewrites occurrence_id and A3 ledger SHA ba149bd55d929d843f353e91bbf68147791fb8b4a20c258426ea2eb7527019d8.
  - An overlay without system_available_at repairs A3 N/E as soon as A2 is visible.
  - Using the census timestamp as system_available_at would authorize runtime lineage from research evidence.
  - Loading refused census classes into FinancialQueryDataset.lineage_evidence would enlarge the runtime evidence plane.
  - Company Facts RevisionEvidence remints at birth and must not feed AAPL core metric truth.
  - Calling FIF-3 done after this research freeze would close the five-issuer slice without SNOW/CAT/BAC/GOOGL.
---

FIF-3A4R remains SPEC_ONLY. Sol ruled PASS WITH BOUNDED AMENDMENTS.
HOLD-FOR-SOL remains. Do not merge. Do not code FIF-3A4.

The 131-row exact class changes to 130 numeric candidates plus 1 nil pair
excluded from v1. All 133 overlaps share us-gaap/2025 on both filings.
Query-relevant consolidated mapped rows remain 15. Dimensioned exact rows
(93) stay lawful lineage.

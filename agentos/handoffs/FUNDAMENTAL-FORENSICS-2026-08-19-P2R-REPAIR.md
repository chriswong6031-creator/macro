---
workstream: WS:FUNDAMENTAL-FORENSICS
session: claude/ff-1p2-bulk-census
model: local
ended_because: blocked
mission: >
  FF-1P2R Sol review repair on PR #5898. Keep accepted current-quarter EDGAR
  index discovery. Fail-close recovery. Fix processed-index-head, PIT retry,
  and baseline-removal lineage. Do not merge. Do not start FF-1R or FF-2.
state_before: >
  Sol reviewed 65cd21f81a10cea56017cf455e4cc799016020f4: architecture PASS,
  merge BLOCKED. Recovery fetched Submissions for every pending CIK (8 then 5
  then 2 in tests). PIT-withheld NEW index events could be consumed.
  Baseline-removed accessions could leave empty-ledger cumulative lineage.
  Previous-quarter weekly reconciliation was still a False-returning seam.
changed:
  - path: engine/fundamental_forensics/broad_sec_store.py
    what: Fail-close mode=recovery with recovery_plan_required before SEC/R2. index_latest advances only on census_complete. Unresolved NEW/PIT/unevaluable index events do not consume the snapshot. Cumulative union is prior ledger plus admitted plus removed index accessions. Correction reason no longer poisons a successful observation.
  - path: scripts/run_fundamental_forensics_broad_sec.py
    what: CLI --mode recovery prints recovery_plan_required JSON and returns 1 before live_fetchers or open_store.
  - path: .github/workflows/filing-forensics-broad-sec.yml
    what: Keep workflow_dispatch recovery option; comment that it fail-closes until FF-1R. Schedule 03:15 UTC, timeout 90, group filing-forensics-sec unchanged.
  - path: contracts/fundamental_forensics_broad_sec_run.schema.json
    what: Add recovery_plan_required and edgar_index_event_not_causally_admitted reason codes.
  - path: tests/test_fundamental_forensics_edgar_index.py
    what: Replace 8-to-5-to-2 recovery execution claims with fail-closed recovery. Add mandatory PIT two-run, unevaluable, and baseline-removal lineage tests.
  - path: tests/test_fundamental_forensics_broad_sec.py
    what: Recovery-execution tests now prove fail-close. Incremental leftover continuation is ignored. Byte-budget overflow does not advance latest-complete or index_latest.
  - path: tests/fixtures/r2_delivery_macro_evidence_files.v1.tsv
    what: Repin broad_sec_store.py line_count/sha256 after the kernel grew.
  - path: tests/fixtures/r2_delivery_macro_anchor_lines.v1.tsv
    what: Move PREFIX fingerprint from line 50 to line 55.
  - path: config/r2_delivery_plane_classification.v1.json
    what: Move fundamental_forensics_broad_sec_source evidence anchor to line 55.
  - path: agentos/decisions/DEC-FF-1-RECOVERY-NOT-COMMISSIONED.md
    what: Sol-owned ruling that #5898 does not commission July recovery.
  - path: agentos/workstreams/WS-FUNDAMENTAL-FORENSICS.md
    what: Status stays blocked. FF-1P2R BUILT_NOT_PROVEN. FF-1R NOT_BUILT with 2560/2541 starting fact.
verified:
  - claim: "Targeted FF-1 suites are green — 70 passed (edgar_index 16, broad_sec 31, lane 4, collector 19)."
    command: "/opt/homebrew/bin/python3.12 -m pytest tests/test_fundamental_forensics_edgar_index.py tests/test_fundamental_forensics_broad_sec.py tests/test_filing_forensics_broad_sec_lane.py tests/test_edgar_forensics_collector.py -q -p no:randomly"
    result: "70 passed"
  - claim: "Recovery mode fail-closes before SEC acquisition and before Research R2 mutation."
    command: "/opt/homebrew/bin/python3.12 -m pytest tests/test_fundamental_forensics_edgar_index.py::test_recovery_mode_is_not_commissioned_before_sec_or_r2 tests/test_fundamental_forensics_broad_sec.py::test_cli_recovery_mode_fails_closed_with_recovery_plan_required -q -p no:randomly"
    result: "2 passed; index/submissions/facts fetches empty; PREFIX keys unchanged"
  - claim: "PIT future-to-cutoff NEW index event is not consumed in run 1 and is admitted exactly once in run 2."
    command: "/opt/homebrew/bin/python3.12 -m pytest tests/test_fundamental_forensics_edgar_index.py::test_pit_cutoff_index_event_is_not_consumed_and_retries -q -p no:randomly"
    result: "1 passed"
  - claim: "Baseline index accession removed before any issuer manifest stays in cumulative lineage."
    command: "/opt/homebrew/bin/python3.12 -m pytest tests/test_fundamental_forensics_edgar_index.py::test_baseline_removed_index_accession_stays_in_cumulative_lineage -q -p no:randomly"
    result: "1 passed"
  - claim: "Trigger closure GAP 0, DAG OK, skip-only 0, workflow YAML OK, AgentOS 0 errors."
    command: "/opt/homebrew/bin/python3.12 scripts/check_ci_trigger_closure.py; /opt/homebrew/bin/python3.12 scripts/check_dag_conformance.py; /opt/homebrew/bin/python3.12 scripts/check_skip_only_suites.py; /opt/homebrew/bin/python3.12 scripts/check_workflow_yaml.py .github/workflows; /opt/homebrew/bin/python3.12 scripts/agentos.py validate"
    result: "TRIGGER GAP 0; DAG conformance OK (2 pre-existing suspect drifts); SKIP-ONLY 0; workflow YAML OK 92 files; agentos 0 error(s), 8 unrelated warning(s)"
  - claim: "Unrun-suite audit has 0 strictly dark suites."
    command: "/opt/homebrew/bin/python3.12 scripts/audit_unrun_tests.py"
    result: "STRICTLY DARK (also untriggerable) : 0"
  - claim: "R2 delivery-plane census is green after FF-1 PREFIX anchor repin."
    command: "/opt/homebrew/bin/python3.12 -m pytest tests/test_r2_delivery_plane_classification.py -q -p no:randomly"
    result: "21 passed"
unverified:
  - claim: "GitHub required packs/fences on the post-repair head will conclude green."
    what_would_verify: "After push, wait for ci.yml packs plus fences.yml on the exact new SHA; do not treat a cancelled planner as green."
  - claim: "A production incremental on Research R2 will finish a 2837-issuer index baseline inside 90 minutes with one master.zip GET."
    what_would_verify: "Only after Sol merges #5898 and authorizes one explicit incremental dispatch."
unresolved:
  - "FF-1 is not PROVEN_LIVE and is not done."
  - "FF-1R July recovery is NOT_BUILT. Live Q3 index candidates were 2560 rows / 2541 unique CIKs with filed_on >= 2026-07-12."
  - "Previous-quarter weekly reconciliation is SPEC_ONLY / NOT_BUILT."
  - "Unevaluable index rows pin the current-quarter processed head until the row becomes evaluable or disappears from the index."
next_actions:
  - "Sol reviews the repaired PR #5898 unmerged."
  - "Do not merge, do not dispatch production incremental, do not dispatch July recovery."
  - "Do not start FF-1R or FF-2."
do_not_redo:
  - "Do not redesign accepted current-quarter EDGAR master-index discovery."
  - "Do not ship recovery that fetches Submissions for every pending CIK before Company Facts."
  - "Do not download submissions.zip or companyfacts.zip."
  - "Do not treat index_latest as the latest downloaded archive."
  - "Do not key baseline on list_prefix(snapshots/) while a processed pointer is absent."
  - "Do not start FF-2, detectors, Prophet, or Neural Web from this PR."
danger_areas:
  - "index_latest is the latest fully processed snapshot. PIT/unevaluable NEW events must retry from that pointer."
  - "Snapshots may exist without advancing index_latest. Do not infer a baseline from snapshot objects if the processed pointer is absent; that would fan thousands of Submissions."
  - "Leftover recovery continuation objects must be ignored by incremental. Do not overflow Company Facts from a planted backlog."
  - "A permanently unevaluable index row pins the quarter head on purpose until the row is evaluable or gone."
prs: [5898]
decisions:
  - DEC:FF-1-BROAD-DISCOVERY-USES-EDGAR-INDEXES
  - DEC:FF-1-RECOVERY-NOT-COMMISSIONED
discoveries:
  - DSC:FF-1-Q3-2026-MASTER-INDEX-CANARY
  - DSC:FF-1-PER-ISSUER-CENSUS-EXCEEDS-90M
  - DSC:FF-1-SEC-BULK-ARCHIVE-EXCEEDS-1GIB
---

PR #5898 now owns current-quarter index-driven discovery only. Recovery
dispatch still exists and fail-closes with recovery_plan_required until
FF-1R. Processed-index-head is the PIT retry boundary; no second queue.

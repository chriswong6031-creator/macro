---
workstream: WS:FUNDAMENTAL-FORENSICS
session: claude/ff-1p2-bulk-census
model: local
ended_because: blocked
mission: >
  FF-1P2R index-driven broad SEC discovery on PR #5898. Supersede the
  unmerged submissions.zip design with official EDGAR master indexes.
  Do not merge. Do not start July recovery. Do not start FF-2.
state_before: >
  PR #5898 HEAD 23186c9d87adb6f82b5cf70c55a2ff0a140ea21e recorded the
  submissions.zip 1.45 GiB stop. Sol rejected a 2 GiB bound and ordered
  EDGAR full-index discovery instead. FF-1 is not PROVEN_LIVE. July
  recovery has not started.
changed:
  - path: collectors/edgar_forensics.py
    what: Narrow retrieve_full_master_index primitive on the existing SEC HTTP stack; canonical www.sec.gov full-index URL only.
  - path: engine/fundamental_forensics/broad_sec_store.py
    what: Index-driven discovery, empty-snapshot baseline, affected-only Submissions, set-diff corrections, quarter-scoped snapshots, recovery backlog bound to index SHA.
  - path: scripts/run_fundamental_forensics_broad_sec.py
    what: Unpack three live fetchers; flushed FF_BROAD_PROGRESS phases.
  - path: contracts/fundamental_forensics_broad_sec_run.schema.json
    what: Index receipt object and new edgar_index_* reason codes.
  - path: tests/test_fundamental_forensics_broad_sec.py
    what: Existing FF-1 contracts rewritten onto index baseline then affected-only fetches.
  - path: tests/test_fundamental_forensics_edgar_index.py
    what: Acceptance A–K — 2837 baseline, unchanged, one-new-10-Q, non-relevant noise, correction, ZIP safety, clocks, July derivation, continuation, quarter rollover, leftover state.
  - path: .github/ci/legacy-jobs.yml
    what: engine-render-guards now names the index suite.
  - path: agentos/decisions/DEC-FF-1-BROAD-DISCOVERY-USES-EDGAR-INDEXES.md
    what: Sol-owned replacement decision.
  - path: agentos/decisions/DEC-FF-1-BROAD-SUBMISSIONS-USES-SEC-BULK-ARCHIVE.md
    what: superseded_by DEC:FF-1-BROAD-DISCOVERY-USES-EDGAR-INDEXES; not canonical.
  - path: agentos/workstreams/WS-FUNDAMENTAL-FORENSICS.md
    what: Status remains blocked; next_action is return #5898 to Sol unmerged.
verified:
  - claim: "Live Q3 2026 master.zip canary was HTTP 200, 2132920 bytes, SHA-256 feb04748bf47569a886f719e63a6efe2f3c67a2a0c9ded9d73acb0b92a5482f3, member master.idx 15184383 bytes."
    command: "cat /tmp/ff-1p2r-canary/canary.json"
    result: "http_status=200 redirected=false archive_bytes=2132920 member_bytes=15184383 parsed_row_count=164511 latest_filing_date=2026-08-17"
  - claim: "July recovery candidates from that index with filed_on>=2026-07-12 are 2560 rows / 2541 unique canonical CIKs."
    command: "python3 -c 'import json; print(json.load(open(\"/tmp/ff-1p2r-canary/canary.json\"))[\"recovery_candidate_unique_ciks\"])'"
    result: "2541"
  - claim: "FF-1 + index + lane suites pass."
    command: "/opt/homebrew/bin/python3.12 -m pytest tests/test_fundamental_forensics_broad_sec.py tests/test_fundamental_forensics_edgar_index.py tests/test_filing_forensics_broad_sec_lane.py tests/test_edgar_forensics_collector.py -q -p no:randomly"
    result: "64 passed"
  - claim: "AgentOS validate is clean of errors."
    command: "/opt/homebrew/bin/python3.12 scripts/agentos.py validate"
    result: "0 error(s), 8 warning(s) unrelated to FF-1"
  - claim: "CI trigger closure, DAG, and skip-only audits are green for this change."
    command: "/opt/homebrew/bin/python3.12 scripts/check_ci_trigger_closure.py; scripts/check_dag_conformance.py; scripts/check_skip_only_suites.py"
    result: "TRIGGER GAP 0; DAG conformance OK; SKIP-ONLY 0"
unverified:
  - claim: "A production incremental on Research R2 will finish a 2837-issuer index baseline inside 90 minutes with one master.zip GET."
    what_would_verify: "After Sol merges #5898, one explicit workflow_dispatch incremental; latest-complete exists; submissions_fetched=0."
  - claim: "The 2541 July recovery CIK count is still accurate on the merge-day index rebuild."
    what_would_verify: "Repeat the read-only canary immediately before any recovery dispatch."
unresolved:
  - "FF-1 is not PROVEN_LIVE. Do not start July recovery from this PR."
  - "Weekly previous-quarter reconciliation is a frozen seam (previous_quarter_reconciliation_due always returns False)."
  - "July recovery backlog is ~2541 CIKs vs MAX_AFFECTED_ISSUERS=64, so recovery is many continuation runs after an incremental baseline."
  - "Timed-out run 32116597760 may have admitted valid issuer objects. Index baseline must not purge them."
next_actions:
  - "Sol reviews PR #5898 unmerged."
  - "After merge, one explicit production incremental baseline under 90 minutes."
  - "Do not dispatch July recovery until Sol sees the 2541 CIK backlog and authorizes continuation runs."
  - "Do not start FF-2."
do_not_redo:
  - "Do not authorize a 2 GiB submissions.zip bound or download submissions.zip nightly."
  - "Do not poll 2837 data.sec.gov Submissions on a quiet night."
  - "Do not raise timeout-minutes or MAX_AFFECTED_ISSUERS to finish recovery in one run."
  - "Do not purge fundamental_forensics/broad-sec/v1/."
  - "Do not implement unbounded historical-quarter crawling. Weekly previous-quarter reconciliation stays frozen until Sol authorizes it."
  - "Do not start FF-2 or July production recovery from this PR."
danger_areas:
  - "Index HTTP Last-Modified, archive_retrieved_at, and index_latest_filed_on are never sec_accepted_at."
  - "Index state is quarter-scoped. Q4 baseline must not treat missing Q3 rows as mass corrections."
  - "Do not advance index latest on a degraded incremental change night, or remaining NEW CIKs will be hidden."
  - "An empty prior snapshot is a discovery baseline (0 issuer fetches), not 2837 new events."
prs: [5898]
decisions:
  - DEC:FF-1-BROAD-DISCOVERY-USES-EDGAR-INDEXES
discoveries:
  - DSC:FF-1-PER-ISSUER-CENSUS-EXCEEDS-90M
  - DSC:FF-1-SEC-BULK-ARCHIVE-EXCEEDS-1GIB
  - DSC:FF-1-Q3-2026-MASTER-INDEX-CANARY
---

Broad FF-1 discovery is the current-quarter EDGAR master index. Per-issuer
Submissions and selective Company Facts run only for affected canonical
issuers. The first incremental with no prior index snapshot is the production
baseline we were trying to obtain, without 2837 issuer GETs.

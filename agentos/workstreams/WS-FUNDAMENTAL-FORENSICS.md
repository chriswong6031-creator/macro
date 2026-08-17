---
key: FUNDAMENTAL-FORENSICS
title: Filing Forensics — source-preserving SEC evidence workbench
objective: >
  Keep Filing Forensics honest about source clocks (FF-0, closed live) and give
  Mastermind a production-grade incremental broad SEC source plane (FF-1) so
  later waves can see which issuers have new SEC information without a rerender
  minting freshness. FF-2 must not start until Sol reviews and merges FF-1.
status: awaiting_review
program: fundamental-forensics
repos: [macro]
owner: coo-fable
class: build
blast_radius: user_facing
ambiguity: specified
owns_paths:
  - engine/fundamental_forensics/
  - app/forensics.py
  - templates/fundamental_forensics.html.j2
  - templates/fundamental_forensics.js
  - templates/fundamental_forensics.css
  - contracts/fundamental_forensics_health.schema.json
  - contracts/fundamental_forensics_broad_sec_run.schema.json
  - contracts/fundamental_forensics_broad_sec_issuer_manifest.schema.json
  - scripts/run_fundamental_forensics_broad_sec.py
  - .github/workflows/filing-forensics-broad-sec.yml
  - tests/test_fundamental_forensics_health.py
  - tests/test_fundamental_forensics_broad_sec.py
  - tests/test_filing_forensics_broad_sec_lane.py
waves:
  - id: FF-0
    title: Freshness truth and visible degradation
    status: done
    pr: 5794
  - id: FF-1
    title: Incremental Broad SEC Source Plane
    status: awaiting_ci
    depends_on: [FF-0]
  - id: FF-2
    title: Broad workbench rebuild from the FF-1 source plane
    status: todo
    depends_on: [FF-1]
landmines:
  - "composed-state generated_at is the EDGAR/source clock, reported as broad_source_at only. It is never composed_state_at, last_successful_build_at, last_publication_at, or private_object_at."
  - "Source freshness SLA is 4 days (daily pipeline + weekend + one missed night). Do not reuse PUBLIC_SUMMARY_MAX_AGE_DAYS (30) as a freshness claim."
  - "GET /api/forensics/health must stay a clocks/status document. Putting assert_no_private_leak in the request path would 500 a paid route; leak checks belong in tests."
  - "Desktop evidence used to early-return in openEvidence(); the CTA only focused a finding. The analysis drawer (is-open + data-analysis-open + scrim) is the FF-0 visible transition."
  - "Session worktrees are sparse by default. Never write into omitted data/ — that truncates the committed artifact."
  - "FF-1 object identity is SHA-256 of exact SEC bytes. Poll clocks must not enter that identity. Company Facts is a current observed snapshot, never as-of poll_started_at."
  - "Partial polls may persist successful issuer evidence but must not advance latest-complete. Scheduled lane exits non-zero on partial."
  - "FF-1 shares concurrency group filing-forensics-sec with Wave-2. Do not give it a second group."
do_not_redo:
  - "Do not modify FF-0 (app/forensics.py, engine/fundamental_forensics/health.py, templates/fundamental_forensics*, site/fundamental_forensics*, scripts/build_fundamental_forensics.py)."
  - "Do not start FF-2: no workbench rebuild, detectors, findings publish, Prophet/Neural Web, attested-history, or Calcbench."
  - "Do not scale Wave-2, raise HARD_MAX_TICKERS, or turn run_fundamental_forensics_wave2.py into a universe crawler."
  - "Do not productionize scripts/backfill_edgar_quarterly.py or write a second data.sec.gov HTTP client."
  - "Do not create a second hand-maintained 1,500-name universe JSON. Universe is data/edgar/fundamentals.parquet."
  - "Do not present page render time or evaluated_at as source freshness."
  - "Do not relabel generated_at or public_summary generated_at as a build, composition, or publication clock."
  - "Do not merge the FF-1 PR from the worker session; return it to Sol for review."
next_action: Sol reviews the FF-1 PR. Do not merge from the worker session. Do not start FF-2.
---

## Context

FF-0 is closed live (operator-signed production smoke, all five checks PASS,
PR #5794). FF-1 is the incremental broad SEC source plane: poll Submissions for
every issuer in `data/edgar/fundamentals.parquet`, admit exact bytes into
`fundamental_forensics/broad-sec/v1/`, and fetch Company Facts only when
relevant periodic filing state changes. It does not rebuild broad FF state.

---
key: FUNDAMENTAL-FORENSICS
title: Filing Forensics — source-preserving SEC evidence workbench
objective: >
  Keep Filing Forensics honest about source clocks (FF-0, closed live) and give
  Mastermind a production-grade incremental broad SEC source plane (FF-1) so
  later waves can see which issuers have new SEC information without a rerender
  minting freshness. FF-2 must not start until FF-1 is production-proven live.
status: blocked
program: fundamental-forensics
repos: [macro]
owner: coo-fable
class: build
blast_radius: user_facing
ambiguity: specified
blocked_by:
  - "Production incremental 32116597760 cancelled at the 90-minute job budget on the 2837-issuer per-issuer census. FF-1 is not PROVEN_LIVE. Do not start FF-2."
  - "FF-1P2R current-quarter index discovery on PR #5898 is BUILT_NOT_PROVEN, awaiting Sol review / production commissioning. #5898 does not perform production recovery."
  - "FF-1R July recovery engine is NOT_BUILT. Live Q3 index candidates are 2560 rows / 2541 unique CIKs. Do not start FF-1R from this PR."
discoveries:
  - DSC:FF-1-LIVE-UNIVERSE-EXCEEDS-2500
  - DSC:FF-1-PER-ISSUER-CENSUS-EXCEEDS-90M
  - DSC:FF-1-SEC-BULK-ARCHIVE-EXCEEDS-1GIB
  - DSC:FF-1-Q3-2026-MASTER-INDEX-CANARY
decisions:
  - DEC:FF-1-UNIVERSE-BIND-CAP-4000
  - DEC:FF-1-BROAD-DISCOVERY-USES-EDGAR-INDEXES
  - DEC:FF-1-RECOVERY-NOT-COMMISSIONED
owns_paths:
  - engine/fundamental_forensics/
  - app/forensics.py
  - templates/fundamental_forensics.html.j2
  - templates/fundamental_forensics.js
  - templates/fundamental_forensics.css
  - contracts/fundamental_forensics_health.schema.json
  - contracts/fundamental_forensics_broad_sec_run.schema.json
  - contracts/fundamental_forensics_broad_sec_issuer_manifest.schema.json
  - collectors/edgar_forensics.py
  - scripts/run_fundamental_forensics_broad_sec.py
  - .github/workflows/filing-forensics-broad-sec.yml
  - tests/test_fundamental_forensics_health.py
  - tests/test_fundamental_forensics_broad_sec.py
  - tests/test_filing_forensics_broad_sec_lane.py
  - tests/test_fundamental_forensics_edgar_index.py
waves:
  - id: FF-0
    title: Freshness truth and visible degradation
    status: done
    pr: 5794
  - id: FF-1
    title: Incremental Broad SEC Source Plane
    status: in_progress
    depends_on: [FF-0]
    pr: [5820, 5864, 5898]
    next_action: FF-1P2R is BUILT_NOT_PROVEN on PR #5898; current-quarter discovery only; awaiting Sol review / production commissioning.
  - id: FF-1R
    title: July recovery engine
    status: todo
    depends_on: [FF-1]
    next_action: NOT_BUILT. Starting fact from DSC:FF-1-Q3-2026-MASTER-INDEX-CANARY — 2560 relevant rows / 2541 unique canonical CIKs with filed_on >= 2026-07-12. Do not start now.
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
  - "recorded_at must not default to poll_started_at. Submissions and Company Facts each carry their own retrieved_at stamped after exact bytes. poll_completed_at is sampled only after issuer attempts conclude."
  - "An empty FF-1 index snapshot makes incremental a discovery baseline: persist the current-quarter relevant set, emit a complete census, and fetch zero per-issuer Submissions or Company Facts. Do not treat quarter-to-date index rows as new events on that first run."
  - "Partial polls may persist successful issuer evidence but must not advance latest-complete. Scheduled lane exits non-zero on partial. latest-complete is a compact pointer and commits last."
  - "FF-1 shares concurrency group filing-forensics-sec with Wave-2. Do not give it a second group."
  - "Live data/edgar/fundamentals.parquet can exceed an outdated MAX_UNIVERSE_ISSUERS. Measure unique issuer count against the cap before dispatching recovery. Do not shrink the parquet to fit the cap."
  - "Broad FF-1 discovery is the official EDGAR full-index master ZIP. Do not fan 2837 data.sec.gov requests. Do not download submissions.zip nightly. Wave-2 stays per-issuer/realtime. Never purge fundamental_forensics/broad-sec/v1/."
  - "A cancelled 90-minute run may have admitted valid immutable objects with no latest-complete. Index baseline may become canonical while those objects remain. Reconcile issuer latest pointers only when an issuer is affected; do not infer emptiness from list_prefix."
  - "Index HTTP Last-Modified, archive_retrieved_at, and index_latest_filed_on are never sec_accepted_at. Acceptance comes only from per-issuer Submissions."
  - "Index state is quarter-scoped. Do not treat Q3 rows missing from a Q4 baseline as mass corrections."
  - "index_latest is the latest fully processed discovery snapshot, not the latest archive downloaded. Unresolved PIT/unevaluable NEW index events must not advance it."
  - "Previous-quarter weekly reconciliation is SPEC_ONLY / NOT_BUILT. Current-quarter rebuilt-index corrections are implemented; FF-1 is not globally correction-safe yet."
do_not_redo:
  - "Do not modify FF-0 (app/forensics.py, engine/fundamental_forensics/health.py, templates/fundamental_forensics*, site/fundamental_forensics*, scripts/build_fundamental_forensics.py)."
  - "Do not start FF-2: no workbench rebuild, detectors, findings publish, Prophet/Neural Web, attested-history, or Calcbench."
  - "Do not scale Wave-2, raise HARD_MAX_TICKERS, or turn run_fundamental_forensics_wave2.py into a universe crawler."
  - "Do not productionize scripts/backfill_edgar_quarterly.py or write a second data.sec.gov HTTP client."
  - "Do not create a second hand-maintained 1,500-name universe JSON. Universe is data/edgar/fundamentals.parquet."
  - "Do not treat prior_manifest is None as equivalent to every issuer needing Company Facts."
  - "Do not write the full run receipt into latest-observation.json or latest-complete.json; those pointers are 16KiB."
  - "Do not relabel generated_at or public_summary generated_at as a build, composition, or publication clock."
  - "Do not treat PR #5820 merge as production proof. The first scheduled incremental failed universe_invalid."
  - "Do not dispatch July recovery from PR #5898. mode=recovery fail-closes with recovery_plan_required until FF-1R. Live Q3 index implies 2560 rows / 2541 unique CIKs after 2026-07-12."
  - "Do not ship recovery that fetches Submissions for every pending CIK before selecting Company Facts. That 8→5→2 shape is not accepted architecture."
  - "Do not raise MAX_AFFECTED_ISSUERS or the Company Facts byte budget to finish recovery in one run."
  - "Do not raise timeout-minutes to finish the 2837-issuer census. Do not treat PR #5864 merge as production proof."
  - "Do not purge fundamental_forensics/broad-sec/v1/ after a cancelled run."
  - "Do not ingest companyfacts.zip. Do not change Wave-2."
  - "Do not authorize or freeze a submissions.zip compressed maximum. Live Content-Length was 1558585919. Sol rejected a 2 GiB bound."
  - "Do not move the 03:15 UTC schedule merely because submissions.zip rebuilds around 03:00 ET. Q3 master.zip Last-Modified was 02:02 UTC."
next_action: Return PR #5898 to Sol unmerged. FF-1P2R is BUILT_NOT_PROVEN (current-quarter discovery). FF-1R is NOT_BUILT. Prior-quarter weekly reconciliation is NOT_BUILT. Do not merge, do not dispatch incremental or recovery, do not start FF-2.
---

## Context

FF-0 is closed live (operator-signed production smoke, all five checks PASS,
PR #5794). FF-1 is the incremental broad SEC source plane. Discovery is the
official EDGAR full-index master ZIP; per-CIK Submissions and selective
Company Facts run only for affected canonical issuers
(`DEC:FF-1-BROAD-DISCOVERY-USES-EDGAR-INDEXES`).

PR #5820 merged (`cd064848298063faac82059f71daf24bdd4112a2`). PR #5864
merged the 4000 bind-cap repair (`4f59f720a0a1459a11a7bd131e41833c38cbe0d4`).
The first scheduled incremental (run 32097495749) failed `universe_invalid`.
The first incremental after the cap raise (run 32116597760) cancelled at the
90-minute job timeout on the per-issuer census and emitted no receipt. The
submissions.zip canary declared 1.45 GiB and was correctly stopped. FF-1 is
not PROVEN_LIVE.

#5898 owns current-quarter index-driven discovery only
(`DEC:FF-1-RECOVERY-NOT-COMMISSIONED`). `mode=recovery` fail-closes with
`recovery_plan_required` before any SEC call or Research R2 write. FF-1R
(July recovery engine) is NOT_BUILT; the measured starting fact is 2560
relevant rows / 2541 unique canonical CIKs with `filed_on >= 2026-07-12`.
Previous-quarter weekly reconciliation remains SPEC_ONLY / NOT_BUILT.
Do not mark FF-1 done. FF-2 remains forbidden.

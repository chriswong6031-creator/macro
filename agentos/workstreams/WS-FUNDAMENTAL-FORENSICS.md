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
  - "Live canonical parquet has 2837 issuers; merged MAX_UNIVERSE_ISSUERS=2500 fail-closed the first scheduled incremental (run 32097495749, universe_invalid). Repair raises the bind cap to 4000. Do not resume July recovery until that repair is on main."
discoveries:
  - DSC:FF-1-LIVE-UNIVERSE-EXCEEDS-2500
decisions:
  - DEC:FF-1-UNIVERSE-BIND-CAP-4000
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
    status: in_progress
    depends_on: [FF-0]
    pr: [5820]
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
  - "Empty-store recovery establishes a Submissions baseline for every observed issuer. Company Facts is only for a genuine recovery_delta / new accession versus the cumulative ledger. filings.recent removal is not a new filing."
  - "Partial polls may persist successful issuer evidence but must not advance latest-complete. Scheduled lane exits non-zero on partial. latest-complete is a compact pointer and commits last."
  - "FF-1 shares concurrency group filing-forensics-sec with Wave-2. Do not give it a second group."
  - "Live data/edgar/fundamentals.parquet can exceed an outdated MAX_UNIVERSE_ISSUERS. Measure unique issuer count against the cap before dispatching recovery. Do not shrink the parquet to fit the cap."
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
  - "Do not dispatch July recovery while the live parquet exceeds the bind cap on main."
  - "Do not raise MAX_AFFECTED_ISSUERS or the Company Facts byte budget to finish recovery in one run."
next_action: Sol accepted MAX_UNIVERSE_ISSUERS=4000. Squash-merge #5864 once required CI/fences are green on the current head. FF-1 remains blocked and not PROVEN_LIVE until production commissioning finishes. FF-2 remains forbidden.
---

## Context

FF-0 is closed live (operator-signed production smoke, all five checks PASS,
PR #5794). FF-1 is the incremental broad SEC source plane: poll Submissions for
every issuer in `data/edgar/fundamentals.parquet`, admit exact bytes into
`fundamental_forensics/broad-sec/v1/`, and fetch Company Facts only when
relevant periodic filing state changes. It does not rebuild broad FF state.

PR #5820 merged (`cd064848298063faac82059f71daf24bdd4112a2`). The first
scheduled incremental (run 32097495749) failed `universe_invalid` because the
live parquet has 2837 issuers and the merged cap was 2500. FF-1 is not
PROVEN_LIVE. July recovery has not started.

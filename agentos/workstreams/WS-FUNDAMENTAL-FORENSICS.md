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
  - "Production incremental 32116597760 cancelled at the 90-minute job budget on the 2837-issuer per-issuer census. FF-1 is not PROVEN_LIVE. July recovery has not started. Do not start FF-2."
  - "Live SEC bulk submissions.zip Content-Length is 1558585919 bytes (~1.45 GiB), above the ~1 GiB canary stop. Do not freeze MAX_BULK_ARCHIVE_BYTES without Sol."
discoveries:
  - DSC:FF-1-LIVE-UNIVERSE-EXCEEDS-2500
  - DSC:FF-1-PER-ISSUER-CENSUS-EXCEEDS-90M
  - DSC:FF-1-SEC-BULK-ARCHIVE-EXCEEDS-1GIB
decisions:
  - DEC:FF-1-UNIVERSE-BIND-CAP-4000
  - DEC:FF-1-BROAD-SUBMISSIONS-USES-SEC-BULK-ARCHIVE
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
waves:
  - id: FF-0
    title: Freshness truth and visible degradation
    status: done
    pr: 5794
  - id: FF-1
    title: Incremental Broad SEC Source Plane
    status: in_progress
    depends_on: [FF-0]
    pr: [5820, 5864]
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
  - "Broad FF-1 scheduled acquisition is the SEC bulk Submissions ZIP. Do not fan 2837 data.sec.gov requests. Wave-2 stays per-issuer/realtime. Never purge fundamental_forensics/broad-sec/v1/."
  - "A cancelled 90-minute run may have admitted valid immutable objects with no latest-complete. Reconcile issuer latest pointers; do not infer emptiness from list_prefix."
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
  - "Do not raise timeout-minutes to finish the 2837-issuer census. Do not treat PR #5864 merge as production proof."
  - "Do not purge fundamental_forensics/broad-sec/v1/ after a cancelled run."
  - "Do not ingest companyfacts.zip in FF-1P2. Do not change Wave-2."
  - "Do not freeze a bulk-archive compressed maximum above ~1 GiB without Sol. Live Content-Length was 1558585919."
next_action: Sol must authorize a compressed bulk-archive bound that can admit the live 1558585919-byte submissions.zip (~1.45 GiB) before FF-1P2 acquisition code may freeze MAX_BULK_ARCHIVE_BYTES. Do not stream the archive under a silent >1 GiB cap. FF-1 remains blocked and not PROVEN_LIVE. FF-2 remains forbidden.
---

## Context

FF-0 is closed live (operator-signed production smoke, all five checks PASS,
PR #5794). FF-1 is the incremental broad SEC source plane: poll Submissions for
every issuer in `data/edgar/fundamentals.parquet`, admit exact bytes into
`fundamental_forensics/broad-sec/v1/`, and fetch Company Facts only when
relevant periodic filing state changes. It does not rebuild broad FF state.

PR #5820 merged (`cd064848298063faac82059f71daf24bdd4112a2`). PR #5864
merged the 4000 bind-cap repair (`4f59f720a0a1459a11a7bd131e41833c38cbe0d4`).
The first scheduled incremental (run 32097495749) failed `universe_invalid`.
The first incremental after the cap raise (run 32116597760) cancelled at the
90-minute job timeout on the per-issuer census and emitted no receipt. FF-1
is not PROVEN_LIVE. July recovery has not started. Broad scheduled
acquisition is the official SEC bulk Submissions archive
(`DEC:FF-1-BROAD-SUBMISSIONS-USES-SEC-BULK-ARCHIVE`).

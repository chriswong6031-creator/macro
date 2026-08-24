---
key: FUNDAMENTAL-FORENSICS
title: Filing Forensics — source-preserving SEC evidence workbench
objective: >
  Keep Filing Forensics honest about source clocks (FF-0, closed live) and give
  Mastermind a production-grade incremental broad SEC source plane (FF-1) so
  later waves can see which issuers have new SEC information without a rerender
  minting freshness. FF-2 must not start until FF-1 is production-proven live.
status: active
program: fundamental-forensics
repos: [macro]
owner: coo-fable
class: build
blast_radius: user_facing
ambiguity: specified
discoveries:
  - DSC:FF-1-LIVE-UNIVERSE-EXCEEDS-2500
  - DSC:FF-1-PER-ISSUER-CENSUS-EXCEEDS-90M
  - DSC:FF-1-SEC-BULK-ARCHIVE-EXCEEDS-1GIB
  - DSC:FF-1-Q3-2026-MASTER-INDEX-CANARY
  - DSC:FF-1R-RECOVERY-PLAN-EPOCH-IS-FROZEN
  - DSC:FF-1-IMMUTABLE-MANIFEST-IS-NOT-A-COMPACT-POINTER
  - DSC:FF-1R-ANGO-ACCEPTANCE-DATETIME-CONFLICT
decisions:
  - DEC:FF-1-UNIVERSE-CENSUS-IS-PARQUET-DERIVED
  - DEC:FF-1-BROAD-DISCOVERY-USES-EDGAR-INDEXES
  - DEC:FF-1-RECOVERY-NOT-COMMISSIONED
  - DEC:FF-1R-BOUNDED-JULY-RECOVERY
  - DEC:FF-1-ACCESSION-PREFIX-IS-TRANSMITTER
  - DEC:FF-1-PRIOR-COMPLETE-FAILS-CLOSED
owns_paths:
  - engine/fundamental_forensics/
  - app/forensics.py
  - templates/fundamental_forensics.html.j2
  - templates/fundamental_forensics.js
  - templates/fundamental_forensics.css
  - contracts/fundamental_forensics_health.schema.json
  - contracts/fundamental_forensics_broad_sec_run.schema.json
  - contracts/fundamental_forensics_broad_sec_recovery_plan.schema.json
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
    pr: [5820, 5864, 5898, 6285, 6318]
    next_action: >
      FF-1P2R is PROVEN_LIVE, but FF-1 remains PARTIAL / in progress. FF-1R
      recovery is a separately commissioned capability and previous-quarter
      weekly reconciliation remains SPEC_ONLY / NOT_BUILT. Do not infer
      recovery, a universe expansion, or FF-2 authorization from P2R.
  - id: FF-1P2R
    title: Current-quarter EDGAR-index discovery
    status: done
    depends_on: [FF-0]
    pr: 5898
    next_action: >
      PROVEN_LIVE. PR #5898 merged as
      21f51a1ecfed778a738b048bd7e5efd30b1d9336. Production Run A
      32604043860 / run_4e7970fb7cb841b6671d established the canonical
      current-quarter baseline for 2,841 parquet-derived issuers. Run B
      32605564919 / run_8583eb7ce7476290c0b2 proved the quiet incremental
      path: baseline=false, one index acquisition, 2,627 unchanged relevant
      rows, zero affected issuers, zero Submissions or Company Facts fanout,
      canonical=true, issuer/ticker/CIK=2,841/2,841/2,841,
      expected/observed/failed=2,841/2,841/0, failures=[], and complete
      publication. This closes current-quarter discovery only.
  - id: FF-1R
    title: July recovery engine
    status: in_progress
    depends_on: [FF-1P2R]
    pr: [6285, 6318]
    next_action: >
      BUILT_NOT_PROVEN / BLOCKED_ON_ANGO_ACCEPTANCE_CONFLICT. PR #6318 landed
      the immutable-manifest transport repair as
      32cbd775e827653e88f8be6f8094d73e8c3014dc. Sol-released corrective
      tranche-A run 32708350406 / run_56830b4a74bd82a33d19 cleared the old
      20,779 > 16,384 transport blocker, then failed closed on its first issuer:
      ANGO accession 0001628280-26-048138 conflicts on acceptance_datetime.
      The run made one current-Submissions request, zero historical or Company
      Facts requests, completed zero issuers, and did not move the recovery
      checkpoint. Preserve plan e252f0a85c193323be128b6de2762c522a0ab86b74d8a2ed15a1f3014695e5a4,
      cursor/completed 0, backlog 2,571 and null last-successful recovery
      receipt. Do not retry or skip ANGO; return the conflict to Sol.
  - id: FF-2
    title: Broad workbench rebuild from the FF-1 source plane
    status: todo
    depends_on: [FF-1, FF-1R]
    next_action: >
      FORBIDDEN / NOT_STARTED. No workbench rebuild, detectors, findings
      publish, Prophet, Neural Web, attested history, or Calcbench work until
      the entire FF-1 source-plane scope, including separately commissioned
      FF-1R where applicable, is complete and production-proven.
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
  - "Broad FF-1 discovery is the official EDGAR full-index master ZIP. Do not fan a per-issuer data.sec.gov census over the canonical parquet population. Do not download submissions.zip nightly. The actual universe is parquet-derived per run and the 4,000 bind cap remains fail-closed. Wave-2 stays per-issuer/realtime. Never purge fundamental_forensics/broad-sec/v1/."
  - "A cancelled 90-minute run may have admitted valid immutable objects with no latest-complete. Index baseline may become canonical while those objects remain. Reconcile issuer latest pointers only when an issuer is affected; do not infer emptiness from list_prefix."
  - "Index HTTP Last-Modified, archive_retrieved_at, and index_latest_filed_on are never sec_accepted_at. Acceptance comes only from per-issuer Submissions."
  - "Index state is quarter-scoped. Do not treat Q3 rows missing from a Q4 baseline as mass corrections."
  - "latest-complete.json is the sole processed authority. Do not ship indexes/quarters/<q>/latest.json as a second mutable pointer. Unresolved PIT/unevaluable NEW index events must not advance latest-complete."
  - "Accession[:10] is the transmitting filer/agent CIK, not the subject issuer. Bind row CIK to path CIK; require accession shape only. Live canary: MSFT 0000789019 / 0001193125-26-323660 (DEC:FF-1-ACCESSION-PREFIX-IS-TRANSMITTER)."
  - "A sha-verified latest-complete missing index-discovery state is corrupt prior, not bootstrap (DEC:FF-1-PRIOR-COMPLETE-FAILS-CLOSED)."
  - "Previous-quarter weekly reconciliation is SPEC_ONLY / NOT_BUILT. Current-quarter rebuilt-index corrections are implemented; FF-1 is not globally correction-safe yet."
  - "FF-1R freezes one recovery plan from the sha-verified latest-complete anchor and its EDGAR snapshot. A later current-quarter poll or mutable index must not change that plan. Every recovery tranche is at most 64 selected CIKs; historical Submissions shards are date-span-selected, bounded, and never an all-shard crawl."
  - "A partial FF-1R tranche may write immutable observations, receipts and its compact continuation, but never latest-complete. Only a backlog-zero final composition may advance latest-complete, and it must preserve newer current-incremental evidence."
  - "POINTER_MAX_BYTES=16 KiB governs compact mutable heads and pointers only. Full immutable issuer manifests use their separately measured 128 KiB finite envelope in both recovery and incremental paths (DSC:FF-1-IMMUTABLE-MANIFEST-IS-NOT-A-COMPACT-POINTER)."
  - "FF-1R run 32626273461 / run_382b4fbf26bb0fe3e298 is a fail-closed transport witness, not tranche progress: ANGO was refused at 20,779 > 16,384 before cursor movement. Do not label its retry tranche B."
  - "Corrective tranche-A run 32708350406 / run_56830b4a74bd82a33d19 proved the immutable-manifest transport repair, then failed closed before progress because ANGO accession 0001628280-26-048138 conflicts on acceptance_datetime. failures is nonempty, cursor remains 0, and the operation is not an accepted checkpoint."
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
  - "Do not raise timeout-minutes to restore the retired per-issuer census. Do not treat PR #5864 merge as production proof."
  - "Do not purge fundamental_forensics/broad-sec/v1/ after a cancelled run."
  - "Do not ingest companyfacts.zip. Do not change Wave-2."
  - "Do not authorize or freeze a submissions.zip compressed maximum. Live Content-Length was 1558585919. Sol rejected a 2 GiB bound."
  - "Do not require accession[:10] == subject CIK. That rejects agent-filed rows and fails the live master index."
  - "Do not bootstrap from a sha-verified latest-complete that lacks a well-formed index block."
  - "Do not move the 03:15 UTC schedule merely because submissions.zip rebuilds around 03:00 ET. Q3 master.zip Last-Modified was 02:02 UTC."
  - "Do not make recovery chase a live index, materialize a full pending-CIK list in continuation, refetch already committed CIKs, or use all historical filings.files shards. FF-1R binds a frozen plan and advances its compact cursor only after an issuer outcome is durable."
  - "Do not raise POINTER_MAX_BYTES to admit issuer manifests, rewrite existing immutable manifests, regenerate plan e252f0a85c193323be128b6de2762c522a0ab86b74d8a2ed15a1f3014695e5a4, or advance the recovery cursor to bypass the ANGO refusal."
  - "Do not rerun 32626273461 or 32708350406, dispatch another cursor-zero recovery, skip ANGO, or call the next operation tranche B. The one corrective tranche-A release was consumed by run 32708350406 and stopped on historical_submissions_conflict."
next_action: >
  FF-1P2R current-quarter EDGAR-index discovery is PROVEN_LIVE. FF-1 remains
  PARTIAL / in progress. PR #6318's bounded transport repair is merged, but
  corrective tranche-A run 32708350406 made zero safe progress and stopped on
  ANGO historical_submissions_conflict for accession
  0001628280-26-048138. Preserve plan e252f0a85c193323be128b6de2762c522a0ab86b74d8a2ed15a1f3014695e5a4,
  cursor/completed 0, backlog 2,571, null last-successful recovery receipt and
  the current incremental latest-complete. Sol must adjudicate the exact
  acceptance_datetime conflict before any new recovery operation. Previous-quarter
  reconciliation is SPEC_ONLY / NOT_BUILT; FF-2 is FORBIDDEN / NOT_STARTED.
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
90-minute job timeout on the former per-issuer census and emitted no receipt.
The submissions.zip canary declared 1.45 GiB and was correctly stopped. P2R
replaced current-quarter discovery with the EDGAR master-index kernel; the old
census architecture remains retired.

#5898 merged as `21f51a1ecfed778a738b048bd7e5efd30b1d9336` and owns
current-quarter index-driven discovery only
(`DEC:FF-1-RECOVERY-NOT-COMMISSIONED`). Run A `32604043860` established the
2,841-name canonical baseline; Run B `32605564919` proved the quiet
incremental path without issuer fanout. Before this successor, `mode=recovery`
failed closed with `recovery_plan_required` before any SEC call or Research R2
write. PR #6285 merged as `1e7d9f5030fd7c7c06fb03f022857510c5d0f9ed`
and commissioned the bounded July recovery engine. Production run
`32626273461` / `run_382b4fbf26bb0fe3e298` selected 64 CIKs but failed
closed on its first issuer, ANGO, because a valid 20,779-byte immutable
manifest was read through the 16 KiB compact-pointer envelope. It made one
current-Submissions request, zero Company Facts requests, and no recovery
progress. Recovery is frozen at plan
`e252f0a85c193323be128b6de2762c522a0ab86b74d8a2ed15a1f3014695e5a4`,
cursor 0, completed total 0 and null last-successful recovery receipt.

PR #6318 merged the separately bounded immutable-manifest transport repair as
`32cbd775e827653e88f8be6f8094d73e8c3014dc`. The next scheduled incremental,
run `32688874242` / `run_2dfb3cc973b3f025b09e`, lawfully advanced
latest-complete without changing the frozen recovery plan or continuation.
Sol-released corrective tranche-A run `32708350406` /
`run_56830b4a74bd82a33d19` selected the same cursor-zero 64-CIK slice and read
the valid 20,779-byte legacy ANGO manifest without the former transport error.
It then failed closed on ANGO accession `0001628280-26-048138` because duplicate
evidence conflicts on `acceptance_datetime`: failures=1, current Submissions=1,
historical Submissions=0, Company Facts=0, completed=0 and backlog=2,571.
latest-complete, ANGO and the recovery continuation remained byte-identical;
only the immutable failed receipt/observations and latest-observation head were
published. This is not an accepted recovery checkpoint. Do not retry or skip
ANGO; return the exact conflict to Sol. Previous-quarter weekly reconciliation
remains SPEC_ONLY / NOT_BUILT. Do not mark FF-1 done. FF-2 remains forbidden.

---
key: FF-1-BROAD-DISCOVERY-USES-EDGAR-INDEXES
question: >
  After production run 32116597760 cancelled at the 90-minute budget, and after
  the live submissions.zip canary declared 1,558,585,919 compressed bytes,
  how should broad FF-1 discover which canonical issuers had relevant filing
  changes without a nightly 2837-issuer Submissions census or a >1 GiB bulk
  archive download?
answer: >
  Broad FF-1 discovery uses official EDGAR full-index master ZIPs
  (https://www.sec.gov/Archives/edgar/full-index/YYYY/QTRN/master.zip,
  member master.idx). Affected-issuer evidence is the existing per-CIK
  Submissions collector. Company Facts stays selective. Wave-2 stays
  unchanged. Do not download submissions.zip nightly. Do not use
  companyfacts.zip. Do not raise timeout-minutes. Do not start FF-2.
  The first incremental with no prior index snapshot is a discovery
  baseline: persist the current-quarter relevant set, emit a complete
  census, and fetch zero per-issuer Submissions or Company Facts.
rationale: >
  FF-1's acquisition problem is two jobs: discovery (which canonical
  issuers changed) and evidence (exact current Submissions plus selective
  Company Facts for those issuers). submissions.zip solved both with one
  ~1.45 GiB object. The current-quarter master index already lists every
  filing in the quarter at ~2.1 MiB compressed / ~14.5 MiB uncompressed
  (live 2026 Q3 canary, 2026-08-18). Set difference against the prior
  verified quarter snapshot yields NEW and correction-candidate CIKs.
  Quiet nights then cost one index GET. Sol forbade authorizing a 2 GiB
  submissions.zip bound.
alternatives:
  - option: Authorize a 2 GiB compressed bound and download submissions.zip nightly
    why_not: Sol forbade it. FF-1 does not need every filer's complete Submissions JSON every night.
  - option: Keep per-issuer Submissions GETs for all 2837 canonical names
    why_not: Production run 32116597760 already exceeded the 90-minute budget on that shape.
  - option: Raise timeout-minutes
    why_not: Hides the architecture defect. Quiet nights would still scale with universe size.
  - option: Ingest companyfacts.zip in the same repair
    why_not: Company Facts remains a selective current-observed snapshot.
supersedes:
  - DEC:FF-1-BROAD-SUBMISSIONS-USES-SEC-BULK-ARCHIVE
evidence:
  - DSC:FF-1-PER-ISSUER-CENSUS-EXCEEDS-90M
  - DSC:FF-1-SEC-BULK-ARCHIVE-EXCEEDS-1GIB
  - "Live 2026 Q3 master.zip GET 2026-08-18: HTTP 200, no redirect, 2132920 bytes, SHA-256 feb04748bf47569a886f719e63a6efe2f3c67a2a0c9ded9d73acb0b92a5482f3, member master.idx 15184383 bytes, SHA-256 be9322c1775d97118dd4a0812c64366b67b325a865ea2ad328083f97e1c11973, 164511 rows, latest filed 2026-08-17, canonical relevant 2592 rows / 2569 CIKs, AAPL 10-Q and MSFT 10-K present."
  - "Sol 2026-08-18: stop on submissions.zip was correct; do not authorize a 2 GiB bound; discovery = EDGAR indexes."
affects:
  - WS:FUNDAMENTAL-FORENSICS
  - collectors/edgar_forensics.py
  - engine/fundamental_forensics/broad_sec_store.py
  - scripts/run_fundamental_forensics_broad_sec.py
  - contracts/fundamental_forensics_broad_sec_run.schema.json
confidence: high
reversibility: costly
decided_by: ceo-sol
decided_at: 2026-08-18
---

Preserve exact Submissions bytes for affected issuers, canonical issuer
manifests, selective Company Facts, and CAS/readback. Do not start FF-2.
Do not alter Wave-2. Do not purge `fundamental_forensics/broad-sec/v1/`.
Index clocks (`archive_retrieved_at`, HTTP Last-Modified,
`index_latest_filed_on`) are never `sec_accepted_at`.

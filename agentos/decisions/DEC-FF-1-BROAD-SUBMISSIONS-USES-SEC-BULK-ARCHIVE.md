---
key: FF-1-BROAD-SUBMISSIONS-USES-SEC-BULK-ARCHIVE
question: >
  After production run 32116597760 cancelled at the 90-minute budget on a
  2837-issuer per-issuer Submissions census, how should the broad FF-1 lane
  acquire SEC Submissions so a complete canonical census can finish inside
  the existing timeout without weakening source identity?
answer: >
  Use the official SEC nightly bulk Submissions archive at
  https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip
  as the scheduled acquisition source for the broad FF-1 lane. Bind only
  canonical parquet CIKs. Keep exact member JSON bytes as the immutable
  source object. Attach bulk transport evidence on the run/observation
  receipt; the logical source remains data.sec.gov/submissions/CIK##########.json.
  Company Facts stays selective per issuer. Wave-2 stays per-issuer/realtime.
  Do not use companyfacts.zip. Do not start FF-2. Do not raise timeout-minutes.
rationale: >
  The SEC publishes the bulk archive specifically for large-scale acquisition
  and rebuilds it approximately 03:00 ET. One archive download replaces 2837
  live Submissions HTTP requests. Exact member bytes preserve content-addressed
  identity, CAS/readback, and canonical issuer manifests. Steady-state work
  then compares member SHA-256 against the prior complete census and performs
  R2/Company-Facts work only for changed issuers. Raising the timeout would
  hide the architecture defect and still leave nightly work scaling with
  universe size instead of actual change.
alternatives:
  - option: Raise timeout-minutes above 90 and keep per-issuer Submissions
    why_not: Sol forbade hiding the throughput problem behind a larger budget.
      Steady-state would still cost thousands of SEC and R2 operations every night.
  - option: Fan out concurrent per-issuer data.sec.gov requests
    why_not: Violates SEC fair-access pacing, creates a second request storm,
      and still performs thousands of R2 writes on an unchanged universe.
  - option: Ingest companyfacts.zip in the same repair
    why_not: Company Facts remains a selective current-observed snapshot.
      Recovery capacity is measured after the repaired incremental baseline.
  - option: Change Wave-2 to bulk as well
    why_not: Wave-2 is the 12-name deep-evidence realtime lane. Keep it.
evidence:
  - DSC:FF-1-PER-ISSUER-CENSUS-EXCEEDS-90M
  - GitHub Actions run 32116597760
  - https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip
  - SEC EDGAR bulk-data guidance that bulk archive ZIPs are the efficient
    large-scale API fetch path
affects:
  - WS:FUNDAMENTAL-FORENSICS
  - collectors/edgar_forensics.py
  - engine/fundamental_forensics/broad_sec_store.py
  - scripts/run_fundamental_forensics_broad_sec.py
  - .github/workflows/filing-forensics-broad-sec.yml
confidence: high
reversibility: costly
decided_by: ceo-sol
decided_at: 2026-08-18
superseded_by: DEC:FF-1-BROAD-DISCOVERY-USES-EDGAR-INDEXES
---

Preserve exact source bytes, canonical issuer manifests, selective Company
Facts, and CAS/readback. Do not start FF-2. Do not alter Wave-2. Do not
purge `fundamental_forensics/broad-sec/v1/`. Transport clocks
(`archive_retrieved_at`, HTTP Last-Modified) are not `sec_accepted_at`.

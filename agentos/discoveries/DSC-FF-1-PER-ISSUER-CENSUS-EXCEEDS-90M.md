---
key: FF-1-PER-ISSUER-CENSUS-EXCEEDS-90M
claim: >
  The first production incremental after MAX_UNIVERSE_ISSUERS=4000 (GitHub
  Actions run 32116597760, job 95647409578, head
  5a59dc7bb06b62cdf8f0129f2e398299b9e55af9, mode=incremental) was cancelled
  by the existing 90-minute job timeout. Poll step 2026-08-18T08:29:38Z to
  2026-08-18T09:59:15Z emitted no final run receipt because the CLI prints
  only when run_broad_sec_poll returns. The live canonical universe is 2837
  issuers. FF-1 is not PROVEN_LIVE. July recovery was not started. The
  cancelled kernel still used a per-issuer Submissions GET plus per-issuer
  raw-object existence GET, issuer-latest GET, prior-manifest GET, manifest
  PUT, latest-pointer PUT, and readback — on an empty baseline roughly 2837
  SEC requests plus ~10 R2 operations per issuer (~28,370 R2 ops) before
  run-level publication.
falsifier: >
  Re-read GitHub Actions run 32116597760 and find a conclusion other than
  cancelled, a final FF-1 run receipt in the poll-step log, or a kernel
  path that did not call retrieve_current per issuer. Re-measure
  data/edgar/fundamentals.parquet and find issuer_count != 2837.
so_what: >
  Do not treat FF-1 as PROVEN_LIVE. Do not start FF-2. Do not start July
  recovery from the timed-out baseline. Do not raise timeout-minutes to hide
  the per-issuer architecture. Do not infer production R2 is empty and do
  not purge fundamental_forensics/broad-sec/v1/. Repair acquisition to the
  official SEC bulk Submissions archive and make steady-state R2 work scale
  with changed issuers, then prove one complete census under 90 minutes.
kind: runtime
verified_at: 2026-08-18
verified_by: >
  gh run view 32116597760 (conclusion cancelled, timeout-minutes 90, job
  95647409578, poll step 08:29:38Z-09:59:15Z, MODE=incremental, no receipt
  JSON); engine/fundamental_forensics/broad_sec_store.py run_broad_sec_poll
  per-issuer retrieve_current / admit_source_bytes / issuer_latest GET /
  manifest PUT / pointer PUT loop; scripts/run_fundamental_forensics_broad_sec.py
  prints canonical_json(result.receipt) only after return.
scope: [macro, fundamental-forensics]
confidence: verified
---

The 4000-cap repair (PR #5864, `4f59f720a0a1459a11a7bd131e41833c38cbe0d4`)
unblocked universe bind. The next production incremental exposed a different
failure: throughput. Exact live progress of the killed run is unknown. The
run may have admitted valid immutable source objects and may or may not have
reached issuer-manifest publication. Absence of a receipt is not absence of
store writes.

---
workstream: WS:FUNDAMENTAL-FORENSICS
session: claude/ff-1p2-bulk-census
model: local
ended_because: blocked
mission: >
  FF-1P2 bulk-census throughput repair: switch broad FF-1 scheduled acquisition
  to the official SEC submissions.zip, keep the 90-minute budget, and return
  one unmerged PR. Do not start July recovery. Do not start FF-2.
state_before: >
  FF-1 code is on main via PR #5820 and the 4000-cap repair PR #5864
  (4f59f720a0a1459a11a7bd131e41833c38cbe0d4). Production incremental
  32116597760 cancelled at 90 minutes on the per-issuer census and emitted
  no receipt. FF-1 is not PROVEN_LIVE. July recovery has not started.
changed:
  - path: agentos/discoveries/DSC-FF-1-PER-ISSUER-CENSUS-EXCEEDS-90M.md
    what: "Production run 32116597760 cancelled at 90 minutes; per-issuer census shape; no receipt; recovery not started."
  - path: agentos/decisions/DEC-FF-1-BROAD-SUBMISSIONS-USES-SEC-BULK-ARCHIVE.md
    what: "Sol-owned decision that broad FF-1 uses the official SEC bulk Submissions ZIP; Wave-2 unchanged; no companyfacts.zip."
  - path: agentos/discoveries/DSC-FF-1-SEC-BULK-ARCHIVE-EXCEEDS-1GIB.md
    what: "Live canary Content-Length 1558585919 bytes (~1.45 GiB); body not streamed."
  - path: agentos/workstreams/WS-FUNDAMENTAL-FORENSICS.md
    what: "Status remains blocked. next_action is Sol bound authorization, not FF-1 done."
verified:
  - claim: "Worktree HEAD contains the 4000-cap merge 4f59f720a0a1459a11a7bd131e41833c38cbe0d4."
    command: "git merge-base --is-ancestor 4f59f720a0a1459a11a7bd131e41833c38cbe0d4 HEAD"
    result: "exit 0; CAP_ON_BASE=yes"
  - claim: "Live GET of submissions.zip returned HTTP 200 with Content-Length 1558585919, no redirect."
    command: "/opt/homebrew/bin/python3.12 requests.get(https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip, stream=True, allow_redirects=False) then print status/url/headers and stop before iter_content"
    result: "status=200 url exact; Content-Length=1558585919; ETag=\"c38423eb2d3aff3ea8e3145e16f6bceb-186\"; Last-Modified=Tue, 18 Aug 2026 05:55:33 GMT; STOP: Content-Length exceeds 1 GiB"
  - claim: "Canonical parquet unique CIK count at canary time was 2837."
    command: "pandas read_parquet data/edgar/fundamentals.parquet columns=[cik]; unique zero-padded CIKs"
    result: "canonical_ciks=2837"
  - claim: "No production Research R2 write and no ZIP body were performed by this canary."
    command: "canary SystemExit after header check; no iter_content; no R2 client call"
    result: "exit 1 STOP: Content-Length 1558585919 exceeds 1 GiB; /tmp/ff-1p2-canary has no submissions.zip"
unverified:
  - claim: "The declared Content-Length equals compressed bytes that would actually be received."
    what_would_verify: "Sol-authorized download under a bound that admits 1558585919 bytes, then compare received bytes and SHA-256 to the header."
  - claim: "ZIP member grammar is CIK##########.json and every canonical CIK is present."
    what_would_verify: "Open the downloaded archive without extractall after Sol authorizes the size bound."
unresolved:
  - "FF-1P2 acquisition code is not implemented. The ~1 GiB stop line blocked freezing MAX_BULK_ARCHIVE_BYTES."
  - "FF-1 is not PROVEN_LIVE. July recovery has not started. FF-2 remains forbidden."
  - "Timed-out run 32116597760 may have admitted immutable objects under fundamental_forensics/broad-sec/v1/. Do not purge."
next_actions:
  - "Sol authorizes or rejects a compressed maximum that can admit 1558585919 bytes with growth room (for example 2 GiB), or names an alternate acquisition design."
  - "After a bound is authorized, resume FF-1P2 in a new branch: bulk download, unchanged-issuer fast path, R2 amplification/concurrency, 09:15 UTC schedule, tests A-O, one unmerged PR."
  - "Do not start July recovery or FF-2 from this stop."
do_not_redo:
  - "Do not silently set MAX_BULK_ARCHIVE_BYTES above ~1 GiB."
  - "Do not download the 1.45 GiB body to 'confirm' Content-Length without Sol authorizing the bound."
  - "Do not raise timeout-minutes to finish the per-issuer census."
  - "Do not purge fundamental_forensics/broad-sec/v1/."
  - "Do not start FF-2 or July recovery."
  - "Do not change Wave-2 or ingest companyfacts.zip."
danger_areas:
  - "ZIP central directory is at the end of the archive; member binding still requires the whole object or range reads of a >1 GiB file."
  - "HTTP Last-Modified 2026-08-18 05:55:33 GMT is not sec_accepted_at."
  - "A cancelled 90-minute run may have left valid issuer objects without latest-complete."
decisions:
  - DEC:FF-1-BROAD-SUBMISSIONS-USES-SEC-BULK-ARCHIVE
discoveries:
  - DSC:FF-1-PER-ISSUER-CENSUS-EXCEEDS-90M
  - DSC:FF-1-SEC-BULK-ARCHIVE-EXCEEDS-1GIB
---

FF-1P2 stopped at the live bulk canary. The official submissions.zip currently
declares 1558585919 compressed bytes. That is above the commission's roughly
1 GiB stop line, so size limits were not frozen and acquisition code was not
written.

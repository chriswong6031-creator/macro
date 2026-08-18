---
key: FF-1-SEC-BULK-ARCHIVE-EXCEEDS-1GIB
claim: >
  A local read-only GET of the official SEC bulk Submissions archive
  https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip
  on 2026-08-18 returned HTTP 200 with Content-Length 1558585919 bytes
  (~1.45 GiB), ETag "c38423eb2d3aff3ea8e3145e16f6bceb-186", Last-Modified
  Tue, 18 Aug 2026 05:55:33 GMT, Content-Type application/zip, no redirect.
  The canary refused to stream the body because a defensible compressed
  maximum that admits this object would have to exceed roughly 1 GiB.
  Archive SHA-256, ZIP member count, canonical-member count, and AAPL/MSFT
  member hashes were therefore not measured.
falsifier: >
  Repeat the same GET with the declared edgar.user_agent, redirects
  disabled, and observe Content-Length absent or <= 1073741824, or a
  redirect/non-200 that makes this header inapplicable.
so_what: >
  Do not freeze MAX_BULK_ARCHIVE_BYTES above ~1 GiB and do not stream this
  object until Sol authorizes a bound that can admit 1558585919 bytes with
  growth room. FF-1P2 implementation of bulk acquisition is stopped on this
  measurement. Do not treat HTTP Last-Modified as sec_accepted_at.
kind: runtime
verified_at: 2026-08-18
verified_by: >
  /opt/homebrew/bin/python3.12 GET
  https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip
  stream=True allow_redirects=False; status=200 url exact; headers
  Content-Length=1558585919 ETag="c38423eb2d3aff3ea8e3145e16f6bceb-186"
  Last-Modified="Tue, 18 Aug 2026 05:55:33 GMT"; exit before iter_content.
scope: [macro, fundamental-forensics]
confidence: verified
---

This is a transport-size fact, not a reversal of
`DEC:FF-1-BROAD-SUBMISSIONS-USES-SEC-BULK-ARCHIVE`. The architecture
decision still stands; the first live canary cannot freeze a compressed
maximum underneath the commission's ~1 GiB stop line. No production R2
write occurred. The ZIP was not opened.

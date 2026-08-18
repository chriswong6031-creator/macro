---
key: FF-1-Q3-2026-MASTER-INDEX-CANARY
claim: >
  A local read-only GET of the current-quarter EDGAR full master index
  https://www.sec.gov/Archives/edgar/full-index/2026/QTR3/master.zip on
  2026-08-18 returned HTTP 200 with no redirect, Content-Length 2132920,
  ETag "84b86a7660577da2657b7ef63b16f54c", Last-Modified Tue, 18 Aug 2026
  02:02:26 GMT. Received archive bytes 2132920, SHA-256
  feb04748bf47569a886f719e63a6efe2f3c67a2a0c9ded9d73acb0b92a5482f3. ZIP
  contained exactly one member, master.idx, uncompressed 15184383 bytes,
  SHA-256 be9322c1775d97118dd4a0812c64366b67b325a865ea2ad328083f97e1c11973,
  UTF-8 text, header CIK|Company Name|Form Type|Date Filed|Filename,
  164511 parsed rows, latest filing date 2026-08-17. Against the live 2837
  canonical CIKs: 42864 canonical rows, 2592 relevant-form rows, 2569
  unique relevant CIKs. AAPL 10-Q 0000320193-26-000020 filed 2026-07-31 and
  MSFT 10-K 0001193125-26-323660 filed 2026-07-29 were present. Filename
  grammar was edgar/data/<unpadded-cik>/<accession>.txt. Relevant rows with
  filed_on >= 2026-07-12: 2560 rows / 2541 unique canonical CIKs. Both size
  bounds (16 MiB zip / 64 MiB member) admitted the object with growth room.
falsifier: >
  Repeat the same GET with the declared edgar.user_agent and redirects
  disabled and observe a redirect, non-200, Content-Length > 16 MiB,
  member name other than master.idx, or uncompressed member > 64 MiB.
so_what: >
  Freeze MAX_MASTER_INDEX_ZIP_BYTES=16MiB and MAX_MASTER_INDEX_MEMBER_BYTES=64MiB.
  Keep the 03:15 UTC schedule: Last-Modified was 02:02 UTC. Do not treat
  Last-Modified or retrieved_at as sec_accepted_at. July recovery from
  2026-07-12T11:23:15Z is about 2541 canonical CIKs, not 2837 Submissions
  GETs, and still far above 64 affected issuers/run — report that backlog
  size to Sol before any production recovery dispatch.
kind: runtime
verified_at: 2026-08-18
verified_by: >
  /opt/homebrew/bin/python3.12 /tmp/ff-1p2r-index-canary.py against
  data/edgar/fundamentals.parquet (canonical_ciks=2837); receipt
  /tmp/ff-1p2r-canary/canary.json.
scope: [macro, fundamental-forensics]
confidence: verified
---

No production Research R2 write. The archive was stored only under /tmp.

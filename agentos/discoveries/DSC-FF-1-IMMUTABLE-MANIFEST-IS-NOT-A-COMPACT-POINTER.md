---
key: FF-1-IMMUTABLE-MANIFEST-IS-NOT-A-COMPACT-POINTER
claim: >
  FF-1 compact mutable heads and pointers remain bounded by
  POINTER_MAX_BYTES=16 KiB, while full immutable issuer manifests require a
  separately measured finite transport envelope shared by recovery and
  incremental readers and writers. Conflating the two caused production run
  32626273461 to reject the valid 20,779-byte ANGO manifest before any
  recovery progress.
falsifier: >
  Run the read-only issuer-prefix metadata census and
  python3 -m pytest -q tests/test_fundamental_forensics_broad_sec.py; this
  claim is disproved if no valid production issuer manifest exceeds 16 KiB,
  if recovery and incremental do not read the same immutable manifest class,
  or if the census no longer supports a finite ceiling no greater than 256
  KiB with measured growth room.
so_what: >
  Keep compact control objects at 16 KiB. Read and canonically encode issuer
  manifests only through ISSUER_MANIFEST_MAX_BYTES, selected from the
  production distribution; fail closed as a storage/manifest transport error
  if that ceiling is exceeded, without rewriting evidence, advancing a
  pointer/cursor, or misclassifying the refusal as SEC source-binding failure.
kind: architecture
verified_at: 2026-08-23
verified_by: >
  Read-only Research R2 census of
  fundamental_forensics/broad-sec/v1/issuers/ plus exact ANGO object and
  continuation reads; tests/test_fundamental_forensics_broad_sec.py manifest
  transport regressions.
scope:
  - macro
  - fundamental-forensics
  - engine/fundamental_forensics/broad_sec_store.py
confidence: verified
---

The 4,819-object production census measured a maximum immutable issuer
manifest of 43,665 bytes. The smallest power of two at least twice that
maximum is 131,072 bytes (128 KiB), which admits the present population with
measured growth room while retaining a credible finite allocation. The
compact-pointer limit is unchanged.

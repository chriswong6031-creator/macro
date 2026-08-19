---
key: CS-MANIFEST-ID-HASHES-RETRIEVAL-CLOCKS
claim: >
  Capital Structure manifest_id is a SHA-256 of the entire source-manifest
  body except manifest_id itself, and that body is required to contain
  retrieval.retrieved_at and retrieval.first_seen_at, both set to the
  collector wall clock after R2 readback, so unchanged SEC bytes do not have a
  stable retention identity.
falsifier: >
  Show manifest_id_for hashing a declared subset that excludes retrieval
  clocks, or show the collector writing first_seen_at from a keep-first prior
  row rather than retained_at, or produce two production complete-submission
  manifests with different retrieved_at and the same manifest_id for the same
  content_sha256. Read engine/capital_structure/source_identity.py:136-141,
  collectors/sec_capital_structure.py retrieval clocks, and
  contracts/capital_structure_source_manifest.schema.json retrieval.required.
so_what: >
  Do not scale live-tail retrieval, concurrent collect, or Git re-derive until
  Wave 1 dual-read lands. Do not treat unique manifest_id count as unique
  evidence count. Do not add tests that rebuild a registered historical
  manifest_id from today's moving clocks. Sequential remint is currently
  masked by _eligible_complete_accessions; concurrent collect is not.
kind: landmine
verified_at: 2026-08-18
verified_by: >
  origin/main @791148b2b7d5. Read source_identity.py:136-141,
  contracts/capital_structure_source_manifest.schema.json:72-78,
  collectors/sec_capital_structure.py:1728-1737 and :1287-1313.
  tests/test_capital_structure_source_identity.py does not assert
  same-bytes to same-manifest_id.
scope:
  - macro
  - capital-structure-intelligence
  - engine/capital_structure/source_identity.py
  - collectors/sec_capital_structure.py
confidence: verified
---

Sibling of DNR:LAW-RUN-CLOCK-IN-CONTENT-IDENTITY (Filing Forensics). Evidence
object keys remain content-addressed and stable; only the Git JSONL identity
is clocked. Architecture ruling: DEC:CS-V2-IDENTITY-DUAL-READ.

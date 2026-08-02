# Calcbench Parity — Wave 3B Filing-Package Foundation

**Canonical implementation handoff for Wave 3B-B0/B1**

**Date:** 2026-08-02

**Status:** implemented foundation; deliberately not semantic XBRL attestation

## Outcome

Wave 3B-B establishes the evidence boundary required before Fundamental
Forensics can claim a filing-backed history.  It can now retain one bounded SEC
archive document safely and assemble an immutable, content-addressed account of
one filing's `index.json` inventory.  The package says exactly which safe index
members were stored, missing, intentionally not requested, or rejected by the
current policy.  It does **not** claim that facts have been extracted,
interpreted, or semantically verified.

The canonical package identity is `ffpkg_<sha256>` under schema
`fundamental_forensics.filing_package/v1`.  Its SHA-256 is over the canonical
package body excluding `package_id`; changing a filing binding, raw-index
receipt, embedded raw-content witness, canonical index projection, member
state, coverage field, or assembly policy changes the ID.

## Implemented artifacts and contracts

| Artifact | Purpose |
| --- | --- |
| `collectors/sec_document_spine.py` | B-B0 bounded SEC archive transport/cache.  It streams responses, hashes and persists immutable gzip objects and receipts, and performs bounded verified reads. |
| `engine/fundamental_forensics/sec_document_spine.py` | Provides the manifest-bound canonical `archive_index_document(manifest)` identity for `index.json`. |
| `engine/fundamental_forensics/filing_package.py` | B-B1 offline package kernel: `FilingPackage`, `build_filing_package`, `validate_filing_package`, `filing_package_json_bytes`, `filing_package_from_json_bytes`, and `filing_package_id_for`. |
| `tests/test_sec_document_spine.py` | Archive streaming, close discipline, receipt, cache, cap, and anti-inflation tests. |
| `tests/test_fundamental_forensics_filing_package.py` | Package binding, canonicalization, hostile-input, coverage, and immutable-restore tests. |

The package binds one already-validated filing manifest via its canonical CIK,
accession, `filing_id`, `manifest_id`, manifest schema, and canonical SEC
archive-index URL.  It separately binds the manifest-derived `index.json`
document identity (`sec_document` / archive role), its exact archive URL,
content SHA-256, byte length, immutable object key, root byte-range source
span, and a checksum-bound SEC archive retrieval receipt
(`sec_archive_receipt_<sha256>`).

### Raw bytes and canonical projection are both retained as evidence

`index.json` raw bytes are the source evidence.  Their canonical base64 form is
embedded in the package as a self-contained derivation witness. Package
assembly and restore both reject bytes that do not exactly match the stored
document's receipt-bound digest and length, and restore re-derives the
projection from that witness. JSON decoding is strict UTF-8: duplicate keys,
binary floats,
non-finite constants, malformed JSON, excessive depth/node count, oversized
payloads, unsafe filenames, and duplicate member names all fail closed.

The decoded index is copied into a bounded canonical JSON projection with its
own `payload_sha256` and `payload_byte_length`.  This projection makes member
accounting deterministic without replacing the raw receipt-bound source bytes.
In particular, semantically equivalent but byte-different JSON cannot be
substituted for the retained source object.

### Explicit inventory accounting

Every safe filename in `directory.item` must appear exactly once in the
canonical sorted inventory, and no invented filename is allowed.  Known manifest
documents preserve their declared role; other index members receive a stable
archive-role identity.  Each inventory item has exactly one state:

| State | Meaning |
| --- | --- |
| `stored` | Immutable bytes are retained, with digest, byte length, object key, and matching retrieved receipt. |
| `missing` | Retrieval produced the canonical, document-bound observed SEC HTTP 404 receipt; no stored-byte claim is permitted. |
| `not_requested` | The member was intentionally outside the request set; no receipt or byte claim is permitted. |
| `rejected_by_policy` | The member was intentionally excluded under policy, with bounded reason text; no receipt or byte claim is permitted. |

Coverage is derived, never trusted from caller input:

- `package_inventory_complete=true` means every *safe member named by this
  retained index* has an explicit state.  It does not mean the filing was fully
  acquired.
- Counts are derived for all four states and the safe index member total.
- `all_index_members_receipted_as_stored` is true only when every indexed
  member has a checksum-bound `stored` receipt.
- `all_filing_bytes_retained=false` and
  `archive_object_presence_attested=false` are fixed in unsigned v1. Receipt
  metadata does not prove that every external object is still physically
  present; B-B3 must add store-backed sealed authority before either claim can
  become true.
- `sec_universe_complete=false` is fixed in v1.
- `xbrl_semantic_attested=false` is fixed in v1.

## B-B0 archive hardening

The archive collector now has a finite default ingest limit of 16 MiB and a
shared hard document ceiling (`HARD_MAX_ARCHIVE_DOCUMENT_BYTES`, currently 32
MiB).  A caller cannot select an unbounded limit.  HTTP responses are requested
with streaming enabled, read only up to the cap plus one byte, and closed on
success, misses, oversized declarations/bodies, transient failures, and stream
errors before any source bytes are persisted.  The collector rejects non-byte
chunks, refuses redirects or a mismatched final response URL, bounds transport
metadata before the first write, and never writes a partial object.

Immutable cache reads are bounded from the trusted receipt byte length, reject
forged oversize receipts before decompression, verify exact decompressed length
and SHA-256, and reject corrupt or inflated gzip objects.  Retrieved and missing
receipts are shape-, identity-, document-, URL-, clock-, status-, and
storage-key-bound. Receipt and manifest metadata reads have their own finite
caps.  These controls bound one supplied filing/document acquisition; they do
not discover or mirror the SEC universe.

## Threat model and intentionally absent claims

This foundation protects against accidental or hostile ambiguity at the archive
and serialization boundaries: oversized or streaming bodies, partial cache
writes, decompression inflation, path traversal, forged/mismatched receipt
metadata, duplicate JSON keys, non-canonical encodings, invented/skipped index
members, mutable caller mappings, forged package IDs, and false derived
coverage.

Package assembly clocks also fail closed: `assembled_at` cannot predate the
stored index receipt or any member retrieval/missing receipt included in the
package.

It does **not** turn a SHA-256 content ID into a SEC signature, legal proof, or
independent publication timestamp.  The package is only as authoritative as
the controlled build identity, archive acquisition policy, retained object
store, and provenance records that produced it.  Storage durability,
distributed write coordination, credential policy, and source availability are
operational responsibilities outside this kernel.

Specifically out of scope for B-B0/B1:

- no inline XBRL/XML parsing, transforms, contexts, dimensions, continuations,
  hidden facts, or semantic fact attestation;
- no claim of filing completeness beyond safe members named by the one retained
  index, and no SEC-issuer/universe completeness;
- no binding to `ffqs_` snapshots yet;
- no network work in `filing_package.py`, no scheduler, API, UI, search surface,
  peer grid, Excel/export, or trading authority;
- no source-signature verification and no assertion that content-addressed
  storage alone establishes publication authority.

## Validation evidence

The contract tests cover the important negative cases as well as the happy
path: exact raw-byte/receipt binding, byte-different equivalent JSON rejection,
strict JSON decoding, source/index and inventory identity mismatch, duplicate,
unsafe, omitted, and invented filenames, all inventory states, role and
coverage recomputation on restore, forged content IDs and clocks, hostile
mapping length lies, hard document/index/package caps, stream failures,
non-byte chunks, response-close discipline, no partial persistence, and
bounded decompression against forged receipts and gzip inflation.

Run the focused evidence set from the repository root:

```bash
pytest -q tests/test_sec_document_spine.py tests/test_fundamental_forensics_filing_package.py
```

Also retain the adjacent acquisition/disclosure and snapshot suites in the
release gate, because the package is an additive evidence layer rather than a
replacement for the existing governed-ledger/query contracts.

## Exact next lanes

1. **B-B2 — hardened iXBRL extraction.**  Add a separately bounded, offline,
   fail-closed parser for retained package members.  Pin parser/transform
   behavior; prohibit DTDs, entities, external dereferences, XInclude and
   recovery; preserve source spans, raw lexical values, scale/sign, nil,
   continuations, contexts, units, dimensions, and hidden-fact provenance.
   This lane must not mutate Company Facts occurrences or silently claim
   dimensions are known.
2. **B-B3 — sealed attestation (`ffatt_`).**  Bind an immutable package and
   parser result to exact filing/fact evidence and explicit coverage clocks.
   Only this layer may make narrowly scoped semantic-attestation claims.
3. **Verified History product.**  Introduce `ffqsv2_` snapshots only after
   attestation integration; then an immutable catalog/read model, signed
   keyset-cursor History API, and premium provenance-first UI/UX.  The UI must
   display attestation scope, source and as-of clocks, immutable snapshot
   identity, coverage boundary, and a per-cell provenance waterfall.  It must
   never treat an un-attested v1 `ffqs_` snapshot as filing-complete history.

The sequence is intentional: source identity and explicit absence come before
semantic extraction, and semantic evidence comes before a polished historical
comparison surface.  That is the clean-room path to a durable Calcbench-class
forensics engine rather than a persuasive dashboard resting on ambiguous data.

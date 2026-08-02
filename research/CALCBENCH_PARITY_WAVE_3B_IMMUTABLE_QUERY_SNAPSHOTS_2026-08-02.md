# Calcbench parity — Wave 3B immutable query snapshots

**Canonical Wave 3B-A implementation and handoff memo**

**Date:** 2026-08-02

## Outcome

Wave 3B-A turns a Wave 3A matrix receipt from selected-occurrence consistency
into a durable, private, reproducible query record. An `ffqs_*` snapshot freezes
the complete ledger supplied to the query, filing metadata, and the matrix's
exact governed interpretation. A later SEC response, raw-ledger append, or live
registry change cannot rewrite that historical answer.

This is a meaningful Calcbench-parity primitive: an as-of fundamental answer can
be inspected and replayed from retained evidence rather than regenerated from a
mutable endpoint. For Neural Web, it creates a receipt-bearing context input:
lobes may consume the descriptive query outcome and provenance, but this lane
does not originate a score, rank, sizing, gate, or trade authority.

Wave 3B-A is private persistence and verification infrastructure. It is not an
API, UI, Excel export, scheduler, or an SEC-universe-completeness claim.

## Implemented surface

- `engine/fundamental_forensics/query_snapshots.py` owns preparation,
  content-addressed publication, loading, verification, and exact replay.
- `engine/fundamental_forensics/query.py` permits
  `BitemporalMetricQueryEngine` to execute against either a live
  `MetricRegistry` or a frozen `GovernanceBundle`.
- `engine/fundamental_forensics/raw_ledger.py` adds strict canonical ledger
  restoration for the external snapshot boundary.
- `engine/research_vault/r2_store.py` adds the fail-closed `StrictReadStore`
  read contract without changing legacy `Store` behavior.

The owned private prefix is
`fundamental_forensics/query-snapshots/v1`. Snapshot IDs are
`ffqs_<sha256>`, derived from the canonical manifest body; the manifest binds
the query hash, frozen governance-bundle ID, selection policy, entity set,
ledger schema/count, clocks, declared input scope, and every artifact digest,
length, and content type.

## Artifact topology and authority

Four immutable content-addressed objects are written under
`objects/sha256/<first-two-hex>/<digest>.bin`; together with the immutable
manifest, they are the five durable artifacts of one snapshot.

| Artifact | Role | Authority and verification rule |
|---|---|---|
| Matrix JSON | `matrix_json` | The authoritative query receipt. It includes the query policy, cells, and exact `GovernanceBundle`; canonical JSON must round-trip byte-for-byte. |
| Full raw-ledger JSON | `ledger_json` | The complete committed ledger supplied to the query, including unselected occurrences and revisions—not a selected-fact subset. It restores only through the strict canonical byte decoder. |
| Filing metadata JSON | `filing_metadata_json` | Canonical occurrence-ID-indexed filing metadata, each bound to its ledger occurrence's accession, document ID, and source-body digest. |
| Cells Parquet | `cells_parquet` | A deterministic, flat projection of matrix cells for future private scanning. Its one-row-group schema, row count, decoded-byte limit, and rows must exactly equal the matrix-derived projection. It is never a second receipt format. |
| Manifest JSON | `manifests/ffqs_<snapshot-id>.json` | Canonical immutable index of the four objects and the snapshot contract. Its ID must equal the SHA-256-derived manifest identity. |

`latest.json` is deliberately separate and is the sole mutable object. Its
canonical pointer binds a snapshot ID, manifest key, query hash, and publication
time. It advances only after all four objects and the manifest have been read
back and the complete snapshot—including deterministic replay—has verified.
An identical retry is idempotent; an older `published_at` cannot rewind latest.

The matrix JSON is authority. Parquet is convenience, and is accepted only when
it proves itself an exact projection of that authoritative matrix.

## Prepare, publish, verify, replay

`prepare_query_snapshot(...)` admits a bounded canonical matrix, complete
`RawFactLedger`, and frozen filing metadata. It rejects bad clock ordering,
metadata not bound to a ledger occurrence, noncanonical input, and a ledger
that cannot reproduce the supplied matrix before any store write. Snapshot
`computed_at` must not precede the policy or retained node readiness; its
`published_at` must not precede `computed_at`.

The replay is the important proof step. It builds a query engine from the
snapshot ledger and the matrix's frozen `GovernanceBundle`, then requires
`query_matrix(...)` to reproduce the authoritative matrix JSON byte-for-byte.
It therefore consults neither mutable SEC state nor a live metric registry. A
frozen bundle must have the same `recorded_at` as the query policy; conflicting
per-query bundles are rejected.

`publish_query_snapshot(...)` checks an existing immutable key for exact-byte
identity or writes it, then strictly reads it back and rechecks its digest. The
same discipline covers the manifest. Only then does it load, validate, and
replay the snapshot before writing `latest.json`. A failed latest-pointer
readback makes latest uncertain and best-effort restores the preceding pointer
in the allowed single-writer lane.

`verify_query_snapshot(...)` verifies canonical manifest/pointer bindings,
artifact size and SHA-256, matrix/manifest bindings, strict ledger restoration,
metadata bindings, Parquet equivalence, clock bounds, and the frozen-engine
replay. Loading an explicit ID does not rely on latest; loading without an ID
also proves that latest binds the resolved manifest.

## Ledger and store fail-closed boundaries

### Raw ledger restore

`RawFactLedger.from_json_bytes(...)` is the external restore boundary. It
accepts bytes only, applies the ledger wire ceiling before UTF-8/JSON parsing,
rejects duplicate JSON keys and non-finite constants, then requires the restored
ledger to serialize to the exact supplied canonical bytes. `from_dict(...)`
performs the same semantic reconstruction for already-decoded mappings, but
cannot prove duplicate-key or original-byte properties and is not the snapshot
boundary.

Admission is bounded at 1,000,000 events, 512 MiB aggregate ledger wire bytes,
and 2 MiB per raw-fact wire object. Each object has an exact field set and JSON
native shapes; bounded strings, dimensions, units, arrays, booleans, integers,
and signed-64-bit source spans are revalidated. Restore recomputes and checks
context/unit semantic keys, logical/duplicate/occurrence identities, source
identity, clocks, and canonical representation. The ledger constructor then
rechecks immutable event uniqueness, revision-parent append order, economic-key
preservation, and source-event lineage chronology.

### Strict private-store reads

`Store.get_bytes(...)` remains the legacy fail-open read for existing research
ingest and read paths. `StrictReadStore` is a separate runtime-checkable extension
so legacy structural `Store` adapters remain compatible without pretending to
provide immutable-publication safety.

- `LocalStore.get_bytes_strict(...)` returns `None` only for a real missing path;
  unsafe keys and read failures propagate.
- `R2Store.get_bytes_strict(...)` returns `None` only for authoritative R2/S3
  `404`, `NoSuchKey`, or `NotFound` responses. Credential, permission, timeout,
  service, malformed-response, and body-read failures propagate.
- Snapshot prepare/load/publish require `StrictReadStore`; an unavailable or
  transient read becomes `QuerySnapshotError`, never an inferred absence. No
  write or latest-pointer advance follows such a failure.

## Invariants pinned by tests

| Invariant | Coverage |
|---|---|
| Duplicate preparation has the same ID, manifest, and payloads; publish/load/replay return the same matrix bytes. | `tests/test_fundamental_forensics_query_snapshots.py` |
| The frozen snapshot retains the full two-event ledger, selects the applicable restatement, and a later live restatement cannot alter the old snapshot. | `tests/test_fundamental_forensics_query_snapshots.py` |
| Every bound sidecar, manifest cutoff/entity binding, pointer canonicality, hostile key, metadata binding, and clock order fails closed when altered. | `tests/test_fundamental_forensics_query_snapshots.py` |
| Parquet rejects wrong schema, duplicate rows, wrong row count, or rows that differ from the matrix projection. | `tests/test_fundamental_forensics_query_snapshots.py` |
| Immutable object readback failure never creates latest; pointer readback failure restores the prior latest; process-local concurrent calls retain the newest pointer. | `tests/test_fundamental_forensics_query_snapshots.py` |
| Frozen governance replay is byte-identical after live-registry mutation/unavailability, enforces matching system cutoff, and cannot cross-contaminate concurrent same-cutoff bundles. | `tests/test_fundamental_forensics_query.py` |
| Ledger restore rejects forged IDs/semantic keys, malformed shapes, unbounded fields, inverted revision order, duplicate keys, noncanonical bytes, and oversize wire input before parsing. | `tests/test_fundamental_forensics_raw_ledger.py` |
| Strict local/R2 reads soften only authoritative misses; operational failures propagate; legacy `Store` remains a valid non-strict runtime adapter. | `tests/test_research_vault_strict_store.py` |

## Explicit boundaries

- **Input scope is `committed_ledger_only`.** The snapshot proves replay from the
  committed ledger it contains; it does not attest that this ledger contains the
  complete SEC universe or every eligible competing fact.
- **No SEC-universe completeness attestation.** The manifest fixes
  `sec_source_completeness_attested: false`; do not market this as absence proof
  or globally optimal selection.
- **JSON authority; Parquet convenience.** The matrix JSON is the only query
  receipt. Parquet is a verified deterministic projection.
- **`single_writer_operator_only`.** The process-local `RLock` serializes only
  callers in one Python process. There is no scheduler, multiprocess, or R2
  concurrent-publication support. Do not add any of those paths until an
  external lease or compare-and-swap primitive is held across publication and
  latest-pointer advance.
- **No API/UI yet.** Do not expose latest as a public query surface, shortcut
  tenant/authorization design, or turn these snapshots into trading authority.

## Next sequence

1. **Wave 3B-B — filing-package/iXBRL source attestation.** Retain and attest
   bounded filing packages and exact iXBRL/XBRL contexts so the snapshot's
   ledger can make source-completeness and dimension evidence claims with an
   explicit, testable boundary.
2. **Verified History API/UI.** Only after the attested filing-package layer:
   expose authenticated, receipt-linked historical query/trace views with
   stable snapshot identity, visible temporal policy, pagination/tenant bounds,
   and provenance drill-down. Neural Web may receive bounded descriptive
   projections from that verified surface, still without authority promotion.

## Local verification

Run the Wave 3B focused contracts from the implementation worktree:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider \
  tests/test_fundamental_forensics_query.py \
  tests/test_fundamental_forensics_raw_ledger.py \
  tests/test_fundamental_forensics_query_snapshots.py \
  tests/test_research_vault_strict_store.py
git diff --check -- research/CALCBENCH_PARITY_WAVE_3B_IMMUTABLE_QUERY_SNAPSHOTS_2026-08-02.md
```

This memo describes the implementation boundary, not merge, CI, deployment, or
production evidence. Record those only after they are independently observed.

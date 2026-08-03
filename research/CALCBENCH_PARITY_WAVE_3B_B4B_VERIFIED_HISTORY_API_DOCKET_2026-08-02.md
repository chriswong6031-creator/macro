# Calcbench Parity — Wave 3B-B4B Verified History API

**Canonical implementation handoff for Wave 3B-B4B**

**Date:** 2026-08-02

**Status:** implementation complete; local release gates passed

## Outcome

Wave 3B-B4B turns the immutable `ffqsv2_` receipt from B4A into a bounded,
authenticated product API. It is a receipt reader, not a source verifier. No
request can fetch SEC data, replay a filing, rerun a query, parse iXBRL, or
publish an object.

The positive claim remains deliberately narrow:

> A selected raw Company Facts occurrence corresponds to one stored B3
> selected-member Company Facts row under the named sealed publication
> receipt.

The API says explicitly that neither the source nor the match body was replayed
at read time. Partial and non-evaluable roots remain visible. A green response
cannot promote one matched leaf into filing completeness, accounting
correctness, or trading authority.

## Product surface

The production router now exposes three `site_full` endpoints:

```text
GET /api/forensics/v1/attested-history/latest
GET /api/forensics/v1/attested-history/snapshots/{snapshot_id}/roots
GET /api/forensics/v1/attested-history/snapshots/{snapshot_id}/roots/{root_cell_id}
```

`latest` returns safe receipt identity, policy, clocks, coverage totals, a
minimal Company Facts conversion receipt, and the exact authority boundary.
It omits object keys, source paths, submission-source records, conversion rows,
full B3 records, and filing bodies.

`roots` uses stable keyset pagination over immutable sorted root IDs. It returns
only the selected, eligible, and attested leaf IDs plus one mechanically derived
coverage state. It never materializes or serializes all receipt roots for one
request.

`root detail` returns one selected-leaf waterfall. An attested leaf may expose
the safe Company Facts identity, period, canonical value, match ID, and the
stored compact B3 projection. An unattested leaf remains visible as unattested;
it is not silently dropped.

## Entitlement and privacy boundary

Authentication runs before `site_full` entitlement, and entitlement runs before
private-store construction. Free, missing, or invalid users cannot use error
timing to open or probe the research bucket.

Every success and expected error carries:

```text
Cache-Control: private, no-store
Vary: Authorization
X-Content-Type-Options: nosniff
X-Robots-Tag: noindex, noarchive
```

Upstream authentication headers are merged case-insensitively. A hostile or
accidental lowercase `cache-control`, mixed-case `Vary`, or conflicting robots
header cannot coexist with and weaken the route policy; unrelated headers such
as `WWW-Authenticate` remain intact.

A paid, OpenAPI-hidden catch-all handles malformed and encoded-slash history
paths with the same private headers. It never constructs the object store.

## Bounded receipt reader

`engine/fundamental_forensics/attested_query_snapshots.py` now includes a
serving-only `AttestedQueryReceiptIndex` and
`load_attested_query_receipt_index(...)`.

The reader loads only:

1. the independent v2 latest pointer when `snapshot_id` is omitted;
2. the exact immutable v2 manifest;
3. `bindings_json`; and
4. `coverage_json`.

It never reads the full `attestations_json`, full
`companyfacts_conversion_json`, v1 matrix, v1 ledger, v1 Parquet, or filing
source bodies. Pointer, manifest, compact-artifact length, digest, canonical
JSON, cross-object identity, coverage state, summary totals, and one-to-one
binding invariants all fail closed.

The reader uses the public cap-only `StrictBoundedReadStore` contract. Each
compact object is read with its manifest-declared byte length as the cap and is
then required to have that exact length and digest. A structurally compliant
third-party strict store does not need a private keyword extension.

## Memory and concurrency budgets

Publication may retain larger reproducibility artifacts, but HTTP serving is a
smaller lane. The receipt reader currently admits at most:

- 2 MiB combined `bindings_json` and `coverage_json`;
- 5,000 B3 projections;
- 20,000 occurrence bindings;
- 10,000 root cells;
- 40,000 selected/eligible/attested leaf references; and
- a conservative 16 MiB decoded-index weight.

Cache weight includes serialized bytes and conservative decoded-object,
mapping, index, and repeated-reference costs. The process cache is bounded to
four entries and 16 MiB. Failed or stale loads are never cached.

Thirty-two fixed lock stripes provide bounded single-flight coordination. A
burst of concurrent cold requests for the same immutable receipt shares one
compact download and parse. Ordinary later cache hits still re-read and
digest-check the manifest and both compact objects, so a mutable or corrupt
backend cannot hide behind a warm process cache.

## Response construction budget

Object-read limits do not by themselves limit a JSON response. Root coverage
therefore has independent per-root and per-page leaf-reference ceilings, and a
root-detail response has a conservative 4 MiB serialized-wire ceiling.

The detail path measures the already-built response prefix and each actual
waterfall row before retaining that row. JSON escaping is included in the
measurement. This closes the case where 1,024 otherwise legal attested leaves
carry very large canonical decimal strings and would create a tens-of-megabytes
response despite satisfying the leaf-count limits.

## Authority returned to clients

Every endpoint preserves the following interpretation:

```json
{
  "positive_claim": "B3_selected_member_companyfacts_row_correspondence_only",
  "coverage_scope": "selected_raw_fact_leaves_only",
  "claim_basis": "sealed_publication_receipt",
  "source_reverified_at_read": false,
  "match_body_replayed_at_read": false
}
```

The manifest's complete fixed-false nonclaim map accompanies this authority.
The field name `stored_b3_projection` is intentional: it is evidence copied
from the sealed receipt, not a fresh request-time attestation.

## Acceptance evidence

The focused B4A/B4B reader suites currently pass **28 tests**. The authenticated
API suite passes **34 tests**, including:

- denial before private-store construction;
- route-local privacy headers on successes and expected failures;
- hostile identifier, duplicate query, cursor, and limit rejection;
- stable keyset pagination and direct root lookup;
- raw B3, object-key, source-record, and full-conversion non-disclosure;
- warm-cache pointer, manifest, bindings, and coverage tamper detection;
- cap-only strict-store compatibility;
- compact-byte, cardinality, decoded-memory, cache, and response budgets;
- concurrent cold-load download/parse coalescing;
- the production-limit large-canonical-value response exploit; and
- encoded-slash/extra-path private catch-all behavior; and
- a real B4 publication through the recursively frozen receipt index and all
  three HTTP routes.

The final broad local gate before the frozen-index integration regression passed
**540** fundamental-forensics/API tests,
**12** CI-pack contract tests, and **34** focused entitlement, denial-before-
store, and production OpenAPI checks. Syntax compilation and `git diff --check`
pass. These counts are local implementation evidence. Hosted CI, merge
ancestry, API deployment, and production health must be recorded only after the
repository ship loop completes.

## Explicitly excluded from B4B

B4B does not create `ffqsv2_` receipts. The repository still needs a scheduled,
single-writer materializer that captures Company Facts, publishes a governed
v1 query snapshot, constructs B3 filing attestations and exact occurrence
bindings, and publishes the v2 overlay pointer last.

B4B also does not add the premium history UI, multi-issuer catalog, Excel
surface, notification, or Prophet/Neural Web score. Building UI before the
materializer would create an attractive empty shelf. The next load-bearing lane
is the scheduled one-issuer evidence-to-receipt operator; the UI follows that
producer.

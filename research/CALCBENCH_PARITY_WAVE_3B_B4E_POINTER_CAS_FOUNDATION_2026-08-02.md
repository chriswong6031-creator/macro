# Calcbench Parity — Wave 3B-B4E Exact-Predecessor Pointer CAS

**Canonical implementation handoff**

**Date:** 2026-08-02

**Status:** implementation and local validation complete; hosted CI, merge, and
production advancement are not claimed by this document.

## Outcome

B4E removes the compliant-writer lost-update and rollback race from the mutable
`ffqsv2_` latest pointer. Publication now requires a store that can read an
exact bounded value with an opaque predecessor token and atomically create or
replace the pointer only if that predecessor still owns the key.

```text
fresh B3 replay + prepared B4 overlay
  -> verified immutable artifacts and manifest
  -> exact current pointer bytes + opaque version
  -> If-None-Match create or If-Match replacement
  -> bounded reconciliation/read-back
  -> no rollback write under any outcome
```

This is the storage-safety prerequisite for a later scheduled operator. It is
not the operator, a publication lease, a receipt producer, or a user-facing
feature.

The publication contract deliberately remains `single_writer_operator_only`.
R2 ETags and the LocalStore token are value tokens and may repeat if an
unrestricted principal recreates old bytes. B4E therefore does not claim ABA
fencing or safety against deletion/unconditional rewrite until an exclusive
credential policy or a non-repeating generation fence is deployed.

## Conditional store contract

`engine/research_vault/r2_store.py` adds:

- `VersionedBytes`;
- `StrictConditionalWriteStore`;
- `get_bytes_strict_bounded_versioned(...)`;
- `validate_strict_conditional_write_capability()`; and
- `put_bytes_strict_conditional(...)`.

A present value must carry exact bytes and one non-empty opaque version. A
missing value is exactly `(None, None)`. The version is concurrency authority,
not a content digest or integrity claim.

For R2, an absent predecessor uses `If-None-Match: *`; a present predecessor
uses its exact quoted ETag with `If-Match`. Only authoritative 409/412
precondition conflicts return `False`. Authentication failures, timeouts,
service errors, malformed responses, unavailable credentials, and unsupported
SDK models raise. The SDK capability is checked before source replay or any B4
write.

The LocalStore implementation uses a no-follow root lock, cross-process
`flock`, exclusive temporary creation, atomic replacement, and directory
`fsync`. Its predecessor scan rejects objects above the pointer plane's hard
16 KiB ceiling before hashing. It is the hermetic conformance backend, not a
claim that a local filesystem is a distributed database.

## B4 pointer transition

`engine/fundamental_forensics/attested_query_snapshots.py` changes only the v2
attested-history publication boundary:

1. prepare and read paths continue to accept strict bounded read stores;
2. publication rejects stores without the conditional contract before replay;
3. all existing source replay, immutable artifact, manifest, read-back, and
   snapshot reconstruction checks still precede pointer advancement;
4. the pointer is compared against the exact observed predecessor;
5. an exact already-current candidate is idempotent;
6. a stale or equal-clock divergent candidate cannot advance;
7. a conditional conflict is reconciled by a new bounded versioned read;
8. a transport exception is treated as ambiguous and accepted only when the
   exact candidate bytes are observed;
9. after an acknowledged CAS, a strictly newer concurrent successor is
   accepted only if its full immutable overlay resolves and all pointer fields
   bind that overlay; and
10. no failure, conflict, or read-back mismatch issues an unconditional repair
    or rollback write.

The process-local `RLock` remains useful load shedding. Conditional replacement
is the compliant-writer lost-update boundary, but it does not widen the public
publication contract beyond `single_writer_operator_only`.

## Compliant race closed; ABA boundary retained

The prior path could interleave as follows:

```text
A reads P0
B reads P0
A writes P1
B writes P2
A reads P2 and restores P0 as a best-effort rollback
```

The new path makes two compliant writers spend the same predecessor version. At
most one conditional write can consume it. A writer that loses or observes a
later successor never mutates the pointer again.

This does not prevent ABA if another principal restores the exact old bytes and
thereby recreates the same value token. The scheduled publisher remains disabled
until its mutation authority is exclusive or the pointer gains a non-repeating
generation/predecessor fence.

## Deliberate nonclaims

B4E does not claim:

- exactly-once publication;
- that a returned snapshot remains latest after return;
- ABA fencing or a non-repeating pointer incarnation token;
- protection from credentials that can issue rogue unconditional writes;
- an outcome when a network failure cannot be reconciled by a strong read;
- lease fencing, work deduplication, or scheduler exclusivity;
- CAS safety for the separate v1 query-snapshot latest pointer;
- current SEC freshness, filing completeness, accounting correctness, or
  investment authority; or
- Neural Web, Prophet, scoring, alerting, or trading authority.

Content-addressed immutable artifacts may remain as valid orphans after a CAS
loss or crash. That is intentional: orphan immutables are safer than a mutable
pointer overwrite.

The production writer credential should eventually be restricted so immutable
prefixes are create-only and the v2 latest key is conditional-only. Application
logic cannot defend against a separate principal with unrestricted overwrite
authority.

## Next controlled lane

After B4D and B4E are merged, the scheduled operator should initially run in
read-only preflight mode:

1. consume only a sealed configuration naming exact `ffqs_` and `ffsecsrc_`
   inputs;
2. materialize the B4D package and Company Facts conversion offline;
3. enumerate the B4D candidate plan;
4. run B4A preparation and fresh replay without publishing;
5. emit a private diagnostic receipt for operator review; and
6. keep scheduled publication disabled until an operator lease and production
   credential policy are deployed and tested.

A lease may reduce duplicate work, but final pointer CAS remains mandatory. An
expired object-store lease is not a transactional fence for a paused writer.

## Acceptance evidence

Observed in the final local worktree before remote release:

```text
Storage + publisher CAS focused surface: 62 passed
Full Fundamental Forensics surface:      628 passed, 5 known warnings
Research Vault storage/API surface:      323 passed, 1 skipped, 5 known warnings
CI manifest/pack:                        12 passed
Changed Python modules/tests:            py_compile clean
Git patch:                               diff --check clean
Independent adversarial re-audit:        SHIP
```

Adversarial coverage includes unsupported SDK models, absent/create and
present/replace headers, exact ETag retention, malformed and oversized reads,
409/412 conflict classification, operational errors, symlink rejection,
stale-token replacement, a spawned two-process one-winner race, both-writers-
read-one-predecessor schedules, acknowledged-CAS overtaking, ambiguous committed
PUT reconciliation, exact-candidate idempotency, and rejection of read-only
stores before replay or writes.

Cloudflare documents conditional operations for R2 `PutObject` and its direct
API consistency model:

- <https://developers.cloudflare.com/r2/api/s3/api/>
- <https://developers.cloudflare.com/r2/reference/consistency/>

Hosted CI, merge ancestry, and production advancement belong in the release PR
and cannot be pre-claimed here.

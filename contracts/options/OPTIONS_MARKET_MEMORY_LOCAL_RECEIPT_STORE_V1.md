# W1A Mac-local immutable receipt store v1

Status: **W1A-A contract and read-only verifier only**. The W1A-B
producer/replicator does not exist yet.

## Boundary

The upstream source contract is the existing private publication composed of:

- `options.market_memory_context_receipt_head/v1`;
- its exact `options.market_memory_context_audit/v1` object;
- its exact `options.market_memory_context_reference_set/v1` object; and
- the `options.market_memory_context_reference/v1` rows in that set.

The local plane preserves those canonical upstream bytes. It does not
reinterpret a mutable upstream `HEAD.json` as history. The only new records are
local content-addressed historical HEAD copies and an append-only publication
descriptor chain.

This contract grants no proposal, selection, score, rank, gate, size, issue,
publication, training, Prophet, Neural Web, execution, portfolio, or trading
authority. It does not change the current sparse-selector canary.

## Fixed production root and caller ownership

The reviewed production path is exactly:

`/Users/chriswong/.mastermind_private/options_market_memory_context_local_v1`

The caller, not the verifier, must create and provision it. The verifier never
calls `mkdir`, `chmod`, `chown`, rename, replace, lock, repair, or delete.

The caller resolves the intended Mac account to one numeric `(uid, gid)` and
passes those exact values to `attest_root`. Every accepted object must satisfy
all of these requirements:

- root and every descendant directory: regular directory, mode exactly `0700`,
  exact caller `(uid, gid)`;
- marker, mutable `HEAD.json`, and every immutable object: regular file, mode
  exactly `0600`, exact caller `(uid, gid)`, link count exactly one;
- no symlink in the absolute root path or any object path;
- no hardlinked file; and
- normalized absolute root and normalized relative object keys only.

`attest_root` returns the absolute path, device, inode, uid, gid, marker hash,
and store id. The selector must persist that `RootIdentity` before admitting
the root and supply it on every later read. A same-path copied or replaced root
is a different root and is refused even if its bytes, owner, and modes match.

## Layout

```text
.options_market_memory_context_local_root.json
HEAD.json
descriptors/<sha256[0:2]>/<sha256>.json
heads/<sha256[0:2]>/<sha256>.json
audits/<sha256[0:2]>/<sha256>.json
reference_sets/<sha256[0:2]>/<sha256>.json
```

The machine object contract is
`options.market_memory_context_local_receipt_store/v1` in
`options.market_memory_context_local_receipt_store.v1.schema.json`.

The marker fixes the store id, the three upstream schemas, and the unchanged
zero-authority object. `HEAD.json` is only the current pointer. A descriptor
mirrors the full canonical upstream HEAD identity, binds its exact historical
HEAD bytes, audit bytes, reference-set bytes, evidence policy, authority,
sequence, and predecessor descriptor hash.

## Immutable history and publication order

Each descriptor file name is the SHA-256 of its canonical bytes. Sequence zero
has no predecessor. Every later descriptor names the exact prior descriptor,
increments sequence by one, uses a unique upstream publication id, and has a
strictly later `published_at` clock. The verifier walks from current tip to
genesis on every read; a missing, substituted, reordered, duplicated, or
skipped descriptor fails closed.

The future W1A-B producer must create historical HEAD, audit, reference-set,
and descriptor objects without replacement, durably seal them, and only then
atomically replace local `HEAD.json`. It must never overwrite a historical
object. Those write mechanics are deliberately not implemented in W1A-A.

Advancing local `HEAD.json` therefore changes only the current tip. A reader
can request an older publication id and receives the same historical HEAD,
audit, and reference-set identity after later publications arrive.

## Monotone high-water

Every successful read returns
`options.market_memory_context_local_high_water/v1`, containing the root marker
hash, store id, descriptor count, tip sequence, tip descriptor hash,
publication id, publication clock, and historical upstream HEAD hash.

The caller persists that value outside this receipt root and supplies it to
the next read. The current descriptor chain must contain the exact prior tip at
the exact prior sequence. A lower count is rollback; a different identity at
that sequence is conflicting history. Neither is recoverable by choosing the
new current HEAD.

## Exact as-of and source binding

An exact-reference read requires the owner schema, owner id, owner
`requested_as_of`, query `as_known_at`, and owner `record_sha256` to match
exactly. There is no nearest, latest, reconstruction, or hindsight fallback.

The authenticated audit additionally preserves the frozen ordered repository
source paths and their SHA-256 values. The descriptor binds the full upstream
HEAD, audit hash, reference-set content hash, reference-set object hash, object
keys, count, and descriptor order. Missing objects and omitted descriptors are
errors, never abstention-shaped evidence invented by this reader.

## Read-only and failure behavior

All path traversal and object reads are rooted in persistent `O_NOFOLLOW`
directory descriptors. File identity is fenced before and after each bounded
read, then re-resolved from the anchored root so a rename-and-replace at the
original path cannot keep the open descriptor. Marker, local HEAD, and the
configured absolute root path are reopened and compared before return.
Returned authenticated structures are recursively immutable; exact-reference
extraction revalidates the canonical reference-set, audit, historical HEAD,
and descriptor mirrors and does not treat caller construction as
authentication. The reader exposes no publish or repair function and performs
no filesystem mutation.

Malformed or conflicting local HEAD, rollback, root substitution, symlink or
hardlink substitution, owner/mode drift, missing objects, omitted descriptors,
historical-object rewrite, non-canonical JSON, hash mismatch, as-of mismatch,
source-hash mismatch, evidence-policy drift, or authority drift all raise
`LocalReceiptError`.

The exact next task is **W1A-B producer/replicator**: implement the network-dark,
credential-free, append-only copy protocol into this caller-owned root and
prove its real 5–8 MiB / 4,096-reference and target-watchdog behavior without
changing the current canary.

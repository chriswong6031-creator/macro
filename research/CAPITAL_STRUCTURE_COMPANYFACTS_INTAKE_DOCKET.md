# Capital Structure Company Facts Intake Docket

Canonical implementation note for the dedicated SEC Company Facts source lane.

## What landed

`collectors/sec_capital_structure_companyfacts.py` is a bounded, serial-SEC-host
collector that admits only unique CIKs anchored by a verified, retained,
parser-clean `complete_submission` row in
`data/capital_structure/source_manifest.parquet`. It never modifies or extends
`capital_structure.source_manifest/v1`.

It retains current SEC Company Facts JSON only after all of these gates pass:

1. the selected complete-submission anchor resolves through its declared stable
   `store_id` and backend, with its digest-derived object key, exact hash, and
   byte length independently read-verified under the run deadline/byte budget;
2. canonical `data.sec.gov/api/xbrl/companyfacts/CIK##########.json` request;
3. streamed response under the declared and actual byte caps;
4. UTF-8 JSON with a CIK exactly equal to the requested CIK;
5. SHA-256 content-addressed source-store write and exact read-back;
6. closed-contract manifest and append-only coverage-row validation; and
7. an immutable generation, chained receipt, and atomic selector publish.

An unknown, missing, corrupt, or rebound anchor store/object never falls back to
the currently preferred R2 bucket and never permits an SEC Company Facts call.
It becomes an explicit deferred coverage outcome. The signed receipt binds each
selected CIK to the declared anchor store, backend, object key, digest, length,
and verification outcome; successful Company Facts manifests repeat that exact
anchor binding. Mixed success/failure runs therefore remain honestly
`partial`, while a stale prior success plus a failed refresh anchor is
`degraded` rather than silently healthy.

The queue is deterministic and hard capped at 24 CIKs/run (64 maximum). A
2:1:1 rotating retry/new/refresh schedule, ordered by due clock then CIK within
each lane, prevents any continually non-empty lane from starving while retaining
retry weight. It is serial inside `scripts.collect`'s shared `sec` host group and
preserves a local 100ms request floor. Delayed retry/defer work and fresh captures
are separately counted; a deferred request never becomes a negative issuer fact.

## Contracts and artifacts

| Artifact | Contract | Purpose |
| --- | --- | --- |
| `data/capital_structure/companyfacts/generations/<sha256>/source_manifest.parquet` | `capital_structure.companyfacts_source_manifest/v1` | Immutable, byte-verified Company Facts source evidence. |
| `data/capital_structure/companyfacts/generations/<sha256>/coverage.parquet` | `capital_structure.companyfacts_coverage_row/v1` | Immutable generation containing the append-only queue/retrieval history. |
| `data/capital_structure/companyfacts/receipts/<sha256>.json` | `capital_structure.companyfacts_coverage_receipt/v1` | Immutable sequence/predecessor receipt that commits both ordered prefixes and exact generation files. |
| `data/capital_structure/companyfacts/coverage_receipt.json` | `capital_structure.companyfacts_current_pointer/v1` | Tiny atomically replaced pointer to the selected immutable receipt/generation. |
| `capital_structure/companyfacts/current_head.v1.json` in the guard R2 bucket | `capital_structure.companyfacts_head_witness/v1` | Signed, external exact-predecessor witness and the production cross-host CAS authority. |

The collector stages and read-backs both Parquet ledgers under an identity-named
generation directory, seals an immutable receipt under `receipts/`, performs the
external exact-predecessor head CAS, then advances only the tiny local pointer.
It never overwrites a ledger or receipt. The absolute lane root is traversed
from `/` one component at a time: every existing ancestor is lstat/openat
identity-checked with `O_NOFOLLOW|O_DIRECTORY`, and every missing component is
created with `mkdirat`, re-opened, verified, and parent-dir-fsynced. Receipt,
generation, pointer, lock, stage, and anchor-ledger reads then remain relative
to held directory descriptors. An ancestor or descendant symlink — including a
not-yet-created lane beneath `inside/parent -> outside` — cannot redirect a
read, create, link, or rename outside the lane.
On startup it authenticates the complete predecessor chain, every required
generation, and the selected generation's exact bytes and ordered prefixes. An
orphaned stage or receipt is unreachable evidence, not a source claim.

Raw-object retention has two distinct verification promises. Every *newly
admitted* JSON object is exact-verified by source-store `put_verified` (write and
read-back). Existing objects receive a deadline-accounted, rotating retention
audit capped at 24 objects: two latest-per-CIK slots for every one historical
slot while both lanes are available, with a deterministic UTC-day cursor. The
signed receipt's `retention_verification` names the exact manifest IDs checked,
the admission-verified suffix, and whether coverage is `complete` or `sampled`.
Thus an `ok` coverage status means the CIK coverage population is healthy; it
never claims every historical object was reread that run. On-demand consumers
must still call `get_verified` for the exact object they intend to consume.

The four local artifacts are registered in `config/synapse.yml`; the R2 witness
is a guard, not a data-plane Synapse artifact. The daily collection step runs the
adapter immediately after `sec_capital_structure`; this dependency is recorded
in `.github/workflows/daily.yml` and `config/dag.yml`.

## Trust, concurrency, and recovery contract

Receipt and head *hashes are identities, not authorization*. Every receipt now
carries an `hmac-sha256/v1` authentication envelope, and the R2 head witness is
signed over the precise selected receipt identity, receipt bytes, generation,
sequence, and predecessor. A locally rewritten history cannot become current by
merely recomputing hashes or even by using a local test signer: startup requires
the external witnessed head to match exactly.

Production has no local signer or local-only fallback. It must be configured
before the adapter makes a network request with:

- `CAPITAL_STRUCTURE_COMPANYFACTS_HEAD_HMAC_KEY` (a secret of at least 32 bytes);
- `CAPITAL_STRUCTURE_COMPANYFACTS_HEAD_KEY_ID` (optional; defaults to
  `companyfacts-head-v1`); and
- `COMPANYFACTS_HEAD_GUARD_BUCKET`, or the existing
  `R2_CAPITAL_STRUCTURE_BUCKET`, or the existing shared `R2_BUCKET`, plus the
  normal dedicated/shared R2 endpoint and credentials used by
  `engine.capital_structure.source_store`.

`.github/workflows/daily.yml` passes the required HMAC secret explicitly. This
is an activation gate, not an optional degradation path: the repository owner
must provision `CAPITAL_STRUCTURE_COMPANYFACTS_HEAD_HMAC_KEY` before merging the
lane. The present shared R2 bucket is a supported guard fallback; a dedicated
`COMPANYFACTS_HEAD_GUARD_BUCKET` may be supplied later without changing receipt
semantics.

The guard uses R2 S3 `PutObject` conditions: `If-None-Match: *` for genesis and
the service-returned quoted ETag in `If-Match` for later heads. A 409/412
precondition failure is a deterministic compare-and-swap conflict. An advisory
POSIX `flock` holds the local lease across load, collection, and publish; R2 is
the authority across hosts.

The order is intentionally guard then pointer. If the external witness is newer
than the local pointer (including a post-CAS pointer fsync failure), or the local
pointer is newer than the witness, startup refuses to select either side or call
SEC. Pointer loss alongside any receipt/generation and all published-head
mismatches require explicit operator recovery; there is no automatic re-genesis
or silent rollback. A directory-fsync failure after rename is surfaced as an
indeterminate publication, not a successful write.

The receipt chain is hard-capped at 512 receipts and each committed Parquet file
at 128 MiB. Empty/no-op runs do not create a new receipt or advance either head.
At the cap the adapter publishes no 513th receipt, prints a line-start
`companyfacts-checkpoint-blocked` operational annotation, and returns a
`checkpoint_blocked` heartbeat. The generic collector maps that heartbeat to
non-failure `blocked`, so it cannot demote the lane to `failed`/`dead`; a
versioned signed checkpoint/compaction migration is the explicit dependency
before publishing resumes. Time checks bracket request setup, streamed response,
source-store retention, and generation sealing. Where a content store lacks a
per-call read timeout, the sampled read runs in read-only daemon isolation and
the caller returns at the remaining hard wall-clock deadline. Server
`Retry-After` is persisted as its full UTC deadline rather than being shortened
locally.

## Scope and hard nonclaims

This lane is source acquisition only. It does **not**:

- normalize or interpret any Company Facts value;
- write, amend, or consume the capital-structure share-count truth ledger;
- infer outstanding, float, fully diluted, capacity, cash runway, risk, or
  financing state;
- create instruments or classifications; or
- affect risk, ranking, sizing, entry, alerting, or Prophet.

The current Company Facts endpoint is not historical availability evidence. Its
receipt records Mastermind acquisition/retention clocks only; future PIT use must
respect that limitation and preserve raw source references.

## Next-wave boundary: share-count consumption

The next wave may add a separate offline consumer that reads **only** verified
Company Facts manifests plus a valid coverage receipt, fetches no network bytes,
and feeds the parked share-count truth plane through an explicit versioned input
contract. That consumer must retain the Company Facts manifest ID, content hash,
object-store namespace, anchor manifest ID, acquisition clock, concept/unit, and
all ambiguity/defer outcomes. It must not use filing date as a public-availability
substitute, must not coerce current-source data into historical values, and must
not grant any authority beyond the existing share-count truth-plane boundary.

## Validation performed

`python3 -m pytest -q tests/test_sec_capital_structure_companyfacts.py`

The focused suite covers canonical request/CIK validation, declared and streamed
byte caps, unique verified-anchor selection, deterministic starvation-free queue
progress, source-store failure, honest `ok`/`partial`/`degraded`/`blocked` status,
force-refresh history preservation, body/semantic/cross-ledger identity checks,
full-chain startup authentication, authenticated queue telemetry re-derivation,
bounded Company Facts retention re-verification, exact filing-anchor store/hash/
length verification before SEC access, missing/corrupt/rebound/unknown anchor
failure telemetry, deadline and byte-budget enforcement, ancestor/descendant
symlink and swap-race refusal across every lane path, retry-after persistence,
R2 conditional-CAS/provider-conflict behavior, both head/pointer split-brain
refusal orders, receipt/no-op cap behavior, and last-good survival across
generation/receipt/pointer publish faults.

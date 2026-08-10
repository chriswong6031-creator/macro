# W0b focused vendor-snapshot quote R2 runbook

Status: **implementation-only / provider activation blocked**

This lane turns an explicit ordered list of already-eligible W0a contracts into
one narrowly labelled ThetaData vendor-snapshot bid/ask receipt. It does not
choose a root, choose a profile, choose a contract, rank, truncate, substitute,
issue, size, recommend, or trade.

No live ThetaData or R2 call was made while implementing this boundary. Do not
enable a scheduled or interactive provider run until a bounded subscribed RTH
`first_order` probe has independently proved the endpoint and the operator has
accepted the resulting receipt semantics.

## Truth boundary

The only provider operation is the existing collector call:

```python
collectors.thetadata.snapshot_greeks(root, order="first")
```

That call uses:

```text
GET /v3/option/snapshot/greeks/first_order
symbol=ROOT&expiration=*&strike=*
```

It returns one full-chain snapshot per root. W0b groups the explicitly requested
contracts locally and makes exactly one call per unique root, in first-input
order.

The published quote label is exactly:

```text
vendor_snapshot_bid_ask
```

It is not an NBBO, live, current, or executable claim. The snapshot endpoint
does not provide the quote sizes, venues, or conditions required to make those
claims. W0b does not call or splice `trade_quote`.

Every decision and receipt fixes these values to `false`:

- `rank_authority`
- `gate_authority`
- `sizing_authority`
- `issue_authority`
- `trade_authority`
- `prophet_authority`
- `neural_web_authority`

## Explicit input contract

The caller supplies a JSON array containing one through twelve rows. Array order
is contractual and is never sorted:

```json
[
  {
    "root": "SPY",
    "profile_id": "convex_otm_30_180_v1",
    "contract_id": "contract:uchain:<64 lowercase hex>"
  }
]
```

Each row must contain exactly `root`, `profile_id`, and `contract_id`. Unknown
keys, duplicate triples, an empty array, or a thirteenth row fail before a
decision is written. Multiple explicit profiles may refer to the same contract;
their original input rows and output ordinals remain separate.

There is no implicit root universe, default profile, fallback contract,
top-N rule, timestamp tie-break, or partial-success truncation.

## Exact W0a attestation

Before creating a decision, W0b verifies the exact canonical bytes of:

1. the W0a-B producer ledger
   `chain_snapshots/_bucket_receipts/<session>.jsonl`;
2. `options_structure/msc_intraday/index.json`; and
3. every immutable packet named by that index, including roots not selected by
   the explicit focused input.

The completion ledger is a mandatory CLI flag and direct `prepare_attempt` /
`run_attempt` argument; there is no polling path without it. W0b decodes the
entire physical ledger with `engine.chain_snapshot_completion.decode_ledger`,
requires exactly one `complete` state for the index session/bucket, and binds
the exact selected intent, decision, and availability records. The semantic
attestation carries their receipt IDs, SHA-256 hashes and causal clocks, the
three-record state bytes/hash, bucket ID, cadence, exact roots/count, and the
producer completion-result hash. Later append-only states in the same physical
session ledger do not change this already-immutable selected-state identity.

The index attestation records exactly once:

- logical key;
- SHA-256 of the canonical bytes;
- byte count;
- `index_id`; and
- epoch.

Each indexed packet attestation records exactly once, in canonical index-root
order:

- root;
- immutable logical key;
- SHA-256;
- byte count;
- `packet_id`; and
- the same epoch.

W0b recomputes the W0a `index_id`, `packet_id`, and `contract_id`, verifies
canonical JSON byte equality, checks object receipt length/hash/identity, checks
packet/index epoch coherence, and proves that each requested contract appears in
the requested profile's explicit `eligible_contract_ids` and matching contract
receipt. Any canonical, schema, identity, byte-count, digest, epoch, profile, or
membership failure stops before a durable decision and before a provider call.

The producer proof and W0a publication must also agree exactly: intent and index
session/bucket, full root set/count, cadence, and each root's installed bucket
row count plus first-order vendor minimum/maximum clocks are matched to every
W0a packet. The W0a index `available_at` must be at or after the producer's
durable availability receipt. A self-asserted `complete_bucket=true` without
this decoded intent→decision→availability chain can never authorize polling.

Schema validation is not inferred from hashes. Every direct preparation path
lazily loads, checks, and applies the repository's Draft 2020-12 contracts with
format checking before accepting either object:

```text
contracts/options/options.contract_eligibility.index.v1.schema.json
contracts/options/options.contract_eligibility.v1.schema.json
```

An unavailable/invalid validator or a canonical object that was re-identified
after violating either schema is a hard pre-decision failure.
The producer ledger is governed by
`contracts/options/chain_snapshots.bucket_completion.v1.schema.json`; W0b uses
the producer module's stricter physical JSONL/state-machine decoder, which
enforces the same exact record shapes, deterministic IDs, clocks, hashes, and
transition laws while rejecting torn or ambiguous ledger prefixes.

## OCC and millistrike preflight

W0b converts W0a `strike_canonical` to an exact decimal and requires
`strike * 1000` to be an integer. It then constructs the 21-character OCC symbol,
parses it back, and requires exact equality of root, expiration, right, and
millistrike.

The only pre-provider abstentions are:

```text
NON_MILLISTRIKE_CONTRACT
OCC_ROUNDTRIP_FAILED
```

They create an immutable decision and terminal receipt but make zero provider
calls. A non-0.001 strike is never rounded to a nearby contract.

## Semantic attempts and durable order

`attempt_id` is the SHA-256 identity of the ordered input rows plus the exact
producer-completion, W0a index/packet, and requested-contract attestations.
W0b's own wall-clock time is not part of the semantic attempt identity.

The local state is:

```text
<state-root>/<attempt-sha>/
  .attempt.lock
  decision.json
  receipt.json
```

The state root is an exclusive, caller-owned `0700` authority. Its directory
inode is opened without following the final path component and flocked across
the entire attempt; the `0700` attempt-directory inode and `0600` child lock are
then checked before and after provider access. Decision and receipt reads/writes
are anchored to the open directory descriptor and require caller-owned `0600`
single-link regular files. Symlinks, special files, hard-linked artifacts,
replaced root/directory/lock inodes, oversized bodies, and non-canonical bytes
fail closed. Replacing `.attempt.lock` therefore cannot admit a concurrent
compliant provider holder.

Local-only `run_attempt` remains an offline/hermetic API for a stable exclusive
state root. Arbitrary same-UID replacement of the entire root cannot be made a
finite security boundary by adding another replaceable local pathname. The
provider-capable CLI therefore requires private R2: global semantic decision CAS
prevents a replacement-root contender from polling even when its local tree is
new.

The sequence is load-bearing:

1. acquire the state-root and per-attempt directory/lock flocks;
2. without publication, create and fsync local `decision.json` without an
   overwrite path;
3. with publication, resolve the private R2 decision first: coherently read an
   existing decision or conditionally create one, adopt the valid semantic CAS
   winner if another host wins with a different decision clock, then create and
   fsync local `decision.json` from those exact winner bytes;
4. only then make one `first_order` call per unique root;
5. verify the exact requested source rows and compute freshness at
   `verified_available_at`;
6. without publication, create and fsync local `receipt.json` without an
   overwrite path; and
7. with publication, conditionally create the private R2 receipt or adopt a
   valid concurrent receipt winner, then create and fsync local `receipt.json`
   from those exact winner bytes.

The R2 keys are immutable and attempt-specific:

```text
private/options_focused_quote/v1/attempts/<semantic-sha>/decision.json
private/options_focused_quote/v1/attempts/<semantic-sha>/receipt.json
```

Writes use conditional create (`If-None-Match: *`) and exact
`Content-Type: application/json` plus `Cache-Control: private, no-store` headers.
Every coherent GET first rejects a missing, non-integer, zero, or greater-than-2
MiB `ContentLength`, then performs a bounded exact-length read and verifies the
body digest. Metadata must contain exactly the governed SHA-256, schema,
record-type, attempt-id, visibility, and immutable fields; extra or malformed
metadata and header drift fail closed. There is no `current.json`, global index,
discovery pointer, or mutable alias.

The private publication plane is a security boundary, not a key-name convention.
The CLI exits before reading input bytes, importing the collector, calling
`run_attempt`, or writing a decision unless the operator supplies both
`--execute-provider-poll` and `--publish`. That explicit poll acknowledgement
also requires `--w0a-completion-ledger` and all four dedicated settings:

```text
OPTIONS_FOCUSED_QUOTE_R2_ENDPOINT
OPTIONS_FOCUSED_QUOTE_R2_ACCESS_KEY_ID
OPTIONS_FOCUSED_QUOTE_R2_SECRET_ACCESS_KEY
OPTIONS_FOCUSED_QUOTE_R2_BUCKET
```

They must identify a dedicated access-controlled private bucket/credential set.
Generic `R2_ENDPOINT`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, and `R2_BUCKET`
are intentionally ignored; the shared/public publication plane is never a
fallback.

Before activation, infrastructure evidence must additionally prove that the
dedicated bucket has no public `r2.dev` URL or custom-domain exposure and that
the credentials are scoped to this bucket/prefix. Environment-variable names
and a `private/` key prefix do not attest bucket policy. Without those dedicated
credentials, provider-live CAS conformance remains an enablement residual; the
hermetic fake-R2 tests do not activate publication.

## Never-repoll recovery law

A durable decision is the point of no return. If it exists, that semantic
attempt never polls again.

That law is global, not just process-local. An R2-enabled contender adopts the
exact valid remote decision before creating local decision bytes. If two hosts
both observe absence, the conditional-create loser adopts the winner's exact
decision bytes, even when their proposed `decided_at` clocks differ. It then
recovers an exact remote receipt if present; with no remote receipt it enters
pending/300s recovery and makes no provider call.

- Existing valid receipt: return or re-publish the exact receipt bytes.
- Decision with no receipt and age below 300 seconds: return pending.
- Decision with no receipt at or above 300 seconds: write an abstention receipt
  with `RECOVERY_DEADLINE_EXCEEDED` and `recovered_without_repoll=true`.

The deadline is measured from the clock embedded in durable `decision.json`, not
filesystem mtime, object metadata, or a current pointer. A recovery clock before
the decision clock is a hard error.

Provider, transport, conditional-write, verification, process, and clock
uncertainty cannot authorize a second call. In particular:

- uncertain decision publication exits before provider access;
- a retry sees the durable decision and cannot poll;
- uncertain receipt publication reuses the durable local receipt bytes; and
- a receipt-key collision never causes another provider call.

The same global-winner rule covers receipt races. Two recovery hosts can cross
the 300-second deadline with different verification clocks, and a long provider
call can finish while another host publishes a deadline recovery. The first
valid receipt to win conditional create is authoritative; every loser adopts
those exact bytes without another provider call. A new contender installs the
winner locally before returning. If a pre-release test state already contains a
different immutable local receipt, it remains immutable and quarantined while
private-R2 mode returns the validated global winner; no shipped W0b state exists
under this implementation-only gate.

## Source-row acceptance

The full-chain source frame must provide these named fields:

```text
root expiration strike right snapshot_ts bid ask
```

W0b matches locally on exact root, expiration, right, and millistrike. It does
not choose the newest or closest row. A requested identity must have exactly one
structurally accepted row. Missing, empty, malformed, crossed, future-clock, or
ambiguous requested rows produce one atomic abstention:

```text
NO_STRUCTURALLY_ACCEPTED_SOURCE_ROW
```

That reason never means "no trades." It means only that this attempt could not
prove one structurally accepted vendor-snapshot source row for every explicit
input. Partial quotes are not published.

Receipt validation replays the complete source-call law rather than trusting a
recomputed receipt identifier. The source calls must be in first-root order,
use the exact `first_order` endpoint/order/root, have coherent returned,
requested-match, malformed, and accepted counts, and agree exactly with the
terminal status. A `complete` receipt requires one accepted source row for each
unique explicit contract; a source abstention cannot coexist with complete
source-call evidence. Recovery receipts instead carry the exact deadline and
zero source calls.

Extra first-order analytics are ignored. Even if a hostile frame supplies size,
venue, or condition-looking columns, W0b does not copy them into the receipt.

## Freshness clock

Theta snapshot timestamps without a timezone are interpreted as
`America/New_York`, matching the existing W0a collector contract. Each accepted
quote records:

```text
snapshot_ts
verified_available_at
age_microseconds
basis = verified_available_at_minus_vendor_snapshot_ts
```

`verified_available_at` is captured after all one-per-root provider calls and
structural verification. A source timestamp later than that clock is not
silently clamped; it fails structural acceptance.

W0b intentionally enforces no maximum-age threshold. `status=complete` means
only that every explicit requested identity was bound to exactly one
structurally accepted vendor snapshot row. It never means fresh, current,
tradable, live, NBBO, or executable. A structurally valid prior-close snapshot
may therefore be complete; consumers must inspect `age_microseconds` and apply
their own separately governed age policy without relabeling this receipt.

## Hermetic verification

Run from the repository root:

```bash
python3 -m pytest -q tests/test_options_focused_quote.py --tb=short
python3 -m pytest -q tests/test_thetadata.py --tb=short
python3 -m pytest -q tests/test_options_structure_intraday.py tests/test_build_options_structure_intraday.py --tb=short
python3 -m py_compile collectors/thetadata.py engine/options_focused_quote.py scripts/build_options_focused_quote.py tests/test_options_focused_quote.py
python3 scripts/build_options_focused_quote.py --help
```

These tests are synthetic. They make no ThetaData or R2 network call.

## Provider activation gate

Activation remains blocked until all of the following are independently
reviewed and recorded:

1. one bounded, subscribed, regular-trading-hours `first_order` probe;
2. proof that the returned contract identity and millistrike round-trip match
   the exact W0a request;
3. proof that the receipt retains only vendor snapshot bid/ask and the truthful
   false provenance flags;
4. create-only private R2 decision and receipt verification on a disposable
   semantic attempt;
5. crash/restart proof showing no second provider call; and
6. an operator decision to enable the caller.

Until then there is no launchd job, scheduler hook, live root list, R2 current
pointer, Prophet/Neural Web promotion, or Terminal trade-plan integration in
this slice.

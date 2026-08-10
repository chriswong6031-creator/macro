# MSC R2.2-A Light U-CHAIN publication runbook

## Scope and authority

This is the existing Market Structure Core R2.2 **Light U-CHAIN publisher**, not a
new signal or execution roadmap. It converts private local Parquet snapshots into
compact descriptive JSON receipts. It has no authority to select an underlying,
rank a candidate, gate a setup, size a position, issue a trade, execute an order,
or promote a Prophet plan. Every packet, profile, and projected contract carries
all six authority flags as `false`.

The builder does **not** implement an execution quote poller, Issue Desk, Terminal
surface, option optimizer, selector, outcome label, lifecycle, or workflow. Raw
high-volume U-CHAIN Parquet stays private/local. JSON is the governed light R2
projection; no JSONL ledger is introduced because this lane publishes immutable
per-bucket objects plus discovery pointers rather than append-only outcomes.

## Inputs and outputs

Private inputs for every requested root:

- `data/chain_snapshots/{ROOT}/{SESSION}.parquet`
- `data/chain_snapshots/{ROOT}/{SESSION}_oi.parquet`
- `data/chain_snapshots/_bucket_receipts/{SESSION}.jsonl` (live hook authority)
- `data/chain_snapshots/_meta.json` (standalone/manual compatibility only)

The production hook accepts only the producer's exact append-once
`intent -> decision -> availability` packet. Runtime validation re-proves its
schema, deterministic IDs and hashes, exact root list, cadence, source-completion
counters, decision clock, and availability clock before the builder starts. It
then re-proves each requested bucket's installed row count/content digest and
the stable OI row count/file digest against the per-root decision evidence. The
legacy standalone/manual CLI still accepts `_meta.json`, but production never
uses that mutable bridge. Any missing, malformed, swapped-while-read,
duplicate-contract, or partial root fails the whole publication before a
discovery marker changes.

R2 keys:

- immutable packet:
  `options_structure/msc_intraday/{ROOT}/{YYYY-MM-DD}/{HHMM}.json`
- per-root pointer:
  `options_structure/msc_intraday/{ROOT}/current.json`
- all-root authoritative manifest and commit:
  `options_structure/msc_intraday/index.json`

Every global index has `complete_bucket: true`; there is no partial index shape.
The complete `index.json` body is intentionally the one authoritative discovery
manifest; no second immutable generation-manifest object is required. It binds
each immutable object's key, SHA-256, byte length, and packet ID. A root
`current.json` is only a repairable convenience projection and binds the
authoritative index ID and epoch that produced it; readers must not treat a
current pointer as proof of complete-bucket publication.

## Profile law

Profiles are named, evaluated, and ordered independently. There is no blended
score and no ordering across profiles.

`prophet_delta60_monthly_v1` reuses the existing
`engine.prophet_bridge` target-delta and monthly-expiry law:

- call for BULL, put for BEAR;
- nearest monthly expiry at or after
  `clock_date + horizon_days + 15 calendar days`;
- primary selection nearest `+0.60` call delta or `-0.60` put delta;
- an equal-distance primary tie uses the first source row, matching the actual
  resolver's pandas `idxmin()` behavior;
- explicit fallback only when target-expiry delta is unavailable.

The legacy EOD resolver's fallback depends on input row order. This packet names
that defect and uses deterministic closest-OTM distance followed by source ordinal
inside its separately labelled fallback. It never calls that fallback delta-60.
The actual legacy candidate is resolved before browser eligibility is checked; if
that exact candidate has an unusable quote or nonpositive spot, the packet abstains
instead of substituting a different contract. If plan clock, horizon, direction,
and entry context is absent, the profile returns `context_required`; it does not
invent a default plan. A supplied plan clock must be a canonical real NYSE
session no later than the packet session. It is context only and is not presented
as the original decision clock.

`convex_otm_30_180_v1` is a Mastermind research-eligibility profile, **not** a
reconstructed competitor rule:

- 30–180 calendar-day DTE;
- 5–20% OTM;
- absolute delta 0.10–0.45;
- relative bid/ask spread at most 15%;
- prior-session OI at least 100;
- structurally valid quote no older than 20 minutes.

Its disclosed within-profile order is spread ascending, OI descending, contract
ID ascending. The packet exposes implied volatility, OI, spread, optional source
volume, every named
filter's pass/fail result for projected contracts, and aggregate pass counts.
Bid/ask size remains explicitly unavailable, and missing volume remains explicitly
unavailable. No IV, realized-volatility, or volume rank is created.

## Session and quote rules

- Session dates use the repo's NYSE holiday calendar.
- Session windows reuse the tested `engine.session_digest` early-close law:
  Friday after Thanksgiving, July 3 when it is a session, and December 24.
- Cadence is exactly 15 minutes.
- Buckets are aligned to `:00/:15/:30/:45`, and the causal order is
  `bucket_at <= builder_observed_at <= available_at` within that same NYSE
  session and its bounded close grace.
- Collector-naive Theta timestamps are interpreted as America/New_York, then
  published in UTC with exactly six fractional digits. Source, observed, and
  available clocks preserve exact microseconds in receipts, digests, and packet
  identity; sub-microsecond input fails closed rather than being truncated.
- Browser eligibility requires positive, non-crossed bid/ask; a quote already
  observed by the builder and no older than 20 minutes at the packet's first
  usable `available_at`; and a stamp inside the session window plus the same
  20-minute closing grace. The exact 20-minute boundary passes; any positive
  microsecond beyond it abstains.
- The OI vendor stamp must be on the availability session and no later than the
  NYSE open, builder observation, or availability clock. Its position vintage is
  derived as the immediate prior real NYSE session, skipping weekends and exchange
  holidays. An optional source vintage must equal that derivation; same-session,
  future, and holiday vintages fail closed. OI is never represented as live
  intraday OI.
- Already-expired OI tuples remain bound into the raw projection digest and row
  count, but are excluded from usable lookup and reported separately. Their stale
  session date cannot contaminate a live contract; the same date on a nonexpired
  tuple fails the whole root. Expiry waives only exact availability-session date,
  never the time-of-day or absolute-causality bounds: every raw OI stamp, including
  an expired tuple, must be no later than the NYSE open and the builder
  observation/availability clocks.
- Root/right/expiry/strike identity is required in both source frames and must be
  canonical. Contract IDs hash the unrounded canonical decimal strike, while OCC
  symbology remains null for a non-millistrike.
- OI and volume retain exact nonnegative integer/string evidence above `2^53`.
  Nullable-Parquet integral floats below `2^53` are accepted; float `2^53`
  itself fails closed because it is indistinguishable from a rounded `2^53 + 1`.
- OCC symbology is present only when the root and millistrike can be constructed
  exactly; otherwise it is `null` while the source contract tuple remains intact.

## Build and publish

Local dry build (no R2 mutation):

```bash
python3 -m scripts.build_options_structure_intraday \
  --data-root /absolute/path/to/data/chain_snapshots \
  --session YYYY-MM-DD \
  --bucket HH:MM
```

Optional Prophet plan context is a strict JSON object keyed by root. Each value
must contain `direction`, `clock_date`, `horizon_days`, and `entry`.

R2 publication requires the standard `R2_ENDPOINT`, `R2_ACCESS_KEY_ID`,
`R2_SECRET_ACCESS_KEY`, and `R2_BUCKET` environment variables plus `--publish`.
No credentials are written to artifacts or logs.

The poller invokes the same CLI with `--completion-packet-stdin`; that mode
rejects `--session`, `--bucket`, `--roots`, `--meta`, and `--observed-at`
overrides so a caller cannot launder receipt identity. The receipt's
`decision_at` becomes `builder_observed_at`; its later `availability_at` remains
the packet availability clock.

Publication order is load-bearing:

1. Build and strict-JSON validate every root locally.
2. Create/re-prove every immutable dated object byte-for-byte.
3. Compare-and-swap the complete global `index.json` manifest. This is the only
   authoritative discovery commit.
4. Repair derivative per-root current pointers after that commit.
5. Commit the monotonic local mirror.
6. Only after steps 1–5 succeed, write a deterministic local-only publication
   acknowledgement under
   `options_structure/msc_intraday/_publication_receipts/{SESSION}/{HHMM}.json`
   plus an immutable sibling `{HHMM}.index.json` containing the exact committed
   index bytes.

The index and currents share one strict monotonic epoch law: an older target is
rejected or safely superseded, identical bytes at the same epoch are idempotent,
different bytes at the same epoch are a collision, and only a newer epoch may
advance by compare-and-swap. A concurrent newer object is always preserved.

An immutable collision is fatal. The publisher never calls conditional delete
and never attempts rollback, because Cloudflare R2 does not guarantee conditional
`DeleteObject`. An index write or verification error is reported as
commit-uncertain: the attempted index is left untouched, no current pointers are
advanced, and an exact retry proves idempotency or exposes the winner. Once the
index commits, a pointer error is reported as committed-but-repair-needed; retry
repairs missing/older pointers, while an independently newer pointer counts as
safely superseded. Undiscoverable immutable packet orphans are harmless because
only a validated index directly confers complete-bucket discovery.

The local mirror uses the same monotonic epoch/collision law under an exclusive
file lock. Every new directory entry is parent-fsynced; each artifact uses temp
write, flush, file fsync, atomic replace, then parent-directory fsync. Any failed
durability fence is an honest uncertain failure. An exact idempotent retry
re-fsyncs the existing file and parent before accepting it, so a post-rename
uncertainty is repairable without rewriting evidence. With `--publish`, R2
commits before the local mirror advances, so an older delayed build cannot
regress local discovery after R2 rejects it.

The acknowledgement binds the exact completion-packet hash and receipt IDs,
completion result hash, index key/hash, and every immutable object key/hash/byte
count/packet ID. Replay re-hashes the immutable local objects and saved index,
revalidates the index ID/object receipts, and requires canonical ack bytes. It is
derivative delivery state, not a new R2 key, source store, signal
contract, or authority surface. It uses the same temp-write, file-fsync, atomic
replace, and parent-directory-fsync law. Missing acknowledgement always means
retry; exact bytes are re-fsynced and accepted idempotently, while malformed or
different bytes fail closed.

Two canonical, local-only cursors live beside the acknowledgements. The
activation-bound `cursor.json` identifies one exact delivered packet, hashes its
durable ack bytes, and binds the complete-packet prefix for that session. It may
advance by exactly one packet; a new session resets the session prefix to one.
The `scan_cursor.json` bounds source-ledger work without claiming delivery. It
may advance only across the immediate next source ledger after re-proving the
sealed ledger SHA-256, terminal state, complete count/prefix, and last ack hash
(or exact zero-complete state). A cumulative ack-prefix hash re-proves every
acknowledgement in the bounded sealed session, so a missing/corrupt non-tail ack
cannot be hidden by a valid tail. Exact replay is idempotent. A cursor missing
before its first durable write is normal crash state; a missing scan cursor is
recovered from the activation-bound delivery cursor. Torn, noncanonical,
hash-drifted, skipped-ledger, or activation-drifted cursor state suppresses
projection and is surfaced for repair. Historical cursor loss after a newer
index/cursor advanced remains the clone-loss STOP below. None creates an R2 key
or source/model authority.

The entire local projection mirror, including every ack/index sibling plus
`_publication_receipts/cursor.json` and `scan_cursor.json`, must be
clone-swap preserved while the poller is stopped with an exact path-size-SHA
manifest. It is explicitly gitignored and is never a public artifact. Missing
ack bytes before commit are normal retry state. Missing/corrupt historical ack
bytes after a newer index advances are an operator-reconciliation STOP, not
permission to regress the index: compare the immutable saved index receipt,
local packets, and remote R2 objects/current index before restoring exact backup
bytes or applying a separately reviewed repair.

## Focused verification

```bash
python3 -m pytest -q \
  tests/test_options_structure_intraday.py \
  tests/test_build_options_structure_intraday.py
```

The focused suite covers schema and strict JSON, deterministic replay, Prophet
primary parity and equal-delta first-row ties against the real resolver, explicit
deterministic fallback, resolve-then-abstain behavior, profile separation, filter
receipts, long-dated convex eligibility, stale/zero/crossed quotes, exact large
integers, sub-millistrike identity, OI vintage/holiday causality, aligned buckets,
early closes, malformed/torn/duplicate source failure, immutable collisions,
hash/size verification, fake-R2 ordering, coherent single-GET version reads,
idempotency, newer-then-older regression rejection, same-epoch drift collisions,
index failure before current writes, post-write commit uncertainty without
rollback or deletion, partial pointer repair, concurrent newer-pointer
preservation, six-digit microsecond identity without truncation, and local-mirror
monotonicity/crash durability including post-rename retry recovery.

## Production completion hook

`scripts/chain_snapshot_poller.py` now owns one optional/config-gated synchronous
call to this existing builder. It runs under the producer writer lock, only after
durable availability, and passes the exact completion packet over stdin. There is
no second scheduler, raw store, producer, root resolver, or clock. A completed
same-bucket retry invokes the same immutable/CAS publisher idempotently. If the
startup receipt drain turns a decision-only tail into availability after RTH,
the poller reacquires the producer lock after config validation and publishes
that exact recovered packet before exiting; it never strands a completed close
bucket merely because source admission has ended.

Crash and transient-failure recovery uses no second workflow. Under the existing
producer lock, an exact immutable `activation_session` excludes all older
receipts, and each pass decodes only the sealed checkpoint ledger, current scan
session, immediate next ledger, and at most one distinct delivery-cursor ledger
(four ledger decodes/pass worst case, independent of retained history). It skips
exact acknowledged deliveries, attempts at most one missing acknowledgement,
and advances one source-hash-bound terminal/no-complete session at a time. The
publisher cursor binds activation forever; changing it after first delivery is
a STOP, not a backfill control. A cursor/ack error suppresses projection but
does not recast, rank, or reject source truth. The work is synchronous under the
writer lock, so it may delay the next source start by bounded scan/reproof time
and at most the configured publisher timeout; M1 rollout must gate total lock
hold rather than call the retry non-gating. An older unacknowledged projection
still suppresses newer projection attempts until ordered catch-up clears it;
the global index is never asked to regress. At normal or early close, backlog
causes a nonzero exit so the existing launchd `KeepAlive.SuccessfulExit=false`
policy retries it. Replay rebuilds the exact bundle, revalidates the source
receipt, and re-proves the R2/local object bytes before acknowledging.

Code defaults the hook off when the config block is absent. Canonical production
config deliberately keeps `chain_snapshots.options_structure_r2.enabled: false`
and `activation_session: null` until target-host dependencies and credentials,
a real full-universe M1 runtime/RSS baseline, a safe multi-run latency series,
and an accumulated-ledger writer-lock timing gate are recorded. Promotion sets
one exact current/future NYSE activation session before first enabled launch and
never changes it while the cursor tree exists. When
promoted, the hard `timeout_sec <= 120` terminates the subprocess at that ceiling;
exceptions, nonzero exits, missing credentials, and timeouts are logged into the
poller observability path but cannot roll back availability or change a successful
source receipt. Partial sweeps and incomplete elapsed buckets never invoke it;
post-close publication requires the exact recovered availability packet above.

Focused tests prove exact receipt transport, default-off zero calls, partial-root
abstention, source-evidence drift rejection, override refusal, timeout
containment, normal/early-close decision-tail recovery, transient retry,
crash-after-availability catch-up, acknowledgement idempotency, monotonic R2
reuse, activation drift refusal, ack-written/cursor-not-advanced recovery,
terminal-empty session progress, bounded two-ledger decoding, cursor
corruption/missing-ledger containment, and all-false authority. Each successful builder run logs `source_bytes`,
`wall_sec`, and `peak_rss_bytes`; the first real full-universe M1 run is one
baseline sample, not p95. Only a subsequent multi-run series may establish p95.
If observed p95
reaches the 120-second ceiling, keep publication non-authoritative and add a
producer-owned per-bucket row-group/light sidecar rather than an independently
scheduled reader that races the poller.

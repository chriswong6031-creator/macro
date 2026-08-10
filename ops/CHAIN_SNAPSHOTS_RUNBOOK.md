# U-CHAIN Chain-Snapshot Poller — Runbook

## Architecture overview

The chain-snapshot poller (`scripts/chain_snapshot_poller.py`) runs on the Mac
during the real NYSE session (actual NYSE open + 5 minutes through the 16:00 ET close bucket on a
regular session; through the 13:00 close bucket on an early-close session).
The close bucket has a sub-minute source-start grace and no later source is admitted.
An already-admitted close sweep may durably finish through close + 20 minutes.
NYSE holidays and weekends are inert. Every `cadence_min` minutes (default
15) it sweeps the active options universe (22 ETF anchors + top `top_names`
gex names, ~150 roots) and pulls a full-chain greeks snapshot per root via the
ThetaData v3 snapshot API — first_order (delta/theta/vega/rho/IV) joined with
second_order (gamma/vanna/charm/vomma/veta) only on exact
`(root, expiration, strike, right, snapshot_ts)`. A per-contract second-order
clock mismatch leaves those second-order values null/unavailable; every
non-null second Greek therefore shares the retained first-order `snapshot_ts`.
This is the Interval Map / Volatility Drift data plane
(`research/OPTIONS_CONFLUENCE_PROGRAM_BY_FABLE.md` §5 U-CHAIN, WP-UCHAIN).

## Files written

| Path (under `data/chain_snapshots/`, gitignored) | Contents |
|---|---|
| `{ROOT}/{YYYY-MM-DD}.parquet` | greeks rows; dedup key = (root, expiration, strike, right, snapshot_bucket) |
| `{ROOT}/{YYYY-MM-DD}_oi.parquet` | one OI snapshot per root per day (first sweep only — OI timing law: the ~06:30 ET stamp holds EOD t-1 positions and never moves intraday) |
| `_bucket_receipts/{YYYY-MM-DD}.jsonl` | authoritative, append-only producer receipt state for each live bucket (`chain_snapshots.bucket_completion/v1`) |
| `_bucket_receipts/.writer.lock` | sole-producer advisory lock; held across receipt reconciliation, the full source sweep, completion, availability, and any injected future hook |
| `_meta.json` | non-authoritative per-cycle observability (sweep count, rows, latency, errors, quarantined, receipt/hook status) |
| `{ROOT}/{date}.corrupt-{ts}.parquet` | quarantine: an existing day frame that failed to read is renamed aside (bytes preserved), never overwritten — check `_meta.json` `quarantined` and recover/inspect manually |

Forward volume ≈ 0.4–1 GB/day (program doc §5) — watch disk alongside the
tape-lane hot window.

### Preserve producer state across checkout refreshes

`data/chain_snapshots/` is one gitignored producer-authority set. Preserve the
whole directory together: chain and OI Parquet, receipt ledgers, quarantines,
`_meta.json`, and `.writer.lock` where present. Before a deploy-worktree refresh
or checkout swap, unload launchd and verify that the producer is stopped. Build
an exact manifest outside that directory containing each regular file's
relative-path, byte-size, and SHA-256; copy/restore the whole directory while it
is stopped; generate the same manifest at the destination; and require a
byte-for-byte manifest match before loading launchd. A pathname, size, hash, or
missing/extra-file difference is a rollout blocker—do not select a partial
subset or reconstruct receipt authority from Parquet or `_meta.json`.

Never copy or restore this state after the producer starts. Copying a live
directory can combine ledger and Parquet moments that never coexisted under the
writer lock. Only after the pre/post manifest matches may the launchd install
sequence below start the producer in the refreshed checkout.

## Producer completion contract (W0a-B)

The JSONL ledger—not `_meta.json`—is the only producer proof that a bucket is
complete. Records are canonical strict JSON (`allow_nan=false`, deterministic
IDs, UTC clocks with six microsecond digits) and every line is newline
terminated. The governed record schema is
`contracts/options/chain_snapshots.bucket_completion.v1.schema.json`, with the
stable ID `chain_snapshots.bucket_completion/v1`.
Fields annotated `x-exact-json-integer` are governed jointly by the schema and
the runtime exact-type validator because Draft 2020-12 numeric equality alone
treats `15.0` like an integer. Physical/runtime validation rejects floats and
booleans for those fields.

For each `(session_date, bucket)`, the only legal physical paths are:

```text
intent -> decision -> availability      # complete
intent -> incomplete                    # terminal, not complete
intent -> decision -> incomplete        # source succeeded, availability not captured
```

The durability order is load-bearing:

1. Resolve and canonicalize the exact producer roots (uppercase, unique,
   producer order), cadence, real NYSE session, and wall-clock-derived bucket.
2. Append the deterministic `intent`, file-`fsync` it, and—when the ledger is
   first linked—`fsync` its parent directory. Every visible ledger/file prefix
   and parent are reconfirmed on recovery. No ThetaData call, root directory,
   or parquet write may precede that durable intent.
3. For every touched chain/OI parquet: write a unique temporary file, `fsync`
   its exact bytes, atomically replace the target, `fsync` the parent directory,
   read the installed parquet back, compare exact installed semantics and bytes,
   then reconfirm the installed file and parent directory. Chain/OI source shape,
   exact canonical root, and `source=chain_snapshot` are checked across the full
   installed day frame before decision. A quarantine rename is likewise
   parent-`fsync`ed; every matching preserved quarantine is rescanned and bound
   into eventual completion after a retry.
4. Only a 100% successful frozen-root sweep may build the full deterministic
   completion summary: exact frozen roots, root/universe counts, positive target-
   bucket row count and canonical content hash, installed chain/OI file hashes,
   chain/OI counts, first-order vendor min/max clocks, prebucket/at-or-after
   counts, exact second-clock matched/unmatched counts, all quarantine names,
   per-root results, and the canonical result SHA-256. These are aggregate
   producer proofs; future W0a core packets remain responsible for row semantics.
5. Capture `decision_at` only after step 4, append the decision bound to the
   exact intent receipt and SHA-256, then file-`fsync` it.
6. Reconfirm that decision prefix, capture `availability_at` only afterward,
   append the availability bound to both prior receipts, and file-`fsync` it.
   Only this terminal is complete.
7. A future completion hook may be injected in-process for later Light U-CHAIN
   work. It is disabled/default-off today (no import, config, R2 path, credential,
   or publication). If injected later, it runs synchronously under the same
   writer lock only after durable availability. Its error is loud and appears in
   `_meta.json`, but cannot roll back or recast a successful source sweep. A
   completed-bucket retry may invoke it again for idempotent repair.

The intent freezes the exact roots, cadence, and whether target-bucket rows
already existed before intent. A fresh intent that finds such orphan rows is
durably terminal-ineligible and performs no source call; it can never bless or
quarantine those bytes. A normal retry while the wall clock
still derives to that same session/bucket reuses the first durable intent and
its clock even if config or universe membership changed. A decision-only crash
reconfirms the ledger prefix and appends only an honest current availability
through the same NYSE session's close + 20 minute recovery window. This does
not authorize any source retry, and downstream freshness may abstain. A visible
availability whose `fsync`
returned uncertain is never duplicated: restart reconfirms the existing file
and directory and skips every source write.

Never backfill an elapsed intraday bucket with a later live snapshot. When an
intent-only tail is found after its source window elapsed, append a terminal
`incomplete` receipt with `reason=bucket_window_elapsed`; a decision tail
terminalizes only after its same-session availability recovery window. After
the session use `reason=session_elapsed`. Then, and only then, the current live
bucket may begin. A completed or incomplete bucket is immutable. Startup drains
durable decisions and elapsed tails under the receipt lock before reading
mutable chain config or applying the RTH source gate; this drain never resolves
the universe or contacts ThetaData.

The parser fails closed on a torn/non-terminated line, blank or malformed JSON,
duplicate object keys, NaN/Infinity, wrong record shape/schema/ID/hash, duplicate
bucket or receipt kind, physical reordering/interleaving, non-canonical root or
clock, clock reversal, session/date mismatch, holiday, early-close violation, or
completion/root-result drift. Preserve the bytes for diagnosis; never truncate,
rewrite, synthesize clocks, or use `_meta.json` to reconstruct authority.

## Concurrency budget (HARD)

`chain_snapshots.max_concurrent: 1` in `config.yml`; the exact integer `1` is
required (no coercion). The live_flow poller
owns 2 of the terminal's 8 concurrent request slots during RTH and the T1
backfill shares the rest.  NEVER raise without explicit Fable adjudication.
A full ~150-root sweep ≈ 300 snapshot requests ≈ ~5 min wall at concurrency 1
— comfortably inside the 15-min cadence.

## launchd install

The job follows the deploy-worktree doctrine (see `ops/LIVE_FLOW_RUNBOOK.md`):
launchd runs from the installed shared M1 ops worktree
`/Users/chriswong/flow-ops-wt`, never from the main checkout. The actual M1
lane/data/log state remains a supervised rollout gate; do not infer it from
repository tests or perform a manual/historical live sweep as verification.

```bash
launchctl unload ~/Library/LaunchAgents/com.mastermind.chainsnapshots.plist 2>/dev/null || true
cp /Users/chriswong/flow-ops-wt/ops/launchd/com.mastermind.chainsnapshots.plist ~/Library/LaunchAgents/
plutil -lint ~/Library/LaunchAgents/com.mastermind.chainsnapshots.plist
launchctl load ~/Library/LaunchAgents/com.mastermind.chainsnapshots.plist
launchctl print gui/$(id -u)/com.mastermind.chainsnapshots
```

The plist fires weekdays at 06:30 PT (= 09:30 ET); the poller waits for the
actual-open + 5 minute window start and self-exits after the actual regular or early close
(`--rth-only`). A holiday/outside-RTH launch creates no new intent/source and
never contacts ThetaData. If an existing durable decision or elapsed tail is
present, the receipt-only startup drain may first append its truthful
availability/incomplete terminal.
`KeepAlive.SuccessfulExit=false` plus `ThrottleInterval=60` restarts crash/nonzero
exits so durable intent/decision recovery can occur in-session; a clean exit 0
stays down until the next calendar fire.
ThetaTerminalApp must be running on port 25503 before the fire (Login Items
recommended).  No R2 creds are required — this lane writes local parquet only.

## Safe verification (no historical/manual live collection)

```bash
# Import/CLI smoke only: no fetch, receipt, or publication.
python -m scripts.chain_snapshot_poller --help

# Hermetic producer receipt, kill-point, schema, calendar, and parquet tests.
python -m pytest tests/test_chain_snapshot_poller.py -q
```

`--once` is a mutating **current-live-bucket** operation, not a smoke or replay
tool. Outside a real current NYSE bucket it creates no new intent/source and
exits before universe resolution or a ThetaData probe; existing durable receipt
tails may still reconcile as described above. Do not invoke it for historical,
weekend, holiday, post-close, or market-closed verification. W0a-B intentionally
adds no historical replay and no Light U-CHAIN R2 publisher.

When diagnosing state, copy the ledger before reading it and validate the copy;
do not edit the live file. A terminal `incomplete` is evidence, not a queue to
rewrite. A future collection begins only under the producer lock in the then-
current live bucket.

## Log tailing

```bash
tail -f /tmp/chainsnapshots.stdout.log /tmp/chainsnapshots.stderr.log
```

## Uninstall

```bash
launchctl unload ~/Library/LaunchAgents/com.mastermind.chainsnapshots.plist
rm ~/Library/LaunchAgents/com.mastermind.chainsnapshots.plist
```

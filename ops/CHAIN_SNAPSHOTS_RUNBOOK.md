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
| `_bucket_receipts/.writer.lock` | sole-producer advisory lock; held across receipt reconciliation, the full source sweep, completion, availability, and the configured Light U-CHAIN hook |
| `_meta.json` | non-authoritative per-cycle observability (sweep count, rows, latency, errors, quarantined, receipt/hook status) |
| `{ROOT}/{date}.corrupt-{ts}.parquet` | quarantine: an existing day frame that failed to read is renamed aside (bytes preserved), never overwritten — check `_meta.json` `quarantined` and recover/inspect manually |

Forward volume ≈ 0.4–1 GB/day (program doc §5) — watch disk alongside the
tape-lane hot window.

The derivative Light U-CHAIN mirror, when enabled, writes local-only delivery
acknowledgements at
`data/options_structure_intraday_r2/options_structure/msc_intraday/_publication_receipts/{SESSION}/{HHMM}.json`.
Each has a sibling `{HHMM}.index.json` preserving the exact committed global
index bytes after the mutable pointer advances. Together they prove a verified
R2 commit plus successful local-mirror commit; they are not
source receipts and confer no signal, selector, or trade authority.
The same private directory also contains `cursor.json`, the activation-bound
contiguous delivery cursor, and `scan_cursor.json`, a bounded forward-ledger
checkpoint. `cursor.json` binds its exact acknowledgement bytes and advances
one bucket at a time, resetting its prefix to one only at a new session.
`scan_cursor.json` may cross a terminal session only when it binds that exact
source ledger SHA-256, terminal complete count/prefix, and last delivered ack
(or an explicit zero-complete proof). Its cumulative ack-prefix hash requires
every acknowledgement in that sealed session, not only the tail, to remain
present and canonical. Both use canonical bytes and the same
temp-write/file-fsync/atomic-replace/parent-fsync law as acknowledgements.

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

On the M1, the physical authority remains at
`/Users/chriswong/flow-ops-wt/data/chain_snapshots`, while the producer code
runs from the dedicated shallow clone
`/Users/chriswong/chainsnap-ops-wt`. The deploy clone's
`data/chain_snapshots` must be an exact symlink to that physical directory.
This isolates governed code from the mixed-vintage `flow-ops-wt` without moving
or duplicating authority bytes. Validate manifests through both paths while the
producer is stopped and require byte equality before launchd is loaded. Never
refresh or reset the dirty shared `flow-ops-wt` as part of this lane's rollout.

Never copy or restore this state after the producer starts. Copying a live
directory can combine ledger and Parquet moments that never coexisted under the
writer lock. Only after the pre/post manifest matches may the launchd install
sequence below start the producer in the refreshed checkout.

When the projection is enabled, preserve
`data/options_structure_intraday_r2/` in the same stopped clone-swap window and
give it its own exact pre/post path-size-SHA manifest. The directory is
gitignored and must never be copied into `site/` or another public tree. Losing
an acknowledgement or either cursor before it is written is safely retryable.
The manifest must preserve all ack/index siblings plus `cursor.json` and
`scan_cursor.json`; never reconstruct either cursor from `_meta.json`. Losing or
corrupting an older acknowledgement after a newer global index has advanced is
an operator-reconciliation STOP: do not delete/rewrite it or regress the index.
Verify the saved immutable index receipt, local immutable packets, and remote R2
objects/current index, then restore exact backup bytes or perform a separately
reviewed repair.

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
7. The config-gated Light U-CHAIN hook runs synchronously under the same writer
   lock only after durable availability. It transports the exact three-record
   completion packet over stdin to the existing
   `scripts.build_options_structure_intraday` CLI, which publishes the governed
   `options.contract_eligibility/v1` R2 family. Before any R2 mutation, the
   builder compares each exact target-bucket row count/content digest and stable
   OI row count/file digest to the producer decision receipt. After verified R2
   and local-mirror success it writes the deterministic local delivery
   acknowledgement and immutable index receipt above. A 120-second subprocess
   ceiling, exception, missing
   credential, or nonzero exit is loud in `_meta.json` but cannot roll back or
   recast a successful source sweep. The direct hook explicitly abstains from
   every completion packet dated before `activation_session`.
8. Missing delivery acknowledgements remain retryable. Enabling requires an
   exact immutable `activation_session`; receipts before it are explicitly out
   of scope, and any later config drift from the activation bound into
   `cursor.json` fails closed. Under the same writer lock, each catch-up pass
   decodes only the sealed checkpoint ledger, the scan-floor session and its
   immediate next ledger, plus at most one distinct delivery-cursor ledger
   (four ledger decodes/pass worst case, independent of retained history),
   attempts at most one
   missing acknowledgement, and advances across a terminal/no-complete session
   by one source-hash-bound scan checkpoint. This covers crash after
   availability, ack-written/cursor-not-advanced restart, transient R2 failure,
   empty sessions, and normal/early-close recovery without another scheduler or
   raw store. A derivative cursor error suppresses projection and is surfaced;
   it never recasts source truth. Catch-up is synchronous and can delay source
   start by its bounded scan and publisher timeout, so rollout must gate total
   writer-lock hold on M1. Older unacknowledged projection suppresses newer
   projection until ordered catch-up clears it. At clean close, remaining
   backlog returns nonzero so launchd retries.

Code defaults off when the config block is absent. Canonical config remains
`enabled: false` with `activation_session: null` until the actual M1
full-universe dependency/credential check, one real-volume runtime/RSS baseline,
a safe multi-run latency series, and accumulated-ledger writer-lock timing pass.
Promotion must set one exact current/future NYSE activation session before the
first enabled launch; that value is immutable for the lifetime of the cursor
tree.

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

The job follows the deploy-tree doctrine (see `ops/LIVE_FLOW_RUNBOOK.md`):
launchd runs from the dedicated standalone shallow clone
`/Users/chriswong/chainsnap-ops-wt`, never from the shared dirty
`flow-ops-wt`, the live-flow tree, or an agent checkout. Its only connection to
the old tree is the exact physical-authority symlink described above. The actual
M1 lane/data/log state remains a supervised rollout gate; do not infer it from
repository tests or perform a manual/historical live sweep as verification.

Build or replace the deploy clone only outside the NYSE session and close + 20
minute recovery window, after both launchd and `pgrep` prove the producer is
stopped. Use the repo-scoped deploy key and pin the checkout to the reviewed
merge. Before loading launchd, build a relative-path/byte-size/SHA-256 manifest
from the physical state and a second manifest through the symlink; they must be
byte-identical. The symlink itself must resolve to the exact physical path.

The M1 rollout sequence is:

```bash
rollout() (
set -euo pipefail
LABEL=com.mastermind.chainsnapshots
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
DOMAIN="gui/$(id -u)"
DEPLOY="$HOME/chainsnap-ops-wt"
STATE="$HOME/flow-ops-wt/data/chain_snapshots"
PY="$HOME/miniconda3/envs/plane/bin/python"
EXPECTED_MERGE="${EXPECTED_MERGE:?set the reviewed merged SHA}"

# STOP during RTH and close recovery. Never kill a live producer to deploy.
HHMM=$(date +%H%M)
DOW=$(date +%u)
if [ "$DOW" -le 5 ] && [ "$HHMM" -ge 0600 ] && [ "$HHMM" -lt 1325 ]; then
  echo "STOP: RTH/close-recovery window" >&2
  exit 1
fi
! pgrep -f 'scripts[.]chain_snapshot_poller' >/dev/null
test -d "$STATE"
test ! -L "$STATE"                  # physical authority, never a redirect
test -f "$PLIST"

STAMP=$(date -u +%Y%m%dT%H%M%SZ)
NEW="$DEPLOY.new-$STAMP"
ROLLBACK="$DEPLOY.rollback-$STAMP"
FAILED="$DEPLOY.failed-$STAMP"
PLIST_BACKUP="$PLIST.rollback-$STAMP"
MANIFEST_DIR="$HOME/chainsnap-state-manifests"
mkdir -p "$MANIFEST_DIR"
for path in "$NEW" "$ROLLBACK" "$FAILED"; do
  test ! -e "$path"
  test ! -L "$path"
done
test ! -L "$DEPLOY"

HAD_DEPLOY=0
if [ -e "$DEPLOY" ]; then
  test -d "$DEPLOY/.git"
  HAD_DEPLOY=1
fi
WAS_LOADED=0
if launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then
  WAS_LOADED=1
fi
cp -p "$PLIST" "$PLIST_BACKUP"       # backup BEFORE unregistering

ROLLOUT_COMMITTED=0
restore_on_error() {
  rc=$?
  trap - EXIT INT TERM HUP
  set +e
  set +u
  if [ "$rc" -ne 0 ] && [ "$ROLLOUT_COMMITTED" -eq 0 ]; then
    ROLLBACK_STOPPED=0
    if launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then
      if ! launchctl bootout "$DOMAIN/$LABEL" >/dev/null 2>&1; then
        echo "ROLLBACK ERROR: new scheduler could not be unregistered" >&2
      fi
    fi
    if ! launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1 && \
       ! pgrep -f 'scripts[.]chain_snapshot_poller' >/dev/null; then
      ROLLBACK_STOPPED=1
    else
      echo "HARD MANUAL STOP: scheduler/PID still active; deploy paths will not be moved" >&2
    fi

    PLIST_RESTORED=0
    if cp -p "$PLIST_BACKUP" "$PLIST"; then
      PLIST_RESTORED=1
    else
      echo "ROLLBACK ERROR: prior plist could not be restored" >&2
    fi

    PRIOR_DEPLOY_READY=0
    if [ "$ROLLBACK_STOPPED" -eq 1 ]; then
      # Infer the interrupted swap phase from the paths themselves. This covers
      # a signal between either atomic mv and the following shell assignment.
      if [ "$HAD_DEPLOY" -eq 1 ] && \
         { [ -e "$ROLLBACK" ] || [ -L "$ROLLBACK" ]; }; then
        if [ -e "$DEPLOY" ] || [ -L "$DEPLOY" ]; then
          if ! mv "$DEPLOY" "$FAILED"; then
            echo "ROLLBACK ERROR: failed new deploy could not be preserved" >&2
          fi
        fi
        if ! { [ -e "$DEPLOY" ] || [ -L "$DEPLOY" ]; }; then
          if ! mv "$ROLLBACK" "$DEPLOY"; then
            echo "ROLLBACK ERROR: prior deploy could not be restored" >&2
          fi
        fi
      elif [ "$HAD_DEPLOY" -eq 0 ] && \
           { [ -e "$DEPLOY" ] || [ -L "$DEPLOY" ]; } && \
           ! { [ -e "$NEW" ] || [ -L "$NEW" ]; }; then
        if ! mv "$DEPLOY" "$FAILED"; then
          echo "ROLLBACK ERROR: failed first deploy could not be preserved" >&2
        fi
      fi

      if [ "$HAD_DEPLOY" -eq 1 ]; then
        if [ -d "$DEPLOY/.git" ] && [ ! -L "$DEPLOY" ] && \
           ! { [ -e "$ROLLBACK" ] || [ -L "$ROLLBACK" ]; }; then
          PRIOR_DEPLOY_READY=1
        fi
      elif ! { [ -e "$DEPLOY" ] || [ -L "$DEPLOY" ]; }; then
        PRIOR_DEPLOY_READY=1
      fi
    fi

    if [ "$WAS_LOADED" -eq 1 ] && [ "$ROLLBACK_STOPPED" -eq 1 ] && \
       [ "$PLIST_RESTORED" -eq 1 ] && [ "$PRIOR_DEPLOY_READY" -eq 1 ]; then
      if ! launchctl bootstrap "$DOMAIN" "$PLIST"; then
        echo "ROLLBACK ERROR: previous scheduler could not be reloaded" >&2
      fi
    fi
    if [ "$ROLLBACK_STOPPED" -eq 1 ]; then
      echo "rollout failed; prior plist/deploy restored, failed clone preserved" >&2
    fi
  fi
  exit "$rc"
}
trap restore_on_error EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

if [ "$WAS_LOADED" -eq 1 ]; then
  launchctl bootout "$DOMAIN/$LABEL"
fi
! launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1
! pgrep -f 'scripts[.]chain_snapshot_poller' >/dev/null

manifest() {
  ROOT="$1" OUT="$2" "$PY" - <<'PY'
import hashlib
import os
import stat
from pathlib import Path

root = Path(os.environ["ROOT"]).resolve(strict=True)
rows = []
for path in sorted(root.rglob("*")):
    metadata = path.lstat()
    if not stat.S_ISREG(metadata.st_mode):
        continue
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    rows.append(
        f"{path.relative_to(root).as_posix()}\t{metadata.st_size}\t"
        f"{digest.hexdigest()}\n"
    )
Path(os.environ["OUT"]).write_text("".join(rows))
PY
}
BEFORE_MANIFEST="$MANIFEST_DIR/$STAMP.before.tsv"
VIA_DEPLOY_MANIFEST="$MANIFEST_DIR/$STAMP.via-deploy.tsv"
manifest "$STATE" "$BEFORE_MANIFEST"

git clone --depth 1 --single-branch --branch main \
  --config "core.sshCommand=ssh -i $HOME/.ssh/macro_dashboard_deploy -o IdentitiesOnly=yes" \
  git@github.com:mastermindx-market-intelligence/macro.git "$NEW"

# Prove the reviewed merge is actually on current remote main. Main may move
# between fetch and ls-remote, so retry the read a bounded three times.
for _ in 1 2 3; do
  git -C "$NEW" fetch --depth 512 origin main
  LOCAL_MAIN=$(git -C "$NEW" rev-parse origin/main)
  REMOTE_MAIN=$(git -C "$NEW" ls-remote origin refs/heads/main | awk '{print $1}')
  [ -n "$REMOTE_MAIN" ] && [ "$LOCAL_MAIN" = "$REMOTE_MAIN" ] && break
done
test "$LOCAL_MAIN" = "$REMOTE_MAIN"
git -C "$NEW" cat-file -e "$EXPECTED_MERGE^{commit}"
git -C "$NEW" merge-base --is-ancestor "$EXPECTED_MERGE" origin/main
git -C "$NEW" checkout --detach "$EXPECTED_MERGE"
test -z "$(git -C "$NEW" status --porcelain)"

install -m 600 "$HOME/flow-ops-wt/.env" "$NEW/.env"
test ! -e "$NEW/data/chain_snapshots"
ln -s "$STATE" "$NEW/data/chain_snapshots"
test "$(readlink "$NEW/data/chain_snapshots")" = "$STATE"

manifest "$NEW/data/chain_snapshots" "$VIA_DEPLOY_MANIFEST"
cmp "$BEFORE_MANIFEST" "$VIA_DEPLOY_MANIFEST"
test -z "$(git -C "$NEW" status --porcelain)"
PYTHONPATH="$NEW" "$PY" -m scripts.chain_snapshot_poller --help >/dev/null
(
  cd "$NEW"
  PYTHONPATH="$NEW" "$PY" -m pytest tests/test_chain_snapshot_poller.py -q
)
plutil -lint "$NEW/ops/launchd/$LABEL.plist"

if [ "$HAD_DEPLOY" -eq 1 ]; then
  mv "$DEPLOY" "$ROLLBACK"
fi
mv "$NEW" "$DEPLOY"
install -m 644 "$DEPLOY/ops/launchd/$LABEL.plist" "$PLIST"
cmp "$DEPLOY/ops/launchd/$LABEL.plist" "$PLIST"
plutil -lint "$PLIST"
launchctl bootstrap "$DOMAIN" "$PLIST"
launchctl print "$DOMAIN/$LABEL" | grep -F "$DEPLOY"

# KeepAlive.SuccessfulExit=false may cause one inert outside-RTH launch. First
# require a stopped/clean status, then prove the run count stays fixed for more
# than the 60-second crash throttle. A restart loop rolls the transaction back.
for _ in $(seq 1 24); do
  ROW=$(launchctl list | awk -v label="$LABEL" '$3 == label {print $1 " " $2}')
  if [ "$ROW" = "- 0" ] && ! pgrep -f 'scripts[.]chain_snapshot_poller' >/dev/null; then
    break
  fi
  sleep 5
done
test "$ROW" = "- 0"
RUNS=$(launchctl print "$DOMAIN/$LABEL" | awk '/^[[:space:]]*runs =/ {print $3; exit}')
test -n "$RUNS"
for _ in $(seq 1 13); do
  sleep 5
  test "$(launchctl list | awk -v label="$LABEL" '$3 == label {print $1 " " $2}')" = "- 0"
  test "$(launchctl print "$DOMAIN/$LABEL" | awk '/^[[:space:]]*runs =/ {print $3; exit}')" = "$RUNS"
  ! pgrep -f 'scripts[.]chain_snapshot_poller' >/dev/null
done

ROLLOUT_COMMITTED=1
trap - EXIT INT TERM HUP
echo "scheduler installed; plist backup and prior deploy rollback retained at $STAMP"
)
rollout
```

`BEFORE_MANIFEST` and `VIA_DEPLOY_MANIFEST` are mandatory external files made
with the manifest procedure above; neither may live under the authority root.
The same block handles a later reviewed refresh: it always builds beside the
live clone, recreates only `.env` and the exact authority symlink, validates
both manifests, preserves the prior clone at `ROLLBACK`, and rolls back on any
failure. Do not hard-reset a dirty deploy clone.

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
recommended). Canonical config keeps the projection disabled pending its M1
rollout gates. When `chain_snapshots.options_structure_r2.enabled: true`, the
standard `R2_ENDPOINT`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, and
`R2_BUCKET` variables must be present in the sourced deploy-worktree `.env`.
Missing credentials fail only the projection hook; local source completion stays
truthful and retryable.

Do not use `launchctl kickstart` and do not invoke `--once` as deployment proof.
Loading outside RTH may cause an inert launch; that is not evidence. Only the
next untouched `StartCalendarInterval` run and its governed receipt ledger can
prove the deployment.

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
adds no historical replay; the bounded completion consumer never synthesizes an
elapsed source bucket.

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

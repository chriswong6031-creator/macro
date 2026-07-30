# ThetaData EOD store — nightly R2 offsite sync

The deep ThetaData store (`/Users/chriswong/theta-ops-wt/data/thetadata_eod` —
~60 GB, ~13k parquets, 380 roots × 2012–2026, tiers `eod/` `oi/` `greeks/`) is
the foundation of all options research and exists **only on the ops Mac**
(the M1 since 2026-07-25 — see Host migration below).
This lane is its sole automated offsite copy.

## Host migration (2026-07-25, M2 → M1)

The 2026-07-25 data-plane migration moved this lane — with the ThetaData
Terminal, the backfill writer, and the store itself — from the operator's
M2 Ultra to the always-on M1 (`ssh m1`). What changed and what didn't:

- **Physical store on the M1 is `~/flow-ops-wt/data/thetadata_eod`;**
  `~/theta-ops-wt/data/thetadata_eod` is a symlink to it, so the canonical
  `THETADATA_STORE` path in this runbook is unchanged. The M2 retains **no**
  copy (its `flow-ops-wt/.env` pointer is dead by design and annotated).
- Log paths, schedule, bucket, and creds layout are unchanged — they just
  live on the M1 now (`ssh m1 tail -50 /tmp/thetadata_r2sync.stdout.log`).
- **The M1 `flow-ops-wt` deploy checkout is not a clean clone** (content was
  rsync'd over an older clone during the migration; hundreds of tracked files
  show as modified). Never whole-tree reset/commit it — deploy fixes
  path-scoped (`scp`/`git checkout origin/main -- <file>`), and confirm
  `scripts/publish_r2.py` carries the #2711 hardened client
  (`max_attempts: 10, mode: adaptive`) — the 2026-07-26 first M1 run died
  mid-multipart precisely because the checkout predated #2711.
- Until a post-migration run completes end-to-end, R2 lags the M2's last
  successful sync and the M1 copy is the only current full copy — treat
  `audit_r2`'s staleness tripwire as urgent, not routine, in that state.

**What runs:** `com.macro.thetadata-r2sync` (launchd, [ops/launchd/com.macro.thetadata-r2sync.plist](launchd/com.macro.thetadata-r2sync.plist))
executes `python -m scripts.publish_r2 --dirs thetadata_eod` from the
`flow-ops-wt` deploy worktree, daily at **22:00 PT (01:00 ET next day)** — after
the backfill refresh pass (gates open 13:10 PT, settles ~15:00 PT) and far from
the 16:00/16:30 PT heavy EOD-store readers. Weekend runs are md5-delta no-ops.

**Where it goes:** bucket `mastermindx`, keys `thetadata_eod/<tier>/<ROOT>/<YYYY>.parquet`
(mirrors the store layout), creds from `/Users/chriswong/flow-ops-wt/.env`
via `run_with_env.sh`. The store path resolves through
`engine.thetadata_store.resolve_thetadata_store` (`THETADATA_STORE` env →
content-checked; empty stub dirs never resolve).

**Volumes:** first sync uploads the full ~60 GB (hours; safe to interrupt —
the next run resumes via md5/ETag delta-skip). Steady-state nightly delta is
the ~47 refreshed roots ≈ 141 files ≈ 1.7 GB.

**Guards (scripts/publish_r2.py):** `_DATA_DIR_MIN_FILES=100` refuses partial
checkouts (a CI stub tree can never clobber the R2 store); the manifest shrink
guard blocks any file-list that would halve the remote manifest. The final
`thetadata_eod/_manifest.json` put embeds the collector's store manifest under
`"store"` (freshness/coverage evidence for `audit_r2`).

## Install (operator, once — as the mac user, not root)

```bash
cp ops/launchd/com.macro.thetadata-r2sync.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.macro.thetadata-r2sync.plist
launchctl list | grep thetadata-r2sync   # registered?
```

Uninstall: `launchctl unload ~/Library/LaunchAgents/com.macro.thetadata-r2sync.plist && rm` the copy.
Never load the repo copy directly — copy first.

## Verify

```bash
# Delta preview, uploads nothing (md5 pass over 60 GB takes a few minutes):
cd /Users/chriswong/flow-ops-wt
set -a; source .env; set +a
python -m scripts.publish_r2 --dirs thetadata_eod --dry-run

# After a run:
tail -50 /tmp/thetadata_r2sync.stdout.log
# expect: "thetadata_eod: NNN files — X changed, Y unchanged" then "R2 publish done"
```

A healthy steady-state night shows ~141 changed / ~13k unchanged. `0 changed`
on a weekday means the backfill refresh didn't write — check
`/Users/chriswong/theta-ops-wt/backfill.log` before suspecting this lane.

**Exit code alone is not proof the offsite index moved.** Three checks, in order
— the last one is the one that was silently failing 07-25→07-30:

```bash
ssh m1 'grep -c "Connection pool is full" /tmp/thetadata_r2sync.stderr.log'   # want 0
ssh m1 'tail -3 /tmp/thetadata_r2sync.stderr.log'                            # want "0 failed"
ssh m1 'grep "manifest put\|manifest untouched" /tmp/thetadata_r2sync.stderr.log | tail -2'
```

The third must read `manifest put — N files`, NOT `manifest untouched`. A run can
upload every byte, exit 1 on three stragglers, and leave the index frozen.

## Restore

`scripts/fetch_r2.py` is the download leg (same key layout, same md5 skip):
`python -m scripts.fetch_r2 --dirs thetadata_eod` with R2 creds in env. It
restores into the checkout's `data/thetadata_eod/` (it does NOT honor
`THETADATA_STORE`) — the resolver picks that path up directly, or move/symlink
it to the ops-wt store path afterwards.

## History

Chartered by research/THETADATA_OPS_RUNBOOK.md §7 (R2 publish plan, A4/A8: raw
vendor pulls are never git-committed). Before this lane (2026-07-16) the
publish was manual-only — no scheduled caller existed in any workflow or plist.

### 2026-07-29 — post-migration vintage-skew heal (OIP W0)

The 07-25 M2→M1 rsync left `flow-ops-wt` mixed-vintage: `scripts/publish_r2.py`
was current while `engine/thetadata_store.py` predated `resolve_thetadata_store`,
so this lane died on ImportError all four nights 07-25→07-28 — the store's only
offsite copy was not advancing. `com.macro.optionsmatrix` was likewise running a
pre-#3521 runner whose gate demanded same-evening OI[t] (structurally impossible
at 19:00 ET), burning its 2h retry window and exiting 1 nightly.

Heal (per this runbook's path-scoped deploy doctrine — never a whole-tree
reset): five files copied from origin/main and md5-verified on the host —
`engine/thetadata_store.py` (strict superset of the old symbols),
`lib/nyse_calendar.py`, `ops/launchd/run_options_matrix.sh`,
`scripts/build_options_matrix.py`, `engine/options_matrix.py` — with
`.bak-oip-w0` backups beside each. Verification before re-arming: `publish_r2
--dry-run` scanned 13,127 files → 2,277 changed / 0 guarded; a matrix smoke
(`MATRIX_FRESHNESS_BYPASS=1 MATRIX_NO_PUBLISH=1`) built all 10 roots locally.

Same-evening outcomes: the kickstarted real sync uploaded 2,276/2,277 (one
transient mid-multipart failure on `greeks/IWM/2017.parquet`, re-pushed by the
follow-up delta run); the 16:00 PT scheduled matrix run passed its gate on
attempt 1 and published all 10 roots + 594 gex_state JSONs — **the lane's first
autonomous publish ever** (R2 matrices had been frozen at the 07-09 manual
smoke). The theta-staleness sentinel's "greeks 1 session behind" WARN during
this window was the historical greeks backfill still grinding 2026 shards —
self-healing and watched, not a lane fault.

Standing lesson: after any host migration, md5-compare the deploy tree's import
closure against origin/main before trusting lane exit codes — a mixed-vintage
tree fails on the seam between two files, and launchd's last-exit column cannot
distinguish that from a data problem.

### 2026-07-30 — connection-pool exhaustion held the manifest shut

With the vintage skew healed, all three 07-29 runs still exited 1: **1, 12 and 3
terminal upload failures**, and every one of them a multipart part
(`?uploadId=...&partNumber=N`) — no single-PUT upload ever failed. The stderr log
carried **1,119** `Connection pool is full, discarding connection ... pool size:
64` warnings.

Cause: `publish_r2._client` pinned `max_pool_connections=64` while the real
ceiling is `workers x s3transfer part concurrency` = **32 x 10 = 320**. urllib3
does not block on a full pool — it opens the connection anyway and discards it on
release, so the lane re-ran the TLS handshake thousands of times and R2 dropped
parts mid-flight (`Connection was closed before we received a valid response`).
The same class of under-provisioning as the 2026-07-16 EMFILE one layer down,
which the plist's 4096-fd `SoftResourceLimits` fixed.

Why it mattered more than "a few files retried": `publish()` deliberately refuses
to write `_manifest.json` when ANY upload failed, so three stragglers were enough
to hold the offsite **index** frozen while the bytes kept landing — a backup whose
descriptor is stale is the state you least want it in when you go to restore. No
successful manifest put appears anywhere in the retained log.

Fix (#4059): the pool is now DERIVED, not a constant —
`_pool_size(workers) = max(64, workers x _TRANSFER_CONCURRENCY + 8)` → 328 at the
default 32 workers, and `publish()`/`fetch()` each hand their own worker count to
`_client()`. `_TRANSFER_CONCURRENCY` is also PINNED into an explicit
`TransferConfig` at the upload/download call, so a future s3transfer default bump
cannot silently invalidate the arithmetic. The restore leg got the same treatment
— `download_file` fans a large object into concurrent ranged GETs exactly as
`upload_file` fans out parts.

Note for anyone reading `thetadata_eod/_manifest.json` on R2: the store's own
collector manifest (`store`/`n_roots`/`per_root`/`updated_at`) is ALSO uploaded to
that key by the ordinary delta pass, because `rglob` picks it up. On a clean run
the publisher's file-list doc is put last and wins; on a failed run the collector
doc is what remains, which is exactly what sat there 07-29→07-30. Distinguish the
two by top-level key: `count`/`files` = publisher, `n_roots`/`per_root` = collector.

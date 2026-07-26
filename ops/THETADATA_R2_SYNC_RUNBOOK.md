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

# Live Options-Flow Poller — Runbook

## Architecture overview

The live-flow poller (`scripts/live_flow_poller.py`) runs on the Mac Studio
during Regular Trading Hours (RTH: 09:25–16:05 ET, weekdays).  It fetches
options tape data per root, runs the flow engine, and publishes JSON artifacts
to Cloudflare R2.  The FastAPI app (`app/main.py`) serves those R2 objects to
the Terminal UI with a 30s TTL cache.

## Files written per cycle

| R2 key | Schema | Contents |
|---|---|---|
| `live_flow/feed_current.json` | `live_flow.feed/v1` | Events + unusual names |
| `live_flow/heat_current.json` | `live_flow.heat/v1` | Sector heat rows |
| `live_flow/meta.json` | `live_flow.meta/v1` | Poller cadence / universe |
| `live_flow/tide_current.json` | `live_flow.tide/v1` | Market tide (NCP/NPP minutes + sectors) |
| `live_flow/dte_tide_current.json` | `live_flow.dte_tide/v1` | DTE-bucket tide |
| `live_flow/tickers/{ROOT}.json` | `live_flow.ticker/v1` | Per-root drill (top ~40 roots) |
| `live_flow/tide/{DATE}.json` | `live_flow.tide/v1` | Dated archive of tide_current (same bytes) |
| `live_flow/dte_tide/{DATE}.json` | `live_flow.dte_tide/v1` | Dated archive of dte_tide_current |
| `live_flow/tide/dates.json` | `live_flow.archive_dates/v1` | Sessions index for the tide archive |
| `live_flow/dte_tide/dates.json` | `live_flow.archive_dates/v1` | Sessions index for the dte archive |

Local copies land in `data/live_flow_out/` (gitignored).
Day state is persisted at `data/live_flow_state/day_state_{date}.json`.

### Dated tide/dte archives (OIP W0 T-lane)

`tide_current.json` / `dte_tide_current.json` are OVERWRITTEN every cycle, so the session's
story used to die at the close. Each cycle now also uploads the SAME two local files under a
date-keyed name (`live_flow/{tide,dte_tide}/{YYYY-MM-DD}.json`) plus a per-family
`dates.json` sessions index — one write, two keys, so the live copy and the archive can never
disagree byte-for-byte. **The day's final write is the settled record**, which is what the
nightly Session Digest (OIP E1) reads. Both payloads already carry the full-session
cumulative series (390 minutes for a full RTH session), so no payload changed and the current
keys are byte-identical to before.

- Writer: `scripts/build_flow_archive.py` (pure functions), wired in `live_flow_poller.main`.
- Retention: newest **30** sessions per family; override with `live_flow.archive_retain_sessions`
  in `config.yml` (a non-positive value is refused and the default is used — a stray `-1`
  would otherwise select every dated object, today's included). Swept once per session (two
  cheap R2 listings), never per-cycle; a failed sweep retries **next session**, not next
  cycle. The prune rebuilds every delete target from `dated_archive_key`, so it can only ever
  delete a key this lane wrote — never `dates.json`, never `live_flow/tide_current.json` — and
  it honors R2's per-key `Errors` array, so a refused delete is reported, not counted.
  Flow-Surface retention stays at 10 sessions (`surface_retain_sessions`) — unchanged.
- **Write gates.** The lane is dark unless the run is a live one on a real trading day: any
  `--date` run (see the smoke warning below) and any non-NYSE-session date
  (`lib/nyse_calendar.is_session` — holidays, not just weekends) skip the dated write, the
  ledger entry and the retention sweep. The current keys publish either way.
- Added cost: +4 R2 PUTs/cycle (~262 KB — `tide` 179 KB + `dte_tide` 82.5 KB, measured live
  2026-07-29 + two ~250-byte indexes). Stored footprint is only the last write per key:
  ~8 MB per 30-session retention window. R2 ingress is free; ~800 extra class-A writes per
  session.
- Fully fail-soft: a staging or PUT failure logs and degrades to current-keys-only; it can
  never cost the poller a cycle or blank a key the live Terminal reads.
- Verify after a deploy:
  ```bash
  R2_BASE=$(python -c "import yaml; c=yaml.safe_load(open('config.yml')); \
    print(c['r2_data_plane']['public_base'])")
  curl -s "$R2_BASE/live_flow/tide/dates.json" | python -m json.tool
  curl -s -o /dev/null -w '%{http_code} %{size_download}\n' \
    "$R2_BASE/live_flow/tide/$(date +%F).json"
  ```

## launchd autostart

Two plists manage the options-flow stack.  Both run on the **M1 ops host**, but
from **two different deploy trees** — a recurring source of confusion:

| Plist | Job | Schedule | WorkingDirectory | Log paths |
|---|---|---|---|---|
| `com.mastermind.liveflow.plist` | Live poller (RTH) | Weekdays 09:25 ET | `/Users/chriswong/liveflow-ops-wt` | `/tmp/liveflow.stdout.log` `/tmp/liveflow.stderr.log` |
| `com.mastermind.optionshub.plist` | Nightly hub builder | Weekdays 16:45 ET | `/Users/chriswong/hub-ops-wt` | `/tmp/optionshub.stdout.log` `/tmp/optionshub.stderr.log` |

Both plists use `ops/launchd/run_with_env.sh` to source `.env` before launching
Python.  Secrets (`R2_*`, `THETADATA_STORE`) must be in the `.env` file inside
the job's working directory.  **Never inline secrets in the plist
EnvironmentVariables block.**

> **Read `*.stderr.log`, not `*.stdout.log`.**  The poller logs through Python's
> `logging`, which writes to **stderr**.  `/tmp/liveflow.stdout.log` sits at
> 0 bytes for weeks at a time (measured 2026-07-30: 0 bytes since 07-27, while
> `/tmp/liveflow.stderr.log` held 4.8 MB from the 07-29 session).  **An empty
> stdout log is not evidence the job failed to run.**  Session evidence — cycle
> lines, root counts, R2 publish confirmations — lives in the stderr log.

### Deploy-tree doctrine (live-flow poller)

The `com.mastermind.liveflow` job MUST run from a **dedicated deploy tree**
`/Users/chriswong/liveflow-ops-wt` (pinned to `origin/main`) — **never** from a
shared agent checkout.  A shared checkout's git HEAD is controlled by many
concurrent agent sessions and is frequently parked at a detached HEAD that does
**not** contain `scripts/live_flow_poller.py`; a launchd run rooted there dies
with `ModuleNotFoundError` at the next 06:25 PT fire.  The launchd
`ProgramArguments`, `WorkingDirectory`, and `PYTHONPATH` therefore all point at
the deploy tree.

#### Two machines — know which one you are on

This section used to read as if there were one machine.  There are two, and only
one of them runs anything:

| | Mac Studio (`Mac14,14`) | M1 ops host (`Mac13,1`, ssh alias `m1`) |
|---|---|---|
| Parent checkout `~/Documents/Cluade/Macro Dashboard` | **exists** (shared agent checkout) | **does not exist** — `~/Documents/Cluade` holds only `Mastermind` |
| `/Users/chriswong/liveflow-ops-wt` | a **dormant stale copy** (last touched 2026-07-25) | the **live** poller tree |
| `com.mastermind.liveflow` loaded in launchd | no | **yes** |

The Studio's `liveflow-ops-wt` is a leftover at the same path: nothing loads it
and nothing reads it.  **Editing it deploys nothing.**  The live lane is the
M1's — reach it with `ssh m1`.

#### Why the old `git worktree add` recipe is gone

Until 2026-07-30 this section prescribed, from the parent checkout:

```bash
# HISTORICAL — impossible on the M1, kept only so the failure is recognisable
cd '/Users/chriswong/Documents/Cluade/Macro Dashboard'
git worktree add -B ops/liveflow-deploy /Users/chriswong/liveflow-ops-wt origin/main
```

On the M1 there is no parent checkout, so this cannot run.  Worse, the tree that
was there had been created that way under some earlier machine state: its `.git`
was a one-line `gitdir:` pointer into
`…/Macro Dashboard/.git/worktrees/liveflow-ops-wt`, which does not exist on that
host — so **every** git command inside the deploy tree failed with `fatal: not a
git repository`.

The lane was therefore being deployed by `scp`-ing individual files, which let it
drift silently.  Measured 2026-07-29, before the rebuild: `engine/live_flow.py`
and `scripts/live_flow_poller.py` matched `origin/main`, but `config.yml`,
`engine/flow_signing.py` and `lib/nyse_calendar.py` were each one commit behind
— and `lib/nyse_calendar.is_session` is what gates the dated tide/dte archive
writes.  A file-copy deploy updates what you remember to copy; nothing tells you
what you forgot.

#### Current procedure — standalone shallow clone

The deploy tree is now a **standalone clone**, not a worktree.  This follows the
precedent already on the M1: `flow-ops-wt` and `fund-ops-wt` were standalone
clones and were the only ops trees whose git still worked.

Constraints that shaped the shape:

- **Disk.**  The M1 sits at ~97% (~15 GB free).  A full clone of this repo costs
  ~13 GB of `.git` alone (measured: `flow-ops-wt/.git`).  `--depth 1` costs
  ~1.6 GB, for ~4.5 GB of tree total.
- **No `--filter=blob:none`.**  A blobless partial clone lazily fetches blobs on
  read; a deploy tree on a live lane must not need the network to read its own
  source files.
- **Auth.**  `gh` on the M1 is authenticated as `chriswong6031-creator` with an
  **invalid token** — do not rely on it.  Two paths do work, both verified
  2026-07-30:
  1. the repo-scoped SSH **deploy key** `~/.ssh/macro_dashboard_deploy`
     (`ssh -i ~/.ssh/macro_dashboard_deploy -T git@github.com` →
     `Hi chriswong6031-creator/macro!`).  There is no `~/.ssh/config` on the M1,
     so the key is pinned in the clone's own `core.sshCommand`.
     Note `macro_dashboard_deploy_v2` does **not** authenticate — use the v1 key.
  2. anonymous **HTTPS** — the repo is public, so `git ls-remote
     https://github.com/chriswong6031-creator/macro.git` needs no credentials.
     Fallback if the key is ever revoked.

Rebuild, while the poller is idle (it self-exits 16:05 ET, so any weekday
evening/overnight works — check `launchctl list | grep liveflow` shows PID `-`):

```bash
OLD=/Users/chriswong/liveflow-ops-wt
NEW=/Users/chriswong/liveflow-ops-wt.new

# 1. clone BESIDE the live path, never over it
git clone --depth 1 --single-branch --branch main \
  --config "core.sshCommand=ssh -i /Users/chriswong/.ssh/macro_dashboard_deploy -o IdentitiesOnly=yes" \
  git@github.com:chriswong6031-creator/macro.git "$NEW"

# 2. carry over what git can never provide (all gitignored)
rsync -a "$OLD/.env" "$NEW/.env"                                  # keeps 0600
rsync -a "$OLD/data/live_flow_state" "$OLD/data/live_flow_out" "$NEW/data/"

# 3. swap, keeping a timestamped rollback; launchd paths never change
mv "$OLD" "${OLD}.orphaned-$(date +%Y%m%dT%H%M%S)"
mv "$NEW" "$OLD"
```

Copy **only** those gitignored paths.  Anything else the old tree has that
`origin/main` lacks is a stale vintage of a file main has since changed or
deleted; copying it back re-creates the drift the rebuild exists to remove.

Verify (no live cycle — see the warning below):

```bash
cd /Users/chriswong/liveflow-ops-wt
git log -1 --format='%H %ci %s'
git status --porcelain -uno | wc -l         # must be 0
ls -l .env                                  # must still be -rw-------
ls data/live_flow_state/                    # day_state_*.json must be present
launchctl list | grep mastermind.liveflow   # PID '-', last status 0, while idle
PYTHONPATH=/Users/chriswong/liveflow-ops-wt \
  /Users/chriswong/miniconda3/envs/plane/bin/python \
  -m scripts.live_flow_poller --help >/dev/null && echo "poller entrypoint OK"
```

> **Do not verify by running a real cycle.**  A bare `--once` publishes to the
> live R2 *current* keys, and `--once --date <past>` overwrites that date's
> flow-surface replay (see the smoke warning above).  The import + `--help`
> check covers the `ModuleNotFoundError` class of failure that this doctrine
> exists to prevent; the real proof is the next 09:25 ET session in
> **`/tmp/liveflow.stderr.log`**.

Refresh thereafter — this is now an ordinary git operation, which was the whole
point:

```bash
cd /Users/chriswong/liveflow-ops-wt
git fetch --depth 1 origin main && git reset --hard FETCH_HEAD
```

Keep `--depth 1` on the fetch: it holds the shallow boundary at one commit so the
tree never grows toward the ~13 GB full-history footprint this disk cannot take.
`git reset --hard` also restores any file an earlier `scp` deploy hand-patched,
and leaves gitignored runtime state (`.env`, `data/live_flow_state/`,
`data/live_flow_out/`) untouched.

> **`theta-ops-wt` only — `reset --hard` breaks the store, re-create the symlink.**
> That tree deliberately overrides a *tracked* path: `data/thetadata_eod` is a
> **symlink** to `/Users/chriswong/flow-ops-wt/data/thetadata_eod`, while
> `origin/main` tracks a directory there holding two snapshot files
> (`_backfill_state.json`, `_manifest.json`).  `git reset --hard` restores the
> tracked directory and silently destroys the override — four lanes
> (`optionsmatrix`, `theme-options-witness`, `thetadata-r2sync`, `optionshub`)
> would then resolve `THETADATA_STORE` to a near-empty directory, and the
> backfill would read a **29-byte** snapshot `_backfill_state.json` in place of
> the live **~88 KB** one and re-pull ~380 roots × 2012-2026 from scratch.
> After any hard reset on this tree:
>
> ```bash
> cd /Users/chriswong/theta-ops-wt
> rm -rf data/thetadata_eod
> ln -s /Users/chriswong/flow-ops-wt/data/thetadata_eod data/thetadata_eod
> ```
>
> Consequently `theta-ops-wt` never shows a clean `git status`: the two
> deletions above are its correct steady state.  Verify it with
> `git status --porcelain -uno -- . ':(exclude)data/thetadata_eod'`, which must
> be empty.  (`flow-ops-wt`, which owns the real store, carries the same two
> files permanently *modified* for the same reason.)

#### Sibling deploy trees on the M1

| Tree | Job(s) | State (2026-07-30) |
|---|---|---|
| `liveflow-ops-wt` | `com.mastermind.liveflow` | **standalone clone — git-refreshable** |
| `hub-ops-wt` | `com.mastermind.optionshub`, `com.mastermind.levelsgrader`, `com.mastermind.levelsseal` | **standalone clone — git-refreshable** (rebuilt 2026-07-30) |
| `theta-ops-wt` | `com.macro.theta-terminal`, `com.macro.thetadata-backfill`, `com.macro.theta-staleness` (+4 readers) | **standalone clone — git-refreshable** (rebuilt 2026-07-30) |
| `flow-ops-wt` | flow enrich / signing lanes | standalone clone, full history (~75 GB) |
| `fund-ops-wt` | `com.mastermind.fund` | standalone clone of a *different* repo (`mastermind-terminal`) |

All three macro-repo deploy trees are now standalone shallow clones.  Refresh any
of them with the ordinary `git fetch --depth 1 origin main && git reset --hard
FETCH_HEAD` above.

**Count the jobs before you touch a tree — `grep -l <tree> ~/Library/LaunchAgents/*.plist`.**
Both rebuilds found a blast radius wider than the tree's name suggests:

- `hub-ops-wt` roots **three** jobs, not one.  `levelsgrader` (18:00 local) and
  `levelsseal` (04:30 + 06:00 local, weekdays) both `exec` scripts from
  `hub-ops-wt/ops/launchd/`.
- `theta-ops-wt` is named by **seven** plists.  Three `exec` scripts out of
  `theta-ops-wt/scripts/launchd/`; the other four
  (`optionsmatrix`, `theme-options-witness`, `thetadata-r2sync`, `optionshub`)
  only resolve `THETADATA_STORE=…/theta-ops-wt/data/thetadata_eod`, which is a
  **symlink** into `flow-ops-wt` — the 60 GB store is not inside the tree, but
  drop that one symlink and four lanes lose the store, including its sole
  offsite backup.

Schedules in these plists are **local (PDT)**, not ET — `optionshub`'s
`Hour 16 Minute 45` fires 16:45 local (19:45 ET) and runs ~80 min.

##### Untracked does not always mean stale

The "copy only the gitignored runtime state, nothing else" rule has one
exception, and it is the dangerous one: a file can be untracked because it was
**never committed**, not because main moved past it.  `hub-ops-wt` held
`ops/launchd/levels_grader_daily.sh` and `levels_seal_preopen.sh` — absent from
`origin/main` entirely, executable, and named directly in two loaded plists.  A
clean clone would have deleted both and killed those lanes silently.  They are
now committed to main, so the tree is genuinely refreshable; if you meet another
one, carry it **and commit it**, don't just copy it forward.

Sort each untracked path into: live runtime state (carry), a stale vintage of a
file main has since changed or deleted (drop), or never-committed load-bearing
code (carry **and** commit).  Derive the set mechanically — diff the tree
against main rather than trusting a remembered list:

```bash
cd <tree> && find . \( -type f -o -type l \) | sed 's|^\./||' | sort > /tmp/actual.txt
# main_tracked.txt = `git ls-tree -r --name-only origin/main | sort`, generated
# on a host that has a working checkout and copied over
comm -23 /tmp/actual.txt /tmp/main_tracked.txt | grep -v __pycache__
```

Carry lists as measured 2026-07-30:

| Tree | Carry | Drop |
|---|---|---|
| `liveflow-ops-wt` | `.env`, `data/live_flow_state/`, `data/live_flow_out/` | — |
| `hub-ops-wt` | `.env`, `data/live_flow_out/` (its own output), `data/levels/` (`grades.parquet`, `track_record.json`, `ledger/`, `backfill_done_years.txt`), `ops/launchd/levels_{grader_daily,seal_preopen}.sh` | `__pycache__`, stale `site/assets/*` render artifacts, templates/tests main deleted |
| `theta-ops-wt` | `.env`, the `data/thetadata_eod` **symlink** | `backfill.log` (118 MB of 60 s gate lines — launchd recreates it), `__pycache__`, 4 templates main deleted |

##### What the drift actually was

`theta-ops-wt` proved the thesis.  Its `scripts/launchd/` copies were stale
vintages predating two merged PRs that never reached the host:

- **#3138** — zombie-proof terminal health.  A terminal on a stale/revoked
  `THETA_API_KEY` stays up serving HTTP 200 with an *empty* body while real data
  endpoints time out (bit live 2026-07-20).  The deployed keepalive *and*
  sentinel both trusted the bare status code, so the monitor stayed green
  through the outage.
- **#3150** — the keepalive hands the key to the JVM via `THETADATA_API_KEY`
  instead of `--api-key` argv.  The stale copy leaked the production ThetaData
  key into world-readable `ps` output, and was still doing so at rebuild time.

Neither was visible as "drift" because nothing on the host could run `git
status`.  That is the whole argument for these trees being clones.

##### Swapping a tree that is never idle

`optionshub` has a clean overnight window, but `theta-ops-wt` roots two
`KeepAlive` jobs that never go idle:

- `com.macro.theta-terminal` — the wrapper blocks holding the java process for
  the terminal's whole lifetime, so launchd does **not** re-exec it while the
  terminal is healthy.  Its jar and log live outside the tree
  (`~/theta/`), and both processes' `cwd` follows the inode through a rename,
  so a swap does not disturb a running terminal.  It keeps the *old* script on
  its open fd and picks up the new one on its next natural restart.
- `com.macro.thetadata-backfill` — `exec`s **every 60 s** (it exits 1 on its
  own pre-close gate until 20:10 UTC, and `ThrottleInterval` re-fires it).  A
  swap can land in that gap; the cost is one failed exec and a 60 s retry.
  Keep the two `mv`s back-to-back in a single shell and it is a non-event.

Do not carry `backfill.log` forward — that once-per-minute gate line grows it
past 100 MB, and launchd recreates it on the next spawn.  Leaving it in the
rollback is the cheap cleanup.

The same TCC constraint applies to the ThetaData EOD backfill agent
(`com.macro.thetadata-backfill`): its keepalive script must live **outside**
`~/Documents/` (kept at `/Users/chriswong/theta-ops-wt/scripts/launchd/`),
because macOS TCC denies launchd `exec` on scripts under `~/Documents/`
("Operation not permitted" / exit 126).

##### Disk

A depth-1 clone of this repo costs **~4.5 GB** checked out (~1.7 GB `.git`), and
takes 20–30 min over the M1's link.  Rebuilding a tree therefore costs ~4.5 GB
until its rollback is deleted, and the M1 runs at ~97%.  Check `df -g
/System/Volumes/Data` before and during, and stop if free space would fall below
~6 GB.  Free space on that host is volatile — the three GitHub Actions runners
(`~/actions-runner-{1,2,3}`, 12–24 GB each) churn tens of GB as CI runs, so a
rebuild that looks unaffordable at the start may be affordable an hour later.

Rollbacks are `~/<tree>.orphaned-<UTC-ish stamp>` and are kept until the lane has
been proven by a real scheduled run; deleting one is an operator call.  For
`theta-ops-wt`, note that the long-lived ThetaData terminal keeps its `cwd`
inside whichever directory it was launched from — after a swap that is the
rollback — so prefer deleting that rollback once the terminal has restarted.

### Live-flow poller — install

```bash
cp ops/launchd/com.mastermind.liveflow.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.mastermind.liveflow.plist
```

Rebuilding the deploy tree does **not** require touching launchd: the plist
addresses the tree by path, so a clone-beside-and-swap is invisible to it as
long as the job is idle and the final path is unchanged.  Reinstall only when
the plist itself changes.

The installed plist on the M1 spells the interpreter as
`/Users/chriswong/miniconda3/envs/plane/bin/python`, while the repo copy uses
`/opt/homebrew/Caskroom/miniconda/base/bin/python`.  On that host the second is
a **symlink to the first** — same binary, same deps — so the two are
interchangeable and the difference is not drift worth "fixing".

### Options-hub nightly builder — install

```bash
cp ops/launchd/com.mastermind.optionshub.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.mastermind.optionshub.plist
```

### Verify

```bash
launchctl list | grep mastermind
tail -f /tmp/liveflow.stdout.log
tail -f /tmp/optionshub.stdout.log
```

### Uninstall

```bash
launchctl unload ~/Library/LaunchAgents/com.mastermind.liveflow.plist
rm ~/Library/LaunchAgents/com.mastermind.liveflow.plist

launchctl unload ~/Library/LaunchAgents/com.mastermind.optionshub.plist
rm ~/Library/LaunchAgents/com.mastermind.optionshub.plist
```

**DO NOT load a plist directly from the repo** — copy it first; launchd
requires the exact installed path when unloading.

### What runs when

| Time (ET, weekdays) | Job |
|---|---|
| 09:25 | `live_flow_poller` starts (--rth-only) |
| 16:05 | `live_flow_poller` self-exits (--rth-only window closed) |
| 16:45 | `build_options_hub_nightly` runs (all roots, --publish) |

### run_status registration

Both jobs write a status entry into `data/run_status.json` (via `lib.store.write_status`)
after each run.  The keys are `live_flow_poller` and `options_hub_nightly` under
`sources`.  The data-health circuit-breaker audit (`scripts/healthcheck.py`) reads
these — if either producer stops writing, the healthcheck will eventually flag it.

NOTE: wiring these into the GitHub Actions `daily.yml` circuit-breaker audit pass
belongs to a dedicated ops wave — add `sources.live_flow_poller` and
`sources.options_hub_nightly` to the healthcheck thresholds when that wave lands.

## Theta Terminal dependency

The poller calls `collectors.thetadata.reachable()` on startup.  If Theta
Terminal v3 (ThetaTerminalApp) is not running on port 25503, the poller exits
with code 1.

- Start ThetaTerminalApp before 09:25 ET each trading day.
- Recommended: add ThetaTerminalApp to System Settings → General → Login Items
  so it starts at boot.
- The terminal must remain open for the session; do not close it while the
  poller is running.

## Secrets / environment

Required environment variables (sourced from `/etc/macro-api.env` or set in
the shell before launch):

| Variable | Purpose |
|---|---|
| `R2_ENDPOINT` | Cloudflare R2 S3-compatible endpoint URL |
| `R2_ACCESS_KEY_ID` | R2 access key |
| `R2_SECRET_ACCESS_KEY` | R2 secret key |
| `R2_BUCKET` | R2 bucket name |

Load for a manual run:
```bash
set -a; source /path/to/.env; set +a
```
Never echo these values — they persist in shell history and logs.

## Manual single-cycle smoke

> **`--date` disables the dated tide/dte ARCHIVE lane — by design.** This recipe polls a
> handful of roots, so its tide payload is a valid-looking *partial* of that past session, and
> the archive key is derived from `session_date`. An ungated smoke would therefore overwrite
> the settled `live_flow/tide/<that date>.json` with a fragment, undetectably (schema valid,
> date correct — `roots_polled` lives only in `meta.json`, which the archive does not carry).
> So whenever `--date` is passed, dated **tide/dte_tide** archive writes and their retention
> sweep are both off and the poller logs it at WARNING. That lane is also dark on any
> non-session (market holidays — launchd fires anyway). To exercise it, run the unit suite:
> `pytest tests/test_flow_archive.py`.
>
> **⚠️ The dated FLOW-SURFACE store has no such gate — a backdated smoke DOES overwrite it.**
> `session_date` flows unconditionally into `build_and_stage_surfaces`
> (`live_flow_poller.py:1717`), so a `--date` run rewrites
> `live_flow/surface/{ROOT}/<that date>/idx.json` + `{HHMM}.json` with a partial few-root,
> single-stamp frame, and its retention sweep still runs. Pre-existing M-XP behavior, not
> changed here. **Do not run a backdated smoke against a session whose surface replay you
> still care about** — pick a date outside the 10-session surface retention window, or accept
> that that session's replay is clobbered until the next live session ages it out.

```bash
# Wipe stale state first
rm -f data/live_flow_state/day_state_2026-07-02.json

# Run one cycle against historical date (uses full_day mode automatically)
set -a; source .env; set +a
python -m scripts.live_flow_poller \
  --once \
  --date 2026-07-02 \
  --retention-hours 96 \
  --roots SPY QQQ KRE NVDA XLF

# Verify outputs
ls -lh data/live_flow_out/
ls -lh data/live_flow_out/tickers/
python -c "import json; d=json.load(open('data/live_flow_out/tide_current.json')); \
  print('minutes:', len(d['minutes']), 'sectors:', len(d['sectors']), \
  'top_net:', len(d['top_net_impact']))"
python -c "import json; d=json.load(open('data/live_flow_out/dte_tide_current.json')); \
  print('buckets:', list(d['buckets'].keys()))"
python -c "import json; d=json.load(open('data/live_flow_out/tickers/SPY.json')); \
  print('minutes:', len(d['minutes']), 'strikes:', len(d['strikes']))"
```

Expected for SPY 2026-07-02 with --roots SPY QQQ KRE NVDA XLF:
- `tide_current.json` minutes_n ~ 390 (one per trading minute 09:30–16:00)
- `dte_tide_current.json` buckets == ['0d', '1_7d', '8_30d', '31_90d', '90p']
- `tickers/SPY.json` minutes > 0, strikes > 0

## R2 public verification

After a smoke run, verify R2 public GET:
```bash
R2_BASE=$(python -c "import yaml; c=yaml.safe_load(open('config.yml')); \
  print(c['r2_data_plane']['public_base'])")
curl -s "$R2_BASE/live_flow/tide_current.json" | python -m json.tool | head -20
```

## State wipe / retention reset

To force a clean accumulator state (e.g. after a state corruption):
```bash
rm -f data/live_flow_state/day_state_YYYY-MM-DD.json
```

To run with a shorter retention window (keeps events for N hours instead of
the config default):
```bash
python -m scripts.live_flow_poller --once --date ... --retention-hours 96
```

## Day-state size guard

The poller logs a warning if the day-state JSON exceeds 50 MB:
```
poller: day_state size N MB exceeds 50 MB threshold
```
If this fires regularly, reduce `top_names` or `retention_hours` in config.yml.

## API endpoints

All unauthenticated, 30s TTL cache, stale fallback on R2 failure:

| Endpoint | R2 object |
|---|---|
| `GET /api/flow/feed` | `live_flow/feed_current.json` |
| `GET /api/flow/heat` | `live_flow/heat_current.json` |
| `GET /api/flow/meta` | `live_flow/meta.json` |
| `GET /api/flow/tide` | `live_flow/tide_current.json` |
| `GET /api/flow/dte` | `live_flow/dte_tide_current.json` |
| `GET /api/flow/ticker/{ROOT}` | `live_flow/tickers/{ROOT}.json` |

ROOT is sanitized to `[A-Z.]{1,8}` — invalid chars return 422.

## Known-good cycle numbers (2026-07-02, 5 roots)

| Metric | Expected |
|---|---|
| minutes_n | ~390 |
| sectors_n | 3–5 |
| tickers_published | 5 |
| cycle_sec | < 60s |
| dte buckets | 5 |

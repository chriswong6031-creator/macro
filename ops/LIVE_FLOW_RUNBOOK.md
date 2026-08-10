# Live Options-Flow Poller — Runbook

## Architecture overview

The live-flow poller (`scripts/live_flow_poller.py`) runs on the M1 ops host
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
| `live_flow/events/{DATE}.jsonl` | `live_flow.event_stage/v1` | Append-only PIT decision + availability receipts |
| `live_flow/events/dates.json` | `live_flow.event_dates/v1` | Newest 64 event-stage sessions available to nightly replay |

Local copies land in `data/live_flow_out/` (gitignored).
Day state is persisted at `data/live_flow_state/day_state_{date}.json`.

### Point-in-time raw event stage (OIP PIT)

The learning source is the date-keyed raw stage, **never** the capped and
overwritten `live_flow/feed_current.json` display artifact:

| Layer | Event ledger | Publication proof / sessions index |
|---|---|---|
| M1 local | `data/live_flow_state/events/{DATE}.jsonl` | `published.json` (remote byte/SHA receipts) + `dates.json` |
| R2 | `live_flow/events/{DATE}.jsonl` | `live_flow/events/dates.json` |

`LIVE_FLOW_EVENT_STAGE_DIR` may redirect the local directory for an isolated
test, but production uses the paths above. The poller is the sole writer of the
raw stage. For each new source event it performs this ordered durability
protocol while holding an exclusive file lock:

1. append the immutable `kind=decision` receipt and `fsync` it;
2. only after that succeeds, observe `available_at`;
3. require that clock to be at or after the stored decision clock; and
4. append the separate `kind=availability` receipt and `fsync` it.

The durable `available_at` receipt is therefore the learning horizon anchor. It
does not mean fetch completion, sequential processing completion, R2 publication,
or the time a UI happened to render the event. R2 publication does not rewrite
either decision-time receipt and `published_at` remains null unless a future,
separate publication receipt can prove it.

The R2 write order is equally load-bearing. The publisher retries every local
session that has never been proven remote or has a valid append-only extension.
It rejects shrinkage, same-size rewrites, and growth whose prior byte prefix no
longer matches the last receipt. Each PUT reads a unique fsynced immutable
snapshot of the bytes already parsed—not the concurrently mutable stage path.
Only a successful snapshot PUT may atomically add/update that session in local
`published.json`, bound to its exact raw byte count and raw-byte SHA-256.
Closed, already-proven sessions whose file size is unchanged take a metadata
fast path; the current, never-proven, or extended file is fully parsed and hashed. Local
`dates.json` is then derived from those proofs—not from the directory listing—and
its newest **64** proven sessions are uploaded to `live_flow/events/dates.json`.
A failed first PUT can therefore never advertise a missing object on a later
day. A failed same-day extension retains the already-proven remote prefix in the
index and remains eligible for retry because its local byte/SHA no longer match
the publication receipt. Display artifacts may continue fail-soft, but the
learning consumer must not advance over an unproven or changed prefix.

After that dates-index PUT succeeds, the M1 normally keeps only the newest **64
proven** stage files and publication receipts. An older file is pruned only when
its exact current bytes equal the successful remote receipt. Never-proven,
rejected, failed-extension, or otherwise mismatched files remain locally with
their prior prefix receipt even outside the window; losing that receipt would
weaken the append-only fence on retry. R2 remains the longer-lived/offline replay
archive. This bounds healthy-state disk/parse cost without silently discarding a
decision ledger during an outage or integrity fault.

The stage fails closed on malformed JSON, a conflicting duplicate decision or
availability receipt, a session/date mismatch, or a file whose final line is
torn. Never truncate a torn stage, synthesize `available_at`, or rebuild it from
`feed_current`. Preserve/quarantine the bytes for diagnosis and restore a
known-good complete prefix or replay the original source event. A crash between
the two receipt writes is recoverable: the next occurrence reuses the first
durable decision clocks, verifies that its causal payload did not drift, and
appends only the missing availability receipt.

#### Nightly consumer and replay ownership

The `OIP PIT — durable episodes + H+60 and declared-session-close proxy accrual` step in
`.github/workflows/daily.yml` runs `scripts/build_options_signal_episode.py`
after the session digest. It is the sole advancer of these committed artifacts:

- `data/options_signal_episode/episodes.jsonl` — immutable decision-time watch
  episodes;
- `data/options_signal_episode/outcomes_h60.jsonl` — later H+60 aligned-bar
  proxy measurements, containing only complete and terminal-incomplete rows;
  pending attempts are not persisted and are retried on a later nightly;
- `data/options_signal_episode/outcomes_session.jsonl` — separate immutable
  EOD/1d/3d/5d/10d underlying close outcomes. Each horizon is an exact NYSE
  session offset from the episode session; the exit is the declared target-session
  close under `nyse_session_window_recurring_schedule/v1` (including modeled
  recurring early closes), not a fabricated bar open; and
- `data/options_signal_episode/checkpoint.json` — per-session record count and
  canonical-record append-prefix SHA-256 (not the raw-byte publication digest).

The builder discovers at most the newest **64** retained sessions, using a
credentialed R2 listing when available and the public 64-session dates index as
fallback. It processes sessions oldest-first, so a missed nightly catches up
without skipping earlier retained stages. Before advancing a checkpoint it
verifies that the stage did not shrink and that the previously consumed prefix
is canonically unchanged. `COLLECT_LANE=nightly` owns committed ledger
advancement; dry runs and other lanes may derive a report but cannot append.

Replay older than the 64-session live catch-up window belongs to an explicit
offline/research restore job. It must consume preserved date-keyed raw stages,
write separate replay outputs, and never mutate the live R2 keys, the live
checkpoint, or `feed_current`. Coarse/delayed H+60 proxies and every session
outcome stay training-ineligible. Every episode and outcome retains zero trade,
pick, ranking, sizing, gating, escalation, and Prophet-training authority.

#### Receipt-bound Polygon price evidence

Price-dependent H+60 and session-close accrual consume a pair restored together
by the Actions cache under `data/intraday/`:

- `<TICKER>.parquet` — the mutable, overlap-corrected adjusted bar cache; and
- `<TICKER>.parquet.receipt.json` — its
  `polygon.intraday_price_receipt/v1` causal sidecar.

`scripts/build_polygon_intraday.py` fsyncs and atomically installs the exact
parquet bytes first, then writes the adjacent receipt with their SHA-256,
`source_available_at`, cadence, vendor delay, adjusted-price basis, timestamp
basis, row count, and coverage endpoints. The `data/intraday` cache path must
carry both files between the hourly collector and nightly engine jobs.

A legacy parquet with no receipt is never consumed: that ticker remains
explicitly pending as `missing_price_receipt` until a receipt-aware collector
refreshes it, while other tickers and the raw-stage checkpoint can advance. A
present receipt with no source, torn/duplicate-key JSON, a changed receipt, or a
source digest/basis mismatch is never consumed. Existing price-dependent H+60
accrual keeps its hard integrity stop; if H+60 was already resolved solely from
clocks, a newly mature session horizon records `invalid_price_receipt` as
retryable rather than retroactively invalidating that H+60 append.
Session-close terminal outcomes are resolved before cache acquisition and
therefore remain invariant to all cache states. Every complete H+60 outcome
retains the exact canonical `[entry, exit)` OHLC observations plus the exit open.
Every complete session outcome instead retains bounded evidence: exact
entry/exit and timestamped observed-extrema metric inputs, plus ordered
per-session manifests with cadence-span counts, first/last bar times,
`uncovered_open_seconds`, creation-time raw-path leaf commitments, and a
recomputable manifest root. Session rows are metric-replayable and
path-committed, not full-path-replayable without a separately retained exact
source snapshot; this v1 creates no durable CAS/R2 path archive. For session
rows, the receipt must cover the final bar start and cannot become available
before the declared scheduled close plus delay.

Session horizons are exactly `eod`, `1d`, `3d`, `5d`, and `10d`, mapped to NYSE
offsets `0`, `1`, `3`, `5`, and `10` by
`lib.nyse_calendar.session_n_forward`. Entry is the first regular-session bar
open at or after `episode.available_at`. Each included session must have a
complete declared-cadence selected span and a bar covering its declared close;
the first admitted bar may be at most `1.10 * bar_seconds` after the applicable
availability/open clock. The manifest discloses the opening stub (1,800 seconds
for the current UTC-clock-aligned Polygon hourly regular-session shape).
Overnight, weekend, and holiday gaps are expected; an interior RTH gap or an
unmodeled schedule/source close mismatch stays pending. Hourly/coarse MFE/MAE
are observed-path proxies, not full-RTH extrema. The calendar basis includes the
repository's recurring early-close model but is not an authoritative one-off
exchange schedule. The source checkpoint advances only after episodes, H+60
rows, and session rows have all appended successfully; replay is byte-idempotent
if a later step fails.

Offline diagnosis reads files only; it must not invoke the live poller:

```bash
export PIT_PRICE_TICKER=SPY
python - <<'PY'
import hashlib, json, os
from pathlib import Path

root = Path("data/intraday")
ticker = os.environ["PIT_PRICE_TICKER"]
source = root / f"{ticker}.parquet"
receipt_path = root / f"{ticker}.parquet.receipt.json"
print({"source_exists": source.exists(), "receipt_exists": receipt_path.exists()})
if receipt_path.exists():
    receipt = json.loads(receipt_path.read_text())
    print({
        "schema": receipt.get("schema"),
        "source_available_at": receipt.get("source_available_at"),
        "recorded_sha256": receipt.get("source_file_sha256"),
        "actual_sha256": hashlib.sha256(source.read_bytes()).hexdigest()
            if source.exists() else None,
    })
PY
```

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
     `Hi mastermindx-market-intelligence/macro!`).  There is no `~/.ssh/config` on the M1,
     so the key is pinned in the clone's own `core.sshCommand`.
     Note `macro_dashboard_deploy_v2` does **not** authenticate — use the v1 key.
  2. anonymous **HTTPS** — the repo is public, so `git ls-remote
     https://github.com/mastermindx-market-intelligence/macro.git` needs no credentials.
     Fallback if the key is ever revoked.

Rebuild, while the poller is idle (it self-exits 16:05 ET, so any weekday
evening/overnight works — check `launchctl list | grep liveflow` shows PID `-`).
This is also the mandatory deployment path when the existing tree is dirty,
hand-patched, stale, or otherwise cannot prove it equals its current commit.
As observed 2026-08-08, the live M1 tree is both dirty and substantially behind
`origin/main`: **do not run a blind reset in that tree.** Clone beside it, carry
only the three runtime paths named below, and keep the complete old tree as the
timestamped rollback:

```bash
set -euo pipefail
OLD=/Users/chriswong/liveflow-ops-wt
NEW=/Users/chriswong/liveflow-ops-wt.new
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
ROLLBACK="${OLD}.orphaned-${STAMP}"
EXPECTED_MERGE="${EXPECTED_MERGE:?export the reviewed main merge SHA first}"

test -d "$OLD/.git"
test ! -e "$NEW"                      # never reuse a stale failed-clone target
test ! -e "$ROLLBACK"

# 1. clone BESIDE the live path, never over it
git clone --depth 1 --single-branch --branch main \
  --config "core.sshCommand=ssh -i /Users/chriswong/.ssh/macro_dashboard_deploy -o IdentitiesOnly=yes" \
  git@github.com:mastermindx-market-intelligence/macro.git "$NEW"
LOCAL=$(git -C "$NEW" rev-parse HEAD)
REMOTE=$(git -C "$NEW" ls-remote origin refs/heads/main | awk '{print $1}')
test -n "$REMOTE"
test "$LOCAL" = "$REMOTE"             # clone is exact current origin/main
if test "$LOCAL" != "$EXPECTED_MERGE"; then
  git -C "$NEW" fetch --deepen 256 origin main
  git -C "$NEW" merge-base --is-ancestor "$EXPECTED_MERGE" "$LOCAL"
fi

# 2. carry over what git can never provide (all gitignored)
rsync -a "$OLD/.env" "$NEW/.env"                                  # keeps 0600
rsync -a "$OLD/data/live_flow_state" "$OLD/data/live_flow_out" "$NEW/data/"

# prove the external interpreter can import the new tree before exposure
PYTHON=/Users/chriswong/miniconda3/envs/plane/bin/python
test -x "$PYTHON"
PYTHONPATH="$NEW" "$PYTHON" -c 'import scripts.live_flow_poller'
PYTHONPATH="$NEW" "$PYTHON" -m scripts.live_flow_poller --help >/dev/null

# 3. swap, keeping a timestamped rollback; launchd paths never change
SWAPPED=0
restore_on_error() {
  rc=$?
  if test "$rc" -ne 0 && test "$SWAPPED" -eq 1; then
    mv "$OLD" "${OLD}.failed-${STAMP}"
    mv "$ROLLBACK" "$OLD"
  fi
  exit "$rc"
}
trap restore_on_error EXIT
mv "$OLD" "$ROLLBACK"
if ! mv "$NEW" "$OLD"; then
  mv "$ROLLBACK" "$OLD"             # restore the live path on a failed swap
  exit 1
fi
SWAPPED=1
test "$(git -C "$OLD" rev-parse HEAD)" = "$LOCAL"
test -z "$(git -C "$OLD" status --porcelain)"
test "$(stat -f '%Lp' "$OLD/.env")" = 600
PYTHONPATH="$OLD" "$PYTHON" -c 'import scripts.live_flow_poller'
PYTHONPATH="$OLD" "$PYTHON" -m scripts.live_flow_poller --help >/dev/null
SWAPPED=0
trap - EXIT
```

Copy **only** those gitignored paths.  Anything else the old tree has that
`origin/main` lacks is a stale vintage of a file main has since changed or
deleted; copying it back re-creates the drift the rebuild exists to remove.

Verify (no live cycle — see the warning below):

```bash
set -euo pipefail
cd /Users/chriswong/liveflow-ops-wt
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git ls-remote origin refs/heads/main | awk '{print $1}')
test -n "$REMOTE"
test "$LOCAL" = "$REMOTE"
test -z "$(git status --porcelain)"
test "$(stat -f '%Lp' .env)" = 600
git log -1 --format='%H %ci %s'
ls data/live_flow_state/                    # day_state_*.json must be present
launchctl list | grep mastermind.liveflow   # PID '-', last status 0, while idle
PYTHONPATH=/Users/chriswong/liveflow-ops-wt \
  /Users/chriswong/miniconda3/envs/plane/bin/python \
  -m scripts.live_flow_poller --help >/dev/null && echo "poller entrypoint OK"
```

This release changes the launchd restart contract, so refreshing the clone is
not sufficient. While the host is idle and outside RTH, reinstall and reload the
reviewed plist, then prove the installed copy and loaded label:

```bash
set -euo pipefail
INSTALLED="$HOME/Library/LaunchAgents/com.mastermind.liveflow.plist"
DOMAIN="gui/$(id -u)"
launchctl bootout "$DOMAIN" "$INSTALLED" 2>/dev/null || true
install -m 644 \
  /Users/chriswong/liveflow-ops-wt/ops/launchd/com.mastermind.liveflow.plist \
  "$INSTALLED"
plutil -lint "$INSTALLED"
test "$(plutil -extract KeepAlive.SuccessfulExit raw -o - "$INSTALLED")" = false
launchctl bootstrap "$DOMAIN" "$INSTALLED"
launchctl print "$DOMAIN/com.mastermind.liveflow" >/dev/null
```

`SuccessfulExit=false` restarts crashes and Theta-unavailable exits after the
60-second throttle, but a clean outside-RTH/post-close exit remains stopped until
the next calendar trigger. Do not reload this plist during RTH merely to test it.

> **Do not verify this deployment by running a real cycle.** Do not run
> `--once`, with or without `--date`: a bare `--once` publishes to the
> live R2 *current* keys, and `--once --date <past>` overwrites that date's
> flow-surface replay (see the smoke warning above).  The import + `--help`
> check covers the `ModuleNotFoundError` class of failure that this doctrine
> exists to prevent. Keep the rollback through the next RTH proof: after the
> next 09:25 ET start, confirm in **`/tmp/liveflow.stderr.log`** that cycles ran,
> the date-keyed event stage uploaded before its dates index, local
> `events/published.json` matches the uploaded byte count/SHA, and no torn-stage,
> checkpoint, or R2 error occurred. Then verify that
> `live_flow/events/{DATE}.jsonl` and the same date in
> `live_flow/events/dates.json` are publicly readable. Only that scheduled run
> proves the PIT writer in production; deleting the rollback remains an operator
> decision after this proof.

Refresh thereafter with the in-place operation below **only when the standalone
clone begins clean and current enough that its diff has been reviewed**. If
`git status --porcelain` is non-empty, HEAD is unexpectedly stale, or any path
has been hand-patched, use the clone-beside/swap procedure above instead; never
erase an unexplained dirty tree to make deployment look clean.

```bash
set -euo pipefail
cd /Users/chriswong/liveflow-ops-wt
test -z "$(git status --porcelain)"
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

There is no safe production CLI single-cycle smoke for this combined poller.
Do **not** run bare `--once` or `--once --date <past>`: both can mutate live R2
current/replay surfaces, and a historical date cannot satisfy the exact
same-exchange-date observation/decision/availability contract for new events.

Use isolated, non-network contract fixtures and the import/entrypoint proof:

```bash
python -m scripts.live_flow_poller --help
python -m pytest -q -p no:cacheprovider \
  tests/test_options_signal_episode.py tests/test_live_flow.py
```

## Scheduled R2 public verification

After the next normal launchd RTH cycle—not after a manual invocation—verify R2 public GET:
```bash
R2_BASE=$(python -c "import yaml; c=yaml.safe_load(open('config.yml')); \
  print(c['r2_data_plane']['public_base'])")
curl -s "$R2_BASE/live_flow/tide_current.json" | python -m json.tool | head -20
```

## State wipe / retention reset

Never delete, truncate, or quarantine the current session's `day_state` alone.
It is the transaction partner of `events/{DATE}.jsonl`: it carries exact engine
dedup state and may own a post-cycle `pending_learning_events` WAL that has not
reached the stage yet. A missing/corrupt state beside a nonempty stage correctly
fails closed; rebuilding from empty would double-count prints and change IDs.

On an integrity stop, leave launchd unloaded and make a recoverable forensic copy:

```bash
set -euo pipefail
cd /Users/chriswong/liveflow-ops-wt
SESSION=YYYY-MM-DD
CASE="/Users/chriswong/liveflow-recovery-${SESSION}-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -m 700 "$CASE"
cp -p "data/live_flow_state/day_state_${SESSION}.json" "$CASE/" 2>/dev/null || true
cp -p "data/live_flow_state/events/${SESSION}.jsonl" "$CASE/" 2>/dev/null || true
shasum -a 256 "$CASE"/* >"$CASE/SHA256SUMS" 2>/dev/null || true
```

Then inspect `pending_learning_events` without editing either original. If it is
the current exchange date, reload the reviewed plist normally: startup drains
the exact WAL before the RTH gate and before probing Theta. If it is a prior
date, the availability clock can no longer be stamped honestly. Record the
incident, preserve the case directory, and move only the prior `day_state` into
`data/live_flow_state/quarantine/` after explicit operator review; never backdate
or synthesize availability. The already-complete decision/availability pairs in
the dated stage remain append-only evidence. A corrupt current-session state
cannot be auto-rebuilt: stop for that session and resume on a new session only
after the same reviewed quarantine procedure.

Automatic retention already prunes old, proven day states. There is no generic
manual state-wipe command, and neither bare `--once` nor historical `--date` is a
valid recovery or smoke test.

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

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

Local copies land in `data/live_flow_out/` (gitignored).
Day state is persisted at `data/live_flow_state/day_state_{date}.json`.

## launchd autostart

Two plists manage the options-flow stack:

| Plist | Job | Schedule | Log paths |
|---|---|---|---|
| `com.mastermind.liveflow.plist` | Live poller (RTH) | Weekdays 09:25 ET | `/tmp/liveflow.stdout.log` `/tmp/liveflow.stderr.log` |
| `com.mastermind.optionshub.plist` | Nightly hub builder | Weekdays 16:45 ET | `/tmp/optionshub.stdout.log` `/tmp/optionshub.stderr.log` |

Both plists use `ops/launchd/run_with_env.sh` to source `.env` before launching
Python.  Secrets (`R2_*`, `THETADATA_STORE`) must be in the `.env` file inside
the job's working directory.  **Never inline secrets in the plist
EnvironmentVariables block.**

### Deploy-worktree doctrine (live-flow poller)

The `com.mastermind.liveflow` job MUST run from a **dedicated deploy worktree**
`/Users/chriswong/liveflow-ops-wt` (pinned to `origin/main`) — **never** from the
main checkout `/Users/chriswong/Documents/Cluade/Macro Dashboard`.  The main
checkout's git HEAD is controlled by many concurrent agent sessions and is
frequently parked at a detached HEAD that does **not** contain
`scripts/live_flow_poller.py`; a launchd run rooted there dies with
`ModuleNotFoundError` at the next 06:25 PT fire.  The launchd `ProgramArguments`,
`WorkingDirectory`, and `PYTHONPATH` therefore all point at the deploy worktree.

Create / refresh the deploy worktree:

```bash
cd '/Users/chriswong/Documents/Cluade/Macro Dashboard'
git fetch origin main
git worktree add -B ops/liveflow-deploy /Users/chriswong/liveflow-ops-wt origin/main
cp '/Users/chriswong/Documents/Cluade/Macro Dashboard/.env' /Users/chriswong/liveflow-ops-wt/.env
# .env must define R2_ENDPOINT R2_ACCESS_KEY_ID R2_SECRET_ACCESS_KEY R2_BUCKET
# THETADATA_STORE  (baselines.json is committed under data/live_flow_baselines/).
```

The same pattern applies to the ThetaData EOD backfill agent
(`com.macro.thetadata-backfill`): its keepalive script must live **outside**
`~/Documents/` (kept at `/Users/chriswong/theta-ops-wt/scripts/launchd/`),
because macOS TCC denies launchd `exec` on scripts under `~/Documents/`
("Operation not permitted" / exit 126).

### Live-flow poller — install

```bash
cp ops/launchd/com.mastermind.liveflow.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.mastermind.liveflow.plist
```

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

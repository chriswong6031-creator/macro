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

The plist at `ops/launchd/com.mastermind.liveflow.plist` schedules the poller
to start at 09:25 ET on weekdays.  The poller uses `--rth-only` to self-exit
after 16:05 ET.

### Install

```bash
cp ops/launchd/com.mastermind.liveflow.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.mastermind.liveflow.plist
```

### Verify

```bash
launchctl list | grep liveflow
tail -f /tmp/liveflow.stdout.log
```

### Uninstall

```bash
launchctl unload ~/Library/LaunchAgents/com.mastermind.liveflow.plist
rm ~/Library/LaunchAgents/com.mastermind.liveflow.plist
```

**DO NOT load the plist directly from the repo** — copy it first; launchd
requires the exact installed path when unloading.

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

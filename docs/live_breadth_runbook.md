# Live breadth runbook (Phase 2 — `site/live/breadth.json`)

Operator deploy + verify + rollback for the live intraday market-breadth poller
(`research/LIVE_TAPE_SCOREBOARD_MASTERPLAN.md` Phase 2, decisions D6/D7). This is
the **engine lane only** — it produces the display-tier JSON the surface lane
(compact adv/dec scoreboard on `us_stocks`) consumes.

**What ships in this PR (engine, no surface):** the poller
(`scripts/live_breadth_poller.py`), its pure join/count core
(`engine/live_breadth.py`), a config block (`config.yml live_breadth:`), a
backstop GH-cron workflow (`.github/workflows/live-breadth.yml`), and tests
(`tests/test_live_breadth.py`). **What the operator must do to arm it:** run the
poller loop on the VPS/Mac host (below), or rely on the coarse GH-cron backstop.
Until then the surface falls back to the baked nightly breadth numbers — never
blank.

---

## Architecture (one glance)

```
VPS / Mac host loop                                site (static)
  live_breadth_poller.py  ──1 REST call/cycle──►  api.polygon.io
    --rth-only --publish        (full-market snapshot, NO tickers filter)
        │                                              │  15-min delayed (STANDARD)
        │  join in-memory ▼                            ▼
        │   data/<ns>/_closes_cache.parquet  (nightly-baked per-name thresholds:
        │   data/<ns>/constituents.parquet    prev_close / MA50 / MA200 / 52w band)
        │   ns ∈ {breadth, midcap_breadth, smallcap_breadth}  = S&P 500 / 400 / 600
        ▼
   site/live/breadth.json  ──git add -f → commit → push (main)──►  Pages deploy
        │                    (same mechanism as intraday-fastpath overlay.json)
        ▼
   live.js fetches live/breadth.json (same-origin, relative) → surface renders
```

- **ONE Polygon full-market snapshot per cycle** (D6) — the no-`tickers`-filter
  form of `/v2/snapshot/locale/us/markets/stocks/tickers`. Never a per-symbol
  fan-out, never a websocket, never a new entitlement. Reuses
  `engine.live_quotes.parse_polygon_snapshot` (the existing pure parser).
- **Thresholds are baked, not recomputed live.** The poller reads the SAME
  nightly close caches the breadth builders write, computes MA50/MA200/52w-band
  once at startup, and refreshes only when a cache's date advances.
- **ZERO writes under `data/`** (house ledger law: intraday lanes discard `data/`
  writes). Output goes ONLY to `site/live/breadth.json` (+ a tmp state file under
  the OS tmpdir if needed).
- **Honest freshness:** `delay_min` = 15 (Polygon STANDARD vendor floor) + the
  snapshot's own staleness. `session` ∈ `pre`/`rth`/`post`/`closed`. `basis` is
  always `"poll"` — never a fabricated "live".
- **Display-tier only:** no store writes, no ledger advancement, and NO stance
  copy (the composite carries the numbers; "broad/thin/mixed" wording is the
  surface's job).

---

## Emitted schema (`site/live/breadth.json`)

Mirrors the nightly `breadth_scorecard()` payload so the surface renders either
through one code path (same tier keys/order as `build_site._BREADTH_TIERS`;
`pa50`/`pa200` are 0–100 percentages; counts are integers):

```json
{
  "schema": "live.breadth.v1",
  "asof": "2026-07-24T18:40:12Z",
  "delay_min": 16,
  "session": "rth",
  "basis": "poll",
  "tiers": [
    {"key": "large", "label": {"en": "Large cap", "zh": "大盘"}, "univ": "S&P 500",
     "n": 501, "adv": 260, "dec": 241, "unch": 0, "adv_pct": 51.9,
     "pa50": 60.4, "pa200": 64.6, "nh": 23, "nl": 5, "net_nh": 18},
    {"key": "mid",  "label": {"en": "Mid cap", "zh": "中盘"}, "univ": "S&P 400", ...},
    {"key": "small","label": {"en": "Small cap","zh": "小盘"}, "univ": "S&P 600", ...}
  ],
  "comp": {"n": 1101, "adv": 552, "dec": 549, "unch": 0, "adv_pct": 50.1,
           "pa50": 65.9, "pa200": 69.0, "net_nh": 45},
  "meta": {"missing": {"large": 2, "small": 3}, "snapshot_names": 1101}
}
```

`comp` carries NO `label`/`verdict`/`tone`. Members absent from the snapshot are
excluded from every denominator and counted in `meta.missing` per tier — never
treated as unchanged. On offline / no-key / dead feed the payload is fail-soft:
`"tiers": []`, null composite ratios, `"meta": {"note": ...}`.

---

## Prerequisites

1. **`POLYGON_API_KEY`** (or `MASSIVE_API_KEY`) in the host env — the same key
   the live overlay uses. Never appears in logs, output JSON, or tests. Absent a
   key the poller emits fail-soft empty payloads (surface falls back to baked).
2. **The nightly breadth caches present on the host:**
   `data/breadth/_closes_cache.parquet` (+ `midcap_breadth`, `smallcap_breadth`)
   and the sibling `constituents.parquet`. These are written by the nightly
   `collect` run (`collectors/breadth.py` and the mid/small subclasses). On the
   Mac Studio nightly host they already exist; on a fresh VPS run one nightly
   `collect` (or restore from R2/cache) first. Missing → that tier emits empty.
3. **Git push rights** for the `--publish` path (the host commits
   `site/live/breadth.json` to `main`, exactly as the intraday-fastpath does).

---

## Deploy — host loop (D7, primary)

Runs beside `live_flow_poller` on the VPS/Mac host. Two options:

### A. launchd (Mac Studio) — `--rth-only`, re-fired daily

`--rth-only` self-exits at 16:05 ET; a `StartCalendarInterval` at 09:25 ET on
weekdays re-launches it. Example plist (`~/Library/LaunchAgents/com.macro.live-breadth.plist`):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0"><dict>
  <key>Label</key><string>com.macro.live-breadth</string>
  <key>ProgramArguments</key>
  <array>
    <string>/path/to/venv/bin/python</string>
    <string>-m</string><string>scripts.live_breadth_poller</string>
    <string>--rth-only</string><string>--publish</string>
  </array>
  <key>WorkingDirectory</key><string>/path/to/Macro Dashboard</string>
  <key>EnvironmentVariables</key>
  <dict><key>POLYGON_API_KEY</key><string>…</string></dict>
  <key>StartCalendarInterval</key>
  <array>
    <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>9</integer><key>Minute</key><integer>25</integer></dict>
    <!-- …repeat Weekday 2–5… -->
  </array>
  <key>StandardOutPath</key><string>/tmp/live_breadth.log</string>
  <key>StandardErrorPath</key><string>/tmp/live_breadth.err</string>
</dict></plist>
```

```bash
launchctl load  ~/Library/LaunchAgents/com.macro.live-breadth.plist
launchctl start com.macro.live-breadth          # or wait for 09:25 ET
```

### B. systemd (VPS) — long-running with SIGTERM

The poller runs continuous cycles and self-exits at 16:05 ET under `--rth-only`;
outside RTH `--rth-only` exits immediately, so pair it with a timer that fires at
09:25 ET. SIGTERM is honored gracefully (finishes the current cycle, then exits).

```ini
# /etc/systemd/system/live-breadth.service
[Service]
WorkingDirectory=/opt/macro-dashboard
Environment=POLYGON_API_KEY=…
ExecStart=/opt/macro-dashboard/venv/bin/python -m scripts.live_breadth_poller --rth-only --publish
Restart=on-failure
KillSignal=SIGTERM
TimeoutStopSec=120
```

Set `VPS_LIVE_PRIMARY=true` as a repo variable once the host loop is soaked — the
GH-cron backstop then goes dark (manual `workflow_dispatch` still available).

## Deploy — GH-cron backstop (coarse floor)

`.github/workflows/live-breadth.yml` runs `--once --publish` at :05/:35 past the
hour, 13:00–20:59 UTC Mon–Fri, on the self-hosted light runner. It cannot hold a
1–2 min cadence (that's why the host loop is primary), but keeps
`breadth.json` refreshed ~every 30 min when the host loop is down. Arm by setting
the `POLYGON_API_KEY` repo secret; it self-disables when `VPS_LIVE_PRIMARY=true`.

---

## Verify

```bash
# 1. Single cycle, no network — must emit a well-formed fail-soft payload
python -m scripts.live_breadth_poller --once --offline
python -c "import json;p=json.load(open('site/live/breadth.json'));print(p['schema'],p['session'],p['basis'],p['tiers'])"
#   -> live.breadth.v1 <session> poll []

# 2. Single live cycle (needs POLYGON_API_KEY + the nightly caches on the box)
POLYGON_API_KEY=… python -m scripts.live_breadth_poller --once -v
python -c "import json;p=json.load(open('site/live/breadth.json'));\
print('tiers',[(t['key'],t['n'],t['adv'],t['dec']) for t in p['tiers']]);\
print('comp',p['comp']['adv'],p['comp']['dec'],'pa50',p['comp']['pa50']);\
print('delay_min',p['delay_min'],'missing',p['meta'].get('missing'))"
#   During RTH: adv+dec ≈ 1000+ across the three tiers; delay_min ≈ 15-17.

# 3. Publish path (host-side; commits to main)
python -m scripts.live_breadth_poller --once --publish
git log -1 --oneline -- site/live/breadth.json     # -> "live: breadth poll <ts>"

# 4. Same-origin fetch on the live site
curl -s https://<host>/live/breadth.json | python -m json.tool | head -20
```

Sanity: `session` should be `rth` during 09:30–16:00 ET, `pre`/`post` at the
edges, `closed` overnight/weekends. `meta.missing` a handful per tier is normal
(a member the snapshot didn't return, or the close cache holds too shallowly for
a 200DMA); a large `missing` count means a stale/partial snapshot — the honest
`delay_min` will also be high.

---

## Rollback

The lane is additive and display-tier. To disable with zero surface breakage:

1. **Stop the producer.** `launchctl unload …/com.macro.live-breadth.plist`
   (Mac) or `systemctl stop live-breadth` (VPS); set `VPS_LIVE_PRIMARY=true`
   is NOT rollback (that only disables the backstop) — to stop the backstop too,
   disable the `live-breadth` workflow in the Actions UI.
2. **The surface auto-degrades.** With no fresh `breadth.json` the surface falls
   back to the baked nightly breadth numbers (the same fallback ladder as
   overlay.json). The last committed `breadth.json` simply ages; its `delay_min`
   grows and the surface can flag it stale.
3. **Full revert.** Revert this PR — `site/live/breadth.json` is gitignored, so
   removing the poller stops all writes; no store or ledger was ever touched, so
   there is nothing to unwind under `data/`.

---

## Notes

- **No data/ writes, ever.** Verify after any host run: `git status data/` must
  be clean (the poller only reads the caches). If `data/` shows changes, a
  non-poller process wrote them — investigate that, not this lane.
- **Symbol mapping.** Polygon uses dotted class shares (`BRK.B`); the breadth
  caches use the Yahoo dash form (`BRK-B`). The poller folds dot→dash via
  `engine.live_breadth.canonical_symbol` — the SAME single mapping the breadth
  collector already applies. No second mapping is introduced.
- **Cadence.** `config.yml live_breadth.cadence_sec` (default 90, clamped 60–120)
  + `jitter_sec` (default 10). The vendor delay floor defaults to the shared
  `live.delayed_min` (15); override with `live_breadth.delayed_min` only.

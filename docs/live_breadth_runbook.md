# Live breadth runbook (Phase 2 — `site/live/breadth.json`)

Operator deploy + verify + rollback for the live intraday market-breadth poller
(`research/LIVE_TAPE_SCOREBOARD_MASTERPLAN.md` Phase 2, decisions D6/D7). This is
the **engine lane only** — it produces the display-tier JSON the surface lane
(compact adv/dec scoreboard on `us_stocks`) consumes.

**Truth boundary (the point of this doc's last revision):** a degraded, stale,
holiday, or failed live snapshot can NEVER overwrite the valid baked nightly
breadth board. Every payload carries an explicit `usable` boolean, adjudicated
server-side by `engine.live_breadth.evaluate_usable` — the browser's job is only
to check `usable === true` and otherwise leave the baked numbers alone. See
"The `usable` contract" below.

**What ships:** the poller (`scripts/live_breadth_poller.py`), its pure
join/count + truth-boundary core (`engine/live_breadth.py`), a config block
(`config.yml live_breadth:`), the CANONICAL installed producer
(`app/deploy/macro-live-breadth.service`/`.timer`, wired into
`app/deploy/live-setup.sh`), a backstop GH-cron workflow
(`.github/workflows/live-breadth.yml`), semantic health in `/api/status` and
`scripts/check_vps_live_health.py`, and tests (`tests/test_live_breadth.py`,
`tests/test_live_breadth_js_contract.py`). **Arming it is a repo commit and
nothing else:** `app/deploy/update.sh` self-arms the lane on the running VPS the
same way the Prophet Live lane does (see "Deploy" below), so a merge to `main`
installs and enables it on the next pull — no manual step, no operator act.
Until it runs, the surface falls back to the baked nightly breadth numbers —
never blank, and never a zero-vs-stale confusion (fail-soft payloads are always
`usable: false`, never zero-as-real).

---

## Architecture (one glance)

```
VPS (canonical, live-setup.sh installed)            site (static)
  macro-live-breadth.timer  ──every ~2m, US session──►
  macro-live-breadth.service
    live_breadth_poller.py  ──1 REST call/cycle──►  api.polygon.io
      --once  (NO --publish)       (full-market snapshot, NO tickers filter)
          │                                              │  15-min delayed (STANDARD)
          │  join in-memory ▼                            ▼
          │   data/<ns>/_closes_cache.parquet  (nightly-baked per-name thresholds:
          │   data/<ns>/constituents.parquet    prev_close / MA50 / MA200 / 52w band)
          │   ns ∈ {breadth, midcap_breadth, smallcap_breadth}  = S&P 500 / 400 / 600
          │
          │  evaluate_usable() — the truth boundary: feed/session/tiers/source-age/
          │  coverage all gate `usable`; nothing but a healthy snapshot passes.
          ▼
   $MACRO_LIVE_DIR/breadth.json   (= /var/lib/macro-live/public/live/breadth.json)
        │  atomic rename                              ▲
        ▼                                              │  no VPS write ⇒ this path is
   Caddy `handle /live/breadth.json` (Cache-Control     │  simply absent; Caddy's route
   no-store) ──same-origin fetch──►  live.js            │  falls back to the STATIC
        │                                               │  site/live/breadth.json copy
        ▼                                               │  (GH-cron backstop below)
   applyBreadth(): usable !== true ⇒ EARLY RETURN, ─────┘
   baked nightly board stays exactly as rendered
```

- **ONE Polygon full-market snapshot per cycle** (D6) — the no-`tickers`-filter
  form of `/v2/snapshot/locale/us/markets/stocks/tickers`. Never a per-symbol
  fan-out, never a websocket, never a new entitlement. Reuses
  `engine.live_quotes.parse_polygon_snapshot` (the existing pure parser).
- **Thresholds are baked, not recomputed live.** The poller reads the SAME
  nightly close caches the breadth builders write, computes MA50/MA200/52w-band
  once at startup, and refreshes only when a cache's date advances.
- **ZERO writes under `data/`** (house ledger law: intraday lanes discard `data/`
  writes). Output goes to `$MACRO_LIVE_DIR/breadth.json` on the canonical VPS
  lane (falls back to `config.site_dir()/live/breadth.json` off the VPS — dev /
  the GH-cron backstop), + a tmp state file under the OS tmpdir if needed.
- **Two clocks, both honest.** `delay_min` stays the existing descriptive number
  (15-min vendor floor + snapshot staleness). `source_asof`/`source_age_min` are
  the SOURCE clock, first-class — the actual vendor snapshot timestamp, never
  inferred from filesystem mtime. `built_at` (= `asof`, kept for back-compat) is
  when THIS producer wrapped the artifact — a fresh `built_at` says nothing
  about how stale the underlying snapshot was.
- **Display-tier only:** no store writes, no ledger advancement, and NO stance
  copy (the composite carries the numbers; "broad/thin/mixed" wording is the
  surface's job).

---

## The `usable` contract (truth boundary)

`engine.live_breadth.evaluate_usable` is the ONE adjudicator for "may the
browser replace the nightly board?" — server-side, never re-derived in JS.
First failing check wins, in this order:

| # | check | `unusable_reason` |
|---|---|---|
| 1 | `feed_status != "ok"` | `"feed_" + feed_status` (e.g. `feed_no_key`, `feed_offline`) |
| 2 | `session == "closed"` or falsy | `session_closed` |
| 3 | fewer than 3 tiers present | `tiers_incomplete` |
| 4 | `source_age_min` is `null` | `no_source_clock` |
| 5 | `source_age_min > 25` | `source_stale` |
| 6 | `coverage_pct` is `null` | `no_coverage` |
| 7 | `coverage_pct < 90` | `coverage_low` |

Else `usable: true`, `unusable_reason: null`. A negative `source_age_min` (clock
skew — the source ahead of the build) is ALLOWED, never rejected — it is not
evidence of staleness.

`templates/live.js`'s `applyBreadth` mirrors this on the client as a fail-CLOSED
gate: `usable !== true` is the load-bearing first check (a legacy v1 payload
carrying no `usable` key is rejected outright), followed by a comp-shape check,
`session !== "closed"`, a present+fresh `source_age_min`, and a fresh
`built_at`/`asof` — every check returns EARLY with ZERO DOM writes. The baked
nightly numbers (adv/dec, %>50/200DMA, net new-highs) are the ONLY thing on the
page unless every one of those passes.

---

## Emitted schema (`breadth.json`)

Mirrors the nightly `breadth_scorecard()` payload so the surface renders either
through one code path (same tier keys/order as `build_site._BREADTH_TIERS`;
`pa50`/`pa200` are 0–100 percentages; counts are integers). New keys (this wave)
are purely additive — `schema` stays `"live.breadth.v1"`:

```json
{
  "schema": "live.breadth.v1",
  "asof": "2026-07-24T18:40:12Z",
  "built_at": "2026-07-24T18:40:12Z",
  "source_asof": "2026-07-24T18:24:12Z",
  "source_age_min": 16.0,
  "delay_min": 16,
  "session": "rth",
  "basis": "poll",
  "feed_status": "ok",
  "usable": true,
  "unusable_reason": null,
  "coverage": {"n": 1101, "expected": 1500, "pct": 73.4},
  "producer": "vps:macro-live-breadth",
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
treated as unchanged. On offline / no-key / dead feed / no-thresholds the
payload is fail-soft: `"tiers": []`, null composite ratios, `usable: false`
ALWAYS (never true — `empty_payload` structurally cannot return `usable: true`),
`"meta": {"note": ...}`.

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
   `collect` (or restore from R2/cache) first. Missing → that tier emits empty
   (and `usable` stays false via `tiers_incomplete`/`feed_no_thresholds`).
3. **`MACRO_LIVE_DIR`** exported (VPS: already done by `live-setup.sh` step
   `[2/6]` into `/etc/macro-live.env`, e.g.
   `/var/lib/macro-live/public/live`) — `_out_path()` honours it directly (no
   extra `live` segment appended); without it the poller falls back to
   `config.site_dir()/live/breadth.json` (dev / the GH-cron backstop, which
   commits that path to `main`).

---

## Deploy — VPS (canonical, D7 primary)

**Ownership arrives by commit, not by operator act.** `app/deploy/update.sh`
carries a self-arming block for this lane (the same one `macro-live-prophet`
uses): on an already-provisioned box it installs the unit pair and runs
`systemctl enable --now macro-live-breadth.timer` when the units change **or
when `/etc/systemd/system/macro-live-breadth.timer` is simply absent**. That
absent-file clause is the whole point — the unit did not exist the last time
anyone ran `live-setup.sh`, so a CHANGED-only trigger would install a timer
nobody ever enables. `live-setup.sh` also lists the pair, which covers a fresh
box; neither path needs a human.

The timer fires every ~2 minutes across the US session
(`app/deploy/macro-live-breadth.timer`'s `OnCalendar`, widened from the sibling
Prophet Live lane's window); each tick runs
`python -m scripts.live_breadth_poller --once` with
`MACRO_LIVE_PRODUCER=vps:macro-live-breadth`, writing
`$MACRO_LIVE_DIR/breadth.json` by atomic rename. A fault in this lane can never
take the served site down — it reads only the nightly-baked close caches off
disk and writes only its own artifact.

**The VPS lane deliberately carries NO `--publish`.** Publication here *is* the
atomic rename into `$MACRO_LIVE_DIR` = `/var/lib/macro-live/public/live`, the
path Caddy serves first (`no-store`), so the artifact is live the moment it
lands. `--publish` is the GH backstop's mechanism — it commits
`site/live/breadth.json` to `main` so the STATIC fallback advances on a box
where this lane is down. Keeping the two apart is what leaves exactly ONE writer
claiming primary ownership. It is also required mechanically: with
`MACRO_LIVE_DIR` set, the output path is outside the git work tree, so
`git add -f` fails, `publish()` returns False, and `--once --publish` correctly
exits non-zero — the unit would fail on every tick.
(`tests/test_vps_live_orchestration.py::test_breadth_vps_lane_never_publishes_via_git`)

```bash
systemctl list-timers macro-live-breadth.timer
journalctl -u macro-live-breadth.service -n 30 --no-pager
sudo bash app/deploy/live-setup.sh    # fresh box only; update.sh self-arms an existing one
```

Set `VPS_LIVE_PRIMARY=true` as a repo variable ONLY once production breadth (the
systemd lane, not just the backstop) is proven live — the truth boundary means a
degraded run from either producer can never overwrite the baked board regardless
of which one is primary, but the repo variable also gates the GH-cron backstop's
schedule (below), so flip it only once the VPS lane is confirmed healthy via
`/api/status` / `check_vps_live_health.py`.

### There is no second producer — and do not add one

The launchd plist this runbook used to document is **deliberately gone**. It was
never installed by anything, its example paths (`/opt/macro-dashboard`, a bare
`venv/`) do not exist on the box, and it carried `--publish` — so following it
would have created a SECOND writer racing the systemd lane for the same
artifact, which is the exact failure this lane was built to end.

Exactly two producers exist, and they own different paths:

| producer | writes | when |
|---|---|---|
| `macro-live-breadth.timer` (VPS, **primary**) | `$MACRO_LIVE_DIR/breadth.json`, served `no-store` | every ~2 min, US session |
| `.github/workflows/live-breadth.yml` (backstop) | `site/live/breadth.json` on `main`, the STATIC fallback | :05/:35, only while `VPS_LIVE_PRIMARY != true` |

If you need a producer on a non-VPS host, run
`python -m scripts.live_breadth_poller --rth-only` **without** `--publish` and
point `MACRO_LIVE_DIR` at that host's live dir. Never arm a third writer against
the same artifact, and never hand-install a unit outside `update.sh` /
`live-setup.sh` — an artifact whose `producer` field flaps between values is the
signature of exactly that mistake, and `/api/status` will show it.

## Deploy — GH-cron backstop (coarse floor)

`.github/workflows/live-breadth.yml` runs `--once --publish` at :05/:35 past the
hour, 13:00–20:59 UTC Mon–Fri, on the self-hosted light runner, with
`MACRO_LIVE_PRODUCER=gh:live-breadth-backstop`. It commits the STATIC
`site/live/breadth.json` copy to `main` (the intraday-fastpath mechanism) —
distinct from the VPS lane's `$MACRO_LIVE_DIR` write, and Caddy only falls back
to it when the VPS-owned path is absent. It cannot hold a 1–2 min cadence
(that's why the VPS lane is primary), but keeps a floor refreshed ~every 30 min
when the VPS lane is down. Arm by setting the `POLYGON_API_KEY` repo secret; it
self-disables when `VPS_LIVE_PRIMARY=true`. A requested publish that fails now
REDS this workflow run (no more swallowed `|| echo "::warning"`).

---

## Verify

```bash
# 1. Single cycle, no network — must emit a well-formed fail-soft payload,
#    ALWAYS usable:false (never true — the fail-soft path structurally cannot).
python -m scripts.live_breadth_poller --once --offline
python -c "import json;p=json.load(open('site/live/breadth.json'));\
print(p['schema'],p['session'],p['basis'],p['tiers'],'usable=',p['usable'],p['unusable_reason'])"
#   -> live.breadth.v1 <session> poll [] usable= False feed_offline

# 2. Single live cycle (needs POLYGON_API_KEY + the nightly caches on the box)
POLYGON_API_KEY=… python -m scripts.live_breadth_poller --once -v
python -c "import json;p=json.load(open('site/live/breadth.json'));\
print('tiers',[(t['key'],t['n'],t['adv'],t['dec']) for t in p['tiers']]);\
print('comp',p['comp']['adv'],p['comp']['dec'],'pa50',p['comp']['pa50']);\
print('delay_min',p['delay_min'],'source_age_min',p['source_age_min']);\
print('usable',p['usable'],p['unusable_reason'],'coverage',p['coverage'],'producer',p['producer'])"
#   During RTH with a healthy feed: adv+dec ≈ 1000+, source_age_min <= 25,
#   coverage.pct >= 90, usable=True, unusable_reason=None.

# 3. Publish path — VPS canonical (writes $MACRO_LIVE_DIR, no git needed there;
#    a requested publish that fails now exits NON-ZERO, FROZEN CONTRACT §2d/§4)
python -m scripts.live_breadth_poller --once --publish; echo "rc=$?"

# 3b. Publish path — dev / GH-cron backstop (commits site/live/breadth.json)
python -m scripts.live_breadth_poller --once --publish
git log -1 --oneline -- site/live/breadth.json     # -> "live: breadth poll <ts>"

# 4. Same-origin fetch on the live site
curl -s https://<host>/live/breadth.json | python -m json.tool | head -20

# 5. Semantic health — VPS-owned lane, dead-man, and browser eligibility all in one
curl -s https://<host>/api/status | python -m json.tool | grep -A 12 '"breadth"'
python -m scripts.check_vps_live_health --url https://<host>/api/status
```

Sanity: `session` should be `rth` during 09:30–16:00 ET, `pre`/`post` at the
edges, `closed` overnight/weekends AND full-day NYSE holidays (Good Friday,
Thanksgiving, observed fixed-date closures — via `lib.nyse_calendar.is_session`,
checked before any time-of-day logic). `meta.missing` a handful per tier is
normal (a member the snapshot didn't return, or the close cache holds too
shallowly for a 200DMA); a large `missing` count drags `coverage.pct` down and
can flip `usable` to `false` via `coverage_low`.

**During the expected live window (weekday, UTC hour 14–20, ~10:00–16:00 ET),
`check_vps_live_health.py` requires `usable: true`, `source_age_min <= 25`,
`coverage_pct >= 90`, and a non-empty `producer`** — outside that window, or
whenever `session == "closed"`, it requires nothing about freshness (stale
last-session data outside a session is legitimate evidence, not a fault). The
`breadth` key is ABSENT-OK (same precedent as `cn_prophet_live`): a box that
has not yet run `live-setup.sh`'s breadth lane never reds the dead-man.

---

## Rollback

The lane is additive and display-tier. To disable with zero surface breakage:

1. **Stop the VPS producer.** `systemctl disable --now macro-live-breadth.timer
   macro-live-breadth.service` (the canonical lane). If also running the dev
   launchd fallback: `launchctl unload …/com.macro.live-breadth.plist`. Setting
   `VPS_LIVE_PRIMARY=true` is NOT rollback (it only disables the GH-cron
   backstop's schedule) — to stop the backstop too, disable the `live-breadth`
   workflow in the Actions UI.
2. **The surface auto-degrades — TWICE over.** With no fresh `breadth.json` at
   all the surface falls back to the baked nightly breadth numbers (the same
   fallback ladder as `overlay.json`). Even if a stale/degraded `breadth.json`
   IS still being written, `applyBreadth`'s fail-CLOSED gate (`usable !== true`,
   a stale `source_age_min`, or a stale `built_at`/`asof`) means the baked
   numbers stay untouched regardless — the truth boundary does not depend on
   the producer being fully stopped to be safe.
3. **Full revert.** Revert this PR. `site/live/breadth.json` (the GH-cron
   backstop's path) is gitignored, so removing the poller stops all git writes;
   no store or ledger was ever touched, so there is nothing to unwind under
   `data/`. The VPS unit files simply stop being reinstalled on the next
   `live-setup.sh` run — a manual `systemctl disable --now` on the box is still
   needed to stop an already-installed timer immediately.

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
  + `jitter_sec` (default 10) governs the long-running loop mode
  (`--rth-only`, dev/launchd fallback only). The canonical VPS lane's cadence is
  the systemd timer (`macro-live-breadth.timer`, every ~2 min), independent of
  this config block. The vendor delay floor defaults to the shared
  `live.delayed_min` (15); override with `live_breadth.delayed_min` only.
- **Holiday awareness (Defect 3).** `session_tag()`/`within_rth()` consult
  `lib.nyse_calendar.is_session()` for the ET calendar date BEFORE any
  time-of-day logic — a full-day NYSE closure (Good Friday, Thanksgiving,
  observed fixed-date holidays) always tags `"closed"`, regardless of clock
  time. Early closes are NOT modeled (out of scope; `lib.nyse_calendar` doesn't
  model them either) — a shortened session still ticks the ordinary
  pre/rth/post windows.
- **One canonical owner (Defect 5).** Before this wave, no VPS install ran
  `scripts.live_breadth_poller` at all — only the coarse GH-cron backstop
  produced `breadth.json`, and a VPS-run poller had no env-overridable output
  path anyway (`config.site_dir()` is repo-relative). `_out_path()` now honours
  `MACRO_LIVE_DIR` (already exported by `live-setup.sh` into
  `/etc/macro-live.env`) directly — no extra `live` segment appended — and
  `app/deploy/macro-live-breadth.service`/`.timer` is the installed, canonical
  producer. Every payload also carries `producer` (`MACRO_LIVE_PRODUCER` env,
  else `"host:" + hostname`) so `/api/status` and the dead-man can tell an
  unowned box from the systemd lane from the GH-cron backstop.

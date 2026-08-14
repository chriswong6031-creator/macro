# Track D — Live data plane + cadence census (Live Entry Radar PR-0 archaeology)

Census only, no design decisions. Macro checkout is **sparse** (`data/`,
`site/`, `mockups/` absent locally); existence/shape checks below use `git
ls-tree -r HEAD -- <path>` (reads the tracked commit tree regardless of the
sparse cone). Mastermind (`/Users/chriswong/Documents/Cluade/Mastermind`) is
a full checkout, read-only. charting-app (Terminal) is out of scope/access —
its facts are relayed from the Macro masterplan's own citations, flagged
inline. `UNVERIFIED` = not confirmed by a direct read this session. No `gh`
calls made (task constraint); PR/CI state below is a static-file snapshot.

---

## 1. prophet-live architecture, element by element

**Backstop — `.github/workflows/prophet-live.yml`** (189/189 lines). Header
(2-46): GitHub cron can't carry the product cadence — measured 2026-07-30,
`marketing-hot-tape.yml` (`*/5` RTH) fired 09:07Z then 12:19Z (~3h12m apart);
`live-quotes.yml` (`*/15`) ~90min apart — "not purchasable at any price" with
~58 workflows in-repo. Three crons span 13:25Z-21:15Z for both DST regimes
(48-67); `live_states.in_window` trims the off-season edge. `permissions:
contents: read` (79) + zero git steps = G0.2 enforcement.
`concurrency:{group: prophet-live, cancel-in-progress: false}` (81-88) —
never overlap, never cancel in-flight. Gate (103): `PROPHET_LIVE_DISABLED !=
'true' && (workflow_dispatch || VPS_LIVE_PRIMARY != 'true')` — kill switch
always binds inside a host gate that self-disables once VPS is primary.
`runs-on: ubuntu-latest` (104), never the render pool. Shallow+sparse+
blobless checkout (110-133); `pyyaml boto3` only, no pandas (148); fetches the
`live-data` branch's `quotes.json` to runner-local scratch, never staged
(150-171); runs `python -m scripts.prophet_live_evaluator` (173-189).

**VPS timer (the real product lane)** — `app/deploy/macro-live-prophet.
{service,timer}` (48+28 lines, both full). `ExecStart=...python -m
scripts.prophet_live_evaluator` (`.service:35`). Resource caps MEASURED
2026-07-30 vs. a 1,742-name pack + 2,025-symbol snapshot (`.service:11-25`):
0.006s wall/CPU compute, ~95MB peak RSS; `MemoryHigh=256M`/`Max=512M`
(~2.7x/~5x measured peak), `CPUQuota=60%`, lowest `Nice`/`CPUWeight`/
`IOWeight` tier (deliberately loses scheduling vs. the quote lanes it reads).
`OnCalendar=Mon..Fri *-*-* 13..21:03/5:00 UTC` (`.timer:20`) — `:03/5` not
`:00/5` gives `macro-live-snapshot` (fires `:00/5`, up to ~230s to publish) a
3-min head start.

**MACRO_LIVE_DIR ladder** — `engine/neuralweb/market_packet.py:86-106`,
`_live_dir()`: (a) `$MACRO_LIVE_DIR` override, else (b)
`/var/lib/macro-live/public/live` if `.is_dir()`, else (c) `root/site/live`.
Shared by `scripts/notify_turn_events.py:122`, `app/main.py:99`. Runtime
layout (`docs/VPS_LIVE_ORCHESTRATION.md:76-96`): `/opt/macro` (code+canonical
checkout) · `/opt/macro/site/live` (per-process staging) ·
`/var/lib/macro-live/public/live` (atomic-published `/live/*`, Caddy
`no-store`) · `/var/lib/macro-live/state` (locks/fingerprints/lane
status/quote cache) · `/var/lib/macro-live/data/intraday` (mutable VPS-only
hourly bars).

**Event spool** — `engine/prophet_live/r2io.py:34`:
`EVENTS_PREFIX = "live_flow/prophet_live_events"`; `events_key(session,stamp)`
(157) mints one R2 object per pass-with-a-transition. Confirmed live:
`R2_AND_DELIVERY_PLANE_TRUTH_CENSUS_2026-08.md:127-128` lists R2 keys
`live_flow/{prophet_live,prophet_marks}.json`, `prophet_live_armed.json`,
`prophet_live_events/**` as `PRIVATE_OPERATIONAL`. **No-intraday-ledger-
writes enforcement** (three layers): workflow `permissions: contents: read`
+ zero git steps; the VPS service also runs no git command; and
`prophet_live_evaluator.py:27-33` docstring law — "writes NOTHING under
`data/`... outside the git work-tree... never under `data/`."

**Nightly reconciliation entry point** — `scripts/reconcile_prophet_live.py`
(1-38 read): `python -m scripts.reconcile_prophet_live --nightly`. Turns the
R2 event spool into `data/prophet_live/forward.parquet` — "the ENTIRE
evidence base" for the intraday-cross-vs-next-close-fill hypothesis (joins
session-correct `confirmed`, `next_close_fill`, first-cross dedup, one price
basis). "Sole writer... intraday lane writes R2 only" (32-34, G0.2/RUL-P10).
**`git ls-tree -r HEAD -- data/prophet_live` returns zero tracked files**,
and it is not gitignored — no `forward.parquet` has ever been committed to
`main`. UNVERIFIED whether the ledger has zero accrued rows yet, or accrual
awaits an unmerged PR.

**Measured/nominal cadence.** Nominal: every 5 min via the VPS timer,
13:00-21:59 UTC weekdays, further gated to 09:25-16:15 ET (+grace) by
`in_window()` (§6). GitHub backstop cannot hit 5 min (measured 90min-3h12m
gaps above) — a ~90-min rollback path only. Actual VPS production hit-rate
vs. nominal is UNVERIFIED from a static census (needs live
`orchestrator_status.json`/sentinel state).

---

## 2. How live payloads reach users today

**VPS pull** — `app/deploy/update.sh:1-16`, installed as `macro-update`,
**cron every 3 minutes**, flock-serialized, pull-if-changed + `git reset
--hard` + rsync `site/`→`site.served` (atomic rename). Confirmed again at
`app/main.py:565` ("the 3-min site pull, the 5-min live overlay").

**Caddy** (`app/deploy/Caddyfile`) serves `root * /opt/macro/site.served`
(88). A short PUBLIC allowlist of `/live/*.json` (`quotes.json`,
`breadth.json`, `release_publications.json`, `staleness.json`, `wires.json`,
`intelligence.json` — 194,205-217,343,469) is served directly from
`/var/lib/macro-live/public`. **Everything else — including
`prophet_live.json` — is NOT allowlisted**, so it hits the `@reg_asset`
matcher (341-346) and routes through `reverse_proxy 127.0.0.1:8000` →
`/api/regwall/check` → `/api/paywall/check` (347-361) before serving.
Verified LIVE: `research/R2_AND_DELIVERY_PLANE_TRUTH_CENSUS_2026-08.md:76` —
`www.mastermind-x.com/live/prophet_live.json` → **`401`, `no-store`**. **A
new gated live path inherits this for free by omission from the allowlist —
no new gate code needed.** Server-side, `app/main.py:553-556`
`_live_artifact(name)` prefers `$MACRO_LIVE_DIR/name`, falls back to
`SITE/live/name`; no dedicated `prophet_live` route exists (`grep
prophet_live app/main.py` empty) — served via the generic gated-static path.

**Client precedent #1 — `templates/dashboard.html.j2:17920-19140`** (the
direct template for this kind of payload): `PLV_URL = 'live/prophet_live.json'`
(17943); `PLV_EVERY = 120000` — "producer writes every ~5 min, so 120s bounds
staleness at ~2 min for ~2.5 GETs/artifact" (17944). Plain
`fetch(PLV_URL,{cache:'no-cache'})` (18583). First fetch unconditional (never
`document.hidden`-gated, so hidden preview panes still paint); later fetches
visibility-gated with a `PLV_FLOOR=30000`ms floor (19129-19137). One shared
artifact, one poll, two panels.

**Client precedent #2 — `templates/live.js:1-60`** (of 573): `POLL =
(LIVE_POLL_SEC || 60) * 1000` (41, default 60s); 3 price sources in priority
(Worker `/quotes` → static full-universe snapshot → `live/overlay.json`);
also opens `/ws/tape` directly for 6 macro instruments (57, §4).
`china_risk_state_live.js:29,232,243` mirrors the same 60s-poll pattern.

**Conclusion:** house idiom = one small gated JSON at `live/<name>.json`
(atomic-rename into `$MACRO_LIVE_DIR`, deliberately omitted from the Caddy
allowlist), polled client-side every 60-120s against a ~5-min producer
cadence (2.5-5x poll:produce ratio is the norm), visibility-gated with an
unconditional first fetch. No new server route or poll framework needed —
`dashboard.html.j2`'s prophet-live block is a literal template.

---

## 3. Market data entitlements — the "Massive" vendor integration

Primary source: `research/MASSIVE_ADVANCED_INTEGRATION_MASTERPLAN_BY_FABLE.md`
(894 lines; §1,§1.1,§2,§3,§4.3,§5,§12 read). Massive = rebranded Polygon.io
(PyPI now `massive` v2.8.x; `polygon-api-client` frozen 1.16.3; hosts
`api.massive.com`/`socket.massive.com` canonical, `*.polygon.io` still
honored — 234-238). Licensing resolved 2026-08-09 (Enterprise Market Data
License + Redistribution Addendum executed, §0 gate CLOSED, 146-150).

**Entitlement verdicts** (TP-0 probe, `scripts/massive_entitlement_probe.py`,
table 159-176, run 2026-08-08T11:44Z market closed):

| Capability | Verdict |
|---|---|
| Real-time trades/NBBO (REST) | entitled |
| WS stocks real-time `T.*`+`Q.*` | entitled (auth+subscribe only at probe time) |
| Second aggregates (`A.*`) | entitled |
| Tick history (`v3/trades`) | **20y+** (non-empty at 2015 and 2005) |
| Quote history (`v3/quotes`) | entitled; depth re-verified to **2005** (§12) |
| Snapshots + grouped daily | entitled |
| Short interest/volume REST | entitled |
| Options trades/WS/realtime | **not entitled** (403) |
| Indices (`v3/snapshot`, WS) | **not entitled** |

(Licensing record: `research/licenses/MASSIVE_ENTITLEMENT_RECORD.md`, not
read this session.)

**Binding vendor facts** (§1.1, 196-238): **ONE simultaneous WebSocket
connection per cluster per product** on individual plans — "the single most
architecture-shaping constraint." Delayed/real-time are separate host
endpoints; `Q.*` NBBO is Advanced-tier only. Flat files (S3): `day_aggs_v1`
from 2006-03-15+, **`minute_aggs_v1` from ≥2010-06-15**; `trades_v1`/
`quotes_v1` LIST-verified to **2005-06**, 2024 `quotes_v1` at **~4.8GB/day gz
market-wide** — "a blanket multi-year quote backfill is TB-scale," so
strategy is episode-windowed files + per-name REST, never a bulk crawl.
**TP-0.5 measured** (§12, 2026-08-08~13:05Z): delayed/real-time **ARE
separate WS buckets**, but **overflow EVICTS THE OLDEST connection** — a
full slot silently kills the incumbent rather than refusing the newcomer
(§3.1b.4, 381-399). Load-bearing for any future WS client: singleton
discipline is existential; a `1008 max_connections` near a reconnect signals
a slot fight, not a benign retry.

**Current build state — NOT YET BUILT.** TP-1 (`engine/tick_plane/`, the
WS-consuming daemon) depends on TP-0.5, itself still "in progress" as of the
last §12 entry (2026-08-08). Confirmed directly: `find engine/tick_plane` →
no such directory; `grep -rl "tick_plane\|ingestd"` → zero hits outside the
masterplan. **No persistent Massive/Polygon WebSocket consumer exists in this
repo today.** `git ls-tree -r HEAD -- data/massive` → only
`capability_manifest.json` (the probe's output, not a data store).

**Daily OHLCV, today** — `collectors/massive_stock_day.py:1-50`. Derived
per-ticker `data/massive_stock_day/<TICKER>.parquet` from `day_aggs_v1`, a
**rolling ~5-year window**. R2 is canonical (~617MB, ~20k parquets); git
tracks only `_manifest.json`+`_backfill_state.json`.

**Intraday, today — HOURLY ONLY, not minute.**
`scripts/build_polygon_intraday.py:1-70`: `data/intraday/<T>.parquet`,
explicitly **15-min delayed** (`DELAYED_MIN=15`, 63), curated universe,
powers only the 4H chart timeframe. Gitignored (`.gitignore:66`). Distinct
from the VPS-side, mutable, also-hourly `/var/lib/macro-live/data/intraday`
— same name, two stores; do not conflate.

**Minute-bar historical store — DOES NOT EXIST.** Entitlement is proven deep
(minute flat files to 2010, tick history to 2005), but no code turns that
into a durable, queryable minute-bar store — that is unbuilt wave **TP-B**
(§5). The nearest existing thing — hourly, 15-min-delayed, curated-universe
`data/intraday/*.parquet` — is the wrong grain, latency, and universe for a
minute-bar replay substrate.

**Sizing anchors for the Radar's ~500-1500-name Probe Set** (comparators, not
requirements): masterplan §3.2 Tier-A pilot caps the planned tick-plane
capture at a **hard 600 symbols**. Nightly `prophet_live` *arming* probes
~1,730 names in 420s wall-clock on 4 workers/4 cores; `max_probe: 500`
starved the pass to `armed_n=0` (`config.yml:699-724`). The simplest live
loop (`live: max_universe: 150`, 617, `poll_seconds: 60`) caps well below the
Radar's target — a Radar at 500-1,500 names/5min sits between these two
existing lanes in both size and per-name compute weight.

---

## 4. Existing WebSocket/stream owners

**Macro — `app/tape.py:1-80`**: `TapeHub`, one process-wide task, connects to
**`wss://streamer.finance.yahoo.com`** (Yahoo unofficial — NOT
Massive/Polygon), 6 symbols (ES=F, NQ=F, YM=F, RTY=F, ^TNX, DX-Y.NYB per
`live.js:57`), fans out over same-origin `GET /ws/tape` (`Caddyfile:146`).
"No browser talks to the unofficial upstream directly... one shared upstream
connection" (6-9) — different vendor, different socket, no competition for
the Massive slot. **The Massive/Polygon stocks WebSocket is UNOWNED in
Macro**: no process connects to `socket.polygon.io/stocks` or
`socket.massive.com` today; TP-1 is unbuilt (§3);
`massive_entitlement_probe.py` opens only a transient probe connection.

**Terminal's Quote Hub (charting-app, out of scope — relayed from the Macro
masterplan, UNVERIFIED independently):** §2.1/§3.1b name `hub/lib/polygon.js`
as the second candidate client, today subscribing `AM.*` on the delayed
cluster with auto-demote-to-delayed. Recorded (not yet exercised) law: once
built, TP-1 is sole owner of the real-time cluster; the hub migrates to
TP-1's derived stream later — and since TP-0.5 showed delayed/real-time are
separate buckets, that migration does NOT fold into TP-1 automatically.

**Mastermind — verified directly, `data_layer/polygon.py:1-90`** (canonical
checkout): REST-only, `grep -n -i websocket` → zero hits. Thin wrapper over
`collectors.polygon_options.PolygonOptions` (the same vendored Macro client
via a `bot` sys.path shim); key resolves `POLYGON_API_KEY` falling back to
`MASSIVE_API_KEY` — Mastermind reuses Macro's key/client, holds no credential
of its own. "Delayed data is fine here: this is a paper book" (1-12). 60s TTL
cache. Repo-wide grep for websocket/massive/polygon (excluding other
sessions' worktrees) surfaced only this file.

**Net answer:** zero processes hold a live Massive/Polygon stocks WebSocket
open anywhere in Macro or Mastermind today. The single-connection slot is
unclaimed. A REST-based Radar (unlimited-call, ~<100 req/s soft ceiling —
already every daily/hourly collector's pattern) needs none of the §3.1b
singleton-discipline machinery; only a WS-based design would.

---

## 5. Breathing Platform program

Source: `research/BREATHING_PLATFORM_MASTERPLAN_BY_FABLE.md` (406 lines,
§3/§4 read) + `...CONTINUATION_HANDOFF_2026-08-10_SESSION4.md` (221/221 —
most recent Breathing-Platform doc found; no newer handoff exists).

**Three cadences, one engine** (§3, 240-263): (1) **Authority** (nightly,
shrinking) — ledgers, grading, pack re-arming, full render; (2) **Provisional
close-pass** (new, ~16:15-17:30 ET) — mac-side pass recomputing admission +
price-derived score legs from the day's closes, publishing "tonight's picks,
pending nightly confirmation" (evening-SLA fix: ~18:30 ET vs. ~11pm-1am ET);
(3) **Breathing lane** (existing, ~5min RTH) — append-semantics crossing
states, partial live rescore (signal 30 + runway 10 pts), risk badges,
2-pass-debounce alerts. "Provisional never touches `data/`" (261) — same
G0.2 law as prophet-live. **For a 5-min Radar:** cadence (2) is
~once/session, not directly reusable; cadence (3) is the closer analog
(5-min RTH, partial rescore) but scoped to the nightly-armed universe's
specific signal/runway legs — a sibling pattern to copy, not infrastructure
to plug into.

**Status as of SESSION4 (2026-08-10):** four PRs (#5217/#5220/#5222/#5223,
payload/receipt/SLA/renderer) built+reviewed, disarmed mid-session by an
unrelated repair, meant to re-arm as one wave. **"The evening lane has NEVER
RUN... `close-pass.yml`'s `publish` job has never fired... both FAILED with
`ModuleNotFoundError: No module named 'pandas'`"** — invisible for a day
(read downstream as absent data, not a fault); fixed incidentally by #5220.
**W-L1's gate needs five consecutive green sessions, which "cannot be built;
it accrues"** — unproven end-to-end as of that doc.

**Fresher in-repo signal (today):** `close-pass.yml`'s header carries a
**"CORRECTED 2026-08-13"** note: the lane "has never been green" until a
`git checkout -- .` discard step was added beside `--heal` — i.e. the
pandas/discard defect reads as addressed today, though no `gh` call
confirmed current CI/merge state this session. **Read status as:
architecture ratified and mostly built; W-L1 not proven green end-to-end as
of the last narrative doc, with today's comment suggesting the known defect
is fixed. Treat "is W-L1 live" as OPEN.**

**Evening render cadence** (`closing-bell.yml`): fires **16:05 ET** both DST
regimes (68-69) — "Build A," full provisional EOD render, non-ledger,
EXCLUDES `build_prophet`/`grade_us_board`/`us_pages`. Measured 109min behind
an 81min spine, lands ~17:55 ET vs. an 18:30 SLA (35min margin) — why the
provisional board is a separate lane. `close-pass.yml` fires **16:25 ET**
both regimes, separate concurrency group, straight to R2→VPS (not through a
render), landing ~30min after close regardless of the render spine.

**Asia-close cadence** (`asia-close.yml`): 7-slot schedule (06:00-11:15 UTC)
racing to be first because GitHub fires this repo's schedules 86-233min late
(measured); early-bird slots gated at an 08:25 UTC data floor (HK auction
~08:10 UTC=16:10 HKT; mainland EOD ~08:00-08:30 UTC) so net start ≈ the close.

---

## 6. Session calendar in live lanes

Exact module: **`lib/nyse_calendar.py`**, via
`engine/prophet_live/live_states.py:386-414` `in_window()`. ET wall clock via
`ZoneInfo("America/New_York")` (239); weekday check; then `from
lib.nyse_calendar import is_session; if not is_session(t.date()): return
False` (398-401) — the holiday-aware check, so the lane stands down on
Thanksgiving etc. **Fail-soft**: an exception degrades to weekday-only
(402-403), never blocks the pass. Window bounds from config (`window_et`
default 09:25/16:15) plus `window_grace_min` (default 10) at the end
(404-411). Same module backs `last_completed_session()` (425-431,
`expected_last_session`) — pack `as_of` must equal this date exactly or the
artifact ships `stale_pack`. Why the two-layer design: "systemd calendars
have no ET" (`macro-live-prophet.timer:1-10`) — the timer's `OnCalendar`
spans a UTC range covering both DST regimes, and `in_window()` is the only
thing that knows what "9:25 ET" means on a given day. Same module anchors
`macro-sentinel` (`VPS_LIVE_ORCHESTRATION.md:161`) and `closing-bell.yml`.

---

## 7. Recent hardening context (pointers only)

All three OPEN per `docs/ACTIVE_BUILD_MAP.md` (generated 2026-08-14T03:07:03Z;
no `gh` calls made, snapshot only):

- **#5555** — `prophet: stale-frame action safety — no current instruction
  off a dead tape` (`engine/prophet_management.py`, `build_prophet.py`). Not
  yet on `main` (`grep stale engine/prophet_management.py` → no hits).
  Implication: gate the *action* surface on frame freshness separately from
  the display — a Radar entry signal needs the same discipline (never emit a
  live "enter now" off a stale/dead-tape frame).
- **#5571** — `ops(prophet-us): availability hardening — bounded self-heal
  rescue lane + resilience layers` (mostly CI plumbing). Implication: an
  idiom already exists for "the nightly bake died, self-heal within a bound"
  that a new live lane should register with, not reinvent.
- **#5487** — `ops: nightly-liveness dead-man switch — the US bake went dark
  for two sessions and nothing reported it`. Implication: silence is the
  default failure mode here (this outage and the Breathing Platform's pandas
  failure, §5, both went undetected until named) — a new 5-min lane MUST
  register a positive liveness signal (content-advanced, not
  process-exited-0) with `macro-sentinel`/`freshness_sentinel.py`.

---

## Sources

Full reads: `prophet-live.yml` · `macro-live-prophet.{service,timer}` ·
`VPS_LIVE_ORCHESTRATION.md` · `prophet_live_evaluator.py` ·
`reconcile_prophet_live.py` · `massive_stock_day.py` ·
`build_polygon_intraday.py` · `app/tape.py` · Mastermind
`data_layer/polygon.py` (canonical checkout) ·
`BREATHING_PLATFORM_CONTINUATION_HANDOFF_2026-08-10_SESSION4.md`. Targeted
section reads (line ranges cited inline above): `market_packet.py` ·
`live_states.py` · `vps_live_orchestrator.py` ·
`MASSIVE_ADVANCED_INTEGRATION_MASTERPLAN_BY_FABLE.md` · `app/main.py` ·
`app/deploy/Caddyfile` · `BREATHING_PLATFORM_MASTERPLAN_BY_FABLE.md` ·
`closing-bell.yml` · `close-pass.yml` · `asia-close.yml` · `templates/live.js`
· `dashboard.html.j2` · `R2_AND_DELIVERY_PLANE_TRUTH_CENSUS_2026-08.md` ·
`config.yml`. Grep-only: `r2io.py` · `china_risk_state_live.js` ·
`docs/ACTIVE_BUILD_MAP.md` (generated 2026-08-14T03:07:03Z) · `.gitignore`.
Tracked-tree checks (`git ls-tree -r HEAD --`): `data/massive`,
`data/massive_stock_day`, `data/prophet_live`, `data/polygon`, `site/live`.

# Track D — Live data plane + cadence census (Live Entry Radar PR-0 archaeology)

Scope: census only, no design decisions. Repos: Macro (this checkout, sparse —
`data/`, `site/`, `mockups/` are absent locally; existence/shape checks below use
`git ls-tree -r HEAD -- <path>` / `git show HEAD:<path>`, which read the tracked
commit tree independent of the sparse cone, per coordinator correction) and
Mastermind (`/Users/chriswong/Documents/Cluade/Mastermind`, full checkout,
read-only). charting-app (Terminal) is NOT in scope/access; its Quote Hub facts
below are relayed from the Macro-repo masterplan's own citations, not
independently verified — flagged inline. `UNVERIFIED` marks anything not
confirmed by a direct read this session.

---

## 1. prophet-live architecture, element by element

**Backstop lane — `.github/workflows/prophet-live.yml`** (189 lines, read in
full). Header comment (lines 2–46) documents the causal chain: this repo's
frequent GitHub cron schedules are throttled far past nominal — measured
2026-07-30, `marketing-hot-tape.yml` (`*/5` RTH) fired 09:07Z then 12:19Z
(~3h12m apart); `live-quotes.yml` (`*/15`) fired ~90 min apart (lines 7–9) — so
a 5-minute product cadence "is not purchasable at any price" on GitHub Actions
with ~58 workflows in the repo. Three crons span 13:25Z–21:15Z to cover both
DST regimes (lines 48–67); `engine/prophet_live/live_states.in_window` trims
the off-season edge on the ET wall clock. `permissions: contents: read`
(line 79) and zero git steps enforce G0.2 (LEDGER LAW): this lane commits
nothing, ever. `concurrency: group: prophet-live, cancel-in-progress: false`
(lines 81–88) — two passes must never overlap, and an in-flight pass is never
cancelled (it may already have published). Gate at line 103:
`vars.PROPHET_LIVE_DISABLED != 'true' && (workflow_dispatch || vars.VPS_LIVE_PRIMARY != 'true')`
— a kill switch that always binds, nested inside a host gate that self-disables
the scheduled legs once the VPS is primary (dispatch still works, as the
rollback path). Runs on `ubuntu-latest` (line 104), never the self-hosted
render pool. Checkout is shallow+sparse+blobless (lines 110–133, cone =
`engine scripts lib site/live site/marketdata`). Deps: `pyyaml boto3` only, no
pandas (line 148). Fetches the `live-data` orphan branch's `quotes.json`
snapshot to runner-local scratch, never staged (lines 150–171). Final step runs
`python -m scripts.prophet_live_evaluator` (or `--dry-run`) (lines 173–189).

**VPS timer — the actual product lane** — `app/deploy/macro-live-prophet.service`
+ `.timer` (both read in full). Service: `ExecStart=/opt/macro/.venv/bin/python
-m scripts.prophet_live_evaluator` (`.service:35`), `Type=oneshot`,
`TimeoutStartSec=120`. Resource caps are MEASURED (`.service:11-25`,
2026-07-30, production-shaped 1,742-name pack + 2,025-symbol quote snapshot):
0.006s wall/CPU compute, ~0.3s process start, ~95MB peak RSS all-in;
`MemoryHigh=256M`/`MemoryMax=512M` (~2.7×/~5× measured peak), `CPUQuota=60%`,
lowest `Nice`/`CPUWeight`/`IOWeight` tier on the box (deliberately loses
scheduling contests with the quote lanes it depends on). Timer:
`OnCalendar=Mon..Fri *-*-* 13..21:03/5:00 UTC` (`.timer:20`) — the `:03/5`
offset (not `:00/5`) gives `macro-live-snapshot` (fires on the `:00/5` boundary,
takes up to ~230s to publish) a 3-minute head start so this lane reads the
current cycle's quote file, not the prior one (`.timer:12-15`).

**MACRO_LIVE_DIR ladder** — `engine/neuralweb/market_packet.py:86-106`,
function `_live_dir()`: (a) `$MACRO_LIVE_DIR` env override, unconditional, else
(b) `/var/lib/macro-live/public/live` when `.is_dir()`, else (c)
`root/site/live` (repo checkout / dev / tests). Same ladder is shared by
`scripts/notify_turn_events.py:122` and `app/main.py:99`
(`LIVE = Path(os.environ.get("MACRO_LIVE_DIR", "/var/lib/macro-live/public/live"))`)
so the brain, the notifier, and the FastAPI app all read the same bytes the
site serves. Runtime layout (`docs/VPS_LIVE_ORCHESTRATION.md:76-96`):
`/opt/macro` (code + canonical checkout), `/opt/macro/site/live` (per-process
staging only), `/var/lib/macro-live/public/live` (atomically-published `/live/*`,
Caddy `no-store`), `/var/lib/macro-live/state` (locks, fingerprints, lane
status, full quote cache), `/var/lib/macro-live/data/intraday` (mutable
VPS-only hourly bars).

**Event spool mechanics** — `engine/prophet_live/r2io.py:34`:
`EVENTS_PREFIX = "live_flow/prophet_live_events"`; `events_key(session, stamp)`
at line 157 mints one R2 object per pass-with-a-transition (object-per-pass
row set per `scripts/prophet_live_evaluator.py:1-5` docstring). Confirmed live
in production: `research/R2_AND_DELIVERY_PLANE_TRUTH_CENSUS_2026-08.md:127-128`
lists R2 keys `live_flow/{prophet_live,prophet_marks}.json`,
`prophet_live_armed.json`, `prophet_live_events/**` as classified
`PRIVATE_OPERATIONAL`.

**No-intraday-durable-ledger-writes enforcement** — belt and suspenders, not
one mechanism: (1) the GitHub workflow's `permissions: contents: read` + zero
git steps (`prophet-live.yml:38-41,79`); (2) the VPS service also runs no git
command (systemd oneshot, no `WorkingDirectory` git step); (3) explicit
docstring law in `scripts/prophet_live_evaluator.py:27-33` — *"LEDGER LAW
(G0.2). This lane writes NOTHING under `data/` and commits nothing... The ONE
filesystem write on this path is the served copy... outside the git
work-tree, outside `site.served`, and never under `data/`."*

**Nightly reconciliation entry point** — `scripts/reconcile_prophet_live.py`
(header read in full, lines 1-38+). `python -m scripts.reconcile_prophet_live
--nightly [--pack PATH] [--now ISO]`. Turns the day's R2 event spool into
`data/prophet_live/forward.parquet` — *"the ENTIRE evidence base for the...
'acting at the intraday cross beats the graded next-close fill' hypothesis"*
(lines 3-6). Joins `confirmed` (gate verdict on the event's OWN session, not a
later one — a vintage bug fixed twice), `close_same_day`, `next_close_fill`
(official fill, mirrors `engine.grading.fill_index`), first-cross dedup
(`first_ts`/`first_px` — first cross is the user-actionable one), and one price
basis reconciliation (raw vendor cross price vs. adjusted store close). Sole
writer law: *"This nightly step is the only writer of `data/prophet_live/`.
The intraday lane writes R2 only."* (lines 32-34, G0.2/RUL-P10). **As of this
census, `git ls-tree -r HEAD -- data/prophet_live` returns zero tracked
files** — `data/prophet_live/` is not in `.gitignore` either (`grep
prophet_live .gitignore` empty), so this is not a gitignore-hidden store: no
`forward.parquet` has ever been committed to `main`. Consistent with the
reconciler's own framing ("accrues from week one with no user surface
attached") — UNVERIFIED whether this means the ledger genuinely has zero
accrued rows yet, or accrual is pending a not-yet-merged PR.

**Measured/nominal cadence achieved.** Nominal: every 5 min via the VPS
systemd timer, 13:00–21:59 UTC weekdays, further gated to 09:25–16:15 ET (+
grace) by `in_window()` (§6 below). The GitHub backstop demonstrably CANNOT
hit 5 min (measured 90min–3h12m gaps, cited above) — it exists only as a
~90-minute rollback path while the VPS is down (`prophet-live.yml:16-19`).
Actual production hit-rate of the VPS timer (gap distribution vs. the nominal
5 min) is UNVERIFIED from a static repo census — would require reading
`/live/orchestrator_status.json` or sentinel state, both live artifacts outside
a read-only code census.

---

## 2. How live payloads reach users today

**VPS pull loop** — `app/deploy/update.sh:1-16` (read in full), installed as
`/usr/local/bin/macro-update`, **cron fires every 3 minutes**, flock-serialized,
pull-if-changed + `git reset --hard` + rsync `site/` → `site.served`
(atomic per-file rename). Confirmed independently by `app/main.py:559-586`
(`/api/status` docstring: *"the 3-min site pull, the 5-min live overlay"*).

**Caddy** (`app/deploy/Caddyfile`, targeted reads) serves `root *
/opt/macro/site.served` (line 88) — the rsync target, never the live git
work-tree. A short PUBLIC allowlist of `/live/*.json` paths (`quotes.json`,
`breadth.json`, `release_publications.json`, `staleness.json`,
`wires.json`, `intelligence.json` — Caddyfile:194,205-217,343,469) is served
directly, `root /var/lib/macro-live/public`. **Everything else — including
`/live/prophet_live.json` — is NOT on that allowlist**, so it falls into the
`@reg_asset` matcher (Caddyfile:341-346, block comment: *"Protected non-HTML
and extensionless paths... direct JSON/JS/model-output URLs no longer bypass
auth"*) and is routed through `reverse_proxy 127.0.0.1:8000` rewritten to
`/api/regwall/check` then `/api/paywall/check` (Caddyfile:347-361) before the
file is served. This is verified LIVE, not just in config:
`research/R2_AND_DELIVERY_PLANE_TRUTH_CENSUS_2026-08.md:76` —
`www.mastermind-x.com/live/prophet_live.json` → **`401`, `no-store`**.
**A new gated live JSON path inherits this for free by NOT being added to the
Caddyfile allowlist** — no new gate code needed, only an omission.

**The FastAPI app** (`app/main.py`) resolves gated live artifacts via
`_live_artifact(name)` (lines 553-556): prefer `$MACRO_LIVE_DIR/name`, fall
back to `SITE/live/name` (dev/back-compat). No dedicated `prophet_live` route
exists in `app/main.py` (`grep prophet_live app/main.py` empty) — it is served
through the generic gated-static path, not a bespoke endpoint.

**Client-side precedent #1 — `templates/dashboard.html.j2:17920-19140`**
(read in full), the existing precedent for exactly this kind of payload:
`PLV_URL = 'live/prophet_live.json'` (line 17943), `PLV_EVERY = 120000` — *"ms
between fetches — producer writes every ~5 min, so 120s bounds staleness at
~2 min for ~2.5 GETs/artifact"* (line 17944). Plain `fetch(PLV_URL,
{cache:'no-cache'})` (line 18583). First fetch is unconditional (never gated
on `document.hidden`, so preview panes still paint); subsequent fetches are
visibility-gated with a `PLV_FLOOR = 30000` ms floor on a
visibility-triggered refetch (lines 19129-19137). One shared artifact, one
poll, two panels (`_plvPaint` calls both `_bsRender()` and `_plvRender()`,
line 19123) — "no new script tag, no new poll and no second hydration path."

**Client-side precedent #2 — `templates/live.js:1-60`** (progressive
enhancement over baked pages): `POLL = (window.LIVE_POLL_SEC || 60) * 1000`
(line 41, default 60s). Three price sources in priority order: Worker
`/quotes` endpoint → static full-universe snapshot JSON (keyless,
`raw.githubusercontent`) → `live/overlay.json`. Also opens the `/ws/tape`
browser WebSocket directly for 6 macro instruments (line 57). Honesty rail:
`DELAYED_MIN` flag suppresses the green "live" pulse on delayed feeds.
`templates/china_risk_state_live.js:29,232,243` mirrors the same 60s-poll,
`fetch(...,{cache:"no-store"})` pattern for the CN risk state.

**Conclusion for a new ~5-min Radar payload:** the house idiom is a single
small JSON at a **gated** `live/<name>.json` path (VPS lane writes it by
atomic rename into `$MACRO_LIVE_DIR`, deliberately NOT added to the Caddyfile
public allowlist), polled client-side every 60–120s against a ~5-min producer
cadence (a 2.5–5× poll:produce ratio is the existing norm), visibility-gated
with a small unconditional-first-fetch exception. No new server route, no new
poll loop framework — `_prophet_card`/`dashboard.html.j2`'s pattern is a
literal template.

---

## 3. Market data entitlements — the "Massive" vendor integration

Primary source: `research/MASSIVE_ADVANCED_INTEGRATION_MASTERPLAN_BY_FABLE.md`
(894 lines; §1, §1.1, §2, §3, §4.3, §5, §12 read in full/targeted).
Massive = the rebranded Polygon.io (§1.1: PyPI package now `massive` v2.8.x;
`polygon-api-client` frozen at 1.16.3; hosts `api.massive.com`/
`socket.massive.com` canonical, `*.polygon.io` still honored — lines 234-238).

**Entitlement verdicts** (TP-0 probe, `scripts/massive_entitlement_probe.py`,
manifest re-runnable; table at lines 159-176, run 2026-08-08T11:44Z market
closed):

| Capability | Verdict |
|---|---|
| Real-time trades/NBBO (REST `v2/last/trade`, `v2/last/nbbo`) | entitled |
| WS stocks real-time `T.*`+`Q.*` | entitled (auth+subscribe only, no data frames proven yet at probe time) |
| Second aggregates (`A.*`) | entitled |
| Tick history depth (`v3/trades`) | **20y+** (non-empty at 2015 and 2005 probes) |
| Quote history depth (`v3/quotes`) | entitled to recency; depth re-verified to **2005** by TP-0.5 (§12 log, 2026-08-08) |
| Snapshots (single/gainers/unified) + grouped daily | entitled |
| Short interest + short volume REST | entitled (new) |
| Options trades/WS/realtime | **not entitled** (403 + subscribe error) |
| Indices (`v3/snapshot/indices`, WS) | **not entitled** |
| WS delayed cluster | ambiguous at TP-0; **resolved by TP-0.5** (below) |

Licensing: *"RESOLVED 2026-08-09... backed by an executed Enterprise Market
Data License and Redistribution Addendum... the §0 gate is CLOSED"* (lines
146-150; record at `research/licenses/MASSIVE_ENTITLEMENT_RECORD.md`,
not read this session).

**Vendor facts binding the architecture** (§1.1, lines 196-238): **ONE
simultaneous WebSocket connection per cluster per product** on individual
plans (extras $75/mo via support) — "the single most architecture-shaping
constraint." Delayed (`delayed.polygon.io`) and real-time (`socket.polygon.io`)
hosts are separate endpoints. `Q.*` NBBO exists at Advanced tier only (no
delayed tier below it). Flat Files (S3): `us_stocks_sip/day_aggs_v1` from
2006-03-15+ (whole-market daily), `minute_aggs_v1` from **≥2010-06-15**
(line 141-142); `trades_v1`/`quotes_v1` flat files verified by LIST
2026-08-08 back to **2005-06**, with 2024 `quotes_v1` at **~4.8GB/day gz
market-wide** (line 213-218) — "a blanket multi-year quote backfill is
TB-scale," so the plan's own strategy is episode-windowed files + per-name
REST, never a bulk crawl.

**TP-0.5 measured semantics** (§12 status log, lines 892, run
2026-08-08~13:05Z): delayed and real-time **ARE separate WS buckets**
(a held RT socket coexisted with a fresh delayed connection). But **overflow
EVICTS THE OLDEST connection** — the vendor does not refuse a second
connection to a full slot, it silently kills the incumbent (§3.1b.4, lines
381-399). This is the single most load-bearing operational fact for any new
WS client: singleton discipline is existential (a stray second client kills
production silently), and a `1008 max_connections` close arriving near a
reconnect signals a slot fight, not a benign retry target.

**Current build state — NOT YET BUILT.** The masterplan's own wave table
(§5, lines 596-613) shows TP-1 (`engine/tick_plane/` ingest daemon — the
actual WS-consuming, R2-publishing daemon) as **dependent on TP-0.5**, with
TP-0.5 itself only "durable probe + RTH re-proof" in progress as of the last
status-log entry (2026-08-08). Confirmed by direct repo check this session:
`find engine/tick_plane` → no such directory;
`grep -rl "tick_plane\|ingestd" **/*.py **/*.md` → zero hits outside the
masterplan itself. **No persistent Massive/Polygon WebSocket consumer exists
in this repo today.** `git ls-tree -r HEAD -- data/massive` → only
`data/massive/capability_manifest.json` (the probe's output, not a data
store).

**Daily OHLCV, today** — `collectors/massive_stock_day.py:1-50` (read in
full). Derived per-ticker store `data/massive_stock_day/<TICKER>.parquet`
(append-only, index=date), sourced from the Massive flat-file
`us_stocks_sip/day_aggs_v1/` entitlement, a **rolling ~5-year window**
(probe-verified earliest day = today−5y). **R2 is the canonical home**
(~617MB, ~20k parquets); git tracks only two sidecars —
`git ls-tree -r HEAD -- data/massive_stock_day` confirms exactly
`_manifest.json` + `_backfill_state.json`, nothing else. Nightly round-trips
via `scripts/fetch_r2`/`scripts/publish_r2 --dirs massive_stock_day`.

**Intraday, today — HOURLY ONLY, not minute.**
`scripts/build_polygon_intraday.py:1-70` (read in full): *"Intraday (hourly)
US price accrual via Polygon/massive.com -> `data/intraday/<T>.parquet`"*.
Explicitly **15-minute delayed** (`DELAYED_MIN = 15`, line 63 — "HONEST
FRESHNESS... the Polygon STANDARD stocks plan serves 15-MIN-DELAYED
aggregates"). Curated universe only (`data/stocks/*` deep-history names +
sector/factor ETFs), not full-market. Powers the 4H chart timeframe, nothing
intraday-signal-facing. `data/intraday/` is explicitly gitignored
(`.gitignore:66`) and is also named in `docs/VPS_LIVE_ORCHESTRATION.md:84` as
the **VPS-local, mutable, hourly-bars-only** store
(`/var/lib/macro-live/data/intraday`) — a different, VPS-side thing from the
git-adjacent `data/intraday/` collector cache; do not conflate the two paths.

**Minute-bar historical store — DOES NOT EXIST.** Entitlement is proven deep
(`minute_aggs_v1` flat files to 2010, `v3/trades` tick history to 2005), but
no code in this repo turns that entitlement into a durable, queryable
minute-bar store. That is explicitly **TP-B** ("History backfill... TP-0
(parallel to TP-1/2)" — masterplan §5 line 603), unbuilt. The nearest thing
that exists is the *hourly*, 15-min-delayed, curated-universe
`data/intraday/*.parquet` above — materially different from a minute-bar
replay substrate (wrong grain, wrong latency claim, wrong universe).

**Universe/sizing anchors for the Radar's ~500–1500-name Probe Set** (useful
comparators, not requirements): masterplan §3.2 Tier A pilot (lines 401-413)
caps the planned tick-plane capture at a **hard 600 symbols**
(`gex_symbols()` ~375 ∪ Prophet US actives ∪ index/sector ETFs). The existing
nightly `prophet_live` **arming** pass (not the 5-min evaluator — the nightly
build) probes a ~1,730-name universe inside a 420s wall-clock budget on 4
workers on a 4-core box, and a `max_probe: 500` cap was tried and starved the
pass (`config.yml:699-724`, comment: *"max_probe 500 did NOT fit... produced
probed_n=3 and armed_n=0"*). The existing simplest live loop,
`config.yml live: max_universe: 150` (line 617, `engine/live_overlay.py`'s
"fast leaves" recompute, `poll_seconds: 60`), caps at 150 names — well below
the Radar's target. A Radar computing provisional oscillator values (heavier
than the live-overlay price-vs-baseline compare, lighter than a full
re-score) for 500–1,500 names every 5 min sits between these two existing
lanes in both universe size and per-name compute weight.

---

## 4. Existing WebSocket/stream owners

**Macro — `app/tape.py:1-80`** (read in full): `TapeHub`, one process-wide
background task, connects to **`wss://streamer.finance.yahoo.com`** (Yahoo's
*unofficial* streamer — NOT Massive/Polygon), subscribes 6 tape symbols
(ES=F, NQ=F, YM=F, RTY=F, ^TNX, DX-Y.NYB per `templates/live.js:57`), fans out
over same-origin `GET /ws/tape` (Caddyfile:146 `reverse_proxy /ws/tape
127.0.0.1:8000`). Explicitly the single shared-upstream-connection owner for
this feed ("no browser ever talks to the unofficial upstream directly...one
shared upstream connection" — tape.py:6-9). This is a **different vendor and
a different WS** from the Massive/Polygon stocks entitlement — it does not
compete for the Massive WS slot.

**Massive/Polygon stocks WebSocket — currently UNOWNED in Macro.** No process
connects to `socket.polygon.io/stocks` or `socket.massive.com` today; TP-1
(the planned owner, `engine/tick_plane/`) is unbuilt (§3 above).
`scripts/massive_entitlement_probe.py` only opens a transient auth+subscribe
probe connection, not a persistent daemon.

**Terminal's Quote Hub (charting-app, out of scope/access — relayed from the
Macro masterplan, UNVERIFIED independently):** masterplan §2.1/§3.1b
(lines 261, 355-380) name `hub/lib/polygon.js` as the second candidate client
in the estate, today subscribing `AM.*` (minute aggs) with
auto-demote-to-delayed on a real-time-denial frame. Law recorded in the
masterplan (binding on any future build, not yet exercised): the TP-1 ingest
daemon (once built) is the sole owner of the real-time cluster; the Terminal
hub pins to the delayed cluster until a later wave migrates it onto TP-1's
derived stream. TP-0.5 already showed delayed and real-time are separate
buckets, so — per the masterplan's own conditional — this migration does NOT
fold into TP-1 automatically.

**Mastermind — verified directly this session, `data_layer/polygon.py:1-90`**
(read in full, canonical checkout, not a worktree): REST-only. `grep -n -i
websocket data_layer/polygon.py` → zero hits. Thin wrapper over
`collectors.polygon_options.PolygonOptions` (the same vendored Macro client,
imported via a `bot` sys.path shim), key resolved from `POLYGON_API_KEY`
falling back to `MASSIVE_API_KEY` — i.e. Mastermind reuses Macro's key/client
rather than holding its own credential. Docstring: *"Live (15-min delayed)
equity quotes... Delayed data is fine here: this is a paper book, marks are
EOD-grade"* (lines 1-12). 60s in-process TTL cache (line 20). Broader repo
grep (`grep -rln -i "websocket\|socket.polygon\|socket.massive"
--include=*.py --include=*.js Mastermind/`, excluding worktrees) surfaced only
this file plus its duplicates inside OTHER sessions' worktrees under
`.claude/worktrees/`/`.codex/worktrees/` (not the canonical checkout, not
counted).

**Net answer:** zero processes hold a live Massive/Polygon stocks WebSocket
connection open anywhere in Macro or Mastermind today. The single-connection
slot is unclaimed. A Radar built on REST (which is unlimited-call, ~<100
req/s soft-ceiling, already the pattern every existing daily/hourly collector
uses) needs no new singleton-discipline machinery at all; only a WS-based
design would need to implement the systemd-single-instance + slot-fight
detection law the masterplan already specifies (§3.1b.4).

---

## 5. Breathing Platform program

Source: `research/BREATHING_PLATFORM_MASTERPLAN_BY_FABLE.md` (406 lines, §3/§4
read in full) + `research/BREATHING_PLATFORM_CONTINUATION_HANDOFF_2026-08-10_SESSION4.md`
(221 lines, read in full — most recent Breathing-Platform-specific doc found;
`find research -iname "*BREATHING*" -newer ...SESSION4.md` returned only the
masterplan itself, no newer handoff).

**Target architecture — three cadences, one engine** (masterplan §3,
lines 240-263): (1) **Authority** (nightly, shrinking) — ledgers, grading,
pack re-arming, full render; (2) **Provisional close-pass** (new,
~16:15–17:30 ET) — a mac-side pass recomputing admission + price-derived score
legs over the full universe from the day's closes, publishing "tonight's
picks, pending nightly confirmation" — the evening-SLA fix (picks by ~18:30 ET
instead of ~11pm–1am ET); (3) **Breathing lane** (existing, hardened+widened,
~5min RTH) — append-semantics crossing states, partial live rescore of the
legs that move intraday (signal 30 + runway 10 pts), risk-overlay badges,
2-pass-debounce alert dispatch. **"Provisional never touches `data/`"**
(line 261) — same G0.2 ledger law as prophet-live.

**What it offers a 5-min Radar evaluator, concretely:** cadence (2) is a
mac-side batch pass ~once/session, not a 5-min loop — not directly reusable
for a 5-min cadence. Cadence (3), the "breathing lane," is the closer analog
(5-min RTH, partial live rescore) but is scoped to the SAME nightly-armed
candidate universe and its signal/runway legs, not a general-purpose 5-min
oscillator evaluator — it is a sibling pattern to copy, not infrastructure to
plug into directly.

**Current status (as of the most recent doc found, 2026-08-10 SESSION4;
program masterplan itself is dated/ratified 2026-08-08 per its own header):**
§0 START HERE (lines 12-35) — four PRs (payload/receipt/SLA/renderer, #5217/
#5220/#5222/#5223) built+reviewed but disarmed mid-session by an unrelated
GitHub-repair session, meant to be re-armed as one wave; #5223 (the renderer)
is inert until #5217 lands (`board.cards` has no producer without it). **§5
(lines 147-163): "The evening lane has NEVER RUN... `close-pass.yml`'s
`publish` job has never fired. Total history: two `workflow_run` events, both
FAILED with `ModuleNotFoundError: No module named 'pandas'`"** — a narrow
`pip install boto3`-only step failed 100% of runs, invisibly (read downstream
as absent data, not a fault). Fixed incidentally by #5220 moving the step into
`daily.yml`'s pandas-carrying engine job. First weekday firing after the fix
was projected as Monday 2026-08-10. **§6 (lines 166-182): W-L1's gate needs
five consecutive green sessions, which "cannot be built; it accrues"** —
unproven end-to-end as of that doc.

**Fresher, in-repo signal (today, 2026-08-13):** `.github/workflows/close-pass.yml`'s
own header carries a **"CORRECTED 2026-08-13"** note (lines 22-29) stating the
lane's discard-contract claim "was false from day one... the lane has never
been green" until a `git checkout -- .` discard step was added alongside the
`--heal` prefetch — i.e. as of today the lane's self-check is understood to be
fixed, though this session made no `gh` calls to confirm current CI/merge
state of #5217/#5220/#5222/#5223 (task constraint: no `gh`). **Status should
be read as: architecture ratified and mostly built, evening-SLA lane
(W-L1) not yet proven green end-to-end as of the last narrative doc, with an
in-repo comment from today indicating the specific pandas/discard defect is
addressed.** Treat "is W-L1 live" as OPEN, not answered, for PR-0 purposes.

**Evening render lane cadence facts** (`.github/workflows/closing-bell.yml`,
targeted reads): fires `20:05`/`21:05 UTC` = **16:05 ET** both DST regimes
(lines 68-69) — "Build A," full provisional EOD render, **non**-ledger-
advancing, EXCLUDES `build_prophet`/`grade_us_board`/`us_pages`. Measured 109
minutes behind an 81-minute spine, lands ~17:55 ET against an 18:30 SLA (35 min
margin) — per `close-pass.yml`'s own header (lines 4-6), which is WHY the
provisional board is a separate ~10-20 min lane rather than bolted onto this
one. `close-pass.yml` fires at **16:25 ET** both regimes (`'25 20/21 * * 1-5'`,
lines 40-46), a separate concurrency group, publishing straight to R2 → VPS
live plane (not through a render) so the board lands ~30 min after the close
regardless of the render spine's state.

**Asia-close cadence** (`.github/workflows/asia-close.yml`, header read):
multi-slot schedule (7 cron lines, 06:00–11:15 UTC) racing to be first,
because GitHub fires this repo's schedules 86–233 min late (measured);
early-bird slots gated at an 08:25 UTC data floor (HK closing auction ~08:10
UTC = 16:10 HKT; mainland vendor EOD ~08:00-08:30 UTC) so net effective start
≈ the close, not +2-4h. A `gate` job dedups/retries/holds
(lines 25-33).

---

## 6. Session calendar in live lanes

Exact module: **`lib/nyse_calendar.py`**, consulted via
`engine/prophet_live/live_states.py:386-414` function `in_window()` (read in
full). Mechanics: `t = et_clock(now)` — ET wall clock via
`ZoneInfo("America/New_York")` (`live_states.py:239`); weekday check
(`t.weekday() >= 5` → stand down); then `from lib.nyse_calendar import
is_session; if not is_session(t.date()): return False` (lines 398-401) — the
actual holiday-aware NYSE trading-day check, so the lane stands down on
Thanksgiving etc. rather than firing ~80 no-op passes. **Fail-soft**: an
exception from the calendar import/call is caught and logged, degrading to
weekday-only (lines 402-403) — never raises, never blocks the pass. Window
bounds come from config (`window_et` start/end, default 09:25/16:15,
`_parse_hhmm` fallback) plus a `window_grace_min` (default 10) added to the
end (lines 404-411). Same calendar module also backs
`last_completed_session()` (line 425-431,
`lib.nyse_calendar.expected_last_session`) — the pack `as_of` must equal this
exact date or the artifact ships dark (`stale_pack`). The systemd timer
comment (`macro-live-prophet.timer:1-10`) explains WHY this two-layer design
exists: "systemd calendars have no ET," so the timer's `OnCalendar` spans a
UTC range covering both DST regimes, and `in_window()` is the only thing that
actually knows what "9:25 ET" means on any given day — one schedule, one
window definition, no second copy of "when is the market open." The same
`lib.nyse_calendar` module is cited as the exchange-calendar anchor for
`macro-sentinel`'s staleness budgets (`docs/VPS_LIVE_ORCHESTRATION.md:161`)
and for `closing-bell.yml`'s own session gate
(`from lib.nyse_calendar import is_session`, cited in that workflow's header).

---

## 7. Recent hardening context (pointers only)

All three are OPEN PRs per `docs/ACTIVE_BUILD_MAP.md` (generated
2026-08-14T03:07:03Z, "Open PRs: 48" — this session made no `gh` calls; status
is this doc's own generation snapshot, not independently re-checked):

- **#5555** — `prophet: stale-frame action safety — no current instruction off
  a dead tape` (branch `claude/prophet-stale-frame-action-safety`, touches
  `engine/prophet_management.py`, `scripts/build_prophet.py`,
  `tests/test_prophet_management.py` — `docs/ACTIVE_BUILD_MAP.md:18`). Not yet
  on `main` (`grep -n stale engine/prophet_management.py` → no hits in this
  checkout). Implication for a new live lane: the house pattern is to gate
  the *action* surface on frame freshness explicitly and separately from
  whether the display renders at all — a Radar entry signal must carry the
  same discipline (never let a stale/dead-tape frame emit a live "enter now"
  instruction; darken the action, not just the price).
- **#5571** — `ops(prophet-us): availability hardening — bounded self-heal
  rescue lane + resilience layers` (branch
  `claude/prophet-us-availability-hardening`, mostly touches CI plumbing —
  `docs/ACTIVE_BUILD_MAP.md:11`). Implication: there is an established idiom
  for "the nightly bake died, self-heal within a bound" that a new live lane
  should register with rather than inventing its own recovery path from
  scratch — CLAUDE.md memory (context provided to this session, not
  independently re-verified) describes a companion `prophet_rescue` responder
  and a wall-clock-based `asof`.
- **#5487** — `ops: nightly-liveness dead-man switch — the US bake went dark
  for two sessions and nothing reported it` (branch
  `claude/nightly-liveness-watchdog` — `docs/ACTIVE_BUILD_MAP.md:49`).
  Implication: silence is the default failure mode across this estate (the
  Breathing Platform's own pandas failure, §5 above, and this PR's own
  namesake outage both went undetected until named), so a new 5-min live lane
  MUST register a positive liveness signal (content-advanced, not
  process-exited-0 — the binding precedent named in the Massive masterplan
  §3.6, "21 nights of silent `{"blocked":"no_creds"}`") with the existing
  `macro-sentinel`/`freshness_sentinel.py` watchdog rather than assuming an
  absence of alerts means health.

---

## Sources read in full or by targeted section (file:line receipts inline above)

`.github/workflows/prophet-live.yml` (189/189) ·
`app/deploy/macro-live-prophet.{service,timer}` (48+28/48+28) ·
`app/deploy/macro-live-{bars,fast,closepass,snapshot}.{service,timer}`
(targeted) · `docs/VPS_LIVE_ORCHESTRATION.md` (290/290) ·
`engine/neuralweb/market_packet.py:70-169` ·
`engine/prophet_live/live_states.py:380-430` ·
`scripts/vps_live_orchestrator.py:1-120` ·
`scripts/prophet_live_evaluator.py:1-90` ·
`scripts/reconcile_prophet_live.py:1-38` ·
`engine/prophet_live/r2io.py` (grep) ·
`research/MASSIVE_ADVANCED_INTEGRATION_MASTERPLAN_BY_FABLE.md:136-480,558-620,888-894`
(of 894) · `collectors/massive_stock_day.py:1-50` ·
`scripts/build_polygon_intraday.py:1-70` ·
`app/tape.py:1-80` · `app/main.py:90-115,545-586` ·
`app/deploy/Caddyfile` (targeted, ~30 lines) ·
`Mastermind/data_layer/polygon.py:1-90` (canonical checkout) ·
`research/BREATHING_PLATFORM_MASTERPLAN_BY_FABLE.md:240-306` (of 406) ·
`research/BREATHING_PLATFORM_CONTINUATION_HANDOFF_2026-08-10_SESSION4.md`
(221/221) · `.github/workflows/closing-bell.yml` (targeted ~70 lines of 684) ·
`.github/workflows/close-pass.yml` (targeted ~60 lines of 196) ·
`.github/workflows/asia-close.yml` (targeted ~45 lines of 966) ·
`templates/live.js:1-60` (of 573) ·
`templates/dashboard.html.j2:17920-19140` (targeted, of ~20k) ·
`templates/china_risk_state_live.js` (grep) ·
`research/R2_AND_DELIVERY_PLANE_TRUTH_CENSUS_2026-08.md:76,127-128` ·
`docs/ACTIVE_BUILD_MAP.md` (grep, generated 2026-08-14T03:07:03Z) ·
`config.yml:604-724` · `.gitignore` (grep) ·
`git ls-tree -r HEAD` against `data/massive`, `data/massive_stock_day`,
`data/prophet_live`, `data/polygon`, `site/live`.

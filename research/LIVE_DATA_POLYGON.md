# Live-Data Layer — Polygon STANDARD (15-min delayed) + the real-time upgrade seam

> **Status:** wired on `feat/signal-engine-buy-filter` (PR into that branch, **not** main directly).
> **Plan:** Polygon **Standard** stocks = **15-MINUTE-DELAYED** aggregates + snapshots. This is
> **NOT real-time.** Every surface that shows it says so. The websocket/real-time plan is a
> documented *future* upgrade (Phase 3 below) — architected here, **not built**.
>
> Companion doc: `research/LIVE_DATA_ARCHITECTURE.md` (the 3-tier slow-brain / fast-leaf /
> event-leaf model + overlay schema). This doc is the Polygon-plan + upgrade-seam addendum.

---

## 0. TL;DR

1. **Phase 1 — intraday bar store.** `scripts/build_polygon_intraday.py` accrues hourly US
   bars into `data/intraday/<T>.parquet`, **append-only / key-deduped**, with an honest
   `data/intraday/_meta.json` delay label. New hourly CI: `.github/workflows/intraday.yml`.
2. **Phase 2 — live-ish quotes overlay.** The existing `engine/live_quotes.py` →
   `scripts/build_live_quotes.py` / `build_live_overlay.py` → `site/live.js` stack already
   pulls Polygon delayed snapshots with the **key server-side**. This change makes the whole
   chain **label the data "≈15-min delayed"** and suppress the green "live" pulse.
3. **Phase 3 — real-time upgrade seam.** A clean interface boundary so a websocket feed drops
   in behind the *same* `/quotes` contract with **zero consumer changes** (§3). Doc-only.
4. **Phase 4 — bar-derivation hooks.** `engine/bar_derive.py` turns the intraday store into a
   daily close Series the confluence engine consumes drop-in, plus supplementary 2D/3D OHLCV
   candles for the Standout grid. Opt-in `build_signal_quality.py --intraday` (off by default).

**Guardrails honored:** 15-min delay labeled honestly everywhere; the vendor key never leaves
the server/CI; everything additive + non-breaking (off-by-default flags, new files, new cron).

---

## 1. What is wired (Phase 1 + 2)

### 1a. Intraday bar store — `data/intraday/<T>.parquet`
- **Collector:** `scripts/build_polygon_intraday.py` (`accrue()` + CLI).
  - Endpoint: `GET /v2/aggs/ticker/{sym}/range/1/hour/{from}/{to}` (Polygon REST aggregates).
  - Universe: the deep-history US names (`data/stocks/*.parquet` stems) + sector/factor/extra
    ETFs from `config.yahoo.tickers`. **US-only by entitlement** (index/futures/fx/crypto are
    not on the stocks plan).
  - **Append-only / key-deduped:** each run reads the existing parquet, re-fetches only a small
    recent window (last bar − 2-day overlap, to absorb late corrections), `concat`s, and
    de-dupes on the bar timestamp (`keep='last'`). `--full` forces a clean re-fetch;
    `--lookback-days N` sets the cold-start window when no prior file exists.
  - **Honest delay:** `DELAYED_MIN = 15` is stamped into `data/intraday/_meta.json`
    (`{delayed_min, source:"polygon_standard", realtime:false, …}`). pandas drops
    `DataFrame.attrs` on the parquet round-trip, so the sidecar JSON is the durable label.
  - **Key:** `config.secret("POLYGON_API_KEY")` (or `MASSIVE_API_KEY` alias) — env/CI only.
    No key → clean no-op (`{"status":"skipped","rows":0}`), so the daily run never breaks.
- **Scheduling:** `.github/workflows/intraday.yml` — hourly during US market hours + the
  delayed tail (`cron: "35 13-21 * * 1-5"`), `workflow_dispatch` for manual runs. Distinct
  `concurrency: intraday` group so it never contends with the daily `pipeline`. The store is
  gitignored and persisted cross-run via `actions/cache` under the shared `intraday-` key
  prefix (warm-starts from the daily collect cache and prior hourly runs); the next
  daily/engine build re-emits `site/intraday/<T>.json` for the chart from it.
  > Note: GitHub only runs `schedule:` workflows from the **default branch (main)** — the cron
  > goes live once this branch reaches main; until then use `workflow_dispatch`.

### 1b. Live-ish quotes overlay (display) — already Polygon-delayed, now labeled honestly
- **Fetch:** `engine/live_quotes.py::fetch_quotes()` routes plain US tickers to the Polygon
  snapshot `GET /v2/snapshot/locale/us/markets/stocks/tickers` (15-min delayed on Standard),
  everything else (suffixed/futures/fx/crypto/caret + the US no-key fallback) to keyless Yahoo
  spark. Each quote carries a `price_basis` (trade/minute/day/prev/regular) and a measured
  `delay_min` so a stale "refresh-only" tick is never treated as live.
- **Two browser delivery paths, both keyless to the client:**
  - static snapshot `quotes.json` force-pushed to the `live-data` branch by
    `.github/workflows/live-quotes.yml` (already on main), fetched via raw.githubusercontent
    (CORS `*`); written by `scripts/build_live_quotes.py`.
  - `site/live/overlay.json` (fast-leaf technicals + divergence) by `scripts/build_live_overlay.py`.
- **Honest "delayed" labeling (this change):**
  - `config.yml live.delayed_min: 15` + `live.feed_label` — the vendor delay floor + caption.
  - `write_live_config()` emits `window.LIVE_DELAYED_MIN` + `window.LIVE_FEED_LABEL` into
    `site/live_config.js`.
  - `site/live.js`: when `LIVE_DELAYED_MIN > 0` it **never shows the green "live" pulse** —
    chips get an amber `data-live="delayed"` dot, a `≥15-min delayed · source · Nm ago` title,
    and the reported age is floored to the vendor delay (a delayed quote *is* old). Any
    `[data-live-label]` element is filled with the honest caption.
  - `quotes.json.meta` and `overlay.json` both carry `{delayed_min, feed, realtime:false}`,
    and `to_worker_quotes()` passes through per-quote `delayMin` — the data declares its own
    delay, not just the UI.

### 1c. Key-stays-server-side (audited)
- The key is read only by server-side Python (`config.secret`) and, if ever deployed, by the
  Cloudflare Worker as a `wrangler secret` (Authorization header on subrequests). It is in CI
  as a GitHub Actions secret (`POLYGON_API_KEY`).
- `write_live_config()` emits **only** URLs + numeric/label vars — never key material.
  `quotes.json` carries only price fields. Guard test:
  `tests/test_live_delay_labeling.py` sets a real key in the env and asserts it appears in
  **neither** `live_config.js` nor `quotes.json`. (`grep -r POLYGON_API_KEY site/` ⇒ empty.)

---

## 2. Honesty rules (do not regress)

- The feed is **delayed, not real-time**, until a real-time plan is live. `delayed_min` is the
  single source of truth: set it `> 0` (currently 15) ⇒ everything labels "delayed" and the
  "live" pulse is suppressed. Set it `0` ⇒ real-time presentation re-enables automatically.
- Never hardcode "real-time"/"live" copy on a page; read `LIVE_FEED_LABEL` / `delayed_min`.
- The intraday store is **raw** prices; the nightly `data/stocks` close is **total-return
  adjusted**. Do not silently mix them in one series (see `engine/bar_derive.py` caveat) — the
  intraday signal path is opt-in for exactly this reason.

---

## 3. Phase 3 — the real-time / websocket upgrade seam (architecture, NOT built)

Goal: when we buy a real-time entitlement (Polygon **Starter+** has a stocks **WebSocket**),
swap REST-snapshot polling for a live WS feed **without touching any consumer** — `live.js`,
`overlay.json`, `quotes.json`, and the Mastermind bot all keep their current contracts. Only
`delay_min` shrinks (→ ~0) and `price_basis` becomes `trade` during RTH.

### 3.1 Why it's a clean swap
Every consumer already speaks one shape — the `/quotes` map of
`{price, ts, source, basis, prevClose, changePct, currency, delayMin}`. The REST snapshot and
a WS feed can both produce that shape. `price_basis` already has a `trade` rung; no schema
change is needed. So the upgrade is a **source swap behind a stable interface**, not a rewrite.

### 3.2 The seam (where the swap happens)
Introduce one quote-source interface and route to it by a flag:

```
QuoteSource.fetch(symbols) -> { SYM: {price, ts, source, basis, prevClose, currency} }
  ├─ RestSnapshotSource   (today)  -> Polygon /v2/snapshot  (15-min delayed)   delay_min ≈ 15
  └─ WebSocketSource      (future) -> reads a live tick cache               delay_min ≈ 0
```

- **Server/Python side** (`engine/live_quotes.py`): `fetch_quotes()` is already the single choke
  point (US→Polygon, else→Yahoo). A WS feed plugs in by making the US branch read the freshest
  tick from a small cache (a local process for a long-running collector, or the Worker's store
  for the browser path) instead of calling `fetch_polygon()`. Same return dict.
- **Edge/Worker side** (`worker/quotes.worker.js`): the `/quotes` handler keeps its canonical
  symbol key, 60s edge cache, CORS, and Yahoo fallback. Add **one branch** on `env.USE_WS_FEED`:
  - `false` (today) → `fetchPolygon()` REST snapshot (unchanged).
  - `true` (future) → read from a **Durable Object** that holds the single upstream WS
    connection (`wss://socket.polygon.io/stocks`), subscribes to `T.*` (trades) / `AM.*`
    (minute aggs), keeps an in-memory `{sym: lastTrade}` map, and answers `/quotes` from it.
    Many browser tabs still fan out through the cached REST endpoint — the DO is the *only* WS
    client. `wrangler.toml` gains `[[durable_objects.bindings]]` (none today) + a
    `POLYGON_WS_KEY` secret (so REST/WS entitlements rotate independently).
- **Message shim:** Polygon WS events `[{ev:'T',sym,p,t,…}]` map 1:1 onto the existing quote
  shape (`{price:p, ts:t, source:'polygon_ws', basis:'trade', …}`). No downstream change.

### 3.3 Flip checklist (when the plan is bought)
1. `wrangler secret put POLYGON_WS_KEY` (or reuse the REST key); deploy the Worker; add the
   Durable Object binding; set `env.USE_WS_FEED=true`.
2. Set `config.yml live.delayed_min: 0` and `live.feed_label: "real-time"` → the UI drops the
   delayed dot and restores the live pulse automatically (no JS edit).
3. Set the repo variable `LIVE_QUOTES_WORKER_URL` → `live.js` prefers the Worker (real-time)
   over the static snapshot; the snapshot stays as the keyless fallback.
4. For intraday bars, set `DELAYED_MIN = 0` in `build_polygon_intraday.py` (or switch to the WS
   minute-agg collector); the `_meta.json` label flips to `realtime:true`.

What does **not** change: `overlay.json` / `quotes.json` schemas, `live.js`, the bot's
`act_on_live` / `invalidated` logic, the 3-tier slow-brain/fast-leaf split. That invariance is
the whole point of the seam.

---

## 4. Phase 4 — intraday → signal-engine bar hooks (`engine/bar_derive.py`)

- `derive_daily_close(intraday)` → a daily **close Series** byte-compatible with
  `pd.read_parquet('data/stocks/<T>.parquet')['close'].dropna()` (index `Date`, tz-naive
  midnight, float64, sorted, no NaN). The confluence engine (`signal_quality.signal_frame` /
  `analyze`) consumes a daily close Series and does the 3B / W-FRI resampling **internally**
  (faithful to the Pine) — so an intraday source plugs in by swapping only *where the close
  comes from*.
- `derive_2d_ohlcv` / `derive_3d_ohlcv` / `derive_daily_ohlcv` → **supplementary** higher-TF
  candles for the Standout grid / ATR / regime reads. Their 3D close equals what `signal_frame`
  derives internally — but **never feed these frames to the confluence** (that would
  double-resample). Pass the close Series, not the candle frame.
- Integration switch: `scripts/build_signal_quality.py --intraday` (OFF by default) routes each
  ticker through `bar_derive.daily_close_for(t, prefer_intraday=True)` — intraday-derived close
  when a file exists, else the adjusted store — and stamps `source:"intraday_delayed"` +
  a delay note on the brain leaf. This is a **research hook** (raw-vs-adjusted caveat above);
  production stays on the nightly adjusted store until validated cross-sectionally per the
  signal-engine CHARTER.

### Proposed §7 CHARTER contract extension (not yet applied — propose first, per the contract rule)
To carry intraday resolution honestly, add an optional field to both §7 payloads:
`"intraday_asof": "<ISO-8601 with tz>"` alongside the existing date-only `"asof"`, plus the
brain-leaf `"source": "daily_adjusted" | "intraday_delayed"`. Add to `CHARTER.md §7` first,
then both the engine and the chart build to it.

---

## 5. File map (this change)

| File | Phase | What |
|---|---|---|
| `scripts/build_polygon_intraday.py` | 1 | incremental append/dedup + `DELAYED_MIN` + `_meta.json` + CLI |
| `.github/workflows/intraday.yml` | 1 | hourly delayed-bar refresh (cache-persisted, own concurrency group) |
| `config.yml` (`polygon.intraday`, `live`) | 1·2 | doc the append/delay behavior; add `live` block + `delayed_min`/`feed_label` |
| `scripts/build_live_overlay.py` | 2 | emit `LIVE_DELAYED_MIN`/`LIVE_FEED_LABEL`; `delayed_min`/`feed`/`realtime` in overlay |
| `scripts/build_live_quotes.py` | 2 | `delayed_min`/`feed`/`realtime` in meta; per-quote `delayMin` |
| `site/live.js` + `templates/live.js` | 2 | amber "delayed" dot, honest title, `[data-live-label]`, no false "live" pulse |
| `site/live_config.js` | 2 | regenerated with the delay vars (no key) |
| `engine/bar_derive.py` | 4 | intraday → daily-close Series + 2D/3D OHLCV hooks |
| `scripts/build_signal_quality.py` | 4 | opt-in `--intraday` source switch (off by default) |
| `tests/test_polygon_intraday.py`, `test_live_delay_labeling.py`, `test_bar_derive.py` | all | append/dedup, delay-label, key-safety, bar-derive contracts |
| `research/LIVE_DATA_POLYGON.md` | 3 | this doc — what's wired + the real-time upgrade seam |

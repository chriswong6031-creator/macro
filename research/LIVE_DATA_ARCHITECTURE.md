# Live data architecture — making the daily site usable intraday

**Status:** Phases 1–3 built (2026-06-21), then hardened after a multi-agent
adversarial review (horizon-matched divergence, corrected `act_on_live`, market
sessions, live market-context, divergence-to-website, outlier/baseline guards,
canonical-symbol fix, Polygon trade-time staleness + status, retry/backoff,
NaN-safe emit, worker hardening). Phase 4 (live GEX/options) deferred.

> **Polygon plan + real-time upgrade seam:** the live feed runs on the Polygon
> **STANDARD** plan = **15-MIN DELAYED** (not real-time), labeled honestly end-to-end.
> The intraday bar store, the delayed-labeling wiring, and the **websocket upgrade seam**
> (swap the quote source behind the unchanged `/quotes` contract) are documented in
> [`research/LIVE_DATA_POLYGON.md`](LIVE_DATA_POLYGON.md).

## The problem

The dashboard is a static GitHub Pages site rebuilt **once per day** (`.github/
workflows/daily.yml`, 22:40 UTC). The ~45-minute build is dominated by HTML
rendering + regional builders + LLM briefs — none of which need to run intraday.
We want Mastermind (the trading bot) to have **up-to-date prices and signals
during market hours** without turning that batch into a "rebuild every minute"
machine.

## The key insight: three tiers by cadence-of-change

Computation splits by *how fast its inputs actually move*, not by how often we
happen to rebuild it:

| Tier | What | Intraday? | Cost |
|------|------|-----------|------|
| **S — slow brain** | regime/quad, factor scores, conviction, GTAA allocation, 13F/news/alt-data/yield-curve | **No, by design** — anchored to daily→quarterly data, *hysteresis-gated* so noise must not flip them | High (the nightly batch) |
| **F — fast leaves** | technicals (RSI/MACD/MA-distance, %-off-52w-high), the live position vs the cone | **Yes** | **Cheap** — seconds of pandas on a small series |
| **E — event leaves** | GEX (live options OI/IV), live breadth, live macro inputs | Yes | Expensive / entitlement-gated → Phase 4 |

So we **do not** rebuild constantly. The nightly batch stays nightly (and *should*
ignore ticks). A thin, cheap live layer recomputes only Tier-F and answers one
extra question the slow brain can't: **has the live move invalidated a nightly
assumption?**

## The contract: baseline + overlay

- **Baseline (nightly):** the full scored snapshot — the decision **spine**
  (conviction, verdict, regime, allocation). Stamped `asof` (close date) + `built`.
- **Overlay (intraday):** per-ticker live price + recomputed fast leaves + a
  **divergence flag**. Stamped `quote_ts`, `source`, `delay_min`, `stale`.

Reconciliation rule, enforced in code (`engine.live_overlay.merge_baseline`):
**the live layer never rewrites a slow-brain score.** It refreshes timing leaves
and raises a flag; when the overlay is stale *or* diverging (an `alert`), the
consumer defers to the nightly baseline (`act_on_live = false`).

## What was built (Phases 1–3)

### Phase 1 — shared "fast brain" + bot contract
- `engine/live_overlay.py` — **pure, importable** (no network/disk): `read_close`,
  `splice` (live price onto the nightly series), `live_tech` (refresh technicals),
  `divergence` (live move vs the nightly short-horizon cone + RSI/MACD crossings),
  `staleness`, `build_ticker_overlay`, and `merge_baseline` (the reconciliation the
  bot applies). The bot imports these and calls the **same** recompute the website
  uses — reading the nightly baseline JSON + a live price.
- Mastermind emit upgraded to **v2** (`scripts/build_masterminds.py`,
  `scripts/build_china_masterminds.py`): `data/regime/masterminds_latest.json` and
  the China twin now carry **current allocation weights + `asof` + `stale_after_min`**
  in JSON, so the bot reads weights from JSON instead of scraping the HTML pages.

### Phase 2 — overlay emit
- `engine/live_quotes.py` — live last-price fetch. Routes US→Polygon snapshot
  (entitled, key server-side), everything else→Yahoo `spark` (keyless); US falls
  back to Yahoo with no key. Pure parsers + isolated HTTP → unit-testable; offline
  returns `{}`.
- `scripts/build_live_overlay.py` — assembles the universe (Mastermind GTAA assets
  + China GTAA + top-N US conviction names + config extras, capped), fetches quotes,
  builds the overlay, mirrors the GTAA allocations marked-to-live, and writes
  `site/live/overlay.json` (+ `site/live_config.js`). **Fail-safe:** any source down →
  the file still emits, legs marked `stale`, consumers fall back to baseline.
  `--offline` forces that path.

### Phase 3 — website progressive enhancement
- `worker/quotes.worker.js` (+ `wrangler.toml`) — Cloudflare Worker quote proxy:
  Polygon (US) + Yahoo spark (rest), edge-cached, CORS, key server-side. Mirrors the
  Python routing so site and bot agree.
- `templates/live.js` — patches live prices into the static cards (`.nb-px[data-sym]`),
  adds a freshness dot (green=live, grey=stale), tooltip with source + age. **Pure
  display**, polls every `live.poll_seconds`, and **cleanly no-ops when no Worker URL
  is set** — so the static deploy is unchanged until you opt in.
- Wired into `dashboard.html.j2` (US), `china.html.j2`, `hk.html.j2`; `build_site.py`
  copies `live.js` and writes `live_config.js` from `config.yml`.

Config lives under `live:` in `config.yml`.

## Data contracts

`site/live/overlay.json` (`schema: live.overlay.v2`):
```
{ built, quote_ts_max, stale_after_min, max_chg_pct,
  sources{us,intl,polygon_key,polygon_status},
  sessions: { us|cn|hk|ca: {region,open,local_time} },
  market: { SPY|QQQ: {price,chg_pct,stale}, VIX: {price,chg_pct,band,stale} },
  n, n_fresh, n_quotes,
  tickers: { TICK: { price, source, price_basis, quote_ts, delay_min, stale,
                     stale_reason, age_min, region, session_open,
                     baseline_asof, baseline_age_days, baseline_stale,
                     prev_close, chg_pct, tech{...},
                     divergence{flag,severity,detail,chg_pct,band,horizon,extreme} } },
  allocations: { us|china: { built, cards:[{key,name,asof,
                     alloc:[{asset,weight,live_price,chg_pct,stale}]}] } } }
```
`divergence.flag ∈ {within_band, band_breach_up, band_breach_down, rsi_cross,
macd_flip, baseline_stale, bad_print, no_quote}`; `severity ∈ {none, watch, alert,
info}`. The breach is tested against the nightly **one-session** expected-move band
(`horizon:"1d"`, derived from `anticipation.vol_cone_ann`), not the multi-day cone —
a single-session move beyond the 5-day cone in one day is additionally flagged
`extreme`. `price_basis` (trade/minute/day/prev/regular) tells a real live trade
from a prior close; `session_open`/`sessions` distinguish "stale because closed"
from "feed broke during RTH".

`masterminds_latest.json` (`schema: masterminds.latest.v2`): adds per-card
`alloc:[{asset,label_en,label_zh,weight}]`, `asof`, `gross_now`; top-level `asof`,
`stale_after_min`.

## How the bot consumes it

```python
import json
from engine import live_overlay as lo, live_quotes as lq

baseline = json.load(open("vendor/macro/site/stockdata/NVDA.json"))
quote = lq.fetch_quotes(["NVDA"]).get("NVDA")
close = lo.read_close("NVDA")
overlay = lo.build_ticker_overlay("NVDA", baseline, quote, close, stale_after_min=20)
read = lo.merge_baseline(baseline, overlay)
# read.conviction / read.verdict  -> nightly slow brain (authoritative, untouched)
# read.live_price / read.chg_pct  -> live timing
# read.act_on_live                -> data trust: True iff the quote is FRESH
# read.invalidated                -> True when a FRESH price breached the nightly band
# read.divergence / .route_hint   -> the invalidation signal + a coarse routing hint
```
Note the reconciliation rule: `act_on_live` reflects **data trust only** (a stale
quote → defer to baseline). A *fresh* breach is **not** suppressed — it surfaces as
`invalidated` so the bot acts at exactly the moment the nightly assumption broke.

For allocations the bot reads `masterminds_latest.json` weights and marks them with
`live_quotes.fetch_quotes(asset_tickers)` — only fresh, real-trade, non-outlier
prices are marked (a stale/limit-move leg is left `stale` with no live price).

## Sharpening accuracy (why this is *more* accurate, not just faster)

1. **Point-in-time stamping** on every live field (`quote_ts`, `source`, `delay_min`,
   `price_basis`) — and `delay_min` is measured from the **trade** time, not the
   snapshot-refresh time, so a delayed/illiquid print can't look fresh.
2. **Horizon-matched divergence** — a single-session move is tested against a true
   one-session expected-move band, not a 5-day cone (which made breaches near-
   impossible). Breaches are real signals again.
3. **Staleness gating, not last-value-carry** — a missing/old/non-live-basis quote →
   fall back to baseline; "closed" vs "feed broke during RTH" are distinguished.
4. **Outlier + baseline-staleness guards** — a glitch print (>`max_chg_pct`) or a
   stale nightly baseline (>1 trading day) can't manufacture a divergence.
5. **Hysteresis guard** — the live layer raises flags; a regime/score *change* still
   requires the nightly process. No tick manufactures a slow-brain signal.
6. **Per-source latency is explicit** — Polygon ≈ real-time US (with `polygon_status`
   surfacing auth/entitlement failures); Yahoo spark ≈ 15-min CN/HK/CA.

## Deployment

1. `cd worker && wrangler secret put POLYGON_API_KEY && wrangler deploy`.
2. Put the deployed `https://…workers.dev` URL into `config.yml → live.quotes_worker_url`.
   The next build bakes it into `site/live_config.js`; the browser cards go live.
3. **Overlay emit cadence** (`scripts.build_live_overlay`): run from whatever
   scheduler fits — a small VPS/serverless cron, or have the bot call the engine
   functions directly (cheapest, no publish latency). We intentionally do **not**
   add a per-minute GitHub Action: it would commit `overlay.json` on every tick and
   flood git history. Browser liveness comes from the Worker, not from committing.

## Non-goals / deferred

- **Phase 4 — live GEX/options.** Needs real-time OI/IV; expensive + entitlement-
  gated. Hourly option-chain snapshots are the reasonable compromise when prioritised.
- **No live macro-regime recompute.** Regime is hysteresis-gated; intraday updates
  would whipsaw. The overlay only *flags* when price breaches the nightly cone.

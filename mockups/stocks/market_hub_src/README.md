# /stocks/ market hub — mockup source

Regenerates `mockups/stocks/market_hub_v1.html`, the design proposal that
replaces the 1,544-card wall at `site/stocks/index.html`.

```bash
python3 mockups/stocks/market_hub_src/gen_mockup.py "$PWD" "$PWD/mockups/stocks/market_hub_v1.html"
```

## What is real in the mockup

Read from the committed `site/marketdata/sp500_heatmap.json` and computed by the
**production** `engine.market_heatmap.page_summary()` — the same arithmetic the
shipped page would run:

- the universe (501 S&P names), company names, sectors, industries
- market-cap-proxy tile sizes, 1D/1W/1M/3M/6M/1Y/MTD/YTD returns
- the stance headline (`_stance()`), breadth split, median move, sector strength
- top gainers / top losers, the treemap, the spine curve

## What is a production-shaped placeholder

These live in `site/stockdata/<T>.json` and `site/ohlc/<T>.json`, both gitignored
and R2-published, so a fresh checkout has neither. The shipped builder
(`scripts/build_ticker_pages.py`) already loads both per ticker and reads them
for real:

| Field | Real source at build time |
|---|---|
| price | `ctx["hero"]["price"]` |
| 1D change | `_day_change(ohlc_bars)` — already computed |
| volume / dollar volume | `ohlc_bars[-1][5]` (candle format, index 5) |
| unusual volume (×normal) | last volume ÷ trailing median volume |
| 52-week position | `_range52()` — already computed |
| our read (stance chip) | `ctx["stance_key"]` — already computed |

`market_hub_v1.html` carries a MOCKUP banner stating this, so nobody mistakes a
placeholder price for a quote.

## Design notes

- **No literal surface colour anywhere in `hub.css`.** Every background resolves
  from a theme.css token. The page being replaced hard-coded
  `rgba(16,22,30,.55)` on `.card` with a light override on the base rule only, so
  `.card:hover` — which had no light twin — repainted every hovered card charcoal
  in light mode. That was the reported defect.
- Directional colour is always `var(--up)` / `var(--down)`, so
  `html[data-lang="zh"]`'s red-up/green-down swap propagates for free, including
  through the treemap ramp and the spine fills.
- The treemap is **server-rendered**. `/marketdata/sp500_heatmap.json` is behind
  the auth gate (see `app/deploy/Caddyfile`) while `/stocks/*` is anonymous-public,
  so a client-side fetch would render an empty card for every logged-out visitor
  and every crawler.
- The A–Z directory keeps all 1,544 internal links the crawl hub exists to
  provide — as text chips rather than cards, which is what let the page shed the
  bulk of its weight.

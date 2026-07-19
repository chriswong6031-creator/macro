# MKT-D04 — Indicators M2: VWAP / Anchored VWAP / Volume Profile / Point of Control

**Department:** Workshop (products) + Studio · **Priority: P1** · **Status: ready now, no operator input**
**Playbook (read it):** `research/MARKETING_TRENDSPIDER_PLAYBOOK_AND_CHART_ENGINE_BY_FABLE.md` — M2 is the named indicator gap vs. TrendSpider after M1 (MACD/RSI/StochRSI crosses) shipped in #2971.

## Why

VWAP/AVWAP and Volume Profile are the two indicator families TrendSpider leans on hardest in high-reach posts ("price reclaimed the AVWAP from earnings", "POC at $187 is the battleground") that we cannot currently compute, post, or mine for confluence. They unlock: richer chart annotations, new confluence combos with historical win rates, and Terminal/Tech-Lab feature parity.

## What already exists (do not rebuild)

- M1 cross events: `engine/momentum_events.py` (weekly MACD+RSI crosses, weekly/biweekly StochRSI; warm-up-phantom guard — crosses require a valid opposite prior bar. Preserve this pattern).
- Confluence miner: `engine/tech_confluence.py` (2–4-signal combos, train/test win rates, `active_now`) + `engine/tech_catalog.py` (indicator registry) + `site/tech_lab.html#combos`.
- Marketing chart engine: `engine/marketing/chart_render.py` (`render_chart_v2` with SETUP highlight + MACD/VOL subpanels).
- OHLCV access: `load_ohlcv` in chart_render (open=prev-close proxy — note the proxy when computing session VWAP) and the stockdata blobs.

## Deliverables

### W1 — calculations + catalog
1. `engine/indicators_m2.py` (or extend the existing indicator home if the builder finds one — check `engine/tech_catalog.py` imports first): rolling VWAP (daily/weekly), **Anchored VWAP** from an event anchor (earnings date, signal date, YTD, 52w-low), **Volume Profile** over a lookback window → POC + Value Area (70%) bounds. Pure functions over OHLCV frames, deterministic, tested against hand-computed fixtures.
2. Register in `engine/tech_catalog.py` so Tech Lab and the confluence miner can see them.

### W2 — confluence + events
3. New event families for the miner: `price_reclaims_avwap_earnings`, `price_above_vwap_w`, `poc_retest_hold` — same warm-up-guard discipline as #2971. Mine combos with the existing train/test split; surface on `tech_lab.html#combos`.
4. **Render-budget law:** volume-profile per-ticker sweeps are heavy. Compute in a cached nightly step OFF the render path (artifact keyed by ticker+window fingerprint, à la the baskets member-chip fingerprint cache), never inline in build_site.

### W3 — chart + posts
5. `chart_render.py` annotation options: AVWAP curve from a labeled anchor, POC horizontal with shaded Value Area band. Style must match the v3 branded look (thin, labeled, non-cluttering — the operator's bar is TrendSpider-grade, not indicator soup).
6. `chart_facts.py` fact emitters: "held the AVWAP from the Apr earnings gap for 31 sessions" style facts with whitelisted numbers, so the copywriter can use them safely.
7. Terminal (separate repo `charting-app`): port the same three families as Terminal indicators. Separate PR in that repo; keep formulas identical (share fixture values across both repos' tests).

## Acceptance

- Fixture parity: VWAP/AVWAP/POC values match hand-computed references to 1e-6; warm-up guard test (no event on first valid bar).
- A mined combo containing an M2 family appears in `tech_lab.html#combos` with train/test win rates; `active_now` lists real tickers.
- A rendered marketing chart with AVWAP + POC annotations passes a `designer`/opus screenshot taste gate (operator law: reviews of user-facing charts need a screenshot gate).
- Nightly render time delta ≈ 0 (cached artifact does the heavy work off-path).

## Traps

- The `load_ohlcv` open-price proxy (open=prev close) biases *intraday-true* VWAP — we only have daily bars, so define VWAP as typical-price ((H+L+C)/3)·V cumulative, and say so in the catalog description. No false intraday claims in copy.
- Confluence stats are **display-tier with printed train/test splits** — never "validated" (CI-enforced word).
- Cross-repo work: the Terminal PR follows charting-app's own conventions; don't copy this repo's scaffolding there.

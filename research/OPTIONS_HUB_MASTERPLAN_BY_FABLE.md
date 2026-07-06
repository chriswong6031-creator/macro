# OPTIONS HUB — UW-suite feature integration masterplan by Fable

_Authored by Fable, 2026-07-05. Operator directive: integrate the complete Unusual Whales
options feature suite — backend + customer front end on the Terminal (app.mastermind-x.com) —
with OUR design language (SaaS-modern, bilingual), not UW's Bloomberg-dense style. Grounded in
a 40-screenshot inventory of the UW web app + the operator-supplied feature map
(unusual_whales_options_data_features.md). Extends research/LIVE_FLOW_PRODUCTION_ROADMAP_BY_FABLE.md
(plan of record for validation tracks — unchanged) with the PRODUCT surface build.
Model routing: Sonnet builds, Opus reviews, Fable adjudicates._

## §0 In plain English

We already own most of the data UW sells: a live signed options tape (shipped 2026-07-05),
12–14 years of per-contract EOD/OI, 9 years of per-contract greeks incl. vanna/charm, and
per-name GEX summaries. What's missing is the PRODUCT: intraday tide/series aggregation,
per-ticker drill analytics, chain/OI screeners, vol-surface views, and dealer-exposure
profiles — served to the Terminal as a coherent Options Hub. This plan builds that in phases,
without touching the money path (display-tier only, Neural Web Article 2).

## §1 Screenshot → feature → data-path map (inventory 2026-07-05)

| UW surface (screens) | Our data path | Phase |
|---|---|---|
| Live Options Flow tape + saved filters/presets | live_flow poller events (notable, floors) | SHIPPED + H1 polish |
| Flow Alerts (unusual feed) | live_flow flags (repeated, vol>OI, z) + sweep-like heuristic (multi-exchange same-contract burst) | H1 |
| Interval Flow / DTE Tide (net prem by DTE bucket, minute series) | poller day-state minute buckets | H1 |
| Net Flow per ticker; net prem ticks; flow by strike/expiry | poller day-state per-root minute series + rollups | H1 |
| Market Tide (cum. NCP/NPP vs SPY) + Top Net Impact + Sector Flow table | poller batch accumulation by group | H1 |
| OI Explorer (ΔOI screener) | T1 oi store (2012→), nightly deltas | H2 |
| Hottest contracts / chains screener | T1 eod latest day + intraday day-state | H2 |
| Contract Lookup (per-contract history + intraday fill quality) | intraday: day-state; history: T1 eod (post-R2 publish) | H2 (intraday) / H3 (history) |
| Per-ticker IV Smile / Term Structure / IV Rank | T1 greeks 2017→ (implied_vol, underlying_price) | H2 |
| SPX&VIX vol dashboard (IV rank, RV vs IV, VRP, VIX term) | T1 greeks + yahoo RV + existing vix_curve store | H2 (ETF-first) |
| Periscope: MM exposure by strike/expiry; greek tabs gamma/delta/vanna/charm; net GEX heatmap; delta flow | T1 greeks×OI[t-1] ladders (REUSE engine/gex_model dealer-sign); polygon_gex summaries; #1374 index recon | H2 (nightly ladders) / H4 (intraday) |
| Ticker Overview options sub-tabs (strikes/net-prem/avg-vol) | day-state + T1 | H1/H2 |
| Earnings sub-tab (moves around earnings, expected vs actual) | event_calendar + T1 implied move | H3 |
| Institutions 13F | existing smart-money tracker (dashboard) | H3 (mirror) |
| NOPE / options price pressure | signed tape × delta (T1 greeks) | H3 (model-derived; labeled) |
| Fear/Greed + Dark Pool (operator: "push in later") | engine/fear_greed.py #1324, darkpool #1327 | H3 (Terminal mirror) |
| WS/streaming, custom alert builder, Kafka/MCP | — | H4+ (gated; polling first per ruled architecture) |

## §2 Laws (binding, inherited)

1. Display-tier ONLY — nothing here ranks/scores/gates the money path (Article 2).
2. "Unusual"/"notable"/"hot" = LABELED HEURISTICS; the words "signal" and "validated" are
   banned in user-facing strings (CI-guarded word for the latter).
3. Direction stays `~`-soft (signing_source=tape; multi-session calibration extension pending).
4. 0DTE bucket-labeled, never glorified. NOPE-class model outputs labeled "model-derived".
5. DEBRAND — no vendor/competitor names on customer surfaces (both repos).
6. EN/ZH everywhere; Terminal i18n via lib/i18n LEX; no zh-only-in-title-attr on dashboard pages.
7. Pure vendor-derived surfaces ship public. Engine-FUSED surfaces (oracle/standout/gex-regime
   annotations) wait for the P0.6 licensing filing (research/licenses/ — STILL UNFILED).
8. Coverage honesty: single-name analytics appear as the T1 universe pass completes (~Jul 8–12);
   every analytics payload carries `coverage` metadata; UI renders "coverage expanding" states.
9. GEX ladders REUSE engine/gex_model.py dealer-sign assumptions — no second convention.
10. OI is always t-1 (or older); same-day OI comparisons are a lookahead bug class.
11. Boring infra: parquet + R2 + JSON over the existing planes. No ClickHouse/Kafka/WS daemons
    until a measured need (brainstorm §6 rejections stand).

## §3 Phase H1 — intraday product core (THIS SESSION, backend + frontend)

Backend (dashboard repo):
- Poller/day-state extension: minute-bucket accumulators —
  (a) market tide: cumulative net call prem, net put prem, gross, volume, per minute;
  (b) per-sector tide (same fields by GICS group);
  (c) per-root minute series (net prem C/P, vol) for drill charts;
  (d) DTE-bucket tide (0d/1_7d/8_30d/31_90d/90p);
  (e) per-root strike + expiry day rollups (gross/net prem, vol, top contracts);
  (f) sweep-like flag: same contract, ≥3 prints, ≥2 exchanges, ≤2s span — labeled "swept"
      (heuristic; never "institutional").
- New R2 objects (live_flow/ prefix, overwrite-per-cycle):
  tide_current.json, dte_tide_current.json, tickers/{ROOT}.json (top ~40 by day gross),
  spy_anchor.json (SPY minute closes from tape for tide overlay).
- app/main.py: /api/flow/tide, /api/flow/dte, /api/flow/ticker/{root} (+existing).
- launchd plist + runbook for RTH poller autostart (ops/).
Frontend (charting-app, branch feat/options-hub off feat/flow-desk):
- /flow becomes the Options Hub: tab bar [Tape, Tide, Tickers, Screener, Vol, GEX].
- Tape = existing feed table (polish: sector column, sweep chip, presets dropdown
  [High conviction ~buys, Repeat hits, 0DTE, Puts on strength] as saved client-side filters).
- Tide = market tide chart (cumulative NCP/NPP area + SPY line overlay, minute x-axis),
  sector tide small-multiples, Top Net Impact bars, DTE tide panel.
- Tickers = per-name drill: minute net-prem chart, strike ladder bar chart, expiry bars,
  top contracts table, day stats card.
- Charts: lightweight-charts v5 (already in repo) for time series; inline SVG for ladders.
- SaaS design language: existing Terminal glass/cards/tokens; NOT UW's dense terminal look.

## §4 Phase H2 — nightly analytics products (THIS SESSION if budget allows, else next)

- scripts/build_options_hub_nightly.py (Mac, off render path): per-root JSONs → R2 options_hub/:
  vol/{ROOT}.json (IV rank 252d, ATM IV, term structure, smile per near expiries, RV20 vs IV,
  VRP; from T1 greeks), gex/{ROOT}.json (gamma/delta/vanna/charm by strike + expiry,
  net + C/P split, walls/flip from gex_model convention), oi_movers.json (top ΔOI contracts),
  hot_contracts.json (premium/vol/vol>OI leaders).
- API: /api/hub/{vol|gex|oi|hot}. Terminal tabs Screener/Vol/GEX consume them.
- ETF anchors first; auto-widen as universe pass lands (coverage metadata).

## §5 Phase H3/H4 — deferred (recorded, not built)

H3: contract-lookup deep history (needs thetadata_eod R2 publish P0.2), earnings positioning
tab, NOPE (labeled), fear/greed + dark pool Terminal mirrors, 13F mirror, seasonality.
H4: intraday GEX refresh, WS streaming (earn-in law), custom alert builder → alert_triage,
options_events nerve registration (P-D; #1368 holds options_flow/iv_surface only).

## §6 Status log

| Date | Event |
|---|---|
| 2026-07-05 | Masterplan adopted. H1 dispatched (backend intraday + hub UI); H2 dispatched (nightly analytics, ETF-first). Screenshot inventory: 40 screens → §1 map. |

# Macro Regime & Sector-Flow Dashboard

Zero-cost daily market dashboard for a top-down framework: **macro regime →
factor appetite → sector flows → sector selection**. Its most important job is
classifying the current regime, scoring confidence, and flagging transitions
before they're confirmed.

No server. GitHub Actions collects data after the US close, commits parquet to
this repo (the repo *is* the database), regenerates a static dashboard on
GitHub Pages, and pings Telegram/Discord with the daily snapshot and any fired
alerts.

## The regime model in one paragraph

Two axes scored daily from market-priced inputs: **growth** (copper/gold,
XLY/XLP, 2Y direction, IWM/SPY, cyclical/defensive basket, breadth; payrolls +
INDPRO as half-weight confirmations) and **inflation** (10y/5y5y breakevens,
energy RS, oil, inflation-beta basket, TIPS-vs-nominal momentum). Each
component is ±1/0 by drift t-stat (20d vs 60d vol); the weighted sums map to a
quad — **Q1 Goldilocks, Q2 Reflation, Q3 Stagflation, Q4 Growth-scare** — with
recession and inflation-shock refinements, a liquidity overlay (WALCL − RRP −
TGA trend), and a cycle tag. Hysteresis (7d confirmation or ±0.85 shock
override) kills whipsaw. A separate transition detector (6 divergence flags →
STABLE/WEAKENING/TRANSITIONING/NEW_REGIME) is designed to fire *before* the
quad flips. Validation: [reports/validation.md](reports/validation.md).

## Beyond the quad: conditions, nowcasts & equity factors

A second, *complementary* layer brings in the non-technical signals quant and
macro firms use — without touching the validated quad. See
[research/QUANT_FACTOR_EXPANSION.md](research/QUANT_FACTOR_EXPANSION.md).

- **Macro nowcast · conditions · risk-appetite panel** (`engine/conditions.py`,
  on macro.html): a Chicago-Fed **NFCI** financial-conditions read; a 0–100
  **recession-risk** score (Sahm rule + smoothed probability + the Fed Board
  **Excess Bond Premium** + a **term-premium-adjusted curve** that strips the
  2022–24 false inversion); real-time **growth** (Weekly Economic Index, GDPNow)
  and **inflation** (Atlanta sticky-vs-flexible CPI) nowcasts; and an
  option-implied **risk-appetite** read — equity volatility-risk-premium, VIX
  term structure, CBOE **SKEW**, the **stock-bond correlation** regime, and a
  cross-asset **RORO** composite. New alerts: NFCI tightening, Sahm trigger, EBP
  spike, recession-band change. All free FRED/CBOE/Fed-Board data.
- **Equity factor rankings** (`factors.html`, `engine/equity_factors.py`): the
  cross-sectional factors quant-equity desks actually trade — **value, quality,
  gross profitability, investment, shareholder yield, low-volatility and
  betting-against-beta** — computed over the S&P 1500 from **SEC EDGAR XBRL**
  fundamentals joined to prices (free, keyless), not proxied by a factor ETF.
  A "what's working now" leadership read ties factor rotation back to the regime.
  These are ranks/context, not a validated alpha — see the caveats in
  [LIMITATIONS.md](LIMITATIONS.md).
- **Four more free datasets** extend the above: **commodity roll-yield carry**
  (backwardation/contango from dated Yahoo futures → Commodity Vector), **EIA
  petroleum supply** (crude stocks vs 5y range, draws/builds, production →
  oil page), a **FINRA short-interest** factor (days-to-cover, the least- vs
  most-shorted cross-section), and **SEC Form-4 insider conviction** (net
  open-market buying vs selling, on the Factors page). All keyless; caveats
  (lags, reconstruction limits, sec.gov rate-limits) in
  [LIMITATIONS.md](LIMITATIONS.md).

## Run locally

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m scripts.collect              # daily incremental collection
.venv/bin/python -m engine.run                   # classify + evaluate alerts
.venv/bin/python -m scripts.build_site           # -> site/index.html
.venv/bin/python -m scripts.notify --dry-run     # preview the daily message
.venv/bin/python -m scripts.weekly_report        # -> reports/weekly-*.md
.venv/bin/python -m scripts.validate             # full 2007-> backtest report
.venv/bin/python -m tests.test_engine && .venv/bin/python -m tests.test_alerts
```

First-time setup needs history: `scripts.collect --full-history`, plus
`scripts.fetch_archive` (archived OAS) — or just dispatch the **backfill**
workflow once after pushing to GitHub.

## China A-share dashboard (Section 3)

A full clone of this dashboard for Mainland A-shares — same regime engine,
sector rotation, ETF/constituent drill-downs, history, daily brief and
single-stock search — reachable from the landing hub (🇨🇳 card) and bilingual
(EN ↔ 中文). Two free data planes: **yfinance** (indices/sector-ETFs/stocks) and
**Eastmoney** JSON (PMI/CPI/PPI/M2/industrial-production + Stock-Connect). The
regime is calibrated + tuned on 2008→2026 (only the **Growth-scare** quad and
**expanding-PBoC-liquidity** overlay survive split-half robustness — shipped as
risk context, not allocation rules). Data sources: [research/CHINA_DATA_AUDIT.md](research/CHINA_DATA_AUDIT.md);
honest caveats in [LIMITATIONS.md](LIMITATIONS.md).

```bash
.venv/bin/python -m scripts.collect --full-history --only china_prices,china_macro,china_breadth
.venv/bin/python -m scripts.calibrate_china       # split-half forward-return + ladder calibration
.venv/bin/python -m scripts.build_china           # -> site/china.html + sectors/ + search + history + brief
```

`build_china` runs after `build_site` and before `build_vector` (which writes
the hub last); it's self-sufficient and returns 0 on any engine error, so it can
never break the macro/vector site.

## Hong Kong / Hang Seng dashboard (Section 4)

A full clone re-thought for Hong Kong — reachable from the landing hub (🇭🇰 card),
bilingual (EN ↔ 中文). HK is ~2× more globally sensitive than the Mainland, so the
regime stands on **three legs**: (1) China-driven fundamentals (reuses the
`china_macro` plane — HSI earnings are China's), (2) a **primary Global Risk
Overlay** (a dollar/VIX/US-equity/copper-gold/USD-CNY/EM composite + the HKD peg
distance 7.75↔7.85, shown as the dashboard hero), and (3) HK-internal structure
(H-share leadership, the HS-TECH tilt, breadth). **Sectors are deep synthetic
baskets** of curated HK large-caps (15–25y history, richer than HK's thin sector
ETFs), RS-ranked vs `^HSI`. Includes sector drill-downs, history, a daily brief and
a single-stock analyzer/search over the HK universe. Calibrated 2000→2026
(split-half): Goldilocks is the best quad and Stagflation the worst — both stable
across halves — expanding dual-liquidity is a tailwind, and the global risk state
differentiates HSI forward returns monotonically (Risk-on > Risk-off > Neutral).
Data sources: [research/HK_DATA_AUDIT.md](research/HK_DATA_AUDIT.md); honest caveats
in [LIMITATIONS.md](LIMITATIONS.md).

```bash
.venv/bin/python -m scripts.collect --full-history --only hk_prices,hk_breadth
.venv/bin/python -m scripts.calibrate_hk          # quad + dual-liquidity + global-risk + ladder calibration
.venv/bin/python -m scripts.build_hk              # -> site/hk.html + sectors/ + search + history + brief
```

`build_hk` runs after `build_site`/`build_china` and before `build_vector`;
self-sufficient and returns 0 on any engine error (it can never break the rest of
the site). Global-risk factors (DXY/VIX/SPY/copper/gold/USD-CNY/EEM) are read from
the existing `yahoo`/`china`/`hk` store groups; only `EEM` + `HKD=X` are newly
collected. Macro is reused from `china_macro` (no new scraper).

## GitHub setup (one-time)

1. Create a repo, `git remote add origin …`, push `main`.
2. Secrets (Settings → Secrets → Actions): `FRED_API_KEY` (free key,
   strongly recommended — the keyless fallback endpoint has multi-hour
   outages), optional `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`,
   `DISCORD_WEBHOOK_URL`, `FINNHUB_KEY`.
3. Settings → Pages → Source = **GitHub Actions** (Pages can't serve `/site`
   from a branch; the workflow deploys an artifact).
4. Actions tab → run **backfill** once.
5. To enable Telegram/Discord, also set `notify.telegram.enabled` /
   `notify.discord.enabled` in `config.yml`.

Schedules: daily 22:40 UTC weekdays (after US close; off-hour minute dodges
scheduler congestion), weekly Saturday 14:00 UTC. Expect up to ~40 min of
GitHub scheduler jitter.

## How to read the dashboard

Every metric on the page has a hover-? tooltip; the "New here?" expander at
the top gives a 60-second orientation. The flow:

- **Header**: regime badge + transition radar are the two things that matter.
  Signal agreement below ~30% means the indicators disagree — expect chop and
  trust the radar more than the label.
- **Playbook panel**: the conclusions layer. An exposure dial
  (DEFENSIVE→AGGRESSIVE) built only from conditions that held up in both
  halves of the 2007–2026 backtest, confirmed sector leadership, an
  evidence-backed avoid list (don't chase extended leaders: 44.7% hit rate;
  don't buy below-trend bounces: negative in every variant tested), the
  probable next regime from historical transition odds, and what would change
  the picture. Sector calls are risk filters, not return predictions — the
  panel says so itself.
- **The two dials**: growth and inflation gauges with the indicators voting
  for/against, the weakest link, and whether the tape agrees with the regime.
- **Sector scoreboard**: rotation stage per sector (improving → leading →
  weakening → lagging) plus relative momentum and year-position.
- **Positioning**: who's crowded where; percentiles near 100 or 0 are
  contrarian context, detailed in the weekly report.
- **Data health footer**: stale sources degrade confidence, never crash the
  run. `blocked` = known, documented limitation (AAII), not a malfunction.

## Alerts and what they mean

| rule | meaning |
|---|---|
| transition_state_change | The detector escalated/de-escalated (e.g. STABLE→WEAKENING). The single most important alert. |
| axis_confidence_floor | An axis's confidence crossed below 0.3 — its components stopped agreeing. |
| sector_rs_cross_high/low | A sector's RS vs SPY crossed the 90th/10th pctile of its 90d range. |
| holdings_active_change | A watchlist manager added/cut ≥20% of a position over 5d, flow-normalized (not creations/redemptions). |
| net_liquidity_roc_flip | The 4-week net-liquidity impulse changed sign. |
| hy_oas_widening | HY OAS widened >2.5σ in one day — credit stress print. |
| gex_flip_cross | Spot crossed the gamma flip or net GEX changed sign — vol regime fragility. |
| circuit_breaker_open | A collector died 3 runs straight and is being skipped. |

## How to add a source

Subclass `Adapter` in `collectors/<name>.py`: implement
`fetch(full_history) -> {series_name: DataFrame(date-indexed)}`, raise on
failure (the runner handles retries/breaker/status), register it in
`scripts/collect.py:all_adapters()`, and put every URL/tunable in
`config.yml`. Storage is append-only upsert — nothing ever silently deletes
history.

## How to tune

Everything is in [config.yml](config.yml): axis component weights, scoring
windows and z-threshold, hysteresis, liquidity thresholds, transition flag
parameters, sector preference table, alert thresholds, watchlist. After any
engine change, re-run `scripts.validate` (and ideally the `scripts.tune`
sweep) and check whipsaw stays <15% and the episode checks still pass.

## Weekly 10-minute ritual

1. Data-health footer: anything failed/dead? (AAII is expected-dead; FRED
   failed is fine if `last data` is recent.)
2. Glance at the weekly report's rotation-vs-regime verdict and contrarian
   flags.
3. Skim `reports/validation.md` drift after engine edits — whipsaw % and the
   2008/2020/2022 episode shares shouldn't move materially.
4. Quarterly: spot-check one ETF holdings diff against the sponsor site
   (N-PORT lags ~60d; it validates the scraper, not the signal).

## Honesty

Read [LIMITATIONS.md](LIMITATIONS.md) before trusting anything here. Biggest
caveats: breadth is survivorship-biased in backtests, GEX rests on the
standard dealer-positioning assumption, put/call is a computed proxy, the
earnings-revision module is weak by construction, and everything Yahoo is an
unofficial API. Engineering rationale lives in [DECISIONS.md](DECISIONS.md).

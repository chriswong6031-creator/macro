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

- **Header**: quad badge + transition state are the two things that matter.
  Confidence below ~30% means the axes are mixed — expect chop, trust the
  transition state more than the label. Liquidity overlay modifies risk
  appetite *within* the quad (Q1 + contracting = fragile goldilocks).
- **Axis panel**: confirming vs contradicting components, and the single most
  fragile input ("flip risk") — the explicit what-would-change-my-mind.
- **Framework vs tape**: when preferred sectors for the quad aren't actually
  leading, that disagreement is itself a transition signal.
- **Sector RS table**: ranked by 60d RS momentum vs SPY. ▲/▼ = above/below
  the 200d RS trend.
- **Positioning**: percentiles of full stored history; >90 or <10 are
  contrarian flags, detailed in the weekly report.
- **Data health footer**: stale sources degrade confidence, they never crash
  the run. fred:failed with recent `last data` just means the live endpoint
  was down that day.

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

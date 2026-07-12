# Odds Desk — Historical Base-Rate Analyzer + Factor Match screener
## Build spec v1 (2026-07-11) — for the macro dashboard (macro repo)

### What this is
A clone-and-improve of tradeodds.io's flagship features, native to our stack:

1. **Analyzer** — pick a ticker; the page shows today's "market fingerprint" as a set of
   toggleable conditions (each with today's observed value); every active condition filters
   35y of history to days that matched; the verdict is the empirical base rate of what
   happened next (win %, median/mean return, CI, sample size), plus the matching-day table,
   a forward price-path cone, and a return histogram.
2. **Factor Match** — a universe screener: the same condition template applied to every
   symbol (each vs its OWN history, sharing today's market-level context), ranked by
   historical win rate per horizon (1d/5d/20d) with a min-sample floor.

### How tradeodds.io does it (recon findings, for reference)
- One `daily_metrics` table: 35y × 3,210 symbols × 22M rows; ~16 pre-bucketed smallint
  INDEXED factor columns + pre-computed forward-return columns `fwd_1d/5d/20d_pct`
  (holiday-aligned, open-to-close: next open → close of horizon end).
- `POST /api/analyze-setup` = WHERE equality (±tolerance) on active bucket columns +
  aggregate. Response carries per-instance rows with every bucket value.
- Factor Match = same filter per symbol vs own history, shared market context
  (`regime_factors`), `min_instances` floor, response rows
  `{symbol, sector, current_factors, analysis_1d/5d/20d: {instances, mean_return, win_rate}}`.
- Bucket schemes (from their glossary/UI): Market Trend = SPY vs SMA50/200 four-state
  (Full Bull / Bull Correction / Bear Rally / Full Bear); VIX level bands (<12, 12–15,
  15–20, 20–25, 25–35, 35+ per impl); VIX move in 2% steps; RSI 5 zones (30/45/55/70);
  magnitude in 0.5-ATR steps; streaks in consecutive-day counts; volume streak vs 20d avg
  (±8 cap); overnight gap buckets; month-of-year; earnings/analyst (Pro; we skip v1);
  "Macro Risk" = yield-curve inversion only (ours will be far richer).
- Returns measured **open-to-close** ("what a trader could actually execute").
- Pipeline: nightly recompute; forward returns for older rows recomputed each run.

### Our architecture (static site — no server)
- **Engine (Python, nightly build)**: `engine/odds_lab.py` (pure functions) +
  `scripts/build_odds.py` (build lane). Computes per-ticker daily factor matrices +
  forward returns from the repo's parquet stores, publishes compact columnar JSON.
- **Client (JS)**: matching + stats run in the browser over the selected ticker's matrix
  (~9k rows × ~20 int cols; trivial). Factor Match is precomputed nightly for a small set
  of condition templates over the whole universe (arbitrary combos stay available on the
  single-name Analyzer; a screener template picker is the honest static-site trade).
- **Data plane**: heavy per-ticker matrices → `site/oddsmatrix/<T>.json` on **R2**
  (5-spot wiring, see below). Light artifacts stay in git/Pages:
  `site/oddsdata/catalog.json`, `site/oddsdata/factor_match.json`.

### Database / backfill answer (updated for audited data reality)
Audit findings: `data/yahoo/` (708 tickers) has close-only columns and uneven depth;
`data/stocks/` (230 tickers, 1980→) lacks OPEN; `data/baskets/ohlcv/` (2,519 tickers) has
full OHLCV but only 2014→. Our open-to-close fwd convention + gap factor need real opens
with deep history → **new dedicated store `data/odds_ohlcv/<T>.parquet`** (columns
open/high/low/close/volume, auto-adjusted), populated by `build_odds.py` itself:
- Ticker missing or stale >3 trading days → `yfinance` fetch: `period="max"` when the
  stored series is missing/shallow (one-time backfill; SPY→1993, many megacaps→1980s),
  else a 1-month overlap window upserted (mirrors `collectors/yahoo.py` line ~60 pattern).
- Store is **gitignored + R2-backed** (the `massive_stock_day` pattern) via publish_r2
  `_DATA_DIRS`; the self-hosted macstudio runners keep it on disk between runs, R2 is the
  cold-start hydration. NOTE `_DATA_DIR_MIN_FILES = 100` guard → universe must be ≥100
  names (it is) or the guard needs a per-dir override.
- The matrix build **recomputes the full factor matrix every run** (vectorized; seconds)
  — forward returns self-fill as future bars arrive; no incremental-index maintenance.
- ^VIX: use existing `data/yahoo/_VIX.parquet` (1990-01-02→, has close) — do NOT refetch.
- SPY for `mkt_trend`: from the odds store (fallback `data/yahoo/SPY.parquet`, 1993→).
- Macro quad joins from `data/regime/regime_history.parquet` (14,485 rows, **1971→**,
  cols incl. `quad`, `liquidity`, `transition_state`) — full coverage of our price history.

### Factor catalog (exact bucket contracts — unit-test the boundaries)
All buckets are small ints. Null (missing input) = JSON null; never matches while active.

**Market-level** (computed once per date from SPY, ^VIX, regime history; joined to all tickers):
| id | definition |
|----|------------|
| `mkt_trend` | SPY close vs SMA50/SMA200 (both include day t): 0 = Full Bull (>50 & >200), 1 = Bull Correction (<50, >200), 2 = Bear Rally (>50, <200), 3 = Full Bear (<both) |
| `vix_level` | ^VIX close: 0 <12, 1 12–15, 2 15–20, 3 20–25, 4 25–35, 5 ≥35 |
| `vix_move` | round(vix 1d %chg / 2), clip ±8 (2% steps) |
| `month` | 1..12 |
| `quad` | our macro quad from regime_history (map Q1..Q4 → 1..4; null where absent) — **our differentiator, tradeodds has nothing like it** |

**Asset-level** (per ticker):
| id | definition |
|----|------------|
| `pct_move` | close-to-close 1d %chg: round(pct / 0.25), clip ±12 (0.25% steps, ±3% tails) |
| `magnitude` | round(pct / (0.5 × atr_pct)), clip ±6, where atr_pct = ATR14 (Wilder) computed through **t−1** ÷ close[t−1] (prior-day ATR so "today's move vs typical" has no same-day contamination). Null until 15 bars. |
| `rsi_zone` | RSI14 (Wilder) at t: −2 <30, −1 30–45, 0 45–55, +1 55–70, +2 ≥70 |
| `rsi_slope` | rsi[t] − rsi[t−3]: −2 ≤−8, −1 (−8,−2], 0 (−2,+2), +1 [+2,+8), +2 ≥+8 |
| `rel_vol` | volume ÷ SMA20(volume through t−1): −2 <0.5, −1 0.5–0.8, 0 0.8–1.2, +1 1.2–1.75, +2 1.75–2.5, +3 ≥2.5 |
| `trend_structure` | s = (EMA9 − EMA21)/close: −2 ≤−1%, −1 (−1%,−0.15%], 0 (−0.15%,+0.15%), +1 [+0.15%,+1%), +2 ≥+1% |
| `streak` | signed run of consecutive up(+)/down(−) closes ending at t (flat close resets to 0), clip ±5 |
| `vol_streak` | signed run of consecutive days volume above(+)/below(−) its 20d SMA, clip ±8 |
| `gap` | (open[t] − close[t−1])/close[t−1]: round(pct / 0.25), clip ±6 |
| `dist_52w` | close vs rolling 252d max close: 0 ≥−1%, −1 (−5%,−1%], −2 (−10%,−5%], −3 (−20%,−10%], −4 ≤−20% (bonus factor tradeodds lacks) |

**Outcomes** (per ticker; ints in basis points, null when future bars missing):
- `fwd1_bp` = close[t+1]/open[t+1] − 1; `fwd5_bp` = close[t+5]/open[t+1] − 1;
  `fwd20_bp` = close[t+20]/open[t+1] − 1. Trading-bar aligned via positional index
  (never calendar math). Open-to-close convention, same as tradeodds, documented in UI.
- `ret_bp` = close[t]/close[t−1] − 1 (for client-side path reconstruction & charts)
- `gap_bp` = open[t]/close[t−1] − 1 (path: close[d+k]/open[d+1] = Π(1+ret[d+1..d+k]) ÷ (1+gap[d+1]))

### Matching semantics (client, and mirrored in the factor-match precompute)
- Candidate day d (excluding today; within selected range) matches iff for every ACTIVE
  factor: |bucket(d) − bucket(today)| ≤ tol. tol = 0 for categorical (`mkt_trend`,
  `month`, `quad`) and = global tolerance setting (0/1/2, default 0) for ordered factors.
- Days with null active-factor buckets or null outcome for the chosen horizon are excluded.
- Data range selector: 5y / 10y / 20y / max (default 10y).
- Default active set (mirrors tradeodds defaults): `magnitude` + `vix_level` + `mkt_trend`.

### Stats (client JS + tested Python mirror)
- n, wins (fwd>0), win_rate, median, mean, p25/p75, min/max.
- **Wilson 95% CI** on win rate (their "46–61%" chip).
- **Unconditional base rate** over the same range+horizon shown alongside — verdict is
  colored by edge-vs-base (≥+5pts green, ≤−5pts red, else neutral), the honest-coloring
  house rule from the BTC forward cones. Never color by raw win rate.
- n<20 → low-sample warning badge; n<5 → "insufficient sample", no verdict color.

### Files & contracts
- `site/oddsmatrix/<T>.json` — `{"schema":"odds_matrix.v1","ticker","asof","dates":[epoch_days...],"close":[...],"cols":{<factor_id>:[...], "ret_bp":[], "gap_bp":[], "fwd1_bp":[], "fwd5_bp":[], "fwd20_bp":[]}}` (columnar, ascending dates)
- `site/oddsdata/catalog.json` — `{"schema":"odds_catalog.v1","asof","market":{today's market buckets + raw values (vix level & 1d chg, spy vs smas, quad)},"factors":[{id,group,label_en,label_zh,desc_en,desc_zh,buckets:{<int>:{label_en,label_zh}},ordered:bool}],"universe":[{t,name,sector}],"defaults":{active:["magnitude","vix_level","mkt_trend"],range:"10y",horizon:"1d"}}`
- `site/oddsdata/factor_match.json` — `{"schema":"odds_factor_match.v1","asof","market":{...},"templates":[{id,label_en,label_zh,factors:[...]}],"horizons":["1d","5d","20d"],"range":"20y","min_n":10,"rows":[{"t","name","sec","cur":{factor:bucket...},"res":{<template>:{<horizon>:[n,win_rate,median_bp,mean_bp]}}}]}`
  Templates v1: core=[magnitude,vix_level,mkt_trend]; trend=[mkt_trend,trend_structure,rsi_zone];
  momentum=[pct_move,streak,rsi_slope]; vol=[vix_level,vix_move,rel_vol];
  quad=[quad,mkt_trend,magnitude]; strict=[magnitude,vix_level,mkt_trend,rsi_zone,rsi_slope].
- `templates/odds.html.j2` → rendered `site/odds.html` by build_odds.py; `site/odds.js`,
  `site/odds.css` (hand-maintained statics, tracked in git, cache-busted `?v=1`).

### UI spec (bar: institutional / Perplexity–Koyfin grade — see aesthetic memory)
- Copy nav from a current origin/main standalone page template; bilingual `L(en,zh)` spans
  everywhere; theme.css vars only; refined flat + generous spacing; glass only on chrome.
- Top bar: ticker search (typeahead over catalog universe, logo via
  `cdn.jsdelivr.net/gh/nvstly/icons@main/ticker_icons/<T>.png`, eager load + onerror hide),
  today's move chip, Outcome selector (Next Day / Next Week 5d / Next Month 20d),
  Range selector (5y/10y/20y/Max), tolerance stepper (Exact/±1/±2).
  (Observed-period multi-day patterns = v2; show selector stub disabled with "soon".)
- Left rail "Market Context": grouped conditions (Core: Price Move %, Move Intensity ATR ·
  Market: VIX Level, VIX Move, Market Trend, Macro Quad, Month · Asset: RSI Zone, RSI Slope,
  Rel Volume, Trend Structure, Streak, Volume Streak, Overnight Gap, 52w Distance). Each row:
  name + today's observed value ("VIX 17.5 · 15–20") + toggle. Active count chip. Live
  match-count feedback as toggles flip.
- Verdict hero: big win% + "closed higher/lower", median & mean, sample n, Wilson CI chip,
  edge-vs-base chip ("+4.2pts vs unconditional"), plain-English EN/zh sentence
  ("On Fri Jul 10, SPY rose 0.43% with a minimal 0.5-ATR move, VIX 15–20, market Full Bull.
  Across 168 similar days in 10y, next day closed higher 53.6% (median +0.06%)."),
  open-to-close footnote + not-investment-advice line.
- Tabs: **Matching Days** (mm_charts price line with matched-day dots colored by outcome +
  sortable table: date, key active buckets, fwd return; CSV export), **Price Path** (median
  cumulative path + p25–75 band over 20 forward days, from matched instances), **Returns**
  (histogram of horizon returns + one-tick-per-instance strip).
- **Factor Match tab**: template picker (the precomputed combos) + universe table: symbol
  (logo), sector, today-condition summary sentence, per-horizon n/win%/median, sortable
  columns, min-n filter, sector filter. Row click → loads that ticker in the Analyzer.
- Empty/degraded states: missing matrix → quiet "no data for <T>"; stale asof (>3 trading
  days) → amber "data as of" banner. Degrade, never raise.

### House rules (hard requirements)
- Additive leaves; degrade-never-raise everywhere (engine step must never fail the build).
- **Display-only**: no engine-contract changes, nothing feeds sizing/decisions.
- Bilingual EN/中文 on every user-facing string.
- Weights/params in config.yml under an `odds:` block (universe list, ranges, templates,
  min_n, bucket params) — no magic numbers in code.
- R2 wiring for the new heavy dir `site/oddsmatrix/` — deliberately **NOT** via the
  data_base.js shim regex (odds.js prefixes fetches with `window.DATA_BASE||''` itself, so
  no global fetch-shim change and local preview is controllable). Wire these 4 spots:
  (1) publish_r2 DEFAULT_DIRS (site list) + `_DATA_DIRS` entry for `data/odds_ohlcv`,
  (2) daily.yml publish lane `--dirs` (line ~1732 pattern, non-fatal `|| echo ::warning`),
  (3) daily.yml (+weekly if it has one) Pages-strip `rm -rf` step (line ~1749),
  (4) .gitignore: `site/oddsmatrix/`, `data/odds_ohlcv/*.parquet` (negate manifests if any).
- Page render goes through `lib/pages.write_page` (injects the data_base shim) like
  build_congress.py lines 631–644; register in daily.yml engine job as a
  `run_py "odds desk (build_odds)" scripts.build_odds` line; builder returns 0 on error.
- Template extends `report_base.html.j2` (shared `_site_nav.html.j2` comes free) and uses
  the `t('EN','中文')` macro pattern (see congress_trades.html.j2:3-5).
- Venv for all python: `"/Users/chriswong/Documents/Cluade/Macro Dashboard/.venv/bin/python"`
  (pandas 3.0.3, pyarrow 24 — mind pandas-3 API: no DataFrame.append, strict copy-on-write).
- Commit source only (templates/, engine/, scripts/, config.yml, workflows, site/odds.js|css);
  CI rebuilds site html. NEVER commit site/oddsmatrix/, data/odds_ohlcv/, or rebuilt pages.

### Tests (pytest, in-repo conventions)
1. Bucket boundary unit tests per factor (exact edges: VIX 11.99/12.00/15.00/34.99/35.00 …).
2. Forward-return alignment on a synthetic 30-bar frame with known opens/closes (assert
   fwd1/fwd5 exact values, nulls at tail, holiday-gap indifference via positional logic).
3. No-look-ahead: ATR/rel_vol denominators use only ≤t−1 data (construct a frame where
   including t changes the answer; assert it doesn't).
4. Matcher cross-check: Python reimplementation of the client match on a real built SPY
   matrix — default conditions, 10y, 1d — assert n>0 and stats equal an independent pandas
   computation to 1e-9; same for one factor-match template row.
5. Matrix JSON round-trip: schema keys, equal array lengths, dates ascending, ints only.

### Universe v1 (config.yml `odds:` block)
Index/style ETFs: SPY QQQ IWM DIA RSP; sector SPDRs XLK XLF XLE XLV XLI XLY XLP XLU XLB
XLRE XLC; industry/asset ETFs SMH KRE XBI GLD SLV TLT HYG; ~110 liquid megacaps (the
tradeodds popular list captured in recon: NVDA TSLA MU MSFT AMZN PLTR AMD AAPL COIN AVGO
META NFLX MSTR INTC GOOG HOOD CRWD COHR APP ORCL JPM WDC XOM NOW GLW SPOT CVX CRM CAT LLY
UNH INTU GEV LRCX AMAT STX BAC V ROST TMUS GS BKNG WMT COST SHOP SOFI KO PANW UBER BA FCX
DELL TGT MA MRNA APH C WBD AXP VRT AA ADBE SMCI ABBV MELI UPS CSCO BSX MDB WFC GE QCOM JNJ
CIEN VZ RTX IBM F OXY LMT TER MRVL PG COP BX NRG T + LITE ASTS IREN BE RKLB NBIS AAOI CRDO
ONDS if yfinance has them). Universe = config list ∩ successfully-fetched; degrade quietly.

### Verification (before PR)
- Run `scripts/build_odds.py` in the worktree (real backfill + build). Inspect
  catalog/factor_match sanity (SPY defaults n in a plausible range; spot-check a few
  matched dates against raw data).
- Local preview: serve site/ via http.server; site/data_base.js ships with the live R2
  DATA_BASE which would 404 for oddsmatrix pre-upload → for verification ONLY, temporarily
  set DATA_BASE='' in the local site/data_base.js copy (or override before load), verify,
  then `git checkout -- site/data_base.js`. Do not commit that edit.
- Headless-Chrome screenshots: both tabs + zh toggle + a second ticker (NVDA) + a low-n
  edge case — verify hero numbers equal the pytest cross-check values.
- py_compile + Jinja `Environment().parse()` + full new-test suite green + existing fast
  tests still green (`tests/test_check_nav_gap.py` as canary).

### v1 non-goals (documented in page footer roadmap)
Earnings proximity/performance + analyst-trend conditions (no PIT history in repo yet),
crypto symbols, multi-day observed patterns, NL "Ask Stanley" chat, arbitrary-combo
universe scans (needs a server or wasm+parquet shipping — candidates for v2).

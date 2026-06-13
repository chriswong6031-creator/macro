# Engineering decisions log

Newest first. Each entry: what was decided, why, and what would change it.

## 2026-06-14 (2nd pass) — immediate value, visual momentum, theme

**D49. Front-page Action Board.** New "⚡ What to act on now" panel at the top
of the dashboard buckets every sector's cycle signal into BUY ZONE (confirmed) /
SETTING UP (~N days) / TAKE PROFITS / HOLD-AVOID, plus standout individual
stocks from the analyzed top-10s. Answers "what do I look at" on entry. Carries
the same honesty caveat (cycle states don't beat buy-and-hold on average; value
is structure + risk placement).

**D50. entry_timing() — a ranged days-to-entry estimate.** From cycle band
position + MACD bars-to-cross: BUY NOW / BUY SOON (~lo–hi d) / WATCH / WAIT /
HOLD / TAKE PROFITS / SELL / AVOID. Phase-aware: a BOTTOM WATCH that's only
early/mid-cycle says "mid-cycle dip, real low ~N+ days out" (WAIT), not a false
"low imminent" — found an inconsistency in testing (XLE day-10 "nearing a low"
contradicting a 26-day estimate) and fixed it.

**D51. Visual MTF cards (templates/mtf.js, one renderer for sector + stock).**
Per-timeframe RSI/StochRSI zoned gauges with a sparkline of the recent path, and
a MACD histogram sparkline with the cross ETA. Replaced the dense text rows and
the per-holding TradingView mini-chart dropdown (which showed little). Engine now
emits compact recent series (spark_rsi/stoch/hist) in each tf state. SVG, theme-
aware via CSS vars.

**D52. Plain cycle language + bullets + expandable detail.** cycle_plain()
labels DAILY vs WEEKLY(investor) cycle explicitly with phase words ("overdue —
a low could form any day"), resolving "is cycle day 27 daily or weekly?".
Translation explained in plain terms. Long why/next prose collapsed to bullet
points with a "full reasoning" expander. The unreadable holdings score-bar was
removed in favor of the urgency pill + explicit "daily cycle day N".

**D53. Dark/light theme (templates/theme.css + theme.js).** Centralized all CSS
color variables into one stylesheet (dark default, html[data-theme=light]
override) linked by every page; inline no-flash init in <head>; toggle persisted
in localStorage; TradingView + MTF widgets recolor on flip. Replaced each page's
inline :root.

## 2026-06-14 — UX clarity + pre-emptive entry layer

**D46. Ladder states got plain, direction-explicit display names** (internal
keys unchanged so the calibration JSON still matches). DECLINE→"DOWNTREND·AVOID",
BOTTOM WATCH→"NEARING A LOW·GET READY", TURN SIGNALED→"BOTTOMING·BUY SETUP",
FRESH BUY→"BUY ZONE·BUY", RALLY ON→"UPTREND·HOLD", TOP WATCH→"NEARING A
HIGH·TAKE PROFITS", ROLLING OVER→"TOPPING·SELL SETUP". A user couldn't tell
direction from "turn signaled"; the bottom/top turns are now named as explicit
mirror images (BOTTOMING=buy setup ↔ TOPPING=sell setup). `STATE_DISPLAY` in
engine/cycles.py is the single source; flows to heat board, sector pages, stock
search via the ladder dict + a JS copy.

**D47. Pre-emptive entry detection added per research (Aspray histogram trough,
RSI divergence with oversold-leg + magnitude + spacing filters, StochRSI pop
out of oversold), exposed as an explicit ANTICIPATED/HEADS-UP tier — never a
new calibrated buy state.** Gated by cycle context (bull signals only when a
low is plausibly near; bear only when extended) so it can't scream buy in
free-fall. CRITICAL honesty result: calibration (BOTTOM WATCH +early-bull vs
no-early, 40 instruments, fwd 21d) showed the early signals did NOT beat
waiting — 57.8%/+1.16% vs 58.8%/+1.58%. Consistent with the heat board (D31)
and playbook (D23): anticipating doesn't raise average return, it trades a
higher false-alarm rate for catching the occasional sharp V. Shipped with that
measured comparison printed on the page; the early note frames it as "know when
to watch, then still require confirmation". What would change it: a different
horizon or a divergence-only (anticipated-tier-only) calibration might separate;
left as future work.

**D48. Tooltips flip horizontally near the right/left viewport edge** (JS adds
edge-right/edge-left anchoring), mirroring the existing top-edge flip — the
rightmost "cycle timing" tooltip was overflowing. Desktop gets centered side
padding (max-width container) above 1100px.

## 2026-06-13 — Bitcoin Vector Phase 2 (signal engine + calibration)

**D42. Signals are vote-ensembles + saturating composites, matching the
mechanics visible in Swissblock's own panels.** Momentum & structure = mean of
−1/0/+1 votes (reproduces their pinning at ±1); Risk Index = weighted stress
composite with a deadband (reproduces their pinning at 0 in healthy uptrends) +
a Risk Oscillator parked at 0.5; BFI = mean of Network-Growth & Liquidity
percentile oscillators with 40/60 bands. All tunables in config `vector:`.

**D43. The Risk Index is judged on forward DRAWDOWN, not forward return.**
Calibration found forward *return* by risk band is U-shaped (low-risk AND
extreme-risk both show high 90d returns) — the documented contrarian-at-extremes
behavior, NOT a defect, and the same shape that burned the macro heat board
(D31). Judged correctly (forward 7d drawdown) it is monotone in all three
sample halves: a working near-term risk gauge. The dashboard will frame it as
risk/drawdown + contrarian-at-extremes, never as a return-timing signal.

**D44. Hysteresis bands (enter ±0.5 / exit ±0.25; risk 25/15) cut whipsaw from
31% to ~20%** without the lag a longer confirm window adds. Daily crypto is
noisier than the macro series, so ~20% (vs the 15% macro target) is accepted and
stated. Allocation backtest is the practical proof: every variant beats HODL
Sharpe and roughly halves max drawdown.

**D45. Swissblock agreement is measured by digitizing their two-toned panel
lines (color = state), not exact values.** Result: Risk regime 65–69%, Momentum
sign 48–56%. The momentum gap is structural (their selling-pressure momentum vs
our trend-vote) and will NOT be overfit away against 13 months of one chart —
the digitized series is a sanity anchor, not a training target. Closing it needs
their real series (the user-offered Hawkeye/Vector subscription). The upside-vol
false-positive this surfaced WAS fixed (risk vol → downside semi-deviation).

## 2026-06-13 — Bitcoin Vector Phase 1 (crypto collectors)

**D39. bgeo (bitcoin-data.com) runs under an explicit request budget** (12 of
15/day, priority-ordered in config) with live X-RateLimit header tracking; the
adapter stops cleanly at quota and returns partials — partial success IS
success, skipped metrics self-heal next run because every call covers the gap
since the last stored date. Archive-forever: the free tier serves a rolling 4y
window, our parquet never forgets (FRED-OAS pattern). What would change it: a
free API key that pins quota to the key instead of IP (untested), or repeated
CI quota collisions → reshuffle metrics to CM/DefiLlama/checkonchain.

**D40. Hourly candles are first-class storage.** store.upsert() gained
normalize_index=False (adapter attr) so Coinbase hourly keeps intraday
timestamps — required for flash-crash calibration and the intraday-vs-interday
volatility split (Swissblock's "Key Risk Elements"). 91.5k rows, 2016→.

**D41. Derived metrics are computed in the engine, never collected:** realized
cap = mcap/MVRV, NUPL = 1 − 1/MVRV (exact identities on CoinMetrics community
series), SSR = btc_mcap / DefiLlama stablecoin mcap. Rationale: fewer quota
slots, one source of truth, derivations visible in code.

## 2026-06-13 — holdings drill-down + cycle engine

**D34. Cycle methodology implemented from graddhy.com / thefinancialtap.com**
(user-directed sources): equity daily cycles 36–42 trading days trough-to-
trough, investor cycle 16–26 weeks; swing low + close above the 10-day MA +
MA turning up as DCL confirmation; right/left translation from crest position;
failed cycle = break of the cycle's birth low. Timing bands catch only ~70% of
lows per the sources — that miss rate is stated on every drill-down page.
Trough detection = confirmed ±10-day local minima merged within 18 days; the
hunt for the NEXT low uses a separate candidate trough (the cycle-start swing
low goes stale, found in testing).

**D35. The signal ladder is calibrated like everything else.** Seven states
(DECLINE → BOTTOM WATCH → TURN SIGNALED → FRESH BUY → RALLY ON → TOP WATCH →
ROLLING OVER) from cycle position × multi-timeframe MACD/RSI/StochRSI, with
weekly gating daily. Walk-forward calibration (2000→, weekly steps, trailing
600-day window) measures forward 21-day stats per state; the table ships on
every sector page. Recalibrated weekly (scripts/recalibrate.py — ~10 min).

**D36. "Approaching cross" proximity** = MACD histogram still on the wrong
side of zero but moving monotonically toward it for 3 bars; bars-to-cross
estimated from current slope. This is the "we're getting close to a buy"
precision the user asked for — an early warning, explicitly not a signal.

**D37. TradingView embeds are official free widgets** (advanced chart for the
ETF, lazy-loaded mini-charts per holding — created only when a card opens, so
pages don't load 10 iframes upfront). TradingView's indicator DATA has no
public API; all signal math is computed locally from stored prices, which also
keeps signals reproducible.

**D38. Top-10 holdings tables bypass the time-series upsert** (10 rows share
one date; the dedup-by-date guarantee would collapse them — found in testing).
They merge-by-snapshot-date directly, like the ARK holdings files.

## 2026-06-12 (3rd pass) — technicals, seasonality, heat board

**D31. The confluence ("heat") score is calibrated, and the calibration is
INVERTED — so the UI sells it as a confirmation gauge, not a buy signal.**
Scoring regime fit + rotation stage + technicals − crowding across 2007-2026
(weekly-sampled, fwd 63d excess vs SPY): band 70+ hit 46.7% (avg −0.57%),
band 0-39 hit 50.0% (avg +0.19%); monotonic worse at 126d (70+: 41%, −1.22%).
"Everything confirmed" = late. The heat tooltip shows each band's measured
record; OVERHEATED explicitly reads "hold/trim, don't initiate". This is the
generalized form of the don't-chase finding (D23) and the answer to "how much
trust": the trust level is printed, and for chasing it's negative.

**D32. Technicals (RSI/MACD/MAs/52w) and monthly seasonality are computed from
stored closes for sectors + gold/oil/copper/dollar.** Seasonality is displayed
as context but EXCLUDED from the calibrated score (scoring history with
full-sample monthly stats would peek at the future). Trigger-distance metrics
(how much more outperformance until the 200d RS cross, and % progress from the
recent low) quantify "how close is this watchlist name to confirming".

**D33. ~~No LLM in the scoring path.~~ RESCINDED by user 2026-06-13.** LLM use
is permitted anywhere it helps (commentary, scenario prose, analysis). Two
engineering facts survive the rescission as facts, not policy: (a) LLM calls
inside CI need an API key secret + per-run cost; (b) historical backtests can
only run against mechanically-computed signals, so anything we want a measured
track record for keeps a mechanical core — an LLM layer on top is fine.

## 2026-06-12 (later) — now-focused front page

**D28. Q-codes removed from all user-facing surfaces.** A user read "Q1
Goldilocks" as calendar-quarter Q1 (it was June). Regime names (Goldilocks /
Reflation / Stagflation / Growth scare) are now the only user-visible labels;
Q1–Q4 remain internal identifiers. The quad-badge tooltip says explicitly
"NOT a calendar quarter".

**D29. Front page restructured around NOW; history moved to history.html.**
Order: where-we-are-in-this-regime (lifespan bar: age vs the distribution of
all same-regime stints since 2007, survival %, median remaining, phase note) →
what's-likely-next (transition base-rate bars + accumulation watchlist +
announce-signals) → how-to-trade-it (dial + leaders + don'ts) → supporting
evidence. The 2y/3y charts and lifespan base-rate table live on history.html.

**D30. Monthly econ series fill bug fixed.** PAYEMS/INDPRO are stamped on the
1st of the reference month; when that's a weekend the business-day reindex
dropped the print entirely, silencing the econ confirmations for stretches
(found because payrolls voted NaN on a day it shouldn't have). Fill now happens
on the union index before reindexing, and the monthly ffill window is 60
bdays to cover INDPRO's ~6-week publication lag. Whipsaw after fix: 9.5%
(still PASS); signal agreement rose 51%→56% with payrolls voting again.

## 2026-06-12 — UX overhaul + playbook (conclusions layer)

**D23. The playbook only claims what the data supports.** Before building the
recommendations layer, every candidate entry rule was backtested
(`scripts/research_playbook.py`, 2000→2026, weekly-sampled, split-half).
Findings that drove the design: (a) sector picks vs the index have NO stable
monthly-horizon edge — per-quad sector results flip sign between sample halves;
(b) chasing extended leaders lost (44.7% hit, −0.6%/3m); (c) buying
below-trend bounces lost in every variant (−0.2..−1.2%/3m); (d) top-3 12-month
relative momentum held 3–6m is the only mild persistent tilt (+0.27%, 51%);
(e) index-level conditions ARE robust in both halves: liquidity-expanding
(~+1.3–2.0%/21d, 72–74% positive), Q3 weakest quad, risk-off quads ~30% deeper
3-month drawdowns, warning-state separation pre-2017. The playbook therefore
leads with an exposure dial (robust), frames sector calls as confirmed
leadership + evidence-backed don'ts, and prints its own caveat. Sector-bucket
stats are constants in `engine/playbook.py` (re-run the research script after
engine changes); index-level stats recompute live from the classifier's history.

**D24. Rotation stages use the standard RRG quadrant logic** (RS vs its 200d
trend × 20d RS momentum → improving/leading/weakening/lagging). 'Improving' is
surfaced as a WATCH/too-early state, never a buy — that's what the evidence
says (see D23c).

**D25. Tooltips are CSS-only** (no JS) and every metric on the dashboard
carries one. Quad bands got a labeled legend. All panel titles renamed to plain
English with the technical term in the tooltip.

**D26. AAII reports status 'blocked', not 'failed'** (`expected_failure` on the
adapter) — a permanent, documented limitation shouldn't look like a breakage.

**D27. pages.yml deploys site/ on push** so locally-rebuilt dashboards go live
immediately instead of waiting for the next scheduled run.

## 2026-06-11 — Phase 3 (outputs & alerts)

**D17. Alerts compare states, not levels.** Every rule is a day-over-day (or
window) *change* test against stored history, logged to
`data/alerts/alerts_log.parquet` keyed by (date, rule, message) — re-running a
day is idempotent and cannot double-send. Severity (act/warn/info) only orders
the message. Rules covered: transition state change, axis confidence crossing
below floor, sector RS 90d-percentile crossings, holdings active change,
net-liquidity RoC sign flip, HY OAS 1d widening z, GEX flip-cross.

**D18. Notify reads, never computes.** `scripts/notify.py` consumes
latest.json + run_status.json only; a notify crash cannot affect data, and
missing secrets skip the channel with exit 0 (the dashboard is the fallback
surface). Telegram uses HTML parse mode (MarkdownV2 escaping is a bug farm).

**D19. Dashboard is a single static page** (jinja2 + plotly-CDN, dark theme),
built from stored outputs only — it renders even when every scraper is down.
Charts capped at 2y windows to keep the page <250KB; the full 2007→ timeline
stays on its own validation page.

**D20. GitHub Pages via Actions artifact.** Pages-from-branch can only serve
root or /docs; the spec's /site layout is kept by deploying with
actions/upload-pages-artifact + deploy-pages. One-time repo setting required:
Settings → Pages → Source = "GitHub Actions".

**D21. FRED fail-fast.** Three consecutive series failures with zero successes
aborts the remaining series (observed: the keyless endpoint can be down for
hours; without this a daily run burns 45+ min of Actions minutes in retries).

**D22. Weekly rotation-type test.** "Which rotation is underway" = highest
average 20d RS momentum among the four quad preference baskets; disagreement
with the classifier quad is explicitly surfaced as a transition signal
(it fired on build day: Q1 regime, Q4-consistent leadership).

## 2026-06-10 — Phase 2e tuning

**D15. Hysteresis/threshold tuning via grid sweep** (`scripts/tune.py`, 36
combos, criteria: whipsaw <15%, episode fidelity 2008/2020/2021/2022, covid
flip speed). Winner applied to config: z_threshold 0.25→0.45, hysteresis_days
5→7, shock_override_z 0.7→0.85, us2y growth weight 1.0→0.5. Whipsaw fell
20.4%→9.3% with 2008 Q4 share *improving* (55%→72%) and the covid shock
override still flipping day-0. The 2Y-direction de-weight is principled, not
just fitted: rising short rates signal growth when inflation is anchored but
signal policy-chasing-inflation in supply shocks (2022), so it gets
confirmation weight (0.5) like the econ series. Re-run the sweep after any
component change.

**D16. NY Fed / Board sources added for liquidity** (`collectors/nyfed.py`):
ON RRP from the NY Fed Markets API (official source FRED derives from),
EFFR likewise, and H4.1 total assets (`RESPPA_N.WW`, verified == WALCL) from
the Board's Data Download Program zip. These are *primary* for RRP/EFFR going
forward; FRED series remain merged-in when available.

## 2026-06-10 — initial build

**D1. Dedicated git repo inside the project folder.** The parent home directory
contained a stray commit-less git repo at `~`. Committing data there would be
wrong; `git init` was run in the project folder itself. When publishing,
`git remote add origin <github-url> && git push -u origin main`.

**D2. FRED access: official API when `FRED_API_KEY` is set, keyless
`fredgraph.csv` otherwise.** The keyless endpoint serves identical data but
intermittently 504s (observed during build), hence 4 retries with exponential
backoff. CI should set the key (free at fred.stlouisfed.org/docs/api/api_key.html).

**D3. OAS rolling-window mitigation (confirmed live).** As of build day FRED
returns only ~3 years for `BAMLH0A0HYM2`/`BAMLC0A0CM` (first obs 2023-06-12).
Mitigations: (a) `lib/store.upsert` is append-only — rows existing only on disk
are never dropped, so every live observation is cached permanently from day one;
(b) full 1996→2025 history restored from Wayback Machine captures of FRED's own
endpoints, stored in `data/archive/` with spot-check verification
(see `data/archive/PROVENANCE.md`). IG archive ends 2024-10-24; live FRED window
(2023-06→present) overlaps it, so the merged series has no gap.

**D4. One vectorized engine code path.** The engine recomputes the full daily
history every run (seconds of compute); the live signal is the last row. The
Phase-2e backtest therefore exercises *exactly* the production classifier — no
separate backtest implementation that could drift.

**D5. Slope z-scoring = drift t-stat.** "Direction of change" = mean daily
change of log level (plain level for series already in %) over 20d, divided by
(60d daily-change volatility / √20) — a t-statistic of recent drift. Scored ±1
beyond |z| ≥ 0.25. Chosen over z-scoring the slope against its own trailing
mean because that variant decays to zero during steady trends — a two-year
expansion must keep reading as growth-up. Windows/threshold in `config.yml`.

**D6. ISM is not on FRED anymore (`NAPM` discontinued 2016).** Econ confirmation
uses payrolls 3-month change sign and INDPRO yoy sign at half weight instead.
Monthly series are step-filled forward (~40 trading days max) — honest
representation of "last known print", and only direction is consumed.

**D7. Monthly econ scored by sign, not slope-z.** A 20d slope on a step-filled
monthly series is zero most days and spikes on release days; sign of the 3m/12m
change is the debuggable equivalent. Lower weight (0.5) per spec.

**D8. Breadth constituent close matrix is a local cache, not repo data.**
Committing ~500 price series daily would bloat the repo (parquet doesn't
delta-compress in git). Only the small computed aggregates
(`data/breadth/breadth.parquet`) are committed; the raw close matrix lives in a
gitignored cache restored via `actions/cache` in CI (on miss: ~2 min re-download).
Backtest aggregates computed once from full constituent history (survivorship
bias documented in LIMITATIONS.md).

**D9. Treasury DTS schema change handled explicitly.** TGA value lives in
`close_today_bal` under account type `Federal Reserve Account` before Oct-2021
and in `open_today_bal` under `Treasury General Account (TGA) Closing Balance`
after (verified against the live API at 2007/2015/2021/2026 dates). Net
issuance = Table IIIA Marketable Issues − Redemptions.

**D10. Net liquidity units.** Normalized to $bn: WALCL(mn)/1000 − RRP(bn) −
TGA(mn)/1000. WALCL is weekly (Wed) and forward-filled ≤7 days; the dashboard
flags the staleness rather than hiding it.

**D11. Holdings active-decision SO normalization.** Fund shares outstanding for
the expected-shares formula is proxied by the total share growth of positions
common to both snapshots when the sponsor doesn't publish SO in the same file.
Exact SO is used where available (iShares embeds it; SSGA fund API).

**D12. Hysteresis interpretation.** "Single-day axis score beyond ±0.7" flips
immediately only when that axis *disagrees with the incumbent quad's sign* —
an extreme reading that agrees with the incumbent regime is confirmation, not
a shock.

**D13. Recession/inflation-shock are refinements (labels), not extra states** —
exactly as specced; hysteresis operates on the 4 quads only.

**D14. GEX flag is live-only.** No free historical dealer-gamma series exists;
in the backtest the GEX transition flag is simply False (NaN-safe). Validation
whipsaw/accuracy stats therefore use 5 of the 6 flags historically.

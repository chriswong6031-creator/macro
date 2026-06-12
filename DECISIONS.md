# Engineering decisions log

Newest first. Each entry: what was decided, why, and what would change it.

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

# Engineering decisions log

Newest first. Each entry: what was decided, why, and what would change it.

## 2026-06-13 — Vector deferred-factor batch 2: global M2 + Deribit basis/skew-term

**D-vec-FACT2. Picked up the three deferred factors; 2 of 3 shipped, 1 blocked.**
(1) **Global (US+China) M2 growth** (`global_liquidity()`) — the broad-money tide
our Fed-balance-sheet net-liquidity lacked. KEY FINDING: the synthesis's FRED
foreign-M2 series are DISCONTINUED (JP ends 2017, CN 2019, EZ/UK 2023), so "global
M2" isn't free as specced — pivoted to US M2 (FRED M2SL, seeded) + China M2-YoY
(Eastmoney `china_macro/money_supply`, already on disk), combined as a weighted
average of YoY GROWTH rates (unit-free, no FX). CALIBRATION: DIRECTIONAL (full+pre
+1, post −1 weak — the 2022 QT decoupling, honest): >11% YoY → +58%/90d @81% hit
(liquidity flood). config `vector.global_liquidity` (us_weight 0.4); surfaced in
the macro panel. _Now 7.0% expanding = mild tailwind._ (2) **Deribit futures BASIS
term structure + options SKEW term structure** (`compute_basis()` + `_skew_at_tenor()`
at 7/30/90d in deribit.py): the leverage-demand curve + near-vs-structural fear our
perp-funding/point-skew were blind to. Snapshot/context (no free history →
accumulates forward, can't calibrate yet). _Now: basis +3.4% ann (mild contango,
not froth), skew_term −0.02 (no acute fear)._ wired into engine options() +
surfaced. (3) **bgeo CDD/Dormancy (bottoms-side behaviour)** — STILL BLOCKED (bgeo
429 rate-limited all session); added `cdd` to the bgeo collector (budget 13→14, the
lowest-priority slot) so it self-heals on the next run, deferred the engine signal
until data exists (VDD from checkonchain already covers the tops/activity side).
What would change it: a live free global-M2 feed (EZ/JP/UK), and the bgeo budget
resetting to seed CDD.

## 2026-06-13 — Vector new-factor hunt: 4 orthogonal axes added (research/VECTOR_NEW_FACTORS.md)

**D-vec-FACT. A 6-agent hunt found the model saturated in valuation/trend but
blind to four orthogonal axes — all now added + calibrated.** (1) **Halving
Cycle Clock** (`cycle_clock()`, deterministic, the time axis we wholly lacked):
accumulation phase +47.9%/90d @81% vs markdown +5.1%/90d @43% (n=3 = soft PRIOR)
→ wired as a ±5pp tilt on scenario probabilities, not a trigger. (2) **CME COT
positioning** (`positioning()` — `cot_bitcoin` was collected but idle): crowded
spec long (z>1.5) → −5.8%/90d @35% = contrarian TOP → wired into composite_state
DISTRIBUTE. (3) **Cross-asset correlation regime** (`cross_asset_corr()`, zero new
data — Yahoo SPX/gold/DXY): coupled-to-equities (corr>0.4) +13%/90d vs decoupled
+33% → context. (4) **VDD Multiple** (`behaviour()`, checkonchain 2011-> deep, the
spending-behaviour/coin-age axis): calibration HONEST — coincident with bull
phases, NOT a clean top signal → DEMOTED to context gauge (measure, don't
overclaim). config `vector.{cycle_clock,positioning,cross_asset}`; btc_inputs adds
cot_net_pct/spx/gold + checkonchain vdd_multiple. LIVE READ: cycle=markdown (weak
phase), COT z=+3.0 (crowded long → headline now DISTRIBUTE), corr 0.44 mixed, VDD
0.36 dormant — a coherent late/distribution picture. What would change it: more
cycles to de-soften the halving prior. DEFERRED (bgeo 429 rate-limited this
session): CDD/Liveliness/Dormancy-Flow (bottoms side), Deribit futures basis +
skew term structure, global-M2 lead.

## 2026-06-13 — Alert quality gates + calibration-graded conviction

**D-alert-Q1. Deadband + N-day confirmation on the noisy macro flip alerts.**
`net_liquidity_roc_flip` now fires only when the 4-week RoC clears a ±25 bn
deadband AND the new sign has held `confirm_days` (default 2) — killing the
"+7bn → -0bn" non-event (a sign flip sitting on zero) the original alert
surfaced, plus one-day whipsaws across zero. `gex_flip_cross` gets analogous
deadbands (gex_net_deadband_bn=1.0, gex_flip_pct_deadband=0.25) and a NaN-safe
message. Tradeoff: a deliberate ~1-day delay before a fresh flip fires, and a
genuine flip whose magnitude stays inside the deadband won't fire. All four
thresholds are config keys under `alerts:` with in-code defaults (behaviour
unchanged if absent). What would change it: tune deadbands once we see the real
firing cadence.

**D-alert-Q2. Conviction layer — every alert carries a tier + grounded edge
note, decoupled from per-fire severity.** Goal: rank by MEASURED edge, not
loudness. Vector (engine/btc_alerts.py CONVICTION + _conviction) derives edge
from data/vector/calibration.json: CONFIRMED signals (risk_index→risk_regime,
bfi→fundamentals) read "proven edge"; DIRECTIONAL-degraded ones
(momentum/structure) read "edge weakened post-2021 (ETF era)"; allocation shows
its real backtest (66% vs 59% CAGR, −42% vs −84% drawdown); state alerts carry
their historical whipsaw rate. risk_extreme is deliberately decoupled from
risk_index's directional verdict (its contrarian-at-extremes thesis is the
OPPOSITE of what that verdict measured) and gets an honest "suggestive, not
proven" note. Macro (engine/alerts.py ALERT_CONVICTION) has no per-rule
backtest, so tiers are documented-reasoning calls (HY OAS=act/high; net
liquidity=watch/medium with the post-2021 caveat; confidence/RS/holdings=
context). `tier`=actionability/horizon, `edge`=trust. What would change it:
re-running the vector calibration (verdicts feed the labels directly).

**D-alert-Q3. Surfacing.** Conviction renders in the Bitcoin Vector timeline
(templates/vector.html.j2 tl-edge/tl-fwd), the macro dashboard alert card
(templates/dashboard.html.j2 .alert-edge), the combined home-hub feed
(scripts/build_vector.py home_alert_feed + _hub_alert_rows .ha-edge, all three
sources), the daily brief (scripts/daily_brief.py), and the Telegram/Discord
ping (scripts/notify.py). Engine logic landed in commit a4f8d20; render +
config-doc + this entry followed.

## 2026-06-13 — Vector IMPULSE + full-signal integration (research/VECTOR_IMPULSE_AND_INTEGRATION.md)

**D-vec-IMP. Added an IMPULSE signal (the Glassnode/Swissblock capability we
lacked) — CONFIRMED both halves.** A 5-agent research+audit workflow established
their Impulse = the "exponential price structure" (rate-of-trend / ACCELERATION),
spotting the START/EXHAUSTION of a move, not the level. engine `impulse()`:
`efficiency_ratio × weighted_mean(zscore(MACD-hist,90d), zscore(Δfunding)+
zscore(ΔOI))`, winsorized ±3. MACD-histogram = denoised 2nd derivative (inflection
core); Kaufman ER is a MULTIPLIER not a vote (collapses to ~0 in chop, the
dominant false-positive mode); funding+OI add an orthogonal positioning impulse
(NaN-skipping mean so the deep 2014→ core isn't poisoned by 2023→ funding).
CALIBRATION: CONFIRMED both halves — >0.5 → +3.7%/7d, +32.6%/90d @66%; <−0.5
exhaustion bounces +1.5%/7d. 4th both-halves signal (w/ Risk Index, BFI, macro).
config `vector.impulse`; own panel (state + breadth bar + ER chop gate).

**D-vec-INT. The confirmed signals are now WIRED INTO the final outputs (audit
found them display-only).** (1) `composite_state` headline now fuses macro_regime
+ BFI>60 + reserve_risk TOP (config `vector.composite`). (2) SCENARIO PROBABILITIES
rebuilt: `_cond_up_prob` conditions P(up) on momentum_state × risk_regime (both
CONFIRMED), empirical-Bayes shrunk toward the momentum marginal (α=10), macro
tailwind/headwind tilt (±5pp), CAPPED [30,70] (anti-overfit for ~3 cycles); honest
n+cell shown. env_probabilities (7d) + scenarios_3d (3d) both use it — replacing
the momentum-only 60/40/25; a bear/high-risk tape now reads ~52% (contrarian
U-shape), not 25%. scenarios_3d ATR bands scaled by DVOL. config `vector.scenarios`.
(3) allocation: reserve_risk>0.02 added as a calibrated TOP safety cap (A/B:
NEUTRAL in-sample = no regression; the macro gate was A/B-REJECTED again, CAGR
51→41 — macro is strategic not tactical). What would change it: more cycles to
de-shrink the probabilities; a working top-350 breadth feed for a true aggregate
Impulse. Caveat held: no double-counting (impulse correlates w/ momentum → NOT a
prob tilt; only orthogonal macro tilts), prior-dominated at ~3 cycles.

## 2026-06-13 — Signal AGE + strength on every ladder state (macro)

**D75 (macro). Every ladder signal now reports HOW MANY TRADING DAYS AGO it
crossed into its current state, plus a plain-language strength read.** The UI
previously showed only the live state ("BUY ZONE", "TOPPING", …) with no sense
of whether it flipped today or three weeks ago, or how decisive it is. New
`engine.cycles.signal_age()` re-runs the ladder BACKWARD over the same trailing
600-day window `calibrate_ladder` uses, comparing each earlier day's state to
today's headline state and stopping at the first day that differs — so a freshly
flipped signal costs ~1–2 evals and only a long-stable trend pays the full 45-day
lookback (≥45 → reported as "established trend, not a fresh signal"). The current
state is passed IN (the live, full-history one shown in the UI) so the answer can
never contradict the displayed label; full-vs-window agreement measured at 0/160
on a sample. `signal_age_fields()` builds EN+ZH prose ("BUY ZONE signal triggered
3 trading days ago (~2026-06-09), switching from NEARING A HIGH. Signal strength:
strong (score +70/100).") + a compact `age_short` badge ("3d ago" / "今日" /
"45d+"). Strength is the qualitative band of the EXISTING transparent ladder
score's magnitude (≥70 strong / ≥40 moderate / ≥15 mild / else faint) — no new
number invented. Wired into `analyze()` ONLY (not `ladder_state`), so the
calibration walk-forward is untouched and it's computed exactly once per
instrument. Surfaced on the stock analyzer, sector ETF + each top-10 holding, and
the dashboard action board + standout-stock chips. Cost: ~+10s on the nightly
stock-library build (533 names, early-exit walk). What would change it: if state
churn made the 45-day cap bind often (measured max age 33 on the live universe, so
caps are rare today) we'd raise the lookback or switch to event-anchored dating.

## 2026-06-13 — Vector i18n: bilingual restored as GRACEFUL-OPTIONAL

**D-vec-I18N2. The Vector page is bilingual again, but the i18n dependency is now
OPTIONAL (supersedes the English-only D-vec-I18N).** After the macro session
re-landed the i18n layer (engine/i18n.py committed), the Vector page opts back in
WITHOUT re-coupling: the template `t(en,zh)` macro emits both language spans
(static zh is hardcoded at call sites, needs no engine.i18n) + the data-lang
toggle/CSS/lang-btn/chart_i18n.js are restored; build_vector wires `td`/`tr`
(main) and `T`/`TR` (_hub_html) via `try: from engine import i18n … except:
identity`. So: i18n present → fully bilingual; i18n absent → English-only,
**still builds (ACID-TESTED with engine/i18n.py removed)**. Best of both:
bilingual now, immune to future i18n churn. Browser-verified: 187 l-zh spans,
zh-mode shows 储备风险/宏观背景/链上需求 (all my panels translate), no console
errors. What would change it: nothing — this is the stable end state for the
i18n coupling regardless of what the macro session does with its layer.

## 2026-06-13 — Top-200 ETF universe (Phase 2, follow-on to the D70 macro entry)

**D71. Broad ETF universe uses the SHARE-BASED flow-normalized active-decision —
NOT the price-decompose engine.** Phase-1 (D70 macro entry) decomposed sector-SPDR
weights into price + residual, which needs each holding's price. The top-200 universe
references thousands of names but `data/stocks/` only covers ~110, so price-decompose
can't scale. Instead the new `collectors/etf_holdings.py` writes FULL daily holdings
(incl. Shares Held) per fund to `data/etf_holdings/<TICKER>/<DATE>.parquet`, and the
engine reuses the existing `collectors.holdings.active_changes_dir` (refactored out of
`active_changes` to take a base dir): `expected_shares(t)=shares(t-1)·SO(t)/SO(t-1)`,
`active=shares(t)−expected` — the canonical "what did the fund actually buy/sell",
needing NO per-stock prices. `engine.holdings_signals.etf_signals`/`top_etf_accumulation`
aggregate across the passive `etf_holdings` universe PLUS the active ARK watchlist
(read from `data/holdings/`, so ARKK/ARKW aren't double-collected). HONEST FRAMING
carried to the page: on ACTIVE funds the signal is manager conviction; on PASSIVE
index/sector funds it is index reconstitution / rebalance flow — tagged per row.
Sponsor reliability — settled by a verify-backed recon Workflow (2026-06-13):
VERIFIED + SEEDED — **ssga** (SPDR XLSX, SPY 504 rows live), **ark**, **invesco**
(`dng-api.invesco.com/cache/v1` JSON — use `idType=cusip`; `idType=ticker` 500s for all
but flagship QQQ; QQQ/RSP seeded), **globalx** (`assets.globalxetfs.com` dated
full-holdings CSV, walk back on 404; URA/LIT/COPX seeded). BLOCKED + NOT seeded —
**iShares** (Akamai Bot Manager returns a `text/csv`-headed HTML consent body even with
consent cookies → needs a headless browser; `_fetch_ishares` retained for that path),
**Schwab** (403/JS), **Vanguard** (no free daily feed — month-end/N-PORT only).
**ProShares EVALUATED + DROPPED**: its one consolidated CSV is mostly leveraged
swap/futures funds with no stock-level conviction signal (the agent's "highest ROI" was
on fund-count, not signal-relevance — caught by adversarially inspecting the data).
Coverage ≈30-40% of top-200 AUM but a large share of fund COUNT; the mega-cap walls
(iShares ~30% / Vanguard ~25-29% of AUM) would need a degraded stockanalysis.com scrape
layer (clearly labelled non-official) to cover. Live full-collector run wrote 17 valid
snapshots (12 ssga + 2 invesco + 3 globalx). GOTCHA fixed: untickered foreign holdings
stringify to `<NA>` under the pyarrow string dtype (not `nan`), so `_normalize`'s
junk-ticker filter must include `<na>`. New `etfs.html` page (ETF flow radar) +
macro-nav link + a landing-hub card (`build_vector._hub_html`, gated on the page).
Volume: extended `StockPriceAdapter` to keep a `volume` column + `volume_surge()`
confirmation enhancer (📊 marker) — populates as daily snapshots accrue / on the next
`--full-history` backfill. Config `etf_holdings.universe` (12 SSGA + 2 Invesco + 3
Global X seeded) grows toward 200 by editing config + adding sponsors we can fetch.
THRESHOLDS UNCALIBRATED + needs ≥2 snapshots per fund to show.
WHAT WOULD CHANGE IT: a headless-browser/proxy path for iShares/Schwab, or a
stockanalysis.com degraded layer for the wall-blocked mega-caps (both would expand
coverage); and calibrating active_change_alert_pct once history accrues.

## 2026-06-13 — Vector dashboard DECOUPLED from i18n (now committable)

**D-vec-I18N. The Vector page is made English-only & self-contained so it no
longer depends on the (separately-owned, currently-reverted) i18n layer —
resolving the hold-back in D-vec-GIT.** The page's only hard coupling was
`engine.i18n` (the `td`/`tr` globals in build_vector + `T`/`TR` in `_hub_html`)
plus a `chart_i18n.js` script. Fix: the template's `t(en, zh)` macro keeps its
two-arg signature (so all ~140 call sites are untouched) but now emits only
English; `td`/`tr` become identity globals; `_hub_html` defines local identity
`T`/`TR`; dead bilingual scaffolding (lang toggle, `data-lang` JS, `.l-zh` CSS,
chart_i18n.js) removed. **ACID-TESTED: `build_vector` builds with `engine/i18n.py`
physically removed** — zero i18n dependency. Also surfaced Reserve Risk in the
Valuation panel (TOP flag >0.02). The page renders English-only (verified in
browser: 0 `.l-zh` spans, no visible Chinese, all 12 panels live). build_vector.py
is co-owned (the macro session's hub China/Commodity cards live in `_hub_html`);
those degrade gracefully (`present:False`, try/except, no untracked imports), so
committing the file is CI-safe. What would change it: if the macro session
re-adds a working i18n layer, the Vector page can opt back in (the `t` macro is
the single re-point). STILL: the two agents share one tree on `main` — the
build_vector.py edit race (the file changed mid-build between two runs) means
this should still be serialized.

## 2026-06-13 — China A-share dashboard (Section 3, full US-clone)

**D71. China is a full clone of the macro dashboard on a two-plane free data
stack, NOT a Vector-style allocation tool.** Plane A = yfinance over a `china:`
config block (indices, 16 mainland sector ETFs, FX, 82 curated large-cap
constituents) → group `china`/`china_breadth`. Plane B = Eastmoney datacenter
JSON (PMI/CPI/PPI/M2/IndPro 2006-08→ monthly, SHIBOR, Stock-Connect) → group
`china_macro`, archive-forever (scraper plane, circuit-breaker isolated per
series). All live-verified — research/CHINA_DATA_AUDIT.md. Gotcha fixed:
datacenter rows carry a RangeIndex that aligns to NaN against a DatetimeIndex —
assign `.to_numpy()`. No free Chinese-ETF holdings feed → sector membership is
CURATED in config (doubles as breadth universe + drill-down + search seed).

**D72. The regime engine reuses the macro quad framework with China inputs.**
engine/china_axes + china_regime + china_inputs + china_run mirror axes/regime/
inputs/run; cycles.py + technicals.py reused AS-IS (the enriched bilingual
ladder — entry/points/cycle_plain/why — is all produced inside ladder_state, so
the sector + stock pages need no separate enrichment). Liquidity overlay = M2-YoY
direction (PBoC stance); inflation axis is PPI-led (see D73).

**D73. Axis weights tuned by split-half forward-return discrimination, like the
US axes.** Per-component diagnostic (scripts/calibrate_china.py) found
indpro_trend / smallcap_largecap / inflation_beta_basket / breadth_direction
FLIP sign or show ~0 edge across sub-periods → demoted (0.25–0.5); ppi_direction
is the strongest + most stable signal (eff −14.3/−2.1pp) → upweighted to 1.5;
cpi/pmi_mfg/cyclical_defensive kept 1.0. Result: 3/4 quads now sign-stable both
halves; only Stagflation flips (pre-2016 n=52 = the 2008 GFC, structural not
noise). CALIBRATION (2008→2026, split-half): **Growth-scare = robust contrarian
bottom** (+5–9%/63d, ~71% hit, both halves); Reflation = consistent mild fade;
expanding-PBoC-liquidity = clean tailwind (+1.7 vs +0.6%/63d). Shipped as a
risk-context map, not an allocation rule; the cycle ladder is a drawdown/
structure tool (early-bull anticipatory layer has NEGATIVE edge, same as US).
Ladder walk made `ladder_step`-configurable (10) for lean weekly CI.

**D74. build_china is standalone + bilingual, runs after build_site / before
build_vector** (which writes the hub last). It renders china.html + sector
drill-downs (sectors/<FUND>.html) + china_history.html + china_stock.html
(chinastockdata/, SSE:/SZSE: TradingView) + china_brief.html, returns 0 on ANY
engine error (verified — can't break the macro/vector site). Hub: build_vector
`_hub_html` gained a China card (gated on china.html present) + auto-fit grid
(future-proofs the parallel Commodity card); both coexist. China sector pages
use a decoupled china_sector.html.j2 clone (not a param of the parallel-owned
sector.html.j2) to avoid contention.

## 2026-06-13 — Vector Reserve Risk (deep cycle top/bottom signal)

**D-vec-RR. Reserve Risk added from checkonchain (2010->), not bgeo.** bgeo's
`reserve-risk` endpoint is only ~4y AND a different scale, so checkonchain is the
single source (scripts/backfill_crypto.py `reserve_risk` spec, trace "Reserve
Risk", stored data/checkonchain/reserve_risk.parquet). Used via bands/percentile
(scale-invariant, so no splice); early-2010 `inf` cleaned on read in
engine valuation(). CALIBRATION (deep, n=974 low band / n=48 top): **a powerful
TOP detector — Reserve Risk >0.02 -> −42.6%/90d at 4.2% hit (96% of the time
underwater 90d later)**; low (<0.0015) is the accumulation zone (+18.6%/90d).
Latest 0.0011 = 16th pctile = accumulation. config
`vector.valuation.reserve_risk_pctile_lookback_d`; emitted by valuation() as
reserve_risk + reserve_risk_pctile. Refresh: run backfill_crypto periodically
(checkonchain serves to today; not yet in a workflow). NOTE numbering: the
shared DECISIONS log has a D70 collision (parallel macro session's holdings D70
vs this session's on-chain D70) — cosmetic, both entries are complete.

**D-vec-GIT. The parallel macro session's `git reset` orphaned this session's
commit a807862; recovered.** Two agents share ONE working tree on `main`; the
macro session reset `main` to a different lineage (107d12e, a revert of its own
"i18n layer") which orphaned the Vector accuracy-upgrade commit. Recovered by
re-committing from the (intact) working tree. The Vector dashboard SURFACING
(build_vector.py vm + templates/vector.html.j2 panels) is intentionally HELD
BACK from the commit because it now depends on the macro session's i18n layer
(engine/i18n.py — untracked, reverted at HEAD); committing it would either
re-introduce reverted code or commit a broken build. The substantive, i18n-
independent engine/calibration/data work IS committed; the UI panels live in the
working tree and build locally. What would change it: serialize the two agents,
or decouple the Vector page from i18n.

## 2026-06-13 — Sector-ETF holdings accumulation backbone (Phase 1)

**D70. Weight-change anomaly detection = PRICE-DECOMPOSED residual, not raw Δweight.**
New `engine/holdings_signals.py` splits each sector-SPDR top-10 holding's weight change
between two daily snapshots into a price part and a residual:
`w_price = w0·(1+r_stock)/(1+r_fund)`, `active_change = w1 − w_price` (percentage
points). `r_fund` is the ETF's own close return; `r_stock` each holding's close return;
both read from the existing `store` (yahoo/stocks). WHY decompose: the 11 sector SPDRs
are PASSIVE, market-cap-weighted index funds — a holding's weight rises almost entirely
because its price/market-cap rose vs peers, so a naive "weight went up" signal just
re-detects price momentum (already covered by the cycle engine) and would mislead as
"accumulation/conviction." The residual is the honest signal. HONEST CAVEAT carried
through UI + ALERT_META + LIMITATIONS: on a passive fund the residual is index
reconstitution / float-weight flow (forced index-fund buying), NOT a discretionary
manager's conviction — that interpretation is reserved for the ACTIVE funds in the
Phase-2 top-200 page, where the SAME `decompose` core becomes a true conviction signal
(this is the design reason the engine is fund-agnostic). The math core `decompose` is a
pure, unit-tested function; readers `weight_decomposition`/`accumulation_signals`/
`all_accumulation_signals` sit on top. Confirmation layer reuses
`engine.cycles.analyze` (the calibrated ladder) — `confirmed` = accumulating AND the
stock is technically basing/turning up (BULLISH_STATES or urgency now/imminent/soon);
volume confirmation deferred to Phase 2 (not stored — `StockPriceAdapter` keeps only
close/high/low). New alert rule `sector_holdings_accumulation` (severity warn when
confirmed, else info) + an "Accumulation Watch" dashboard panel (#accumulation) + a
per-fund section on each sector drill-down. Config `holdings_signals` (lookback_days 5,
active_change_pp 0.15, active_change_pct 8, alert_pp 0.25, min_price_history 60,
panel_top_n 12) + `alerts.sector_holdings_accumulation` toggle. THRESHOLDS UNCALIBRATED
— only one snapshot (2026-06-11) exists today; everything degrades gracefully
(None/[]/"building" empty-state) until a second daily snapshot lands, after which
thresholds should be tuned against a few weeks of residual history (consistent with the
project's calibration discipline). Estimated $-flow = active_change × fund AUM (from
data/flows) — labelled approximate. WHAT WOULD CHANGE IT: Phase-2 adds
`collectors/etf_holdings.py` (generic multi-sponsor scraper, configurable top-200 list),
a dedicated `etfs.html` page, and volume confirmation (extend StockPriceAdapter + one
full-history backfill).

## 2026-06-13 — Vector on-chain regime adds (CryptoQuant-style, measured)

**D70. Coinbase Premium / SSR oscillator / MPI added and MEASURED — only
Coinbase Premium survives, as a CONTRARIAN signal.** The three reproducible
CryptoQuant-style demand metrics (their wallet-labeled Netflow/Whale-Ratio moat
is NOT free, VECTOR_PROVIDER_RECON.md). Coinbase Premium = real Coinbase−Binance
index via the bgeo `coinbase-premium-index` endpoint (2023→, seeded; config line
re-applied after the parallel macro session reverted it — budget 12→13). SSR
oscillator = −z-score of SSR (mcap/stablecoins, 2017→ deep); MPI = miner
outflow-USD / 365d-MA (from bgeo miner_sell_pressure minerOutflowBtc, 2022→).
engine `onchain_regime()`; config `vector.onchain`. CALIBRATION verdicts:
**Coinbase Premium is CONTRARIAN at the extreme — premium >+1.5% (US FOMO) →
−5.9%/90d at 36% hit = a measured TOP; 0 to +1.5% is the healthy-demand zone**
(reframed shape:extremes; naive "higher=bullish" was INVERTED). **SSR oscillator
= CONTEXT-ONLY** (no clean forward-return edge even at 2017→ depth). **MPI =
INVERTED** on the 2022-26 sample (miner distribution coincided with continued
upside — flagged loudly, not used as a bear signal). Surfaced on vector.html as
an "On-Chain Demand" panel with the honest labels (premium = contrarian gauge
w/ EUPHORIC-TOP flag >1.5%; SSR/MPI shown as context, not signals). House rule
held: measure, demote failures to context, never overclaim. What would change
it: more cycles of cohort data, or the paid CryptoQuant wallet-labeled flows.

## 2026-06-13 — Vector Tier-3 macro liquidity / risk-appetite overlay

**D68. Macro overlay added — and macro_score is a CONFIRMED signal (one of only
three).** engine `macro_overlay()` rebuilds, in the Vector engine (standalone —
reads the shared parquet store, doesn't import the macro engine), net liquidity
(WALCL−RRP−TGA, D10 normalization) + its 13-week RATE OF CHANGE, plus real-yield
change, HY-OAS percentile, VIX percentile and DXY momentum, blended (tanh/pctile
→ [−1,+1], + = BTC tailwind) into `macro_score` + a `macro_regime`
(tailwind/neutral/headwind) hysteresis. config `vector.macro`; btc_inputs loads
walcl/rrp/tga/real_yield/hy_oas/vix/dxy. CALIBRATION (BTC 2014→, deep): **net_liq_roc
monotone full sample** (liquidity expanding >5% → +47.7%/90d vs contracting <−2%
→ +11.1%; post-half weak = QT-era noise); **macro_score CONFIRMED — robust in
BOTH halves** (headwind <−0.3 → +1.4%/90d @41% hit; tailwind >+0.3 → +48.8%/90d
@76% hit). Only risk_index + bfi + macro_score are confirmed-both-halves.

**D69. Macro is kept STRATEGIC — NOT blended into the tactical allocation
(gate failed).** A/B test of a macro-headwind cap (trim when macro_score<−0.3)
REDUCED CAGR on all 4 variants with flat Sharpe/MaxDD — redundant with the
(momentum, risk) timing + valuation overlay, and the headwind band isn't
negative enough to sit out. So macro stays a standalone confirmed signal +
strategic context panel on vector.html (net liquidity / real yield / HY-OAS /
VIX-DXY + the measured headwind/tailwind record + TAILWIND/HEADWIND badge),
deliberately separate from the tactical composite_state — different horizon
(months vs days). What would change it: a longer-horizon allocation variant
where the macro tide is the primary timing input.

## 2026-06-13 — Vector leverage layer + Tier-1b blend + dashboard surfacing

**D65. Leverage/liquidation layer rebuilt from the 15-exchange BGeometrics OI +
aggregate funding we already store (what CoinGlass aggregates; their liquidation
heatmap is MODELED, not raw — VECTOR_PROVIDER_RECON.md).** engine
`leverage()`: oi_total (sum of a fixed core-venue basket — the bundled aggregate
col goes NaN), oi_mcap_ratio/pctile (froth), oi_price_divergence (ΔOI−Δprice =
crowding), funding_z, leverage_stress composite. Calibration (OI 2022→, funding
2023→ ⇒ confirmation): **funding_z<−1 (crowded shorts) → +18%/90d @70% hit**;
oi_price_divergence is directional (monotone −1 full+post — OI building faster
than price drags returns); leverage_stress 50-75 = de-risk zone. config
`vector.leverage`. A short-horizon RISK amplifier, not a trend signal.

**D66. Tier-1b blend SHIPPED — gated on the allocation backtest, and it passed.**
allocation() now takes the valuation frame and applies the calibration-confirmed
deep-history tails as contrarian overrides: MVRV-Z<0 (or NUPL<0) = accumulation
FLOOR (≥0.5), Mayer>2.4 = distribution CAP (≤0.5). Clean A/B (overlay off vs on,
same code, 2015→): **CAGR and Sharpe up on ALL FOUR variants** (conservative
47.7→51.4 CAGR/1.33→1.38 Sharpe; aggressive MaxDD −57→−48), cost = −1.4 MaxDD on
conservative (deep-value zones can extend). Kept ON (`use_valuation_overlay`).
Also added `composite_state()` — ACCUMULATE/DISTRIBUTE/RISK-OFF/RISK-ON/NEUTRAL,
valuation+extremes winning over the Risk Index so the forward-return U-shape
resolves into a direction; flips ~140× in 4288d (≈monthly, not whippy). What
would change it: if a future variant's MaxDD degrades materially, gate per-variant.

**D67. The new layers are surfaced on vector.html.** build_vector vm gained
valuation/options/leverage sub-dicts + composite_state; templates/vector.html.j2
got a hero Stance line and three bilingual panels (Valuation & Cycle · Options
Structure · Leverage & Positioning) between BFI and Cross-Asset, each carrying
its measured calibration record and honest depth caveat (options/leverage =
confirmation-only; per-strike snapshot = context until history accrues).
Verified in-browser (en+zh), no console errors. DVOL/skew/funding/OI all live.

## 2026-06-13 — Bitcoin Vector Tier-2 options structure (Deribit)

**D63. The options/funding layer is rebuilt from the FREE public Deribit API,
not bought.** Provider recon (research/VECTOR_PROVIDER_RECON.md, 3 web agents):
Laevitas/CoinGlass mostly repackage public data — Laevitas options analytics ≈
a skin over Deribit (≈85% of BTC options OI; unauthenticated API), CoinGlass's
signature liquidation heatmap is MODELED (OI × assumed leverage), not raw.
CryptoQuant's wallet-labeled flows are the only real moat; none has a usable
free API. Built `collectors/deribit.compute_structure()` — ONE
`get_book_summary_by_currency` call → ATM IV term structure (7/30/90/180d), 25Δ
skew/risk-reversal, put/call OI+vol ratios, max pain, gamma exposure, with
Black-Scholes greeks computed locally (scipy-free, r=0, normal CDF via
math.erf). Stored `deribit/options_structure` one row/day (accumulating —
the chain has no free history, so the per-strike panel is CONTEXT until depth).
GEX dealer-sign is the one modeling assumption (dealers long calls/short puts),
labeled as such. config `deribit.{term_tenors_d,skew_target_d}` +
`vector.options`.

**D64. DVOL + VRP are the calibratable options signals (history 2021→); the
structure snapshot is not yet.** engine `options()` adds dvol/dvol_pctile,
realized_vol, vrp (= DVOL − realized vol). Calibration (shape:extremes,
post-2021 ⇒ confirmation-only per house rule): **DVOL is a U-shaped risk gauge
— the 70-90 band (elevated, not panic) is the danger zone, −12.6%/90d @18.7%
hit (n=401); >90 panic bounces +15.8% @71.4%**. **VRP<−5 (realized overshooting
implied) → +17.2%/90d @77.8% hit** = post-capitulation recovery tell. Both
episode-autocorrelated and one-cycle deep → context, not anchors. What would
change it: another cycle of history, or per-strike snapshot accrual enabling
skew/term calibration.

**D60. The signal is two-dimensional: TACTICAL (daily) × REGIME (higher TF) —
expressed separately, never collapsed.** Diagnosis (user-reported, confirmed by
running the engine on BTC/ETH/COIN): the old ladder collapsed a genuinely
2-D read into one label, and a single noisy daily bit — `above_ma10` — swung the
headline 125 pts (BTC = +45 "BOTTOMING·BUY SETUP" vs ETH = −80 "DOWNTREND·AVOID"
while the two were structurally identical: both failed daily cycle, both failed
investor cycle, both weekly MACD crossed down, both daily ~1 bar from an up-cross
— BTC just happened to close a hair above its 10-day MA). Added
`regime_state(cyc, mtf)` → bull/neutral/bear from weekly+3-day MACD + investor-
cycle health + translation (score ≤ −1.5 bear, ≥ +1.5 bull). `weekly_ok` is now
`regime == bull` (was a weak binary on weekly MACD sign). ladder output carries
`regime`, `regime_line`, `summary_line` (short-term vs bigger-picture) + a
duration/"failed N days ago" line. What would change it: real Swissblock series
or a calibrated regime weighting.

**D61. New calibrated state COUNTERTREND BOUNCE + failed-cycle hard veto.** A
bullish daily setup (FRESH BUY / TURN SIGNALED) inside a BEAR regime — or with
failed_cycle AND ic_failed regardless of regime — is re-labeled to a distinct
state (score −25, action "HIGH-RISK · NIMBLE ONLY", tight-stop entry text), not
a green buy. Made it a real LADDER state (internal key fixed, per D35 calibration
discipline) so recalibrate() measures whether the bounce actually has forward-
return edge — per the house rule that anticipation ≠ edge until measured. ~11%
of the 533-name library lands here; bull/neutral setups (137 RALLY ON, 51 FRESH
BUY, 93 TURN SIGNALED) are untouched (SPY = BOTTOMING in a MIXED regime stays a
normal setup — the relabel is conditional on bear/hard-fail only).

**D62. Per-asset-class cycle clock (crypto ≠ equity).** BTC trades 7d/wk with no
gaps, so its daily cycle runs ~8–10 weeks (graddhy/thefinancialtap), not the
36–42 trading-day equity band — applying the equity band made BTC read
"stretched/bottoming" far too early (it showed dc_day 75 vs band 36–42).
`CYCLE_PRESETS` keyed by `kind`: crypto = dc_band (56,70), ic (24,40), dc_early
18, and 3-day bars resampled on `3D` CALENDAR days (equity `3B` business-day
resample silently mishandles weekend crypto bars). `analyze(..., kind=)` threaded
from build_stock_library (kind = crypto when ticker ends `-USD`). Trough geometry
(window/gap) deliberately left shared so the change is isolated to labeling, not
trough detection. What would change it: a proper crypto trough-window calibration.

**D58. Tier-1 metrics are added as STANDALONE columns and MEASURED before any
blend.** Diagnosis (research/VECTOR_ACCURACY_UPGRADE.md): the Vector had no
valuation/cycle anchor — momentum & structure are 100% price-derived trend
votes, which is exactly why they grade "DIRECTIONAL, one half weak" post-2021;
and ~60% of collected calibration-grade series (MVRV, NUPL, hashrate,
issuance, supply-in-profit, F&G…) never entered a calculation. Added
engine/btc_signals.py `valuation()` (MVRV-Z on a rolling 4y std window for
ETF-era responsiveness, NUPL, Mayer), `miner()` (hash ribbons + Puell),
`cost_basis()` (STH realized-price level + ratio) and `market_extreme()`
(capitulation/euphoria vote of NUPL/supply-in-profit/F&G/MVRV-Z). The existing
momentum/risk/structure composites are left byte-for-byte unchanged so prior
calibration stays comparable — blending the *confirmed* signals in is a gated
follow-up, not this pass. config `vector.{valuation,miner,cost_basis,extreme}`.

**D59. Valuation/miner metrics are U-SHAPED — judged on their TAILS, not
monotone rank-trend.** The split-half calibration's monotone test mislabels a
real top/bottom call as INVERTED (same reason the Risk Index is judged on
drawdown, D43). Added an `_extremes_verdict` path (spec `shape: extremes`) that
characterizes the low/high tail vs. the sample mean. Findings: **MVRV-Z <0 is
the keeper — +40.5%/90d at 71.9% hit (n=356) vs. a 22.4% sample mean**, deepest
history → the trustworthy deep-accumulation anchor. Mayer >2.4 is a genuine TOP
flag (−13.9%/90d, 33.9% hit). NUPL<0 corroborates MVRV-Z (collinear, as
predicted — pick ONE per axis when blending). Puell >4 is directionally right
but n=23 (too thin to trust). Hash-ribbon CAPITULATION is CONTEXT-ONLY — the
periods themselves don't carry higher avg forward return (the project's
recurring "anticipation ≠ edge" result, honestly reproduced).

## 2026-06-14 (3rd pass, macro) — light-mode color fix

**D-macro-A. Badges/pills/tags are tinted from ONE base color via `color-mix()`,
not hardcoded.** The "black buttons in light mode" were dark-bg badges
(state-STABLE, the cycle-state STATE_STYLES, stage pills) that never adapted.
templates/theme.css now does `background: color-mix(in srgb, var(--c) 15%,
var(--panel)); color: color-mix(in srgb, var(--c) 80%, var(--text))` for every
badge family, each class assigning a semantic `--c`
(up/down/warn/orange/info/muted). Auto-adapts: dark tint + light text in dark
mode, light tint + dark text in light mode. Removed all per-page `.st-*` CSS
generation (theme.css owns it), the Python STATE_STYLES/STAGE_STYLE inline-hex
usage (→ `.st-*`/`.stg-*` classes), and every hardcoded #7aa7e0 link / #fff
gauge marker / dark tooltip bg (→ var(--link)/var(--text)/var(--panel)).
HEAT_COLORS now emit CSS vars. (NB: D49–D55 numbers are taken by the parallel
Bitcoin Vector session in this shared log; using neutral keys to avoid clash.)

**D-macro-B. Plotly charts render on their own dark slate (#12161d) in both
themes.** A light-mode chart of dark-tuned lines on a white panel was invisible;
rather than maintain two renders, the charts keep one dark surface always
(`.chart`/`.tv` round the corners). Token approach learned from the Bitcoin
Vector dashboard (everything via var()).

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

## 2026-06-14 — Bitcoin Vector Phase 3 (alerts + timeline + home feed)

(Renumbered D54–D57 to deconflict from the macro session's parallel D49–D53 in
this shared log — content unchanged.)

**D54. The alert timeline is DERIVED, not a stateful append-log.**
engine/btc_alerts.py recomputes the full event timeline deterministically from
signal + hourly history each build (daily state changes + flash-crash state
machine), so it's idempotent by construction — no double-fire risk. The only
stateful piece is the intraday sentinel, which appends genuinely-new flash
events; the daily recompute reproduces them from the now-stored candles (id =
type:ts-bucket:to_state → natural dedup).

**D50. Flash-crash machine needs ABSOLUTE drop floors, not sigma alone.** First
cut (3σ over 6h) produced 800 false "crashes" — crypto fat tails make 3σ/6h
routine. Fixed to: 6h move ≥3.5σ AND ≤−7%, OR 24h ≤−12% (tail ≤−18%). Now
captures the real episodes (May-2021 −21%, Aug-2024 −18%, FTX/Celsius −18%,
Luna −15%) at ~10 acute entries/yr and ignores −3% grind days. Thresholds in
config `vector.alerts.flash`; provisional (episode-fit, not a formal sweep).

**D51. Sentinel commits only on a flash-state CHANGE** (no 48×/day heartbeat
spam). State is recomputed deterministically from a trailing 90-day candle
window each run and the sentinel re-fetches the last 300h live, so it never
needs persisted state to know the CURRENT state — only to detect a transition.
Exit code 10 = changed (CI rebuilds + commits), 0 = quiet (nothing committed).

**D52. The landing hub is "Market Intelligence" with a combined alert feed from
both engines; "Macro Dashboard" renamed to "Macro Vector" on the hub.** Home
shows MAJOR alerts only (macro act+warn minus operational circuit-breaker;
vector high+medium), deduped within 5d, capped 12, each expandable with a
deep-link into its source dashboard. The full granular Vector feed lives on
vector.html#timeline. Cross-session note: tried to coordinate the "major" rule
list with the macro session via send_message but it's unavailable in
unsupervised mode — defaulted from reading engine/alerts.py directly (the macro
feed data/alerts/alerts_log.parquet is live, written by engine/run.py).

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

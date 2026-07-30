# Engineering decisions log

Newest first. Each entry: what was decided, why, and what would change it.

## 2026-06-14 — Vector CME (regulated) futures basis — institutional carry CONTEXT (measured null)

**D-vec-CME. Added the CME regulated futures basis as a positioning-context read — built
exactly because the empirical test said it's NOT a predictive signal, which is the honest
outcome.** New BTC=F Yahoo pipe (config yahoo.tickers.crypto_fut; stored as BTC_F, daily
2017->; the collector already handles `=F` tickers as `_F`). btc_signals.cme_basis: the
front-month future vs spot premium = the REAL-MONEY, regulated institutional carry, distinct
from the offshore Deribit perp funding already in the model. Emits cme_basis (%), ~annualized
(x12 front-month approx), 1y percentile, and a regime (contango froth / flat / backwardation
stress). MEASURED FIRST: rank-IC vs forward BTC return is ~ZERO (−0.006/30d, +0.025 for the
z-score, flat across all bands incl. the extremes, 2021->). So it is NOT calibrated / NOT a
signal — shipped as institutional POSITIONING CONTEXT in the leverage panel with that null
stated plainly. (The earlier 8% "basis" was a Yahoo weekly-vs-daily artifact; the daily
series is clean, median 0.19%.) LIVE: +0.52% (~+6%/yr, 68th pctile, flat-to-mild contango).
tests/test_vector_cme.py (2). This is the 3rd remaining Tier-2 candidate empirically tested
this session: cross-asset beta (symmetric, weak) and CME basis (null) both shipped as
context/not-shipped; ETF flow (real edge) was already built. The high-value factor roadmap
is complete. NOTE: build_vector.py is under heavy concurrent-session editing — used atomic
read-replace-write for the contended inserts. The vector.html chart bloat (flagged via
spawn_task) appears fixed (page 1.2MB -> 495KB).


## 2026-06-14 — Vector scheduled-catalyst (FOMC/jobs) gate + cross-asset-beta tested & skipped

**D-vec-CAT. A 'don't size into the binary' event gate; and an honest skip of a weak
factor.** Two Tier-2 candidates were tested empirically before building.
(1) **Downside-vs-upside cross-asset beta — TESTED, NOT SHIPPED.** Thesis: BTC couples
hard to equities on the way down, decouples up. Measured: downside β to SPX = 0.65 vs
upside β = 0.64 (asymmetry ~0.03, roughly SYMMETRIC), and forward-30d drawdown by
asymmetry quartile is weak + non-monotone. The 'fragile down / antifragile up' narrative
isn't borne out for BTC → not shipped as a signal (don't ship weak factors). The spot-ETF
flow factor (the other candidate) was found ALREADY BUILT (etf_flow_z, monotone, 30d
rank-IC 0.209, +8.1%/30d on heavy inflows; shipped <2yr confirmation-grade).
(2) **Catalyst window — BUILT.** build_vector.catalyst_window: deterministic calendar of
the next scheduled macro BINARY (FOMC decision dates, Fed-published 2024-26 + 2027 est.;
jobs report = first Friday). Returns next_event / days / imminent. When a binary is within
`imminent_days` (config vector.catalyst, 3), the Kelly sizing card shows an amber 'expect a
vol jump; the Kelly size models neither the gap nor the vol crush — don't size into it'
gate. A new MODALITY (the Vector's only prior event was days_since_halving), free, and an
honest risk-awareness gate, not a forecast. LIVE: FOMC in 3 days (imminent). tz-aware input
handled; wrapped so it can't break the build. tests/test_vector_catalyst.py (3). 11 vector
test files now green. The high-value factor roadmap is now substantially complete; remaining
Tier-2 (CME basis, NRPL, 25Δ butterfly, funding term-structure) need new data pipes or are
near-duplicates / marginal.

## 2026-06-14 — Vector conviction → capped fractional-Kelly position sizing

**D-vec-KELLY. The conviction + forward-drawdown apparatus now outputs an actual "how
much to hold" — a half-Kelly position size capped by the worst-case-dip budget.**
`build_vector.kelly_sizing(sig, cfg)`: the EDGE is the calibrated forward-90d return of
the CURRENT composite stance (direction is a coin-flip, so the edge comes from the REGIME,
not the 3-7d call — ACCUMULATE +33%/90d, RISK-ON +32%, RISK-OFF +18% contrarian-bounce,
DISTRIBUTE +6.9%, NEUTRAL −9.7%); fractional-Kelly f = kelly_frac·max(E,0)/σ² sizes on it
(σ = forward-90d return std); and the position is CAPPED so the 90d worst-case dip (the
forward-drawdown p05 tail for the LIVE risk band, reusing forward_risk(sig,90)) stays
inside a drawdown budget: f_tail = dd_budget/|tail|. size = clip(min(f_kelly, f_tail),
0, pos_max); the binding constraint (edge vs tail) is named, and a non-positive regime
edge → 0% (hold nothing). config vector.sizing (kelly_frac 0.5 = HALF-Kelly since full
Kelly over-bets fat-tailed crypto; dd_budget 0.25; pos_max 1.0). LIVE: composite DISTRIBUTE,
E +6.9%/90d (σ 53.5%), 90d band tail −51% → half-Kelly f 0.12 (EDGE-binding, not tail) →
**12%** — honestly small in a distribution regime. Surfaced in the hero allocation card
with the binding-constraint prose + the coin-flip caveat. tests/test_vector_kelly.py (3:
positive-edge-sizes-up / negative-zeroes, size==binding-min, live-valid). NOTE: the deeper
edge source could be the calibrated allocation strategy's own per-state return rather than
the raw composite band — a refinement. Separately flagged (spawn_task): site/vector.html is
~1.1MB pre-existing (the risk-strategy Plotly chart inlines 4288 pts at full float
precision); rounding the chart data would cut it ~3x — NOT this change.

## 2026-06-14 — Vector point-in-time: the "valuation regression refit" gap was a PHANTOM; proven causal + guarded

**D-vec-PIT. Investigated the roadmap's "expanding-window refit of regression valuation
bands" item — it does NOT exist in the live engine.** The roadmap (workflow-generated)
claimed full-sample regression fits (difficulty-regression R²=0.944, Metcalfe log-log,
NVTS thresholds) silently look-ahead-bias their bands. Verified by code inspection +
empirically: those models were Tier-3 REJECTED and never built. The live valuation logic
is ALREADY rolling/causal — MVRV-Z uses a rolling std + rolling percentile, Mayer a rolling
200d MA, valuation_state a hysteresis on FIXED domain thresholds (Mayer>2.4 etc. — economic
priors, not sample-fits), every `_pctile` a causal `rolling().rank(pct=True)`. The only
non-rolling `.mean()/.std()` is inside `_zscore`, where the object is already a rolling
window. EMPIRICAL AUDIT (the proof): recomputed compute_all on inputs truncated at
2023-06-01 and compared the overlap ≤2023-02-01 vs the full run — **all 76 numeric signals
AND every state signal are byte-identical at past dates** (0 look-ahead leaks >1%). So
there was nothing to refit; the engine is point-in-time. DELIVERABLE (the durable form of
the discipline): tests/test_vector_pit.py institutionalizes it — recompute-on-truncated ==
full at past dates, for numerics (≤1% drift) + states (exact), failing on any future
full-sample fit / forward window / leaked bar. REMAINING (narrow, separate, NOT done): the
data-VINTAGE issue — FRED returns revised finals, so historical M2 / payrolls in the store
are revised values not as-of vintages (ALFRED realtime_start would fix it). Impact is small
(M2 revisions are minor; the market-priced macro inputs — yields/OAS/VIX/DXY — are final),
so deferred as low-value/high-complexity vs the Tier-2 factor list.

## 2026-06-13 — Vector ensemble capstone: tested a principled ensemble, KEPT the heuristic (validated)

**D-vec-ENSEMBLE. The deferred capstone — a fixed-form, orthogonalized, gate-passed
ensemble to replace the hand-tuned composite_state — was BUILT, MEASURED, and honestly
NOT promoted: the heuristic beats it in both halves, so the heuristic is kept and now
*validated* rather than just hand-set.** Design from a 12-agent workflow (robustness lens
won; adversarial overfit-skeptic panel). Six one-per-orthogonal-axis signals (risk_index,
net_liq_roc, vrp, cot_z, mvrv_z, momentum — the collinear valuation cluster collapsed to
mvrv_z ONLY, by admission not averaging), de-correlated in a fixed robustness order via a
NEW causal-residual primitive `engine.validation.resid_z` (z-series analogue of forex
orthogonalize, which returns a price index — wrong shape). KEY FINDING (the discipline
working): a naive linear `z×want` ensemble had rank-IC −0.01 and was INVERTED at extremes
(ACCUMULATE at the 2021 top), because 4 of 6 axes are U-SHAPED — a linear blend can't
orient them. Fixed by orienting each axis by its CALIBRATED expected-return band-map →
ensemble OOF rank-IC jumped to **+0.22**. The promotion gate (`ensemble_promotion` in
calibrate_vector) then compared net-cost Sharpe in both halves: orthogonalized ensemble
**1.01** (pre 1.24 / post 0.31) BEATS the best single signal (mvrv_z) 0.47 — de-redundancy
+ orthogonalization earn their keep — but the hand-tuned Stance **1.19** (pre 1.48 / post
0.65) beats the ensemble in BOTH halves → verdict **KEEP-HEURISTIC**. We do NOT ship a
worse model to look sophisticated (the forecast-combination literature: equal-weight /
best-single are brutal baselines on ~3 cycles). composite_state stays the headline,
untouched (time-machine/alerts read it). Surfaced as an honest transparency card on the
page + the calibration report. tests/test_validation_gates.py +resid_z. What would change
it: a future regime where the ensemble sweeps both halves + best-single + heuristic would
flip the verdict to PROMOTE (the gate re-decides every calibration). This is the capstone:
the ensemble machinery exists and is measured; promotion is data-driven, not assumed.

## 2026-06-13 — Vector dealer gamma-FLIP level (zero-gamma spot) + distance-to-flip

**D-vec-GAMMA. The last roadmap Tier-1 factor — a dealer gamma-regime boundary, computed
from the options chain the Vector already fetches.** collectors.deribit._gamma_flip
recomputes net dealer gamma across a ±25% spot grid (same BS closed form + assumed dealer
sign — long calls / short puts — as the existing gex_per_1pct_usd scalar) and finds the
zero-gamma crossing nearest spot. Emits gamma_flip (spot), dist_to_flip_pct (signed), and
gamma_regime: ABOVE the flip = net long gamma (dealers hedge against the move → pinning /
mean-reversion / vol suppressed), BELOW = net short (hedge with the move → amplification /
trend / vol expansion). A binary vol-regime BOUNDARY distinct from the per-1% sensitivity
scalar — directly addresses the documented 'post-2021 trend votes degrade' problem by
giving a gate. Wired through btc_signals.options() (snapshot passthrough) + surfaced in the
options panel. LIVE: spot $64,624 sits +1.9% ABOVE the flip $63,399 → long-gamma (pinning)
regime; a break below $63,399 would flip to amplification. SNAPSHOT-ONLY (Deribit has no
free options history) → it forward-ACCRUES rather than being back-calibrated; framed as a
regime read, not a forecast. tests/test_gamma_flip.py (2: flip-in-range + regime-sign +
degenerate-None). NOTE: the daily pipeline aligns the snapshot date with the close date; a
manual mid-day fetch can run 1 day ahead (cosmetic, self-resolves). Completes the 4 roadmap
Tier-1 factors (RV cone, stablecoin tide, peg monitor, gamma-flip); next = the deferred
ensemble capstones the stability gates unlock.

## 2026-06-13 — Vector stablecoin PEG-deviation monitor (measured → ships as CONTEXT, not a veto)

**D-vec-PEG. A stablecoin peg-integrity monitor — and an honest negative result that
kept it from shipping as a risk signal.** Roadmap Tier-1: a peg-deviation "veto" (the
missing BTC-side Gate-1). Built the data path: DefiLlamaAdapter (crypto_misc.py) now also
fetches stablecoinprices and stores `stablecoin_peg` = daily MAX |price-1| across the
ALIVE systemic majors (USDT/USDC/DAI; config defillama.peg_majors). DATA-QUALITY CATCH:
dead coins (UST/BUSD) sit at ~0 forever (10000bps) and would false-trigger permanently →
excluded by a 0.2<px<1.8 sanity window; their collapses are captured by the supply tide
instead. btc_signals.stablecoin_tide emits peg_dev_bps + peg_state (stable<50 / watch / 
break≥150bps) + peg_stress. Series 2020→, current 4bps (healthy); only real big-3 event
is the USDC SVB depeg (2023-03-12, 389bps). HONEST MEASURED RESULT (event-study): a peg
break does NOT cleanly precede BTC drawdown — the one major break (SVB) was followed by a
BTC RALLY (+7.8%/7d, banking-crisis hedge); watch-level stress shows only a modest edge
(−4.9% vs −3.5% fwd-7d-dd). So it is event-driven and its BTC-directional thesis is
UNCONFIRMED → it ships as a collateral-solvency MONITOR + context flag (with that caveat
shown), NOT a calibrated risk input or a veto on the composite. A textbook measure-before-
blend save: a plausible risk factor that the data says is situational awareness, not alpha.
Surfaced in the macro panel; config defillama.peg_watch_bps/peg_break_bps. What would
change it: more big-3 break events (a second data point) could establish a real direction.

## 2026-06-13 — Vector Tier-1 factors: realized-vol cone + vol-of-vol, stablecoin liquidity tide

**D-vec-RVCONE / D-vec-STBL. Two orthogonal, both-halves-clean factors from the factor
roadmap (research/VECTOR_FACTOR_ROADMAP_2026.md), now MEASURED through the new stability
gates before any blend.** Both effort-S (data already on disk).
(1) **Realized-vol CONE + vol-of-vol** (engine.btc_signals.options): the RV series was
trapped in the DVOL branch (~2021 only) — moved it to FULL history (close-based, 2015→)
so realized_vol now feeds VRP with deep history, and added rv_cone_pctile (where current
RV sits in its own ~3y distribution) + vol_of_vol + vov_pctile. The only vol-regime read
that survives BOTH halves (DVOL can't reach back). MEASURED (calibrated EXTREMES, U-shaped
like DVOL/risk_index): high vol-of-vol pctile preceded **+37.7%/90d at 76% hit** (n=826,
capitulation bounce), calm cone +24.8%/90d — a near-term risk gauge, not a direction call.
Not purged-CV-robust (U-shaped → mixed fold signs, expected). config options.rv_cone_lookback_d.
(2) **Stablecoin supply-growth TIDE** (engine.btc_signals.stablecoin_tide): a z-scored,
de-trended 30d growth rate of aggregate stablecoin mcap (data/defillama/stablecoins.parquet,
2017→, already on disk but only used for the SSR *ratio*). Crypto-native liquidity —
orthogonal to the FIAT net-liquidity/M2 overlay. MEASURED **DIRECTIONAL** (same tier as
net_liq_roc/global_m2/macro_score): expanding tide (z 1–2) → +23%/90d at 76% hit;
contracting (z < −1, **the live state**, z −1.8) → only +0.8%/90d at 42% — a measured
headwind. config global_liquidity.stbl_growth_window_d/stbl_z_lookback_d. Both calibrated
(SIGNALS in calibrate_vector, so they ride the both-halves + purged-CV + collinearity
gates) and surfaced honestly in the options + macro panels with their records. NOT yet
wired into the live risk_index/composite — that is the deferred ensemble capstone the
gates unlock (measure-before-blend discipline). All 9 vector tests green; reconciliation
intact. NEXT roadmap Tier-1: gamma-flip (Deribit recompute) + stablecoin peg-deviation veto.

## 2026-06-13 — Vector stability gates: purged CV, OOF probability calibration, collinearity, bootstrap CI

**D-vec-GATES. Four compute-only methodology gates added to the calibration harness
(no new data; can only reduce overfit).** A 14-agent factor-research workflow
(research/VECTOR_FACTOR_ROADMAP_2026.md) found the highest-leverage Vector upgrades are
NOT new factors but methodology gaps — the precondition that lets thin post-2024 factors
ship honestly. Built as ADDITIVE calibration.json blocks (existing verdicts untouched) +
reusable primitives in engine.validation (shared with commodity/forex calibrators):
purged_folds, block_bootstrap_ci, brier_reliability, platt_fit, vif, top_correlated_pairs.
NOTE: DSR + cost-aware backtest + trial_log ALREADY shipped — the research over-stated
those as gaps; the real remaining work was these four.
(1) **Purged + embargoed walk-forward CV** — the single split_date leaked (a pre-half
row's 90d forward label peeked across the split). Fixed: embargo the pre-half's last
embargo=max(horizons)=90 rows + add a stricter K=5 purged walk-forward gate (each fold
embargoed on its right edge; robust = full sign==want + no fold flip + all-but-one agree;
drawdown gauges judged at 7d, returns at 90d). LIVE: only **6/27** signals survive the
leak-free gate (risk_index, vrp, net_liq_roc, impulse, cycle_pct, cot_z). config
vector.calibration.cv_folds.
(2) **OOF probability calibration of the conviction layer** — _conviction stated odds
with NO reliability/Brier anywhere. Added out-of-fold Brier + reliability + Platt (each
day's P(up) = the momentum×risk cell rate fit on the OTHER folds, the live EB mechanism,
scored vs realized). LIVE: Brier 0.250 vs base 0.248, **skill ≈ 0**, Platt a≈0.69 — the
measured proof that direction is a near-coin-flip with ~calibrated odds and no skill.
(3) **Collinearity (VIF + top-corr pairs)** — surfaces the cost-basis triple-count.
LIVE: 14 signals VIF≥5; mvrv_z~nupl 0.94, mayer~sth_cb 0.94 → orthogonalize before blend.
(4) **Block-bootstrap CI on the allocation backtest** — circular 21d-block bootstrap →
95% CI. LIVE: optimal Sharpe **1.42 [0.79, 2.03]**, P(Sharpe>0)=1.0 (pairs with the DSR
mean-haircut). tests/test_validation_gates.py (5). Verdicts/reconciliation unchanged; all
9 vector tests green. NEXT (deferred): wire the orthogonalized residual into the LIVE
composite (the ensemble capstone) and refit the regression valuation bands on expanding
windows (the next PIT gap) — both build on these gates.

## 2026-06-13 — Vector "Cycle Time Machine": scrubbable point-in-time history

**D-vec-TIMEMACHINE. A draggable timeline that rewinds the whole Vector core to any
past day — 13 pieces move at once.** User wanted a scrubber to see "historically what
the stages those times are." CLONED the proven macro/HK time-machine pattern (shared
client-side scrubber over a columnar JSON tape; no deps, canvas ribbon + range + play
+ jump presets + readout). KEY EFFICIENCY: 17 of 19 stages are ALREADY causal per-day
in signals.parquet (price, momentum, risk_index, cycle_phase, cycle_position->stage,
valuation, composite stance, market_extreme, alloc...). Only the cycle-LADDER state +
regime are build-time-only (engine.cycles.analyze is latest-only), so
scripts/backtest_ladder_history.py REPLAYS analyze() on expanding windows (point-in-
time, NO look-ahead) and caches data/vector/ladder_history.parquet (3888 days,
2015-10->; ~2.6min first pass, incremental after). VALIDATED the backtest nails every
inflection: 2017/2021 tops -> TOP WATCH/bull/overvalued/DISTRIBUTE/euphoria/low-risk;
2018/FTX bottoms -> DECLINE/bear/undervalued/ACCUMULATE/capitulation/high-risk (risk_
index is contrarian at extremes, by design). build_vector.vector_timeline() merges
signals + ladder cache -> site/vector_timeline.json (370KB, 3888 days); build_timeline()
runs it + the incremental backtest each build (wrapped, can't break the build). NEW
site/vector_timemachine.js (cloned mechanics: paint/setIndex/idxFromClientX/nearest/
play/wire) with a Vector readout + a cycle-PHASE-coloured ribbon (accumulation/markup/
recovery/markdown) + a robust theme/lang reactivity (custom events OR a MutationObserver
on data-lang/data-theme). Panel in vector.html.j2 after the Risk-vs-Strategy section.
Verified live (eval): tape loads, jumps + scrub rewind date/tag/phase/stage/regime/
ladder/momentum/valuation/extreme/stance/alloc/risk-gauge/price coherently; EN<->中文
(async re-render); dark repaints; 0 console errors. What would change it: adding a stage
to the readout = add a column to vector_timeline() + a DOM id + a label map in the JS.

## 2026-06-13 — Vector cards re-framed onto forward DRAWDOWN (the confirmed quantity)

**D-vec-RISK. The mid/short cards now LEAD with calibrated forward drawdown/risk;
direction (the conviction toss-up) is demoted to a secondary strip.** Follow-up to
D-vec-CONV: short-horizon DIRECTION is a coin-flip, but forward DRAWDOWN is the
quantity the engine actually predicts and it is already calibrated + both-halves-
stable in calibration.json -> risk_drawdown (avg dip + p05 tail by risk_index band,
7d/30d/90d, split pre/post-2021). New `forward_risk(df, horizon)` in build_vector
(+ `_band_of` right-closed to match calibrate's pd.cut, `_fwd_dd`, `_risk_lines`)
computes the conditional forward worst-drawdown for the LIVE risk_index band at 3d
(DIRECT window, no calibrated col -> never a sqrt haircut) and 7d, with the calm-band
(0-25) baseline for excess-over-calm framing, a pre/post-2021 stability flag, and a
thin-n flag. Wired as env.risk / scn.risk; reconciles with calibration.json to 2dp
(7d band 25-50: helper avg -4.2 vs -4.17, tail -16.6 vs -16.61). UI: the shared
convcard macro gains an R param and a risk-led layout — a band state word
(CALM/ELEVATED/HIGH/EXTREME, the SAME 0-25/25-50/50-75/75-100 cuts as the verdict
table so they can't disagree), horizon WELDED to the headline ("ELEVATED · next 7
days") so a near-term dip can't read as a cycle call, a typical/worst-case line with
the calm parenthetical, and a DRAWDOWN RAIL (downside=70% emphasized r3 half +
faint-blue upside stub + a ringed grey calm-baseline dot whose gap to the live tail
IS the excess-over-calm story). The TOSS-UP needle shrinks to a labeled coin-flip
strip ("direction is a coin-flip — drawdown above is the predicted quantity"). HONESTY
GUARDS (workflow honesty-review, 9 agents): the 90d CONTRARIAN FLIP (high risk marks
bottoms at 90d) is fenced — the contrarian softener fires ONLY in bands 50-75/75-100;
band 25-50 (current, the WORST 90d band post-2021) gets the plain near-term-only line.
Non-monotone (avg dip -2.97/-4.17/-4.65/-4.40 — extreme < high) so it's a GRADED read,
never "more risk = more drawdown". thin-n (75-100 n=98/33) de-emphasises the tail.
Monochrome (downside r3, no red). Live: ELEVATED, 7d typical -4.2% (calm -3.0%) /
worst -16.6% (calm -14.0%), stable. tests/test_vector_forward_risk.py (4 tests: band
edges, calibration reconciliation, 3d-direct-window vol-time ratio, excess-over-calm).
What would change it: a band genuinely clearing the calm spread shifts the state word;
re-running calibrate updates the reconciliation target.

## 2026-06-13 — Vector conviction layer: label the no-edge state instead of a fake 53/47

**D-vec-CONV. The mid/short scorecards now lead with an HONEST conviction state
(TOSS-UP / LEAN / EDGE), not a bare ~53/47 probability bar.** User: "53:47 / 52:48
looks odd, as if the system doesn't know what it's doing — give more accurate
signals, OR if this IS the accurate read (genuine hesitation) add a MIXED/Undecided
state." A workflow (10 agents: adversarial diagnosis + UX research + 3-lens design
panel + judge + synthesis) confirmed the SECOND reading with hard data: the near-
50/50 is an HONEST coin-flip, not a bug. MEASURED: BTC's unconditional 7d up-rate is
54.1%; the current cell (bear-momentum / high-risk, **n=1351**) has a 7d up-rate of
**51.9%** RAW (before any shrink/cap) — flatness arrives in the DATA. Across all
reliable (n>300) cells the up-rate spans only **51.9-57.1%** — short-horizon BTC
DIRECTION barely depends on the state; the predictive content is in DRAWDOWN and at
30/90d (the calibration report already says this). So manufacturing more 7d
separation = overfitting (un-capping [30,70], stacking collinear MVRV/NUPL/Mayer, or
reading thin cells like bear/low_risk n=26 @23%); the right fix is to LABEL the
no-edge state. **Build** (`_conviction` + `_conviction_why` + `_tape_sign` in
build_vector, wired in the vm block where verdict+mtf_rows co-exist; bands in config
`vector.scenarios.conv_band_pp: [3,7]`): TOSS-UP `|p-50|<=3` (grey, no direction
word, a grey "bear-lean" chip for the tilt sign), LEAN `<=7` (washed-out tint, named
driver), EDGE `>7` (full color) — but EDGE is gated: needs n>=300 AND verdict
agreement AND a non-conflicting tape, and a non-reliable cell can't print an
EDGE-sized lean (the n=26 noise guard). The technical tape (W/2W mid, D/3D short) is
an orthogonal 2nd vote that only DEMOTES on conflict, never manufactures edge.
**UI** (vector.html.j2, shared `convcard` macro so mid & short are byte-identical):
a centered tug-of-war NEEDLE on a FLAT grey rail with a grey 47-53 dead-zone (the dot
stays grey inside the zone, so 53% LOOKS like no-edge), the state word as the
headline, the raw % as support, an honest one-liner ("bear-high: 7d ~53/47 over 1,351
samples — a coin-flip; the edge is in the cycle, not the week"), and a DEFER line
echoing the hero verdict ("↳ Defers to CAUTION — no edge to add"). Monochrome palette
(bull=blue, bear=r3, toss=grey; no red — reserved for alerts). The short card keeps
its ATR levels, reframed as "if it resolves up / if it resolves down" scenarios.
**Result:** today both cards = TOSS-UP, reconciling the whole page top-to-bottom
(Risk OFF / bearish → counter-trend bounce → week/3-day = coin-flip, don't trade it
directionally). 13-case classifier unit test + 4 macro-branch render checks +
`tests/test_vector_conviction.py` (5 tests). What would change it: a regime where a
reliable cell genuinely clears ±7pp would surface a real EDGE; widening conv_band_pp
would re-tier. The deeper upgrade (re-frame the cards onto the CONFIRMED drawdown/risk
read the engine actually predicts) is noted but out of scope.

## 2026-06-13 — Forex Vector (Phase 0–1): dollar-first currency board

A new section (`forex.html`) built after a research + adversarial-review workflow
(`research/FOREX_DASHBOARD.md`). It is a structural CLONE of the commodities section
— same `factor_panel`-style stack, the same `[-100,+100]` conviction scale and bands,
the same price layer (`engine/commodity_signals` `momentum/structure/risk/ts_momentum/
positioning` imported as-is) — with FX-specific deviations decided below.

**D-FX1. ★ Dollar-first / orthogonalized residual (not raw pairs, not a per-pair dollar
factor).** ~89% of FX routes through USD, so 8 USD pairs share one dollar move. We score
each pair on its broad-dollar-ORTHOGONALIZED residual (rolling causal beta vs `DTWEXBGS`,
prior-window beta to avoid same-bar look-ahead) and put the dollar in a single board-level
master tile — NOT also as a per-pair factor. Reason: keeping both would double-count the
dollar (the review's top finding) and make the board print false 8-pair consensus on a
dollar day. A **dollar-day haircut** (when `|daily z of broad-$|` > 1) shrinks per-pair
confidence as a second guard. Trade-off: residual signals are less intuitive than raw
pairs; mitigated by plotting the raw quote AND the ex-$ index together. Test:
`test_orthogonalize_strips_dollar_beta` (residual β-to-dollar ≈ 0).

**D-FX2. Carry from policy/short-rate differentials, labeled honestly; NOT a fake 2y.**
The review confirmed there is no free, clean, daily cross-currency 2y on FRED. We use the
foreign policy/short rate (ECB `ECBDFR` daily; JP/AU/GB/CA/CH `IR(ST/3TIB)…` monthly) minus
US `DFF`. Crucially these are PIECEWISE-CONSTANT step functions, so monthly cadence +
ffill is economically correct (the rate really is still that value) — the monthly-into-daily
look-ahead concern only bites market prices (REER), not policy rates. Carry is vol-penalized
(carry-to-vol haircut) so fragile high-vol carry is down-weighted. EM (MXN/BRL/CNH) have no
free clean front-end rate → `carry: context` (no weight), surfaced as such on the tile.

**D-FX3. Risk-context headline, LONG/SHORT-base secondary.** FX fails UIP (the Fama slope
flipped post-2008) and carry has fat-tailed crash skew. A confident "STRONG LONG EUR" would
be dishonest, so the verdict HEADLINES as a regime/risk-context read; the directional
LONG/SHORT-base chip is secondary and the crash-skew caveat ships inline, not in a footnote.

**D-FX4. Pegs/intervention override the verdict AND (later) calibration.** Managed `USD/CNH`
→ forced FLAT; an `USD/JPY` MoF intervention watch zone (150–162) caps `|score|`; SNB history
flagged. Phase-2 calibration must also EXCISE peg/intervention windows from the return
windows (carry over a peg looks riskless until the discontinuous break). Test:
`test_conviction_peg_intervention_caps`, `test_conviction_managed_forces_flat`.

**D-FX5. Phase 1 ships before calibration.** Weights are a documented prior (`FX_PRIOR`),
`score_reliable=False`, and confidence is dampened ×0.6 — honest about being un-measured.
`split_date` is **2015-01-01** (not commodities' 2013) so BOTH halves straddle a carry
unwind (2008 | 2015 SNB/2020/2022/2024). Forex orientation is the #1 silent-bug surface;
`test_real_orientation_crosscheck` pins canonical base-vs-USD price to the FRED `DEX*`
reference per pair (and `1/USDJPY` vs `1/DEXJPUS` for inverted pairs).

**D-FX6. No new collector code — config-only data.** `yahoo.tickers.fx` + `fred.series.fx_*`
+ `cot.markets` (currency prefixes) drive the existing Yahoo/FRED/COT adapters unchanged.
`build_forex.py` returns 0 on any engine error (never breaks the site), runs before
`build_vector`. What would change it: COT was unavailable at build time (CFTC Socrata 503
outage) — positioning populates on the next successful collect; REER value + real-rate
factors + the full pair board + MTF + alerts are Phase 3.

**D-FX7. Phase 2 calibration is PRIOR-ANCHORED, not raw-IC (the overfitting guard).**
`calibrate_forex.py` measures each naive-bullish factor's Spearman IC vs forward
base-vs-USD returns over [21,63,126]d, split-half (split 2015), peg windows excised.
First attempt = raw IC weights → a single weak factor (AUDUSD `risk`, |IC|=0.09) ballooned
to 87% of the weight after normalization, and noise-level ICs (|0.03|) got labeled
CONFIRMED. That's exactly the short-FX-history overfit the review warned about. So the
shipped method keeps the STABLE prior magnitude and uses measurement only to (a) flip the
sign of robustly-INVERTED factors (same sign both halves, |IC|≥0.06), (b) halve
DIRECTIONAL ones, (c) down-weight CONTEXT to 0.25× prior. `score_reliable` (lifts the
×0.6 confidence damp) requires ≥2 robust factors — the active EUR/JPY/AUD each have only 1,
so they stay dampened (honest). Findings that survived: USD/JPY trend CONFIRMED (yen
trends), GBP riskoff CONFIRMED (pro-cyclical), carry INVERTED across EUR/GBP/CAD/CHF (the
forward-premium puzzle). The score is scale-invariant (100·Σwf/Σ|w|) so only relative
weights matter. Caveat that remains: a Gaussian split-half can't price the carry crash
tail (LIMITATIONS.md) — verdicts are honest over-this-sample, not regime-proof.

**D-FX8. Phase 3 — full 9-pair board + value/rates factors.** All pairs go live,
archetype-grouped (Majors / Commodity-dollars / Haven-funders / EM) in an auto-fill grid,
plus a cross-pair carry & valuation table. Two new factors: (a) **value** = −z of the BIS
REER gap vs its 5y mean (overvalued → mean-reversion headwind); (b) **rates** = z of the
Δ(foreign 10y − US 10y) — relative monetary policy, the honest "rate differential" the
review demanded (NOT a fake free 2y). Both are monthly/lagged, so a `_lag_to_daily` helper
shifts each by its publication lag BEFORE ffill — the daily factor never sees a print
before release (test `test_value_lag_has_no_lookahead`). Calibration: value CONFIRMED for
EUR/AUD (REER reverts), INVERTED for JPY (the yen kept cheapening), rates mostly CONTEXT
(weak IC on coarse data) — and value tipped EUR/JPY/AUD over the ≥2-robust bar, so the
active majors now read RELIABLE. **USD/CNH** has no usable Yahoo history, so `load_price`
falls back to FRED `DEXCHUS` (onshore CNY) when the Yahoo series is < 300 rows — flagged as
an onshore proxy / managed regime. Deferred (Phase 3.5, honestly out-of-scope): MTF
(equity-preset fit unverified for FX) and the alerts/timeline engine (wants hourly data).

**D-FX9. Phase 3.5 — MTF (reused, honestly framed) + daily-only alerts.** MTF REUSES
`commodity_mtf.mtf_ladder`/`confluence_verdict` directly rather than forking: for FX the
macro-fusion (`driver_score`/`ts_momentum` polarity) gracefully zeroes out (no driver_score
column; calib keys differ), so the verdict collapses to the asset-agnostic D/3D/W/2W/ME
RSI/Stoch/MACD technical confluence — shipped as a TACTICAL overlay with an inline note
that it runs the equity cycle preset and isn't return-validated for FX (rather than build an
unvalidated FX cycle preset). Alerts (`engine/forex_alerts.py`) clone only the commodity
DAILY `_transitions` layer — NO intraday shock machine, since FX has no hourly feed here —
and add three FX-native event types: carry-inversion (foreign−US short rate crossing zero),
peg-zone approach (quote entering the MoF watch band), and dollar-smile regime shift (from
the `_dollar` master frame). Alerts are display-only (a timeline), NOT a conviction input —
adding an alert tilt would have forced a re-calibration for no measured edge. Events recompute
idempotently to `data/forex/alerts.jsonl`.

**D-FX10. Extras — measured FX cycle preset + the CNH offshore-onshore basis.** (1) Rather
than keep the MTF on the equity preset with a "not validated" caveat, I MEASURED FX cycle
lengths: ran `cycles.find_troughs` (the same detector `analyze` uses) over the G10 majors and
their weekly resample. Daily cycle ≈ 35 trading days (median; IQR 25-47 — close to equities'
36-42 but shorter and noisier); intermediate ≈ 34 weeks (vs equities' 16-26, nearly double).
Added `CYCLE_PRESETS["fx"] = {dc_band:(30,44), dc_early:11, ic_band_w:(26,42), tf3:"3B"}` and a
tiny `engine/forex_mtf.py` (runs `cycles.analyze(kind="fx")`, reuses `_long_timeframes` +
`confluence_verdict`). The note changes from "equity preset, unvalidated" to "FX-calibrated
preset" — but still flags that only the cycle LENGTHS are measured, not a forward edge.
(2) CNH offshore-onshore basis: `CNH=X` spot has no Yahoo history (1 row), but `CNH=F` (CME
offshore-CNH futures continuous) has 3,284 rows back to 2013 — so USD/CNH now prices off
`CNH=F` (replacing the `DEXCHUS` onshore fallback) and a new `cnh_basis` (`CNH=F − DEXCHUS`, bps;
+ = offshore yuan weaker = depreciation/outflow stress) shows on the tile with stress/inflow
alert events. Framed as a managed-regime STATE, not a signal (futures-roll + onshore-lag caveats
in LIMITATIONS). Measured basis range −168…+224 bps spans the real 2015/2016/2022 stress episodes.

## 2026-06-13 — Section 4 (HK) enrichment: native features ported from China/US

After a verified viability research pass (4-cluster workflow + web checks), added the
HK-native, free-data features the China/US dashboards have but HK lacked. Everything
below was confirmed to have a live free source before building.

**D82. ★ HKMA peg-funding collector — the most HK-unique signal.** `collectors/hkma.py`
pulls HKMA's keyless Open API (api.hkma.gov.hk daily-monetary-statistics): the
**Aggregate Balance** (banks' settlement liquidity — it mechanically SHRINKS when the
HKMA sells USD to defend the 7.85 weak-side peg, the real driver of HIBOR spikes/HSI
funding headwinds) + HIBOR (O/N, 1m) + TWI + base rate. 6,263 rows back to 2002. The
API caps page size at 100 → paginate by returned-count, not requested limit. Surfaced
as an HKMA peg-funding PANEL on hk.html. ALSO tested as a 4th dual-liquidity leg
(`hkma_funding`, agg-balance 63d direction) but the recalibration showed it **INVERTED
the overlay's measured edge** (contracting +0.78 > expanding +0.37 at 21d, vs the clean
monotone expanding +0.52 > contracting −0.41 without it — peg-defense draining coincided
with the 2022-25 recovery) → DEMOTED to panel-only (house rule: don't ship a leg that
hurts the measured edge). Live signal is real: Aggregate Balance drained ~70% YoY
(173.5k→53.9k) = active peg defense.

**D83. VHSI via Yahoo `^HSIL` (NOT `^VHSI`, which 404s).** HK's own VIX (HSI 30-day
implied vol, 2003→). Added to the Global Risk Overlay as a 7th factor `vhsi`
{sign:-1, weight:0.75} (config + FACTOR_LABELS) AND surfaced in the regime hero
(level + percentile). Makes the fear gauge HK-direct, not borrowed US VIX.

**D84. AH-premium COMPUTED basket (`engine/hk_ah.py`), not the official index.** The
official Hang Seng AH index (china_flows/ah_premium) source is dead (eastmoney HSAHP
ConnectionError; Sina gives 1 value/day). Instead compute per-pair from dual-listed
H-shares (hk_breadth cache, HKD) vs A-share twins (china_search/closes, CNY),
FX-adjusted by CNY/HKD = USDCNY/USDHKD. 12 pairs (config hk.ah_pairs), 726 days NOW,
per-pair decomposable. Label "computed basket" + lean on trend/percentile (absolute
level differs from the official index by share-class/float weighting). Live: +24% A-over-H,
4th percentile of 3y (premium compressed 20pp/yr — the H/HK value gap has closed).

**D85. Southbound flow panel + China backdrop reuse `china_internals` verbatim.** The
southbound Connect flow (the #1 HK flow) and the China credit-impulse/RRR backdrop
(HSI is ~75% China earnings) are rendered via `china_internals.southbound_flow()` /
`credit_tape()` / `pboc_policy()` — shared stores, read HK-side. The China backdrop is
a slim CONTEXT strip (monthly/lagged) so HK doesn't become a China-macro clone.

**D86. HK playbook/exposure-dial (`engine/hk_playbook.py`) — port of china_playbook,
NOT the US one.** Quad meaning + lifespan progress + next-quad odds + an exposure DIAL
whose reasons are HK-grounded: quad (Goldilocks +1/Stagflation −1, both split-half
stable), the global risk_state (Risk-on +1 — HK's measured headline edge), dual
liquidity, the HKD peg state, and southbound. Live posture: DEFENSIVE.

**D87. Time machine + sortable tables + range-selectors.** `hk_regime_timeline()`
emits hk_regime_timeline.json; the `timemachine.js` scrubber on hk.html rewinds the
regime core over ~20y (HK presets: 2015 rally / 2018 peak / 2020 COVID / 2021 HS-TECH
top). Added timemachine/charts/tablesort.js to ASSETS + Plotly CDN to the page; sector
board is now class="sortable"; the history charts gained 1M…All range-selectors.

SKIPPED (verified non-viable for HK): US recession/nowcasts (FRED US-only), equity
factor rankings (no free point-in-time HK fundamentals), commodity carry/EIA/FINRA.

## 2026-06-13 — Section 4: Hong Kong / Hang Seng dashboard

**D77. HK sectors = deep SYNTHETIC baskets of curated constituents, not sector
ETFs.** HK sector-ETF coverage is thin/short, but constituent stock history is deep
(most names 2000–2006→). So each HK "sector" is an equal-weight `basket_index` over
~6 curated large-caps (`config.yml hk.sectors`), RS-ranked vs `^HSI`. This gives
15–25y of history for *every* sector — richer than China's ~5y ETFs and a genuine
improvement over a literal ETF clone. Trade-off: it's a large-cap basket, not a
float-cap reconstruction of the HSCI industry indices (labeled on the page). Changes
if a free HK sector-index/holdings feed appears.

**D78. The HK regime stands on THREE legs; the global risk overlay is PRIMARY.**
Measured (memory `china-global-factors`): HK is ~2× more globally sensitive than the
Mainland. So the engine = quad (growth×inflation) + **dual liquidity** (PBoC China-M2
*and* Fed-via-peg = HKD distance + Stock-Connect southbound) + a **Global Risk
Overlay** (`engine/hk_global.py`: a DXY/VIX/SPY/copper-gold/USD-CNY/EEM composite +
the HKD peg, surfaced as the dashboard hero). Fundamentals reuse `china_macro` (HSI
earnings are ~75% China) — *no new macro scraper*. Global factors are read from the
existing `yahoo`/`china`/`hk` store groups; only `EEM` + `HKD=X` are newly collected.
The overlay is framed as a CONCURRENT risk STATE, not a forecast (lead-lag ~0).

**D79. Calibration result — HK quad ordering is split-half STABLE (unlike China).**
2000→2026, on `^HSI`: Goldilocks best (+1.3%/21d, 64% hit, positive both halves),
Stagflation worst (−0.9%/21d, negative both); expanding dual-liquidity > contracting
(monotone); and the KEY test — the global risk state differentiates HSI forward
returns monotonically (Risk-on +0.9%/21d 57% hit > Risk-off +0.3% > Neutral −0.2%).
All three legs ship with their measured record on the page; the cycle ladder stays a
drawdown/structure tool, never a standalone trigger (house rule). `^HSTECH` is not on
Yahoo → HS-TECH proxied by the CSOP ETF 3033.HK (2020→, drops out of deep pre-2020
classification via axis renormalization). Built as a full clone preserving the China
interface — engine modules `hk_inputs/hk_axes/hk_regime/hk_run/hk_global`, scripts
`build_hk/build_hk_library/calibrate_hk/hk_brief`, templates `hk*.j2`, wired into the
hub (🇭🇰 card + `_hk_state`), nav and daily/weekly CI. Browser-verified bilingual.

**D80. Adversarial review pass (3 dimensions, each finding independently verified) →
5 confirmed defects fixed.** (1) The "dual liquidity" SOUTHBOUND leg was reading the
DEAD `china_macro/connect_flow.southbound_cum` (100% NaN — a frozen legacy store), so
the overlay silently ran on 2 legs while config/report/docstrings advertised 3 →
repointed `hk_inputs` to the LIVE `china_connect/southbound` store (a parallel
session's repaired collector; `southbound_cum` = cumsum of daily net flow, 2017→).
The overlay is now genuinely 3-leg; recalibration kept it monotone and *widened* the
edge (expanding +0.5% vs contracting −0.4%/21d). (2) `hk_global.composite` had no
min-factor floor → a pre-1993 single/double-factor signal was mislabeled a confident
6-factor risk_state in the raw parquet; added `min_factors: 3` (→ `unknown` below it,
mirroring `score_axis.min_components`). (3) `hk_global.snapshot(asof)` truncated only
the composite, not the factor panel/peg → a latent look-ahead on any historical call;
now slices every factor series + the HKD series to `asof`. (4) peg weak-side threshold
hard-coded `*0 + 0.75`, ignoring `pressure_pct` → made it `1 - pressure_pct/100`. 3
findings correctly REFUTED (use_log heuristic = no numeric diff since all factors
positive; "monotonic" wording defensible; the peg fix double-reported). Live read
after fixes: Stagflation · neutral 3-leg liquidity · Neutral risk · HKD weak-side.

**D81. HK charting → TradingView Lightweight Charts on our own EOD data (not the
symbol widget).** The free `TradingView.widget()` symbol embed returns "This symbol
is only available on TradingView" for HKEX tickers — HKEX data is gated behind a TV
login, regardless of symbol format. Rather than shop for another live-quote provider
(CORS/rate-limit/key headaches, against the repo's zero-cost static-data philosophy),
the HK stock-analyzer (`hk_stock.html`) and the 12 sector drill-downs now draw an
adjusted-close + 50/200-DMA area chart from OUR nightly stored closes using the
open-source `lightweight-charts` lib (CDN, ~45KB). `build_hk_library.chart_series()`
adds a compact columnar `chart:{t,c}` (~2y/504 pts) to each `hkstockdata/*.json`;
sector pages embed the basket series via `s.chart_json`. MAs computed client-side.
Trade-off: EOD close only (no intraday/candles/volume — we don't store OHLC for HK
constituents). China/US/crypto keep the live TV widget (those exchanges aren't gated).

## 2026-06-13 — Entry-Quality score: a RISK-TIMING conviction, not an alpha leaderboard (macro)

**D76 (macro). Added `engine.cycles.entry_quality()` — a SIGNED −100..+100 "how good
is THIS moment to enter" score (buy-setup positive / sell-exit negative), surfaced as
a concise badge.** User asked for a multi-faceted buy-conviction score weighting time
(closeness to the momentum cross — about-to-cross → just-crossed, decaying as days
pass) and price (closeness to the bottom / a bottoming process arching up). Before
building, a 54k-sample backtest (110 deep-history names, ~14y, all regimes;
`scripts/research_conviction.py`, `research/ENTRY_QUALITY.md`) tested each lever in
isolation. **Findings:** (1) **proximity-to-the-cycle-low is the dominant, robust
lever — for RISK, not return**: forward-63d drawdown −7.0% at 0–3% above the low vs
−10.5% chasing (>25% above), monotone; (2) **freshness is real but mainly a staleness
penalty** (cross >20d old = worst band); (3) the visible "arch" (10d MA already rising)
*underperforms* — it correlates with being later/higher, so swing-low/curl is used as a
*knife-catch filter*, not a "wait for confirmation" gate; (4) **decisive & humbling:** a
buy-near-the-low score *anti-correlates* with forward RETURN (rank-corr −0.05..−0.14),
**even inside uptrends** — ordinary momentum/trend-persistence beats short-horizon
mean-reversion. So the score is honestly scoped as **entry-quality / risk-timing**, NOT
a return predictor (same lesson the ladder calibration already states). **Design:** sign
is ANCHORED to the ladder state (`_EQ_BULLISH`/`_EQ_BEARISH`) so it can never contradict
the displayed call (0/110 inconsistencies); magnitude =
`gate × (0.55+0.45·hold) × (0.52·proximity + 0.30·freshness + 0.18·momentum)`; cheap
point-in-time (MACD cross-age from the histogram, no backward walk). Wired into
`analyze()` only (not the calibration walk). **UI:** concise badge + one-line honest
tooltip ("entries near the pivot drew ~30% smaller drawdowns than chasers far above it —
risk control, NOT a return forecast") on the stock analyzer, sector ETF header + holding
rows, and the dashboard action board + standout chips; EN/ZH, both themes. **Calibration
of the shipped engine** (`data/regime/entry_quality_calibration.json`): buy-setup forward-63d
avg drawdown shrinks monotonically with quality (light −7.88% → solid −7.82% → strong
−7.13%) while return falls (4.74% → 3.07%) — confirming "safer, not higher-returning".
**Adversarially reviewed** (4-lens workflow, every finding skeptic-verified): 8 issues
fixed — proximity-curve discontinuity at the −3% pivot edge made continuous, regime-gate
`KeyError` made `.get`-safe, genuine RSI-0 no longer coerced to neutral, badge rounded
once so arrow/grade/number never disagree, COUNTERTREND-BOUNCE magnitude capped to the
"light" band (it's "NIMBLE ONLY"), and watch-state wording softened ("buy setting up" /
"exit setting up"). What would change it: a different universe/period (small-caps, mean-
reverting assets, bear-dominated) could shift the trend-vs-mean-reversion balance — re-run
the walk before trusting the bands elsewhere; if a future regime label appears, the gate
already degrades gracefully to neutral.

## 2026-06-13 — Vector allocation deep-dive page + alt-cycle ETH

**D-vec-ALLOC. New allocation deep-dive page (vector_allocation.html) with an
altcoin-cycle / ETH allocation overlay.** engine/alt_cycle.py: ethbtc_signal
(ETH/BTC ratio = the deep, calibratable alt proxy 2017→, 0.05 = deep BTC-season /
0.07 = alt-season confirmed), alt_season_score (0-100 blend of ETH/BTC pctile +
slope + dominance context; dominance/TOTAL from CoinGecko snapshot = context
only), and a BTC/ETH/alts/cash ALLOC_GRID keyed to cycle regime × alt-season
(rules: alts only when alt-season AND not bear; ETH leads alts; cash dominates
bear regardless — the "nimble only" message). scripts/build_vector
build_allocation_page() + chart_ethbtc() write site/vector_allocation.html (runs
in main(), wrapped so it can't break the main build); new
templates/vector_allocation.html.j2 (self-contained light theme, bilingual);
nav link added. config vector.alt_cycle. LIVE READ (coherent with the cycle/macro
read): ETH/BTC 0.0262 @13th pctile, falling, below 50w MA → deep BTC-season
(score 20); regime bear → **25 BTC / 5 ETH / 0 alts / 70 cash** — matches the
stock analyzer's cash-heavy "not an investment buy". Page also explains the 4 BTC
variants + backtest scorecards. Honest caveats surfaced: the % grid + 0.05/0.07
lines are judgment/convention (not optimized), ~1.5-2 ETH/BTC cycles = low
confidence, regime overlay not an entry timer.

**D-vec-LAYOUT (done, follow-up). Top-of-page restructure per the user's tidy ask.**
Block A (hero) is now LONG-TERM (left, larger via cols-2 1.15/.85) + the BTC
allocation card next to it — the allocation card gained a prominent "Full
allocation strategy — BTC · ETH · alts · cash →" link to vector_allocation.html.
New Block B "Mid term & Short term" is a cols-eq (1fr 1fr, new class, added to the
900px stack media query) of two equal peer cards in the SAME format: Mid term ·
Environment (moved out of the hero right rail) + Short term · Scenarios with Bear
& Bull FOLDED INTO ONE card (two halves split by a divider) so it mirrors the mid
card's footprint. Removed the old standalone two-card short-term section.
Verified: hero 645/477, mid&short 561/561 equal, stacks <900px, 0 console errors.

## 2026-06-13 — Vector MTF cycle-ladder + confluence verdict (reconcile bounce vs bigger picture)

**D-vec-MTF. The Vector now REUSES the macro cycle-ladder/MTF engine and resolves
the short-vs-long contradiction the user flagged.** Problem: the macro stock
analyzer called BTC a "counter-trend bounce inside a bearish bigger picture,
nimble only, not an investment buy", while the Vector showed mid/short-term
higher bull odds — with no technicals/momentum confluence to reconcile them. New
`engine/btc_mtf.py`: `mtf_ladder(close, high)` calls `engine.cycles.analyze(...,
kind="crypto")` (the SAME calibrated DCL/ICL + MTF engine the stock analyzer runs
— so they can't diverge) and EXTENDS the MTF to biweekly (`2W-MON`) + monthly
(`ME`) → D/3D/W/2W/ME. `confluence_verdict()` rolls timeframes into ONE read:
LONG (cycle regime + monthly + translation) is the governor, SHORT is the
calibrated ladder tape (authoritative — catches the bounce the raw MACD misses);
disagreement is NAMED ("Counter-trend bounce within a bearish bigger picture —
CAUTION, nimble only"), reusing the ladder's verbatim entry text so Vector ==
stock analyzer. Verified: current BTC → ladder COUNTERTREND BOUNCE / regime bear,
verdict CAUTION, short +1 / mid −1 / long −1, all 5 timeframe trends down.
Surfaced: a confluence-verdict banner in the hero + a "Multi-Timeframe Momentum &
Technicals" panel (cycle-ladder card + a 5-timeframe RSI/StochRSI/MACD/trend
table). Recomputed each build, persisted nowhere; {} on failure so it can't break
the build. NEXT: side-by-side short/mid layout tidy + allocation deep-dive page
(engine/alt_cycle.py: ETH/BTC ratio deep 2017→ = 0.0262 deep BTC-season; ETH/alts
/cash grid keyed to cycle×alt-season×risk).

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

**D15. The `us3m` alias is DGS3MO, and only DGS3MO.** Both `DGS3MO` (group
`curve`) and `DTB3` (group `fx_rates_short`) were aliased `us3m` until
2026-07-30. `engine/inputs.build_features` flattens every `fred.series` group
into one map, so the later group won and the whole constant-maturity curve —
`yield_curve.NODES`, the `spread_10y3m` fallback, the Engstrom-Sharpe NTFS leg,
`near_term_forward_spread`, the bonds curve chart — read its 3m point off a
*discount-basis* bill sitting ~13bp below the bond-equivalent yield every other
tenor is quoted on. The two constructions disagree on whether 3m10y is inverted
on 99 of the last 1260 sessions. DTB3 now carries `us3m_bill`.

Basis, not preference, decides this: DGS3MO is quoted on an investment
(bond-equivalent) basis and FRED's `T10Y3M` is exactly `DGS10 - DGS3MO`
(verified to 4e-16 on 11,142 of 11,144 shared dates), so the engine's fallback
now reconciles with the published spread it falls back from. The CP-bill funding
spread (`engine/conditions.py`) deliberately keeps the *bill*: the Fed quotes
commercial paper as annual discount yields, so DTB3 is the basis-matched leg
there and the CMT would shave ~13bp off the spread by convention alone.

No stored artifact needs a correction note. `slope_3m10y` itself was always
sourced from the published `T10Y3M` and was never wrong — what was wrong was the
displayed 3m *leg* (which did not subtract to the spread shown beside it) and
everything computed from the nodes directly. The pre-registered forward-test
trials read `data/fred/T10Y3M.parquet` directly and never touched the alias, so
no scored or gauntleted result is contaminated; the live `latest.json`
artifacts are nightly snapshots that self-heal on the next render.

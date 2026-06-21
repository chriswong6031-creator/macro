# Anticipation Engine + the Honest Alpha Truth

**Question (user, 2026-06-20):** how do we actually get alpha from the Top Individual Stocks
dashboard, and how do we reconcile the confirmation-lag problem — the engine signals too late
(after the bounce) or not at all — by making preemptive calls that forward just-about-to-sprout
buys to the top of the watchlist, *without* catching dead-cat bounces?

Built from a 4-agent research workflow (codebase anticipation inventory · honest alpha audit ·
external bottom-detection literature · data-feasibility) + first-hand reading + measurement.

## The honest alpha truth (measured, not assumed)
- **Residual (sector-neutral) momentum** is the only multiple-testing-survived edge, and it is
  marginal in the modern era: **2002-2026 IC 0.0065, DSR 0.75 (FAILS the 0.90 bar)**, and on PIT
  de-biased data the long-short Sharpe goes **negative (−0.29)**. The full-history glory (IC
  0.0268, t 3.7) was a pre-2000 + survivorship artifact.
- **Insider net-buy** survives BH-FDR (IC 0.029, q=0.10) but only in mid-caps; its long-only
  Sharpe dies under the deflated-Sharpe whole-program haircut. **SUE collapsed to IC 0.0005.**
- **The entry/timing machinery has NEGATIVE return correlation**: entry-quality rank-corr to
  forward return is **−0.05 to −0.14**; timing-only IC **−0.0046**; blending cycle timing into the
  setup score **HALVES** the alpha (63d IC 0.0231→0.0107). I.e. `E[return | early high-conviction
  entry] < E[return | extended momentum]`.
- **What IS forecastable / robust**: forward **drawdown / durability** (bottom_confidence held-rate
  **73% high vs 37% low**), and the **net-liquidity regime** (the one robust orthogonal edge:
  +6-8pp forward hit-rate on buy setups, survives split-half + ex-QE). Short-horizon single-name
  **direction is a measured coin-flip** (Brier skill ≈ 0).

**Conclusion:** anticipation is **NOT a credible incremental RETURN-alpha lever.** It is a
**drawdown-control / capital-efficiency lever** — it lets us own the SAME thin-edge momentum
leaders **earlier, at smaller size, with a tighter well-defined stop**, improving
return-PER-UNIT-OF-DRAWDOWN of an edge we already have. It must NEVER touch the cross-sectional
SELECTION rank (that demonstrably dilutes the edge) — only the ENTRY-axis / watchlist ordering.

## The anticipation ladder (theory: REFINED, not refuted)
PRIMED → TURNING → CONFIRMED is sound (matches the external evidence: confluence + hard vetos +
size-by-probability, and our own BOTTOM WATCH→TURN SIGNALED→FRESH BUY states). Three required
refinements: (1) pure ENTRY/ordering overlay, never selection; (2) **forward-to-top is gated on
the EXPANSION context first** (pre-qualified momentum leader in an accelerating theme) — the
expansion gate is the *real* dead-cat discriminator, more than the oscillator; (3) PRIMED size is
genuinely small (≤¼), justified by **payoff not probability** (buying first-leg optionality paid
for by a hard stop at the spring low), and **calibration must PROVE per-stage expectancy > 0 net
of the stop before any size is enabled — else PRIMED ships display-only.**

## bottom_formation_probability (new `engine/bottom_radar.py`)
A single calibrated 0-100 = logistic blend of oriented legs → a **FITTED score→P(holds) curve**
(not raw weights as probabilities). Legs (+ = more-likely-durable):
1. **Cycle timing band** (cycle_state dc_day in [36,42]) — close-only — w 0.18 (the ~70% timing prior).
2. **Bullish divergence GRADE A/B/C** (rsi_divergence + StochRSI; A = clear price LL + RSI HL +
   RSI oversald on D/W, reject hidden/continuation) — close-only — w 0.20 (strongest close-only,
   but ~40% FP standalone → it only ARMS).
3. **MTF turning confluence** (count `_tf_turning_up` D/3D/W/M, weekly heaviest) — close-only — w 0.18.
4. **Volatility contraction** (rolling-std pctile coiling; vol_squeeze for the 114) — close-only — w 0.12.
5. **RS holding/improving** (RS vs SPY+sector not making a lower low while price does) — close-only — w 0.12.
6. **Deterioration easing** (velocity.deterioration_z rolling off peak + rvar_vel turning down) — close-only — w 0.08.
7. **Capitulation/washout-resolving** (washout knife + reclaim of 10d; volume capitulation→dry-up→
   accumulation for the 114) — needs-volume for the strong form.
**HARD VETOS (dead-cat discriminators):** failed_cycle; HTF downtrend / weekly rolling over;
washout deep-below-200d + VIX-panic in a **put-absent** regime (master_switch_frame — measured
37% hold / −22% tail); no divergence; declining RS; deteriorating theme.

## Data tiers
- **Tier A (114 deep, OHLCV+volume):** full radar incl. capitulation/dry-up/accumulation.
- **Tier B (~1100 close-only):** price-only legs (divergence, vol-contraction, RS, timing, MTF) —
  structurally weaker (~15-20% higher FP), separate refit calibration, breadth cache <1yr so
  200dma/cycle legs unreliable → largely watchlist-ordering display-only.
- **Tier C (thin / sector ETFs):** ordering/context only.

## Backtest + CALIBRATION plan (the GO/NO-GO gate)
Labels per candidate-bottom event: `durable_bottom=1` if forward path rises ≥X% within N days
WITHOUT first hitting the proposed stop (spring low − buffer); grid X∈{5,8,12}%, N∈{21,42,63} to
find the early-vs-late crossover; log MAE + realized R. Metrics: (1) **per-STAGE expectancy** =
WinRate·AvgWin − LossRate·AvgLoss, net of stop + one-way cost (`validation.backtest_core`) — PRIMED
must be >0 to earn a starter size; (2) **calibration curve** — decile reliability, Brier +
reliability slope, near-diagonal (Kelly uses only the calibrated P); (3) **dead-cat control** —
vetoed events' hold-rate materially below non-vetoed (target ≤ Bulkowski 33%); (4)
**INCREMENTALITY** — does watchlist ordering improve return-per-drawdown (Calmar / return-at-equal-
MAE) of the EXISTING residual-momentum picks vs entering at CONFIRMED only (the real success test).
Rigor: walk-forward with **PURGED + EMBARGOED** folds, OOS-only, **deflated_sharpe** across the
whole X/N/weight grid (non-negotiable — this is exactly where overfitting hides).

## Phases (calibrate before any UI)
- **P0 — CALIBRATE FIRST (no UI):** `scripts/calibrate_bottom_radar.py` on the 114 Tier-A names.
  **GO/NO-GO: PRIMED expectancy > 0 net of stop AND calibration near-diagonal.** If NO-GO, the
  engine is **watchlist-ordering only** (no new size) — and that's the honest answer.
- **P1** `engine/bottom_radar.py` + `engine/expansion_gate.py` (Tier A): 7 legs + 6 vetos + fitted
  calibration → emit `bottom_formation_probability` + staged verdict + `watchlist_priority`. Run
  the incrementality test before shipping.
- **P2** UI (Tier A): PRIMED/TURNING/CONFIRMED chips + starter/half/full + "stop @ X"; sort the
  watchlist by `watchlist_priority`; selection rank untouched.
- **P3** Tier B graceful degrade (price-only, separate calibration); thin = ordering display-only.
- **P4** Tier C: flow.json expansion gate, sector-ETF radar via sector_read, index breadth-thrust/
  FTD ratifier as CONFIRMED context (~55% necessary-not-sufficient); optional Mastermind context lens.

## PHASE-0 CALIBRATION RESULT (109 deep names, 18,238 PIT events, durable = +8% in 42d before a swing-low stop)
| stage | durable% | E[R] | median MAE |
|---|---|---|---|
| primed | 49.6 | 0.199 | −4.81% |
| turning | 46.9 | 0.182 | −4.52% |
| confirmed | 49.7 | 0.158 | −3.95% |
| watch | 44.4 | 0.251 | −4.34% |
| blocked | 46.6 | 0.246 | −4.34% |
- **Raw-score calibration is FLAT** — durable% across raw-score deciles is 46-53% with no monotonic
  lift. The score does NOT rank durability.
- **PRIMED does NOT beat the base rate** — its E[R] 0.199 is BELOW blocked (0.246) and watch (0.251);
  the positive E[R] everywhere is just the survivor-leader base rate (an 8%-in-42d move happens
  ~half the time from any point on these names).
- **Earlier = MORE drawdown** — PRIMED MAE −4.81% is DEEPER than confirmed −3.95%. Waiting for
  confirmation REDUCES drawdown ~0.9pp at no cost to durability/expectancy — the opposite of the
  "be early to catch more" thesis, and consistent with the measured negative timing-return-corr.
- **Dead-cat control FAILED** — vetoed durable 46.6% vs non-vetoed 48.4% (~no separation). The
  **survivor-leader 114 rarely have real dead-cats** (they recover), so this universe cannot
  validate the vetos — which is precisely why the broader (volume-expanded) universe is the real test.

**VERDICT: NO-GO for SIZE.** Per the pre-committed decision #2, the anticipation tier ships
**watchlist-ordering / heads-up display-only** (no recommended size, no auto-buy). The honest finding
is that on the testable data, being early does not add return and slightly worsens drawdown.
**Next real test:** expand volume to the broader, non-survivor universe (decision #3) and re-calibrate
there — that universe actually contains dead-cats and is where the score+vetos could earn their keep;
also try a harder label (first-leg capture / +12% before −4%) and a logistic refit of the leg weights.
Until a re-calibration on that universe passes the STRICT gate (calibration lift ≥5pp + dead-cat
separation ≥5pp + PRIMED beats base by ≥0.03R), the tier stays ordering-only.

## BROAD-UNIVERSE RE-CALIBRATION (593 non-survivor small-caps, 17,694 events) — the real test
Volume captured for the breadth universe (`collectors/breadth.py` now caches volume/high/low;
`smallcap_breadth` = 603 names × 777 bars w/ volume). Re-ran on this NON-survivor universe:
| stage | durable% | E[R] | MAE |
|---|---|---|---|
| primed | 59.3 | 0.173 | −6.04% |
| watch | 55.1 | 0.122 | −6.53% |
| blocked | 53.3 | 0.259 | −6.39% |
- **The raw score now RANKS durability** (flat on survivors → here decile durable% rises
  51%→61%, ~10pp monotone lift, `calib_lift_ok=True`). REAL signal on the universe where
  dead-cats live — validates the broad-universe hypothesis.
- **PRIMED is more durable** than watch/blocked (59% vs 55%/53%).
- STILL NO-GO for size: PRIMED E[R] 0.173 < blocked 0.259 (`primed_beats_base=False`) and
  dead-cat separation only 3pp (`deadcat_ok=False`, need ≥5pp). TWO fixable causes:
  1. **Stop too tight** — the swing-low stop is hit on the whipsaw before +8% lands, so PRIMED's
     higher durability doesn't convert to R. FIX: ATR-based / wider stop, or measure first-leg
     capture instead of a fixed target/stop.
  2. **Expansion gate not yet in the loop** — the research's primary dead-cat discriminator
     (RS leadership + thematic acceleration) isn't applied. FIX: require positive expansion for
     PRIMED → PRIMED-in-a-leader vs PRIMED-in-a-broken-laggard should separate strongly.
- Also TODO: logistic refit of the leg weights to the durable label (vs hand-weights); fix the
  `turning`/`confirmed=0` artifact on the breadth walk (price-confirmation stages need the high
  series threaded through the cycle swing detection).
**NEXT ITERATION (concrete, the "tweak + backtest" loop): (a) ATR stop + first-leg-capture label,
(b) wire engine/expansion_gate.py into the PRIMED gate, (c) logistic refit — then re-run the strict
gate. The signal is real; these three are the path from NO-GO to a possible GO.**

## Honest limits
Close-only ceiling (~1100 names can't do volume/Wyckoff); NO measured return edge (may end
ordering-only); overfitting risk (DSR + purged folds mandatory); irreducible early-call FP (graded
divergence ~40% FP; 67% of sharp bounces make new lows — Bulkowski); regime dependence (works far
better Fed-put-present + index above trend); index-vs-name mapping gap (breadth-thrust confirmers
are index-level, no validated per-name analog).

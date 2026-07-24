# MWR — Mag-7 washout re-entry gate (pre-registration)

Status: REGISTERED (Fable, 2026-07-24). Operator-chartered, same day as the forced-call
postmortem: "the mag 7 board can be resurfaced when there's an actual washout in mag 7 …
2W STOCH RSI bullish cross under 20 is the best tool for MAGS … the 3D MACD-RSI called the
2024, 2025, 2026 bottoms exactly." This prereg is the lawful path mandated by
`DO_NOT_REBUILD.md` §2 (a Mag-7 leadership read returns only via prereg + gauntlet) —
operator conviction entering as a pre-registration, exactly as
`POSTMORTEM_20260723_MAG7_FORCED_CALL_BY_FABLE.md` R1 requires.

Engine: `engine/mag7_washout.py` (MWR-W0, background-only; `data/mag7_washout/`).
Phase-0 census: `reports/mag7_washout_scan.md` (regenerate:
`python3 scripts/research/mag7_washout_scan.py`). Sibling organ:
`engine/index_momentum.py` (IHM) — RSI-MACD washout_turn tags on the same EW carrier at
1D/2B/3B/W; MWR adds the 2W layer, member breadth, and the gate ladder.

## §0. Epistemic status — read this first

The constructions were chosen by the operator **after** seeing three bottoms on a
TradingView chart of MAGS (ETF history starts 2023). That is a post-hoc fit on n=3 with
selection bias. What phase-0 adds: the same constructions replayed on the house EW basket
2014→2026 (12.5y, 39 signals across families) — the operator's three instances reproduce,
AND the census exposes the failure regime chart-memory missed. Nothing here is validated;
the forward gates below are what can promote it. The word "washout" names three PRIOR
registry kills (§6) — the constructions are distinguished there explicitly.

## §1. Pinned constructions (changing any = prereg amendment, disclosed)

- **Series**: daily-rebalanced equal-weight basket of AAPL MSFT NVDA AMZN GOOGL META TSLA
  from `data/baskets/ohlcv` (house form — NOT MAGS; longer history, no inception
  truncation). Members individually for breadth.
- **Bars**: 2W = W-FRI closes at even index from the 2014 series start (**anchor A**,
  pinned — TV 2W bars are phase-sensitive; A matched the operator's chart K≈53 vs our
  55.1 on 2026-07-24; anchor-B values are emitted in the scan for robustness reads).
  3D = 3-trading-day block closes. 1W = W-FRI.
- **Stoch-RSI**: Wilder RSI(14) (`engine.technicals.rsi`), stoch window 14, K smooth 3,
  D smooth 3 (TV defaults).
- **RSI-MACD**: MACD(12,26,9) computed ON the RSI(14) series (TH_RSIMACD+ analog; the TV
  script's exact params are unpinned — operator to confirm; amendment allowed BEFORE any
  forward trigger is graded, never after).
- **S1 (primary)**: 2W Stoch-RSI K crosses above D with prior-bar K < 20.
- **S3 (precision arm)**: 3D RSI-MACD line crosses above signal while line < 0, valid
  only while the gate is ARMED (2W K < 20 within the last three 2W bars, or breadth).
- **Breadth**: count of members with 2W-A Stoch-RSI K < 20; ≥4/7 = cohort washout
  (operator's heterogeneity point: TSLA ≠ AAPL — a 1-2 name drag is not a cohort event).
- **States**: idle → washed_out (2W K<20 or breadth ≥4/7) → triggered (cross while
  armed). Triggers append once to `data/mag7_washout/triggers.jsonl` (nightly-only).

## §2. Phase-0 census results (descriptive, not a gauntlet pass)

S1 anchor-A, 2015→2026: **13 signals — 10 good, 3 bad** by the descriptive lens
(fwd63 > 0 and adverse > −10%). Median fwd63 ≈ +15.7% vs +8.9% all-days baseline.
Caught 2016-02, 2018-05, 2019-01, 2020-05, 2021×2, 2023-01, 2024-09, 2025-04, 2026-04.
**All three failures are the sustained 2022 bear** (2022-03: fwd63 −26.1%, adverse
−27.2%; 2022-06: −8.2%; 2022-11: −15.6% adverse first). S2 (1W) and S3 (3D) show the
same shape: superb at capitulation lows inside secular uptrends (S3 2025-04-24: +28.6%,
adverse 0; 2026-04-09: trough 7td prior), lethal in 2018-Q4/2022 downtrend rallies
(S3 2018-12-03: −18.2% adverse; 2022-03-18: −27.2%). The operator's three claimed calls
all reproduce in our stores.

**The open question phase-0 does NOT answer**: the 2022-class conditioner. Three failure
instances are not fitting material — any "bear-regime guard" tuned on them would be
overfit-on-the-overfit. Candidate conditioners for a phase-1 study (each needs its own
prereg discipline, multiplicity-counted): drawdown-from-ATH depth at signal; the house
risk band; weekly+monthly structure per postmortem rule R2 (note: the 2022 cluster IS
R2's evidence from the long side — these may unify into one higher-timeframe law).

## §3. What accrues now (display-tier, freely)

Nightly `snapshot()`: gate state + 2W K/D + 1W/3D RSI-MACD + member breadth into
`latest.json`; trigger events into `triggers.jsonl`. No surface, no consumer — the
artifact exists to build the forward record. Interactive sessions never advance the
ledger (house ledger law).

## §4. Uses and gates

- **Use-A — process gate (in force now).** Any proposal to resurface a Mag-7
  leadership/entry surface must cite a `triggers.jsonl` event within the preceding 63
  trading sessions, plus the DO_NOT_REBUILD §2 conditions (prereg + gauntlet + operator
  ruling). No trigger → no proposal. This is de-escalatory only (it can delay, never
  force) — promotable without a gauntlet as process law.
- **Use-B — timing signal (authority; NOT in force).** Claim to be tested: an S1/S3
  trigger marks a favorable Mag-7 entry. Grading per trigger (pre-stated): HIT =
  fwd63 > all-days baseline median AND adverse > −10%; FAIL = fwd63 < 0 OR adverse
  < −15%; else MIXED. Promotion needs: ≥8 graded forward triggers (history: ~2-3/yr)
  with ≥6 HIT and 0 catastrophic (adverse < −20%), OR a jointly-adjudicated read of
  forward triggers + the 39-signal census under one ruler. KILL: 2 consecutive forward
  FAILs, or any single adverse < −25% (the 2022-03 class) → construction returns here
  for redesign, not to a surface.

## §5. Non-goals

No auto-alerts, no page panel, no stance copy, no feed into rank/size/gate anywhere.
A future surface, if earned, starts as a Tier-2 receipt inside an existing Mag-7 data
display, not a board.

## §6. Distinctions from prior washout kills (blocklist compiler: these are different constructions)

- "Washout × turn (2W operator seed)" KILLED (#1747) — an entry-stack interaction
  feature on a different universe; not a cohort-scoped re-entry gate. The rhyme (operator
  seed, 2W, washout) is exactly why THIS one is pre-registered instead of shipped.
- "Buyback-floor washout (S11)" FALSIFIED — buyback-support mechanism, unrelated.
- "MCO thrust / MCO-oversold+MSI-washout bounce as radar legs" REJECT-KILLED
  (coincident-by-construction) — breadth-oscillator radar legs graded on coincidence.
  Acknowledged head-on: MWR's Use-B is graded on FORWARD returns with pre-stated
  hit/fail/kill rules, and Use-A is a gate, not a forecast.
- DO_NOT_REBUILD §2 forced-call row — this prereg is that row's mandated re-entry path.

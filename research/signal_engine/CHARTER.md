# Signal Engine — Charter & North Star

> **NEW SESSION: READ THIS FIRST, IN FULL, BEFORE WRITING ANY CODE OR RUNNING ANY BACKTEST.**
> This document exists because ~10 prior sessions went off the road by misunderstanding
> *what we are building and how to judge it*. It cost enormous effort to articulate. Do not
> re-derive it, do not "improve" it by reverting to the defaults below, and do not start
> running return backtests to "see if it works." The framing here is the product of long,
> hard reasoning with the project owner. Honor it.

---

## 0. TL;DR (the whole thing in six sentences)

1. We are building a **native signal engine** that produces **entry signals (primary) and, later, exit signals** for the **Mastermind/Opus brain to consume as inputs**, and for the owner to review visually.
2. The **signal engine** is distinct from the charting web-app (a separate, active workstream that it *feeds* — see §1); it is **NOT** a standalone autonomous algo and **NOT** a magic stock-picker. Two indicators cannot be an all-weather money printer — if they could, everyone would be rich.
3. Judge every signal on **risk / drawdown / entry-quality / shake-out avoidance — NEVER on "does it beat buy-and-hold return."** This is a **risk tool**, not a return-alpha engine. (Using the return yardstick is the #1 mistake that wasted prior sessions.)
4. Signals are **inputs the brain combines** with everything else + risk management. The bar for "useful" is **informative**, not "profitable on its own."
5. **Detect regime contemporaneously; never try to predict catalysts** (nobody foresaw the JNJ re-rate or the Tencent buybacks).
6. **Backtests are a diagnostic microscope and a regression test for improvements — not a verdict machine.** Fix the indicator's *mechanism* first; validate second; and the only verdict that counts is **out-of-sample / cross-sectional generalization.**

---

## 1. What we are building (and explicitly NOT building)

**Building:** a refined, mechanistic signal layer on top of the owner's flagship confluence
indicator. It computes, per ticker, high-quality **entry** signals (and eventually **exit**
signals), persists them as a structured **leaf the Mastermind brain reads**, and renders them
on the chart for human review. The ambition is **"the next best thing to a magic algo"**:
a tool good enough that the *brain + tool + owner judgment together* make better-timed,
lower-drawdown decisions than any of them alone.

**NOT building:**
- **This charter governs the SIGNAL ENGINE, not the charting product.** A TradingView-style
  charting web-app IS being built — but in a SEPARATE, ACTIVE workstream (another session, going
  live soon). Do **not** conflate the two, and do **not** assume the chart was abandoned. The signal
  engine is the *data/signal layer*; the charting app is the *visualization/app layer*. They
  **integrate** — the engine's buy/sell/cut markers and entry-quality signals are meant to render on
  that chart — but this document is about the signal logic and how to judge it, not the charting UI.
- A standalone autonomous quant strategy that must be profitable by itself.
- A system that predicts which stock will win, or predicts catalysts.
- An "all-weather" algo from two indicators. That is not realistic and is not the goal; a true
  near-autonomous trader is a *future* Mastermind-brain stage that needs many more signals.

---

## 2. The core mental model (the lens — internalize this)

**(a) It's a scalpel, not an oracle.** The owner (and later the brain) decides *what* and *when*
at a high level (which name, which regime). The engine's job is **execution quality**: time the
entries/exits to harvest the move, sidestep drawdowns during rotations, and avoid the opportunity
cost of dead money. Alpha comes from the *combination*, applied to the right vehicle — not from the
tool autonomously picking winners.

**(b) It is a RISK tool, not a return engine.** Our own research and this codebase's prior work
(`research/ENTRY_QUALITY.md`) independently concluded: these confluence signals do **not** produce
return-alpha, but they **do** reduce drawdown / tighten entries. That is the value, and it is
exactly what the owner wants (avoid the "one missed sell → 80% tumble"). **So evaluate on
drawdown, shake-out rate, entry efficiency, per-trade expectancy — not average return, and never
vs buy-and-hold.**

**(c) Win rate ≠ the indicator alone.** The owner reports ~80–90% WR trading this manually; the
mechanical take-every-signal version is ~52%. The gap is **discretion + selection + exits**. The
engine reproduces the *floor*; the owner's judgment (and the brain's) is the rest. Don't expect the
mechanical rule to hit 80–90%, and don't "fix" it until it does.

**(d) Detect, don't predict.** We cannot foresee idiosyncratic catalysts (JNJ's re-rate, Tencent's
buyback fakeouts). We can only **recognize a regime once it is underway** and adapt — accepting a
lag (~2 weeks at turns). Any design that needs to know the future is wrong by construction.

**(e) "Personality" is real, but capture it the right way.** Different tickers/asset classes
genuinely move differently (crypto ≠ equities; a low-vol grinder ≠ high-beta momo). Fitting to that
is legitimate **calibration** — *but only* when done via **universal rules that read a persistent
property** (volatility/ATR, efficiency), validated **cross-sectionally**. Fitting **per-ticker
parameters to past P&L** is **overfitting** (tiny data, many degrees of freedom) and will not
generalize. The label "calibration vs overfitting" is decided by **out-of-sample persistence**,
nothing else. Prefer asset-class and archetype/cluster adaptation (lots of data) over per-name tuning.

**(f) Backtests are a microscope, not a verdict.** Use them to (1) diagnose a *specific* failure on
the cases it occurs, and (2) regression-test that a fix helps without breaking what worked. Fix the
indicator's mechanism *first*; only then validate. The single gate that decides whether something
ships is **does it generalize to names/periods you did NOT tune on.** In-sample beauty is worthless.

---

## 3. How to evaluate (metrics + validation discipline)

- **Primary metric:** max drawdown reduction; secondarily shake-out rate, avg-loss size, entry
  efficiency, per-trade expectancy. **Not** total return, **not** beat-buy-and-hold.
- **Trade-level simulation** (enter on signal, exit on signal/cut, re-buy on reversal) — the way it's
  actually traded. **Not** fixed-horizon forward returns of a "state" (the flawed lens of the old
  `scripts/_bt_signals.py` study).
- **Generalization is the verdict:** test on the broad panel / held-out names; a result that only
  shows on the handful of names you examined is overfitting. Use percentiles not absolute thresholds;
  filtered (forward-only) not smoothed/Viterbi values; confirmed pivots only (repaint trap); keep the
  feature/threshold spec tiny (multiple-testing inflates in-sample winners).
- **Pre-commit the kill rule:** if an addition doesn't beat the simpler baseline on drawdown
  out-of-sample, **ship the simpler baseline.** (We did this and killed the regime router; see §5.)

---

## 4. OFF-THE-ROAD TRIPWIRES (if you catch yourself doing these, STOP)

- ❌ Running a "does the indicator beat buy-and-hold / make money on its own" backtest, then
  declaring it dead. → Wrong metric. It's a risk tool. (This is the exact loop that wasted ~10 sessions.)
- ❌ Treating it as a standalone autonomous algo that must be profitable alone. → It's a brain input.
- ❌ Using a standard price MACD(12,26,9). → The owner's indicator uses an **RSI-based MACD** and
  **stoch-of-RSI** (see §5). Standard MACD = unfaithful port = garbage results.
- ❌ Rebuilding a regime/exit-routing classifier. → Built, tested, **killed** — didn't generalize (§5).
- ❌ Hand-tuning per-ticker parameters to maximize past P&L, or tweaking until in-sample wins. → Overfitting.
- ❌ Designing anything that requires predicting catalysts or knowing the future. → Detect, don't predict.
- ❌ Concluding "it doesn't validate" before checking whether the *indicator itself* produces clean
  entries/exits. A bad signal can't be rescued by a backtest; fix the signal first.

---

## 5. What is already established (DO NOT re-derive — build on it)

All code lives in `research/signal_engine/`.

- **Faithful port — `confluence.py`.** The owner's flagship = `MACD STOCH RSI CONFLUENCE SIGNAL.pine`,
  run on the **3-day (3D)** timeframe. Exact math (NOT standard MACD):
  - RSI-MACD: `rsi = RSI(close,14); macd = EMA(rsi,14) − EMA(rsi,60); signal = EMA(macd,5)`.
  - StochRSI: `k = SMA(stoch(RSI(close,14),14), 3); d = SMA(k,3)`.
  - Confirmed BUY★/SELL★ = staged Stoch cross (B1) then RSI-MACD cross (B2) within a window + gates;
    plus a fast-reversal **cut-loss / re-buy** (the owner's anti-shakeout feature).
- **Data:** US deep-history OHLC in `data/stocks/*.parquet` (close/high/low/volume); Tencent `0700.HK`
  close-only in `site/hkstockdata/0700.HK.json`; BABA in `data/yahoo/BABA.parquet`.
- **The two known holes:** (1) false BUYS in a monthly bear / fakeout bounces (e.g., Tencent
  buyback-driven spikes); (2) over-SELLING up a steep low-amplitude grind (e.g., JNJ) and unable to
  re-buy. Diagnosed root cause: a mean-reversion oscillator applied blindly across all regimes.
- **✅ THE KEEPER — the buy-side filter** (`refined_buy()` in `diagnose_v2.py`): confluence cross
  **+ reclaim-and-hold + bearish-divergence veto + 200-day-MA as a confidence bar-raiser (NOT a hard
  gate).** It **GENERALIZED** (`test_buyfilter.py`): across all 110 US names — every one held out, since
  the filter was designed on Tencent/BABA — average max drawdown went **−23.7% → −15.5%, shallower on
  84% of names.** Honest caveat: it captures less total return (it's selective) and does **not** improve
  return-per-drawdown — i.e. it is a **risk overlay / brain input**, not standalone alpha. This is the
  piece worth promoting.
  > **2026-07-01 re-grade (W1c, audit #15).** Re-ran `test_buyfilter.py` on the current, larger
  > panel (now **219** names, all still held-out): average max drawdown **−24.0% → −14.5%, shallower
  > on 91% of names** — the headline SURVIVES and slightly strengthens on the bigger panel. The
  > original harness already used the honest **next-bar fill** (`c.iloc[i+1]` entry), so this number
  > was never contaminated by the same-bar bias. What W1c fixed was the *live* per-marker logger
  > (`engine/track_record.py`), which used a same-bar fill and thus rendered every per-marker MDD
  > ~0.6pp shallower than the validated convention — now corrected to next-bar (`engine/grading.py`),
  > with a `fwd_mdd_60_samebar` shadow column so the correction stays measurable.
- **❌ KILLED — the regime router** (`regime_router.py`): a classifier routing entry/exit by regime
  (efficiency + volatility axes). Looked great on ~7 hand-examined names; on 105 held-out names it was
  **no better than always-oscillator-exit and captured less.** Textbook regime-switching failure (the
  literature predicted it). **Do not rebuild it.** Lesson: **drawdown control comes from filtering bad
  ENTRIES, not from clever EXIT-routing.**
- **Regime research** (full literature sweep, verified): real primitives = Kaufman Efficiency Ratio,
  rolling-regression R², ATR%-percentile. Folklore/avoid = Hurst, Choppiness Index thresholds, and ADX
  as a filter. Regime overlays earn their keep on **drawdown, not return**.

---

## 6. Where we're going (roadmap)

1. **Promote the buy filter (the keeper) into production:** `engine/signal_quality.py` computing the
   confluence state + buy-filter verdict (TAKE/BLOCK + reason) per ticker; surface as a **display-only
   `latest["mtf_signals"]` leaf** the Mastermind brain reads (honestly labeled a *risk/entry-quality*
   signal); render buy/sell/cut markers on the chart via `chart.js`. Display-only, never auto-trade.
2. **Exit signals (future):** keep exits **simple** (a single fixed exit ≈ as good as the killed
   router). Improve exits only via cross-sectionally-validated changes; remember drawdown control is an
   entry-filtering problem first.
3. **Broaden carefully:** any new confluence / gate / archetype adaptation must pass the same
   generalization gate (held-out, drawdown metric, tiny spec) before it ships.
4. **Endgame:** these validated signals become high-quality *inputs* to the Mastermind brain, which —
   combined with its other engines and risk management — is where near-autonomous, well-timed,
   low-drawdown decisions can eventually emerge. The engine's job is to feed the brain clean signals,
   not to be the brain.

---

## 7. Signal → chart marker contract (the seam between the two workstreams)

The signal engine and the charting web-app meet here. **Both sides build to this contract** so signals
render on the chart without a later rewrite. The signal engine WRITES these; the charting app READS them.

**A) Per-ticker chart markers** — `site/signals/<TICKER>.json` (written by `scripts/build_signal_quality.py`):
```json
{
  "ticker": "AAPL", "asof": "2026-06-18", "tf": "3D",
  "state": "long-bias" | "short-bias" | "mixed",
  "above200": true, "weekly_bull": false,
  "markers": [
    {"date": "2025-07-16", "type": "buy",   "quality": "take" | "block" | "pending", "reason": "held confirmation"},
    {"date": "2025-09-30", "type": "sell"},
    {"date": "2026-01-16", "type": "cut"},
    {"date": "2026-03-12", "type": "rebuy", "quality": "take" | "block" | "pending", "reason": "counter-trend, no reclaim"}
  ]
}
```
- `type`: `buy` (confluence BUY★), `sell` (confluence SELL★), `cut` (fast-reversal cut-loss), `rebuy` (fast-reversal re-entry).
- `quality` (on `buy`/`rebuy` only): `take` = passed the validated buy-filter (reclaim-and-hold + no bearish-div + 200MA bar-raiser); `block` = filtered out; `pending` = the most recent 1–2 bars whose forward confirmation isn't in yet — **neither endorsed nor rejected** (NOT the same as `block`), and it may still resolve to `take` or `block` on the next build. **Chart should render `take` solid, `block` greyed/hollow, and `pending` dim/dashed** so the eye sees which entries the risk-filter endorsed vs which are still unconfirmed. A `pending` entry must NEVER be treated as a `take`.
- Suggested rendering: buy=▲ below bar (green), sell=▼ above bar (red), cut=✕ (orange), rebuy=▲ (lime). Dates are 3D bar dates.
- **Display-only side channels (separate date lists, NOT in the validated `markers` stream, never scored/auto-traded):**
  - `risk_flags`: dates of a close-below-EMA8(3D) trailing-trend breach (tail-risk protector); plus current `trail_stop`/`trail_breach` state.
  - `early_markers`: dates of the **2D-MACD pre-cross advance-warning** (the 3D StochRSI bottom-turn while the faster 2D RSI-MACD histogram is only rising). Validated as `m2d_s3d_early` — fires ~5 trading days BEFORE the confirmed `buy` and ~2% cheaper, but acting on it early is empirically WORSE entry quality (deeper drawdown; a secondary location guard could not fix it — see `CONFLUENCE_TUNING.md` §3/§5b). It is **advance-warning context only**: not every early marker is followed by a buy, it is suppressed on a confirmed-buy bar, and it must NEVER be rendered as a `buy`/`take` or fed to conviction. Suggested rendering: a faint/hollow pre-dot below the bar, visually distinct from the green `buy` ▲. `early_now` (brain leaf) = latest bar is an active advance-warning.

**B) Brain leaf** — `data/signal_archive/mtf_signals_latest.json` → loaded into `latest["mtf_signals"]` by `engine/run.py`:
```json
{"asof": "...", "tf": "3D", "universe": "us_deep",
 "signals": [{"ticker": "AAPL", "asof": "...", "state": "...", "above200": true, "weekly_bull": false,
              "trail_breach": false, "early_now": false,
              "last": {"date": "...", "type": "buy", "quality": "take", "reason": "..."}}]}
```
The brain consumes this as a **risk / entry-quality input** (honestly labeled — NOT alpha, per §2), never as an auto-trade trigger. `last.quality` may be `take`/`block`/`pending` (per §7A) — `pending` is an unconfirmed latest entry; treat it as non-endorsed, never as a `take`. `early_now`/`trail_breach` are display-only context flags (per the side-channel note above), never scored.

> Contract rule: if either workstream needs a new field, ADD it here first, then both sides build to it.
> Never let the chart and the engine invent divergent shapes.

---

*If a future session is about to contradict §2 or trip §4, stop and re-read this document. The owner
spent real effort getting these ideas across; the whole point of this charter is that it should only
have to happen once.*

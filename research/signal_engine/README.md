# Signal Engine — module guide

> **Read [`CHARTER.md`](CHARTER.md) first, in full.** This README is the *map*; the
> CHARTER is the *territory*. It explains what we are building (an entry/exit **signal
> layer the Mastermind brain consumes**, not a standalone algo), why we judge it on
> **drawdown — never on beating buy-and-hold**, and the tripwires (§4) that wasted ~10
> prior sessions. If anything here seems to contradict the CHARTER, the CHARTER wins.

This is a **risk / entry-quality** engine, not an alpha engine. The keeper — a buy-side
filter — cut average max drawdown **−23.7% → −15.5%, shallower on 84% of 110 held-out
US names** (`test_buyfilter.py`). Honest caveat (CHARTER §5): it is **selective — it
captures less total return and does *not* improve return-per-drawdown**; the value is the
shallower drawdown, nothing more. That number is the gold standard every change is held to.

---

## Map of the modules

**Canonical math (import these):**
- **`confluence.py`** — the faithful Python port of the owner's flagship
  `MACD STOCH RSI CONFLUENCE SIGNAL.pine`, run on the **3D** timeframe. RSI-MACD
  (`EMA(RSI14,14) − EMA(RSI14,60)`, signal `EMA(·,5)`) + StochRSI (`SMA(stoch(RSI14,14),3)`,
  `%D = SMA(%K,3)`) — **NOT** standard price MACD. `compute_signals(close)` returns the 3D
  signal frame (`CB`/`CS`/`revBuy`/`revSell` + gates) every other module builds on. **Do not
  change this math.**
- **`buy_filters.py`** — THE KEEPER, in one doctested place: `swing_highs`,
  `bearish_divergence`, `reclaim_and_hold`, `buy_filter_verdict(i, sig) → (take|block|pending,
  reason)`. Byte-for-byte equivalent to `engine/signal_quality.py` (verified: 1,427 verdicts,
  0 mismatches). New research and tests should import here.
- **`exit_rules.py`** — deliberately minimal: `fixed_exit` (confluence SELL\* / fast cut)
  plus a marked expansion point. Real exit work is a **separate session** — keep exits simple
  (CHARTER §6.2); a single fixed exit ≈ the killed router.

**Production (the leaf the brain reads — don't duplicate, extend):**
- **`engine/signal_quality.py`** — production twin: `signal_frame()` + `analyze()` → chart
  markers + `state`. **Source of truth for the buy-filter math** (CHARTER §4); keep
  `buy_filters.py` in lock-step with it.
- **`scripts/build_signal_quality.py`** — heavy compute; writes `site/signals/<T>.json`
  (chart markers, §7 contract) + `data/signal_archive/mtf_signals_latest.json`.
- **`engine/run.py`** — loads that snapshot into `latest["mtf_signals"]` (display-only).

**Microscopes & harnesses (diagnostic, not verdicts):**
- **`diagnose_tencent_baba.py`** — the 3 discriminators on Tencent/BABA (`load_tencent`,
  `load_baba`, `swing_points`, `divergence_at`). The keeper was *born* here.
- **`diagnose_v2.py`** — `refined_buy` (legacy research twin of the keeper; returns
  TAKE/BLOCK strings) + structural-stop exit study. Kept importable for in-flight sessions.
- **`diagnose_v3_exits.py` / `diagnose_v4_exits.py`**, **`tuning_harness.py` /
  `tuning_lead.py`** — exit + entry-timing research microscopes.
- **`test_buyfilter.py`** — the cross-sectional generalization test that produced the gold
  standard. **`test_buy_filters.py`** — synthetic unit tests pinning each gate.
- Notes: `NEW_BUY_SIGNALS.md`, `CONFLUENCE_TUNING.md`.

> **Sibling-session artifacts** — the concurrent exit / entry-timing / tuning sessions land
> these on the branch separately, so they **may not be present in every checkout**:
> `diagnose_v5_exits.py`, `walk_forward.py` (the purged/embargoed walk-forward harness),
> `tuning_gate.py`, `HARNESS_USAGE.md`, `SCHEMA.json`.

---

## Writing a new signal (the template)

1. **Read the CHARTER (§2 lens, §4 tripwires).** If your idea needs to predict a catalyst,
   route by regime, or be profitable on its own — stop now.
2. **Compute the mechanism as a pure function of the 3D `sig` frame** (the output of
   `confluence.compute_signals`). Leak-free only: forward-only (filtered, not smoothed/Viterbi)
   values, **confirmed pivots** (the last `w` bars are never pivots — no repaint), percentiles
   not absolute thresholds. Keep the spec **tiny** (every extra knob inflates in-sample winners).
   ```python
   def my_gate(i, sig, n):           # -> (bool|None, reason); None = pending (can't confirm yet)
       ...                           # read sig['close'], sig['macd'], sig['above200'], ...
   ```
3. **Diagnose first, on the cases it should change** (microscope). Fix the *mechanism* until
   the entries/exits are clean by eye. A bad signal can't be rescued by a backtest.
4. **Gate it** (next section). If — and only if — it beats the simpler baseline on **drawdown,
   out-of-sample**, promote it into `engine/signal_quality.py` and emit the marker (§7 contract).
   Otherwise ship the simpler baseline and write down why.

---

## The verdict gate

A signal ships **only** when all of these hold (this is the discipline the keeper passed):

- **Metric: max-drawdown reduction** (secondarily shake-out rate, avg-loss size, entry
  efficiency, per-trade expectancy). **Never** total return, **never** beat-buy-and-hold.
- **Cross-sectional generalization: % of HELD-OUT names improved.** The keeper was designed on
  Tencent/BABA and tested on all 110 US names it never saw → **84% shallower drawdown**, avg
  **−23.7% → −15.5%** (`test_buyfilter.py`). A result that only shows on the handful you examined
  is overfitting, full stop.
- **Trade-level simulation as actually traded** (enter on signal, exit on signal/cut, re-buy on
  reversal) — not fixed-horizon forward returns of a "state."
- **Walk-forward embargo:** purged + embargoed, net of costs, so the test period never leaks
  into the fit (the workstream's `walk_forward.py` harness — a sibling-session artifact above).
- **Pre-committed kill rule:** if the addition doesn't beat the simpler baseline out-of-sample,
  **ship the simpler baseline.** (We did exactly this and killed the regime router.)

---

## Killed ideas — do not rebuild

- **Regime router** (`regime_router.py`, removed). A classifier routing entry/exit by regime
  (efficiency + volatility axes) looked great on ~7 hand-picked names; on 105 held-out names it
  was **no better than a fixed oscillator exit and captured less** — textbook regime-switching
  failure (CHARTER §5). Lesson: **drawdown control comes from filtering bad ENTRIES, not clever
  EXIT-routing.** The file was deleted as the killed surface; the history is in the CHARTER.
- **Per-ticker parameter tuning to past P&L.** Tiny data, many degrees of freedom → does not
  generalize. Legitimate calibration reads a *persistent property* (ATR/efficiency) via a
  **universal rule validated cross-sectionally** — prefer asset-class/archetype adaptation
  (lots of data) over per-name fits.
- **Return / beat-buy-and-hold backtests as a verdict.** The #1 mistake that burned ~10
  sessions. Backtests are a **microscope and a regression test**, not a verdict machine. This is
  a risk tool; judge it on drawdown.

---

## Decision tree

```
New signal idea
│
├─ Judging it on return / "beats buy-and-hold"?            → STOP. Wrong metric (§3,§4). Use drawdown.
├─ Needs to predict a catalyst / know the future?          → STOP. Detect, don't predict (§2d).
├─ Per-ticker params fit to past P&L?                      → STOP. Overfitting (§2e). Universal rule on a persistent property.
├─ A regime / exit-routing classifier?                     → STOP. Killed (§5). Filter ENTRIES instead.
│
└─ Reduces DRAWDOWN on HELD-OUT names, tiny spec,
   survives the walk-forward embargo?
        ├─ YES → ship as a DISPLAY-ONLY leaf (engine/signal_quality.py + §7 marker),
        │         honestly labelled a risk/entry-quality input — never auto-trade.
        └─ NO  → ship the simpler baseline; record why it was killed here.
```

*The engine's job is to feed the brain clean, honestly-labelled signals — not to be the brain.*

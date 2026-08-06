# The MCD miss — why no surface said "washout turn," and the name-grain lane that fixes it

**Date:** 2026-08-05 (operator escalation: MCD weekly MACD-RSI bullish cross from washout
depth + 2.11% close; our surfaces showed Oracle "Sell — Jul 23", Research Desk
"Bounce unconfirmed — wait, as of Jul 31 · 6d", Prophet absent.)

**Verdict up front:** the operator's read is confirmed by our own canonical math, and the
miss decomposes into FOUR independent failures — each alone would have hidden MCD.
The engines could have seen it; nothing the operator looks at said so
(the same detection-without-narration failure class as the 2026-08 precious-metals miss).

All numbers below are frozen from a reproduction run on 2026-08-05 using
`engine.canon` / `engine.mtf_upturn` / `engine.confluence_tiers` verbatim
(sim: fresh tape = committed stores through 07-31 + yahoo 08-03/08-04 + 08-05 close 274.00).

---

## F1 — The data plane ended 2026-07-31 (P0 outage; repair lane owns it)

Every committed US price store ends **2026-07-31** (`data/stocks/MCD.parquet`,
`data/baskets/ohlcv/MCD.parquet`; yahoo side-store ends 08-04). Known chain:
massive_stock_day publish outage since ~07-28 + the #4311 collect crash (healed #4534)
+ nightly 08-05 run concluded FAILURE → board snapshots and Research Desk verdicts
frozen at 07-31. The card's "as of Jul 31 · 6d" is this outage, honestly disclosed.
**Nothing this program builds fixes F1** — but F2–F4 are all still true with fresh data.

## F2 — The house golden oracle FIRED at weekly grain — and nothing consumes weekly grain

Running the canon confluence math (`canon.rsi_macd`, `canon.stoch_rsi_kd`, the CB gate
composition from `canon.confluence_signals`) on **weekly** bars:

* Weekly RSI-MACD bullish cross printed on the **2026-07-31 completed bar**
  (line −8.416 vs signal −8.436) — visible in the data the last good nightly had.
* The full weekly-grid **CB (confluence buy) fired on 2026-07-31** — cross + StochRSI
  bull cross + from-oversold + RSI-regime all true. Close 270.64.
* On the fresh tape the cross strengthens: line −7.88 / signal −8.25 / hist +0.37 —
  matching the Terminal chart pixel-for-pixel (its "MACD-RSI −7.88 / signal −8.25").
* Depth receipt: the line sits at the **6.3rd percentile of MCD's entire weekly history
  (1968→)** at the cross — a genuine washout-depth turn, not a mid-range wobble.

Consumers of this weekly-grain read today: **none.** Prophet's cascade runs the 3D grid;
`mtf_upturn`'s weekly leg watches standard **price** MACD-vs-zero (reads only
"approaching" today); no organ reads the house RSI-MACD at weekly grain per name.

## F3 — The washout-turn cohort has no name-grain lane (the named standing gap)

* `mtf_upturn` on the FRESH tape: **state NONE, k=0** (legs: d_macd F, d3 F,
  w_macd "approaching", w2 F). Construction watches a different indicator family.
* Prophet cascade on the FRESH tape: **eligible=False, tier=None, ticks=14** — the 3D
  master cross expired (that was the 06-11 CB → 07-06 board admission the operator
  remembers; entry 282.21, still "Below entry" in the record). Median cascade window is
  3 sessions; a name that bases for a month falls off with no re-arm at washout depth —
  **Door R excludes below-200dMA by design** (trend-intact re-arm only, #1747 Amendment-3).
* Basket/theme washout-turn lanes shipped 2026-08-05 (W-A bottoming watch, W-D tape
  group) are **basket-grain** — MCD is a single name in `us_sector_discretionary`;
  no basket-grain lens will ever name it.

This is exactly [[trailing-rs-floors-are-blind-to-washout-turns]]: the 1W-up/1M-deep-down
shape ranks last on every trailing lens at the moment it matters, and the shipped answer
is a **labeled watch lane**, not loosened floors.

## F4 — The surfaces latch stale one-sided verdicts with no counter-read

The Terminal card stacks three trailing reads: Oracle "Sell — Jul 23" (last manifest
verdict), Research Desk "Bounce — turn not confirmed; wait" (`entry_signal.bounce_wait`,
the honest regime-gate demotion — frozen at 07-31 by F1), TREND "DOWNTREND weeks–months".
All three are individually defensible; stacked with no washout-turn dual-read, the page
reads "dead short" while the house's own weekly CB fires from the 6th percentile.
FT-R1 dual-read chips are the shipped pattern for exactly this.

## Own-history context (display receipt, not a promotion claim)

Weekly RSI-MACD bullish crosses with line ≤ bottom-12% of own history, MCD 1968→2026:
**n=31 · 13w median +5.5% (67% win) · 26w median +7.9% (70% win)**. Not uniform —
1973–74/2000/2002 crosses failed inside secular bears. Windows, not certainties.
(Scored washout→turn constructions remain NULL/killed per Oracle P8 P-W1/S-W3 and
Entry-stack Amendment-3 #1747 — this lane ships display-tier watch vocabulary only.)

## The build (this PR)

`engine/washout_turn.py` — per-name weekly washout-turn watch organ (US, display tier,
zero authority):

* **Trigger** (canon math on completed W-FRI bars only): weekly RSI-MACD bullish cross
  within the last 2 completed bars with line depth ≤ 15th percentile of the name's own
  weekly history → `WASHOUT_TURN`. Depth ≤ P15 + hist rising 2 bars (no cross yet)
  → `TURN_WATCH`.
* **Persistence**: state holds while the turn develops — drops when hist re-flips
  negative (1-bar hysteresis) or the line crosses 0 (graduated; trend lenses own it).
* **Receipts** per name: cross date, depth percentile, line/sig/hist, weekly StochRSI,
  weekly-CB coincidence, drawdown vs 52w high, own-history base rates (n, 13w/26w
  medians + win rates, min n=8), data_through.
* **Surfaces**: chip on the stock page beside the entry-timing verdict (the dual-read),
  `site/stockdata/washout_turn.json` cohort artifact, Discord turn-events source.
* **Ledger**: `data/washout_turn/ledger.jsonl`, nightly-gated, transitions only —
  forward-gradeable at 21d/63d excess-vs-SPY from state entry (63d is the basing-class
  horizon per W8 S-COIL). Promotion only via pre-registered gate, earliest after a
  matured cohort exists.

With this lane live, MCD reads: `WASHOUT_TURN since 2026-07-31 · depth 6th pctile ·
weekly confluence buy · own-history n=31, 13w median +5.5%` — on the Friday-night
render, from data the system already had.

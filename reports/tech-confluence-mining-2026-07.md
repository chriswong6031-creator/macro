# Tech Lab combo miner — first full mining run (2026-07-12)

Display-tier descriptive research. Survivor mega-cap universe (225 names), signal
fires from the canonical `engine.tech_catalog` (TLT-R3), horizons on the
descriptive ladder {10, 21, 42, 63}d (TLT-R6). Found by search — leads, not proof;
nothing here is a gauntlet verdict or an allocation input.

## What was built

`engine/tech_confluence.py` mines 2–4-signal combinations ("combos") across two
timeframes:

- **Legs** = (signal, timeframe). All 56 eligible catalog signals run on daily
  bars; trend/context families additionally run on completed W-FRI weekly bars
  (97 legs total). Weekly values reach a daily bar only after the week closes —
  no lookahead (unit-tested).
- **Combo fire** = the rising edge of the AND of leg activities (states must be
  on; events must have fired within 5 daily / 4 weekly bars). Entry next close.
- **Stats discipline**: win rates collapse each calendar month to one
  observation (fires cluster; effective N ≈ months — house law), train/test
  split at 2018-01-01, ranking = Wilson lower bound of test-half month-collapsed
  WR minus the random-entry baseline at 21d. Combos need ≥40 fires, ≥24 months,
  ≥10 tickers, ≥15 test fires, ≥12 test months to be reported.
- **Search**: exhaustive pairs → apriori/beam triples/quads;
  92,368 candidates evaluated; identical-fire-set duplicates dropped (446);
  top lists diversified (single-leg swaps of a higher-ranked combo omitted).

Full run ≈ 8 min on the Mac Studio; nightly in `tech_lab_offrender` (off the
render budget). Artifact: `site/factordata/tech_confluence.json` (~530 KB).

## Headline findings

Baselines (random entry, month-collapsed, 2018+): long 21d ≈ **5.7 wins per 10**;
short 21d ≈ **4.3 per 10**.

1. **Cross-timeframe alignment dominates.** 132 of the top 150 long combos and
   68 of the top 75 short combos mix weekly and daily legs. The recurring
   winning shape is *weekly trend context + daily trigger cluster* — exactly the
   "slow signals belong on the higher timeframe" hypothesis. Pure-daily
   variants of the same ideas rank lower.
2. **Trend-alignment stacks, not dip-buying, top the long board.** The best
   long combos are multi-cross agreement moments (e.g. weekly Ichimoku bull
   cross + daily 21/100 golden cross + price reclaiming the 21-day line +
   riding the upper band): 21d test WR ≈ 8.3–9.3 per 10 vs 5.7 baseline
   (+26 to +37pp), with 130/150 holding up in both the pre-2018 and 2018+
   halves. Entry counts are honest but modest: ~0.8–6.6 entries/yr across the
   whole universe per combo — these are rare alignment moments, best used as a
   watch-list generator, and the board says so.
3. **Washout-dip combos exist but rank below trend stacks.** e.g. weekly MA
   reclaim pair + short-term uptrend + lower-band reclaim: 21d test ≈ 9.2/10,
   ~1.1 entries/yr. The pure mean-reversion families only clear the gates when
   a trend/backdrop leg gates them.
4. **The short side has the larger *relative* edges.** Weekly RSI-overheated +
   daily death-cross/ribbon breakdown stacks: 21d test ≈ 7.7–8.9 per 10 (win =
   price fell) vs 4.3 baseline — +33 to +46pp, 49/75 era-consistent. Bear
   entries cluster in 2018Q4/2020/2022; month-collapse keeps single crashes
   from inflating them, but regime concentration remains the honest caveat.
5. **21d is the sweet spot.** The top combos' edges peak at the 21-day horizon
   (e.g. L0001: +10.7pp @10d, +36.5pp @21d, +20.9pp @42d, +18.8pp @63d) —
   alignment thrust decays after a month.

## Caveats (printed, not hidden)

- Survivor mega-caps only; up-market concentration bias on the long side.
- Mined from 92k candidates: even with train/test + Wilson-LB ranking +
  month-collapse, selection bias survives; treat as leads for confluence
  reading, not tradeable proof. The UI stance line and per-combo receipts carry
  this disclosure.
- Test-half months for the tightest 4-leg stacks run 12–30 — wide intervals;
  the Wilson-LB ranking is the guard, and raw n is printed per row.
- Non-consistent ("recent era only") combos are retained and badged, not
  hidden — a 2018+ edge with no pre-2018 counterpart may be regime-specific.

## Where it surfaces

`site/tech_lab.html` → **Combos** tab: leaderboard (bullish/bearish), per-combo
detail (4-horizon table, matches-now, chart with real entry markers), and a
custom builder (any 2–4 legs → live matches from the nightly `now` map +
backtest record when the exact combo cleared the gates; all 1,014 long +
890 short qualifying pairs included). Screener right rail shows the top
backtested combos with a live match today.

## Follow-ups (not built, candidates only)

- Regime-conditional stats (SPX above/below 200dma splits) per combo.
- Per-ticker per-signal WR summaries in `tech_events/` for the Signal Lab
  detail pane (currently chart + fire markers for any ticker, pooled stats).
- Exit-side study: time-exit vs MA-loss exit for the top stacks (reversion
  ruler per the Oracle reframe would be the wrong ruler here — these are
  continuation entries).

# Sector Confluence Engine — timing sector entries/exits off 3-day crossovers (measured)

> **STATUS: engine BUILT + VALIDATED (2026-06-23).** `engine/sector_signals.py`
> + `scripts/_bt_sector_confluence*.py` + `tests/test_sector_signals.py`. Replaces
> the "leaders & avoids" scorecard and the heat board as the **primary** sector
> buy/sell board. The verdict is a *qualified yes*: a confluence of MACD + StochRSI
> crossovers on the 3-day chart, daily-triggered and 200-day-gated, has a modest,
> era-robust, correctly-signed edge. It is a **risk / rotation-timing** map, NOT an
> alpha machine and NOT a return forecast.

## The problem (user)

> The "Regime-approved sectors" scorecard just shows what is extended on the weekly
> MACD/RSI/StochRSI and calls it *confirmed leadership*. If we buy the confirmed
> leadership we lose money as institutions rotate out and dump on us. XLI shows
> StochRSI 100 last week / 91 this week after a 3% drop, still flagged a leader.
> The heat board shows Industrials/Materials as "Uptrend" yet they topped a week
> ago — **no topping signal was given**. We should map sector entries off a
> confluence of bottoming signals from MACD, RSI and StochRSI on the 3-Day chart:
> a MACD crossover or a StochRSI bullish cross back up over 20 confirms a bottom; a
> MACD/StochRSI bearish cross confirms a top. One indicator = partial; both = a
> BUY/SELL. The "setup" is the days leading up to a potential crossover.

## Why the old tools mis-time entries

* **`engine.playbook` "leaders/avoid" + heat** — a weekly-oscillator + 200-day-
  smoothed RS rotation lens. The heat tooltip itself admits the hottest band (70+)
  *underperformed* over the following 3 months. It confirms turns weeks late and has
  **no top trigger** — "leading" fires identically on a healthy trend and on a
  distribution top.

## Method (no look-ahead)

`scripts/_bt_sector_confluence*.py`, the 11 SPDR sector ETFs, full Yahoo history
(most 1998-2026; XLRE 2015, XLC 2018), benchmark SPY. Indicators reuse
`engine.cycles.macd_parts` / `stoch_rsi` and `engine.technicals.rsi` so the research
and the live engine share one definition. Signals are read on a **3-business-day**
resample (the user's "3-day chart") and on the **daily**; each signal is evaluated at
the close of its bar and forward returns start from that close (point-in-time). Cross
flags match `engine.cycles._tf_state`:

* `macd_up/dn` = histogram >0/<0 having crossed zero within the last 3 bars
* `stoch_up/dn` = StochRSI ≥20 from <20 / ≤80 from >80 within the last 3 bars
* `setup_up/dn` = histogram rising/falling 3 bars while still on the wrong side of zero
* daily `stoch_roll`/`rsi_roll` = the early topping tell (momentum turning down out of
  overbought) — fires *before* the confirmed cross

## What the data said (forward 63-day excess vs SPY, pooled)

| Signal | exc63 | hit | n | takeaway |
|---|---|---|---|---|
| BUY = daily fresh-up **AND** 3D fresh-up, above 200d, RSI<65 | **+0.87%** | 53% | 1864 | MTF agreement ~2× the edge of 3D-alone |
| SETUP-up (approaching the cross) + above 200d | **+0.65..0.73%** | 54% | ~2000 | the *days before* the cross carry the most edge |
| 3D fresh-up alone, above 200d | +0.42% | 52% | 3709 | |
| SETUP-up **below** the 200-day (knife) | **−0.18%** | — | 1211 | same setup on a knife *loses* → 200-day gate is mandatory |
| EXTENDED alone (RSI>70 or StochRSI>80) | −0.12..−0.33% | ~49% | 7323 | never a fresh buy; "late" |
| TOP = EXTENDED **+ confirmed 3D down-cross** | **−1.34%** | 39% | 218 | the flagship "don't chase leadership" flag |
| Down-cross from a **non-extended** state | +0.29% | — | — | a bounce trap — NOT a sell; topping must be gated on "extended" |
| Cross-sectional BUY-side − AVOID-side | **+0.83% / 63d** | — | — | monotone (buy +0.42 / rest −0.04 / avoid −0.41) |

**Robustness** (`_bt_sector_confluence3.py`): the AVOID edge is negative in **all 4
eras** (1999-07, 2008-15, 2016-20, 2021-26) and 6/7 sectors; the BUY edge is positive
in 3/4 eras and 7/11 sectors. The earliest signal (SETUP, approaching) beats the
confirmed full cross — by the time both indicators have crossed the move is mature.

## The decisive refinement: daily-trigger + 3-day-confirm

Checked against the user's own live calls (`_bt_sector_confluence_now.py` / `5.py`):
a pure-3-day engine **lagged** and read XLI "neutral" and XLB even "buy" while the
user (watching the daily) saw a clear roll-over. The user's evidence — "3% drop",
"6 straight days", "stoch 100→91" — is **daily** action. So the production engine is
**multi-timeframe**: the daily is the early trigger/warning, the 3-day is the
confirmation. A BUY needs both to agree (+0.87%); a top fires on **extended +
momentum stalling** (daily roll), escalating to TOPPING (extended + 3D rolling) and
SELL (extended + confirmed 3D down-cross). This is exactly how `engine/cycles.py`
already treats single names.

## The engine (`engine/sector_signals.py`)

State machine over the latest daily + 3-day flags, 200-day-gated (verbatim states in
the module): `BUY` (full MTF confluence) · `BUY_PARTIAL` · `SETUP_BUY` · `NEUTRAL` ·
`EXTENDED` (late) · `TOPPING` · `SELL` · `BELOW_TREND` (knife; hardened by the index
Fed-put gate). `calibrate()` re-measures each state's forward-63d excess weekly-
sampled across history so the UI shows **measured** base rates (the static
`STATE_BASE_RATES` defaults equal that calibration). Honest nuance the calibration
surfaces: the negative avoid-edge concentrates in TOPPING/SELL — a pure EXTENDED
(overbought but still rising) is ~market-neutral at 63d, i.e. *"late, don't chase"*
rather than *"short it"*.

## Honest ceiling (carried onto the UI)

Edges are modest and hit-rates ~50-54% — the edge lives in magnitude/tail and in
**avoidance**, not in a high win-rate. This times rotation and flags distribution; it
does not call exact tops/bottoms and is not alpha. The single most valuable, most
robust output is the **EXTENDED/TOPPING/SELL** flag that stops us chasing the
"confirmed leadership" the old board sold us.

"""Reusable WALK-FORWARD validation harness for the signal engine — STOP-AWARE.

> READ research/signal_engine/CHARTER.md FIRST (§2 lens, §3 metrics, §4 tripwires).

WHAT THIS JUDGES — AND WHY IT IS DIFFERENT FROM THE OLD HARNESS
--------------------------------------------------------------
The owner trades **with a stop-loss** (default ≤ −5%). A *bad entry* is therefore one
that gets **faked out and stopped out** before the move it was trying to catch. So the
ONE metric that matters for entry quality is the **stop-out / shake-out rate**: the
fraction of taken entries that hit the stop. LOWER is better.

This is a deliberate correction. A PRIOR harness scored the **loose-hold max drawdown**
of a position carried with NO stop (the "−23.7% → −15.5% max-DD" headline). That number
conflates *entry quality* with *exit policy* — it is the drawdown of a strategy nobody
runs. Two positions can have the same loose-hold max-DD yet wildly different stop-out
behaviour, and the owner only ever experiences the stopped version. So we simulate every
trade **AS TRADED, WITH THE STOP**:

    enter on the (leak-free) signal  ->  exit at the ≤ stop_pct stop  OR  the validated
    exit signal (confluence SELL* / fast-reversal cut), whichever comes first  ->  re-buy
    on the next reversal signal.

and we judge on stop-out rate + the realised per-trade loss distribution UNDER that stop
+ entry efficiency. Total return AND loose-hold max-DD are carried only as clearly
labelled CONTEXT fields and can never enter a verdict (charter §4 tripwire #1).

THE SIX COMPONENTS THE TASK ASKS FOR
------------------------------------
  1. PURGED / EMBARGOED WALK-FORWARD.  Expanding train [0:Ti], test [Ti:Ti+test_len],
     rolled by `step`, with a `purge` gap before each test and an `embargo` after it, so
     no test bar's information bleeds into a neighbouring split.  (`make_windows`.)

  2. LEAK-FREE MULTI-TIMEFRAME BAR -> DAILY MAPPING.  A 3D (or N-day) bar's close is only
     KNOWN on the last daily date inside its bin — `resample("NB")` labels the bin's LEFT
     edge, which can sit 2-4 calendar days BEFORE that close.  Every TF bar is mapped to
     its true known-date and fired on the first daily bar STRICTLY AFTER it.  The whole
     trade simulation then runs on the DAILY grid so a ≤ stop_pct stop is checked every
     day (a 3D-only sim would step over intraday shake-outs).  (`tf_bars`, `to_daily`,
     `_daily_events_after`.)

  3. AS-TRADED-WITH-STOP METRICS.  stop_out_rate (PRIMARY), realised-loss distribution
     under the stop, avg loss size, entry efficiency, per-trade expectancy, win rate.
     NOT total return, NOT loose-hold max-DD.  (`simulate_trades`, `trade_metrics`.)

  4. CROSS-SECTIONAL AGGREGATOR.  Percentile stats of the metric across 110+ names AND
     the **% of names improved vs baseline** — never just a pooled mean.  (`cross_section`.)

  5. OVERFIT GUARD.  In-sample vs out-of-sample decay flag + the pre-committed KILL RULE:
     reject unless >= 70% of HELD-OUT names improve on the stop-based metric, deflated for
     the number of trials searched.  (`overfit_guard`, `kill_rule`.)

  6. PER-TRIAL JSON LOGS to data/signal_archive/wf_<run_id>.json.  (`_write_log`.)

Interface (the contract):

    walk_forward(signal_fn, panel, cfg, baseline_fn=None, ...) -> {by_ticker, pooled, overfit_flags}

  * signal_fn / baseline_fn : a SIGNAL CALLABLE.  daily close -> daily buy events.
      - simple:  fn(close, high=None, low=None) -> pd.Series[bool]   (daily BUY events;
                 paired with the default confluence exit + the panel's daily high/low.)
      - rich:    fn(close, high=None, low=None) -> pd.DataFrame with daily-indexed
                 boolean 'buy' and (optional) 'exit' columns.  Use this to supply your
                 own exit; close/high/low for the stop ALWAYS come from `panel` so the
                 stop is checked on real daily bars.
  * panel : {ticker: DataFrame with 'close' (and ideally 'high','low' for an intraday
            stop; close-only names fall back to a close-based stop).}
  * cfg   : {train_len, test_len, step, purge, embargo, stop_pct=-0.05}.  Window lengths
            are in DAILY bars (the sim grid); stop_pct is the stop (negative).

Gold-standard self-test:  `python3 walk_forward.py --gold`
  Runs the validated buy-filter (engine/signal_quality / diagnose_v2.refined_buy) against
  raw confluence buys on data/stocks/ and confirms the FILTER REDUCES THE STOP-OUT RATE
  (the honest, as-traded restatement of the old loose-hold "−23.7 -> −15.5" headline).
"""
from __future__ import annotations

import sys
import json
import glob
import hashlib
import argparse
import warnings
import logging
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd

# same-dir siblings (confluence.py, diagnose_v2.py, ...) — mirror test_buyfilter's import path
sys.path.insert(0, str(Path(__file__).resolve().parent))

if __name__ == "__main__":
    # CLI-only silencers.  logging.disable() is PROCESS-GLOBAL state: at module level it
    # leaked out of `import walk_forward` (tests/test_trial_registration_lint.py) and muted
    # every logger for the rest of the pytest run — breaking any later test that asserts on
    # emitted log records (e.g. test_whitehouse_w5's qledger import-guard tests).
    warnings.filterwarnings("ignore")
    logging.disable(logging.CRITICAL)

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "stocks"
ARCHIVE = ROOT / "data" / "signal_archive"

# Entries are counted from here.  Long window on purpose: stop-out rate is a per-trade
# rate and needs many trades per name for the cross-sectional %-improved read to mean
# anything (charter §3: generalisation is the verdict, not a handful of names).
SINCE = pd.Timestamp("2010-01-01")
STOP_PCT = -0.05          # the owner's default stop; a trade hitting this = a stop-out
EFF_WIN = 21              # daily bars forward used to score entry efficiency (~1 month)
MIN_DECAY_TRADES = 3      # a name must trade >= this in BOTH is & oos to enter the decay pop

# Default purged/embargoed walk-forward config, in DAILY bars (the simulation grid).
DEFAULT_CFG = {"train_len": 378, "test_len": 189, "step": 189,
               "purge": 5, "embargo": 5, "stop_pct": STOP_PCT}

# --- metric direction + verdict policy (mechanical enforcement of charter §3/§4) -----
# A "verdict" metric decides SHIP/REJECT.  TOTAL RETURN and BOTH max-DD flavours are BANNED
# from any verdict: return is the §4 tripwire #1; the max-DD metrics are what this harness
# exists to retire (they conflate entry quality with exit policy — see the module header).
_CONTEXT_ONLY = {"captured", "cap", "strat_max_dd", "nostop_max_dd", "mae_med", "mfe_med"}
# higher value == better (avg_loss/worst_loss/expectancy are SIGNED; "less negative" == higher).
_HIGHER_BETTER = {"avg_loss", "worst_loss", "expectancy", "win_rate"}
# lower value == better.
_LOWER_BETTER = {"stop_out_rate", "entry_eff", "n_trades", "frac_below_stop"}


def _check_verdict_metric(metric: str) -> None:
    """Refuse to render a verdict on a context-only metric — makes the §4 tripwire (and
    the max-DD mistake this harness corrects) un-trippable by construction."""
    if metric in _CONTEXT_ONLY:
        raise ValueError(
            f"metric={metric!r} is CONTEXT-ONLY (total return / max-DD): banned from any "
            "verdict.  This is an AS-TRADED-WITH-STOP risk harness — judge on "
            "stop_out_rate / avg_loss / expectancy / win_rate / entry_eff.")


def _is_better(treat: float, base: float, metric: str) -> bool:
    """Direction-aware 'did treatment improve on baseline' for `metric` (charter §3)."""
    if metric in _HIGHER_BETTER:
        return treat > base
    if metric in _LOWER_BETTER:
        return treat < base
    raise ValueError(f"unknown metric {metric!r}: add it to _HIGHER_BETTER/_LOWER_BETTER")


# Lock the metric directions so a future edit can't silently invert a verdict (the audit
# caught worst_loss mis-signed here): less-negative loss is better; lower stop-out is better.
assert _is_better(-5.0, -6.0, "worst_loss"), "worst_loss: less-negative must be better"
assert _is_better(-3.0, -4.0, "avg_loss"), "avg_loss: less-negative must be better"
assert _is_better(38.0, 39.0, "stop_out_rate"), "stop_out_rate: lower must be better"
assert not _is_better(40.0, 39.0, "stop_out_rate"), "stop_out_rate: higher must be worse"


# ============================================================ cross-grid utils (comp. 2)
# Leak-free TF -> daily mapping.  A TF bar is labelled by its bin's LEFT edge but is only
# KNOWN on the last daily date in the bin; we map by that known date and fire on the first
# daily bar STRICTLY AFTER it.
def tf_bars(daily: pd.Series, n: int):
    """resample to n-business-day bars (faithful to confluence.py) and return, per bar,
    the true daily date its close became known."""
    if n == 1:
        return daily.copy(), pd.Series(daily.index, index=daily.index)
    s = daily.resample(f"{n}B").last().dropna()
    known = (daily.resample(f"{n}B")
                  .apply(lambda x: x.dropna().index.max())
                  .reindex(s.index).dropna())
    s = s.reindex(known.index)
    return s, pd.Series(pd.to_datetime(known.values), index=known.index)


def _daily_events_after(known_dates, daily_index: pd.DatetimeIndex) -> pd.Series:
    """Place a True on the first daily bar STRICTLY AFTER each known date (leak-free).
    `known_dates` is an iterable of timestamps (the true known-dates of the TF bars whose
    signal is True).  Strictly-after (searchsorted side='right') because a known date is
    itself a real daily close — you can only act on the NEXT bar, never that same close."""
    out = pd.Series(False, index=daily_index)
    kd = pd.DatetimeIndex(pd.to_datetime(list(known_dates))).dropna()
    if len(kd) == 0:
        return out
    for p in daily_index.searchsorted(kd, side="right"):
        if 0 <= p < len(daily_index):
            out.iloc[p] = True
    return out


def to_daily(tf_series: pd.Series, known: pd.Series, daily_index: pd.DatetimeIndex,
             how: str = "event") -> pd.Series:
    """Map a TF-bar boolean/value series onto the daily index by its KNOWN date.
    how='event' -> True only on the first daily bar STRICTLY AFTER each known date where
    the TF value is True (the leak-free entry/exit fill).  how='ffill' -> state held from
    the bar after its known date until the next (for regime flags)."""
    kd = pd.Series(tf_series.to_numpy(), index=pd.to_datetime(known.to_numpy()))
    kd = kd[~kd.index.duplicated(keep="last")].sort_index()
    if how == "ffill":
        shifted = pd.Series(kd.to_numpy(), index=kd.index)
        # advance each known date to the first daily bar strictly after it, then ffill
        pos = daily_index.searchsorted(shifted.index, side="right")
        out = pd.Series(np.nan, index=daily_index, dtype="float64")
        for p, v in zip(pos, shifted.to_numpy()):
            if 0 <= p < len(daily_index):
                out.iloc[p] = float(v)
        return out.ffill()
    true_known = kd.index[kd.to_numpy().astype(bool)]
    return _daily_events_after(true_known, daily_index)


# ============================================================ core trade sim (comp. 3)
def simulate_trades(close: np.ndarray, high: np.ndarray | None, low: np.ndarray | None,
                    buy: np.ndarray, exit_: np.ndarray, *, stop_pct: float = STOP_PCT,
                    start_idx: int = 0, eff_win: int = EFF_WIN, close_open: bool = False,
                    no_stop: bool = False):
    """AS-TRADED-WITH-STOP daily simulation (the substrate for every metric).

    Long/flat exactly as the owner trades it:
      * FLAT  : enter on a daily buy event (fill at that bar's CLOSE — the event already
                sits on the first daily bar after the signal's known date, so the close is
                leak-free).  Stop checking begins the NEXT bar.
      * LONG  : each bar, FIRST test the stop intraday (low <= stop level, or close if no
                low) -> a STOP-OUT, filled at the stop level (or the bar high on a
                gap-through); ELSE test the exit event (confluence SELL*/cut) -> exit at the
                bar CLOSE.  Re-buy on the next event.

    A stop hit takes precedence over a same-bar exit signal (the stop is intraday, the
    signal is end-of-bar).  `no_stop=True` disables the stop entirely (hold to the signal
    exit) — used to compute the CONTEXT-ONLY no-stop loose-hold drawdown that the stop-out
    metric exists to debunk.  An open position at series end is booked only if close_open.

    Returns (curve, trades).  The equity `curve` (length n) is reconstructed from the booked
    trades so it realises at each entry/exit FILL with no one-bar mark-to-market drift; it
    feeds the CONTEXT-ONLY drawdown/return, never the stop-out verdict (which is read from
    `trades`).  Each trade dict carries: entry_i, exit_i, ret, exit_reason
    ('stop'|'signal'|'eod'), mae, mfe, entry_eff (0=bought the local low .. 1=the local high
    over eff_win bars), below_stop (realised return worse than stop_pct -> a gap-through).
    """
    n = len(close)
    has_lo = low is not None
    has_hi = high is not None
    pos = 0
    ep = None            # entry price
    e_i = None           # entry bar index
    trades: list[dict] = []
    for i in range(n - 1):
        if pos == 0:
            if i < start_idx:
                continue
            if buy[i]:
                pos, e_i, ep = 1, i, float(close[i])
            continue
        if i <= e_i:                                    # never act on the entry bar itself
            continue
        # --- LONG: stop first (intraday), then the exit signal (end of bar) ---
        if not no_stop:
            stop_lvl = ep * (1.0 + stop_pct)
            bar_low = float(low[i]) if has_lo else float(close[i])
            if has_lo and np.isnan(bar_low):            # missing low -> fall back to close
                bar_low = float(close[i])
            if bar_low <= stop_lvl:                      # STOP-OUT
                # Normal intraday touch fills at the stop level; a bar that GAPS THROUGH
                # (whole range below the stop, high < stop) can only fill below it -> use the
                # bar high, so the realised loss can exceed the stop (gap risk -> below_stop).
                bar_high = float(high[i]) if has_hi else float(close[i])
                if has_hi and np.isnan(bar_high):
                    bar_high = float(close[i])
                xp = min(stop_lvl, bar_high)
                trades.append(_mk_trade(e_i, i, ep, xp, "stop", close, high, low,
                                        stop_pct, eff_win))
                pos = 0
                continue
        if exit_[i]:                                     # validated SELL*/cut -> exit at close
            trades.append(_mk_trade(e_i, i, ep, float(close[i]), "signal", close, high, low,
                                    stop_pct, eff_win))
            pos = 0
    if close_open and pos == 1 and e_i is not None:
        trades.append(_mk_trade(e_i, n - 1, ep, float(close[-1]), "eod", close, high, low,
                                stop_pct, eff_win))
    return _equity_curve(close, trades), trades


def _equity_curve(close: np.ndarray, trades: list[dict]) -> np.ndarray:
    """Reconstruct the long/flat equity curve (length n) from booked trades: flat (constant)
    out of the market, marked-to-market on closes while long, REALISED at each entry/exit
    fill.  Decoupled from the trade state machine so it can't drift the booked trades, and
    correct at both trade boundaries (the inline running-product version credited the
    entry-bar move late and the exit-bar move one bar too far)."""
    n = len(close)
    curve = np.ones(n)
    eq, last = 1.0, 0
    for t in trades:
        e, x = t["entry_i"], t["exit_i"]
        ep = float(close[e])
        xp = ep * (1.0 + t["ret"])                       # exit FILL (stop level / close / gap)
        curve[last:e + 1] = eq                           # out of market up to & incl. entry bar
        for j in range(e + 1, x):                        # intra-trade mark-to-market on closes
            curve[j] = eq * float(close[j]) / ep
        eq *= xp / ep                                    # realise at the exit fill
        curve[x] = eq
        last = x
    curve[last:] = eq
    return curve


def _mk_trade(e_i, x_i, ep, xp, reason, close, high, low, stop_pct, eff_win) -> dict:
    """Build one trade record incl. excursions and entry efficiency."""
    has_lo, has_hi = low is not None, high is not None
    seg_lo = (low if has_lo else close)[e_i + 1:x_i + 1]
    seg_hi = (high if has_hi else close)[e_i + 1:x_i + 1]
    mae = (float(np.min(seg_lo)) / ep - 1.0) if len(seg_lo) else 0.0
    mfe = (float(np.max(seg_hi)) / ep - 1.0) if len(seg_hi) else 0.0
    # entry efficiency over a FORWARD window from entry (post-hoc diagnostic, not a trade
    # input): where in [local low, local high] did the entry land?  0 = bought the low.
    w_lo = (low if has_lo else close)[e_i:min(e_i + eff_win, len(close))]
    w_hi = (high if has_hi else close)[e_i:min(e_i + eff_win, len(close))]
    lo_v, hi_v = (float(np.min(w_lo)), float(np.max(w_hi))) if len(w_lo) else (ep, ep)
    eff = ((ep - lo_v) / (hi_v - lo_v)) if hi_v > lo_v else 0.0
    ret = xp / ep - 1.0
    return {"entry_i": int(e_i), "exit_i": int(x_i), "ret": ret, "exit_reason": reason,
            "mae": mae, "mfe": mfe, "entry_eff": float(np.clip(eff, 0.0, 1.0)),
            "below_stop": bool(ret < stop_pct - 1e-9)}


def trade_metrics(curve: np.ndarray, trades: list[dict], stop_pct: float = STOP_PCT,
                  nostop_curve: np.ndarray | None = None) -> dict:
    """The AS-TRADED-WITH-STOP metrics suite (component 3).

    PRIMARY  : stop_out_rate (% of trades exited by the stop — lower is better).
    risk     : avg_loss, worst_loss, frac_below_stop (gap-through rate), entry_eff.
    quality  : expectancy, win_rate.
    CONTEXT  : captured (total compounded return), strat_max_dd (the WITH-STOP strategy
               equity drawdown) and nostop_max_dd (the RETIRED no-stop loose-hold drawdown —
               the metric whose "win" the stop-out rate debunks).  All labelled, never a
               verdict (charter §4 / module header)."""
    if len(curve):
        strat_dd = float((curve / np.maximum.accumulate(curve) - 1.0).min())
        cap = float(curve[-1] - 1.0)
    else:
        strat_dd, cap = 0.0, 0.0
    nostop_dd = strat_dd
    if nostop_curve is not None and len(nostop_curve):
        nostop_dd = float((nostop_curve / np.maximum.accumulate(nostop_curve) - 1.0).min())
    base = {"n_trades": 0, "stop_out_rate": 0.0, "avg_loss": 0.0, "worst_loss": 0.0,
            "frac_below_stop": 0.0, "entry_eff": 0.0, "expectancy": 0.0, "win_rate": 0.0,
            "mae_med": 0.0, "mfe_med": 0.0, "captured": 100 * cap,
            "strat_max_dd": 100 * strat_dd, "nostop_max_dd": 100 * nostop_dd}
    if not trades:
        return base
    r = np.array([t["ret"] for t in trades])
    stops = np.array([t["exit_reason"] == "stop" for t in trades])
    losses = r[r < 0]
    base.update({
        "n_trades": len(trades),
        "stop_out_rate": 100 * float(stops.mean()),                       # PRIMARY
        "avg_loss": 100 * float(losses.mean()) if len(losses) else 0.0,
        "worst_loss": 100 * float(r.min()),
        "frac_below_stop": 100 * float(np.mean([t["below_stop"] for t in trades])),  # gap risk
        "entry_eff": float(np.median([t["entry_eff"] for t in trades])),
        "expectancy": 100 * float(r.mean()),
        "win_rate": 100 * float((r > 0).mean()),
        "mae_med": 100 * float(np.median([t["mae"] for t in trades])),
        "mfe_med": 100 * float(np.median([t["mfe"] for t in trades])),
    })
    return base


# ============================================================ signal resolution
def default_confluence_exit(daily: pd.Series) -> pd.Series:
    """Shared daily exit for SIMPLE-mode callables: the baseline 3D oscillator SELL/cut
    (exit_rules.fixed_exit == CS|revSell), mapped to the daily grid by known date so the
    ONLY thing that differs between variants is ENTRY timing."""
    from confluence import compute_signals
    sig = compute_signals(daily)
    if sig.empty:
        return pd.Series(False, index=daily.index)
    s3 = sig["close"]
    _, kn = tf_bars(daily, 3)
    kn = kn.reindex(s3.index).dropna()
    ev = (sig["CS"] | sig["revSell"]).reindex(kn.index).fillna(False)
    return to_daily(ev, kn, daily.index, "event")


def _resolve(result, daily: pd.Series, exit_default: pd.Series):
    """Normalise a signal-callable return into daily (buy, exit) boolean series on the
    daily index.  close/high/low for the stop ALWAYS come from the panel (see walk_forward),
    never from the callable — so the stop is always checked on real daily bars."""
    if isinstance(result, pd.DataFrame):
        if "buy" not in result.columns:
            raise ValueError("rich signal frame must have a 'buy' column")
        buy = result["buy"].reindex(daily.index).fillna(False).astype(bool)
        if "exit" in result.columns:
            ex = result["exit"].reindex(daily.index).fillna(False).astype(bool)
        else:
            ex = exit_default.reindex(daily.index).fillna(False).astype(bool)
        return buy, ex
    buy = result.reindex(daily.index).fillna(False).astype(bool)
    return buy, exit_default.reindex(daily.index).fillna(False).astype(bool)


def _start_index(idx: pd.DatetimeIndex, since: pd.Timestamp) -> int:
    return int((idx < since).sum())


# ============================================================ walk-forward splits (comp. 1)
def make_windows(n: int, start_idx: int, cfg: dict):
    """Purged/embargoed expanding walk-forward splits over DAILY bar indices.
    Returns (train_lo, train_hi, test_lo, test_hi): train=[0:Ti-purge], test=[Ti:Ti+test_len];
    consecutive test blocks separated by `embargo` (step floored at test_len+embargo so test
    windows never overlap).

    The signals here are GLOBALLY-COMPUTED CAUSAL functions (every indicator at bar t uses
    only data <= t), so a value is identical computed on [0:t] or the full series — nothing
    is re-fit per window.  OOS-ness comes from (a) causal indicators, (b) entries MASKED to
    test-window bars, (c) leak-free fills.  train_lo/train_hi are the documented seam for a
    FUTURE fitted-signal refit hook; the non-fitted path does not consume them.  Do NOT add
    a per-ticker P&L-fitted refit here (charter §4)."""
    train_len = int(cfg.get("train_len", DEFAULT_CFG["train_len"]))
    test_len = int(cfg.get("test_len", DEFAULT_CFG["test_len"]))
    step = int(cfg.get("step", DEFAULT_CFG["step"]))
    purge = int(cfg.get("purge", DEFAULT_CFG["purge"]))
    embargo = int(cfg.get("embargo", DEFAULT_CFG["embargo"]))
    windows = []
    ti = max(start_idx + train_len, train_len)
    while ti + 1 < n:
        test_lo, test_hi = ti, min(ti + test_len, n)
        if test_hi - test_lo < 10:                 # too small to be meaningful (daily bars)
            break
        windows.append((0, max(ti - purge, 0), test_lo, test_hi))
        ti += max(step, test_len + embargo)        # embargo gap between test blocks
    return windows


# ============================================================ per-ticker eval
def _eval_one(close, high, low, buy, ex, start_idx, cfg):
    """Evaluate one (close, buy, exit) frame on the daily grid: full-sample, walk-forward
    OOS (stitched over purged/embargoed test windows), and the in-sample burn-in region.
    OOS/IS are each ONE continuous sim with ENTRIES masked to the relevant bars (exits
    always allowed) so a trade spanning a boundary is booked exactly once."""
    c = close.to_numpy(float)
    h = high.to_numpy(float) if high is not None else None
    lo = low.to_numpy(float) if low is not None else None
    b = buy.to_numpy(bool)
    x = ex.to_numpy(bool)
    n = len(c)
    sp = float(cfg.get("stop_pct", STOP_PCT))

    def _view(mask):
        bb = b if mask is None else (b & mask)
        curve, trades = simulate_trades(c, h, lo, bb, x, stop_pct=sp, start_idx=start_idx)
        ns_curve, _ = simulate_trades(c, h, lo, bb, x, stop_pct=sp, start_idx=start_idx,
                                      no_stop=True)            # context-only loose-hold DD
        return trade_metrics(curve, trades, sp, nostop_curve=ns_curve)

    windows = make_windows(n, start_idx, cfg)
    first_test_lo = windows[0][2] if windows else n
    oos_mask = np.zeros(n, bool)
    for (_t0, _t1, te_lo, te_hi) in windows:
        oos_mask[te_lo:te_hi] = True
    is_mask = np.zeros(n, bool)
    is_mask[start_idx:first_test_lo] = True
    return {"full": _view(None), "oos": _view(oos_mask), "is": _view(is_mask),
            "n_windows": len(windows)}


# ============================================================ cross-section (comp. 4)
_PCTS = (10, 25, 50, 75, 90)
_CONTEXT_MEANS = ("stop_out_rate", "avg_loss", "worst_loss", "frac_below_stop",
                  "entry_eff", "expectancy", "win_rate", "n_trades",
                  "captured", "strat_max_dd", "nostop_max_dd")


def cross_section(by_ticker: dict, view: str, metric: str = "stop_out_rate") -> dict:
    """Percentile distribution of `metric` for treatment and baseline + the % of names
    improved (metric-aware direction).  A name only counts toward frac_improved if BOTH
    arms actually traded in this view (n_trades>0) — a zero-trade name has a degenerate
    0.0 metric that is neither an improvement nor a regression."""
    _check_verdict_metric(metric)
    treat, base, names, improved, comparable = [], [], [], 0, 0
    for t, d in by_ticker.items():
        tv = d["treat"][view].get(metric)
        if tv is None:
            continue
        treat.append(tv)
        names.append(t)
        if d.get("base") is not None:
            bv = d["base"][view].get(metric)
            if bv is None:
                continue
            if d["treat"][view]["n_trades"] > 0 and d["base"][view]["n_trades"] > 0:
                comparable += 1
                improved += int(_is_better(tv, bv, metric))
            base.append(bv)

    def _pcts(a):
        a = np.asarray(a, float)
        if not len(a):
            return {}
        return {f"p{p}": float(np.percentile(a, p)) for p in _PCTS} | {"mean": float(a.mean())}

    out = {"view": view, "metric": metric, "n_names": len(treat), "treat": _pcts(treat),
           "treat_means": {k: float(np.mean([by_ticker[nm]["treat"][view].get(k, 0.0)
                                             for nm in names])) for k in _CONTEXT_MEANS}}
    if base:
        out["base"] = _pcts(base)
        out["base_means"] = {k: float(np.mean([by_ticker[nm]["base"][view].get(k, 0.0)
                                               for nm in names if by_ticker[nm].get("base")]))
                             for k in _CONTEXT_MEANS}
        out["n_comparable"] = comparable
        out["frac_improved"] = float(improved / comparable) if comparable else None
    return out


# ============================================================ overfit guard (comp. 5)

# W1d: a harness that never REGISTERED its multiple-testing budget still swept many configs
# in development. Defaulting n_trials to 1 (no deflation) is the lie the trial ledger exists
# to end. When a family is unregistered, we assume this CONSERVATIVE FLOOR of trials rather
# than 1 — a deliberate over-estimate (de Prado: over-estimating N is the safe direction). A
# family that registers its true budget (via @register_trials / log_declared_budget) overrides
# the floor upward; it can never go below it.
UNREGISTERED_TRIALS_FLOOR = 8


def _ledger_n_trials(family: str | None, ledger=None) -> int:
    """Honest n_trials for `family` sourced from the Trial Ledger (declared budgets +
    itemized grid configs, summed across every ledger family that STARTS WITH `family` so a
    'commodity_tsmom' budget also covers 'commodity_tsmom:carry'). Returns the conservative
    UNREGISTERED_TRIALS_FLOOR when nothing is registered — never 1. `family=None` keeps the
    legacy floor too (an anonymous run is still a searched run)."""
    try:
        from engine.trial_ledger import TrialLedger
        led = ledger if ledger is not None else TrialLedger()
        if family is None:
            fams = led.families()
        else:
            fams = [f for f in led.families() if f == family or f.startswith(family)]
        total = sum(led.effective_n(f) for f in fams)
    except Exception:  # noqa: BLE001 — the ledger is advisory; never crash a validation run
        total = 0
    return max(total, UNREGISTERED_TRIALS_FLOOR)


def _mt_bump(n_trials: int) -> float:
    """Deflated-Sharpe-style multiple-testing bump on the OOS bar: more configs searched
    -> a higher bar, so a lucky best-of-n can't pass.  Capped so it never demands >90%."""
    if n_trials <= 1:
        return 0.0
    return min(0.20, 0.05 * np.log2(n_trials))


def overfit_guard(by_ticker: dict, n_trials: int | None = None, metric: str = "stop_out_rate",
                  min_frac: float = 0.70, *, family: str | None = None, ledger=None) -> dict:
    """IS vs OOS decay flag + the pre-committed KILL RULE.  The IS->OOS decay is computed on
    a LIKE-FOR-LIKE population (names that traded >= MIN_DECAY_TRADES in BOTH views for BOTH
    arms) so burn-in zero-trade names can't skew it.  The real search guard is the
    n_trials-driven bar.

    W1d: n_trials now SOURCES FROM THE TRIAL LEDGER by `family` when not passed explicitly —
    an unregistered family gets the conservative UNREGISTERED_TRIALS_FLOOR (not 1), so a
    harness that never declared its search budget is deflated as if it swept several configs.
    Passing an explicit int still works (legacy callers) and takes precedence."""
    _check_verdict_metric(metric)
    if n_trials is None:
        n_trials = _ledger_n_trials(family, ledger=ledger)
    cs_oos = cross_section(by_ticker, "oos", metric)
    cs_full = cross_section(by_ticker, "full", metric)
    bar = min_frac + _mt_bump(n_trials)
    comparable = [t for t, d in by_ticker.items() if d.get("base") and min(
        d["treat"]["is"]["n_trades"], d["base"]["is"]["n_trades"],
        d["treat"]["oos"]["n_trades"], d["base"]["oos"]["n_trades"]) >= MIN_DECAY_TRADES]

    def _frac(view):
        if not comparable:
            return None
        imp = sum(_is_better(by_ticker[t]["treat"][view][metric],
                             by_ticker[t]["base"][view][metric], metric) for t in comparable)
        return imp / len(comparable)

    frac_is, frac_oos_cmp = _frac("is"), _frac("oos")
    decay = (frac_is - frac_oos_cmp) if (frac_is is not None and frac_oos_cmp is not None) else None
    return {
        "metric": metric, "n_trials": n_trials,
        "frac_improved_full": cs_full.get("frac_improved"),
        "frac_improved_oos": cs_oos.get("frac_improved"),      # headline OOS read (all names)
        "decay_population": len(comparable),
        "frac_improved_is": frac_is,                           # like-for-like
        "frac_improved_oos_comparable": frac_oos_cmp,
        "is_oos_decay": decay,
        "decay_flag": (decay is not None and decay > 0.20),
        "decay_note": ("drift smell on names traded in both windows; for n_trials=1 this is "
                       "informational — the search guard is deflated_bar (raises with n_trials)."),
        "deflated_bar": bar,
        "kill_rule": kill_rule(by_ticker, view="oos", metric=metric, min_frac=bar),
    }


def kill_rule(by_ticker: dict, view: str = "oos", metric: str = "stop_out_rate",
              min_frac: float = 0.70) -> dict:
    """Pre-committed kill rule (charter §3): SHIP only if >= min_frac of held-out names
    improve on the stop-based metric; otherwise REJECT and ship the simpler baseline."""
    _check_verdict_metric(metric)
    cs = cross_section(by_ticker, view, metric)
    frac = cs.get("frac_improved")
    if frac is None:
        return {"verdict": "NO-BASELINE", "frac_improved": None, "min_frac": min_frac}
    ok = frac >= min_frac
    return {"verdict": "SHIP" if ok else "REJECT — ship the simpler baseline",
            "pass": bool(ok), "frac_improved": frac, "min_frac": min_frac, "view": view}


# ============================================================ the public entry
def walk_forward(signal_fn, panel: dict, cfg: dict | None = None, *,
                 baseline_fn=None, since: pd.Timestamp = SINCE, n_trials: int | None = None,
                 metric: str = "stop_out_rate", run_id: str | None = None,
                 tag: str = "wf", log: bool = True, family: str | None = None) -> dict:
    """Run the harness over a panel.  Returns {run_id, config, by_ticker, pooled,
    overfit_flags}.  See the module header for the signal-callable contract.

    W1d: pass `family` to source the multiple-testing `n_trials` from the Trial Ledger
    (declared budget + itemized grid). An unregistered family is deflated at the conservative
    UNREGISTERED_TRIALS_FLOOR, never 1. An explicit `n_trials` int overrides the ledger."""
    _check_verdict_metric(metric)
    cfg = {**DEFAULT_CFG, **(cfg or {})}
    by_ticker: dict = {}
    dropped: dict = {}
    for t, df in panel.items():
        try:
            daily = df["close"].dropna()
            if len(daily) < 400:
                dropped[t] = f"skip: thin history ({len(daily)} daily bars < 400)"
                continue
            # high/low reindexed onto the SAME daily index as close (the sim grid)
            high = df["high"].reindex(daily.index) if "high" in df.columns else None
            low = df["low"].reindex(daily.index) if "low" in df.columns else None
            exit_default = default_confluence_exit(daily)

            tb, tx = _resolve(signal_fn(daily, high, low), daily, exit_default)
            si = _start_index(daily.index, since)
            treat = _eval_one(daily, high, low, tb, tx, si, cfg)

            base = None
            if baseline_fn is not None:
                bb, bx = _resolve(baseline_fn(daily, high, low), daily, exit_default)
                base = _eval_one(daily, high, low, bb, bx, si, cfg)
            by_ticker[t] = {"treat": treat, "base": base}
        except Exception as e:
            dropped[t] = f"ERROR: {type(e).__name__}: {e}"
            continue

    errs = {k: v for k, v in dropped.items() if v.startswith("ERROR")}
    if errs:
        print(f"[walk_forward] {len(errs)} name(s) dropped on UNEXPECTED errors: {errs}",
              file=sys.stderr)

    pooled = {v: cross_section(by_ticker, v, metric) for v in ("full", "oos", "is")}
    overfit_flags = overfit_guard(by_ticker, n_trials=n_trials, metric=metric, family=family)

    rid = run_id or _make_run_id(tag, cfg)
    result = {"run_id": rid, "config": cfg, "since": str(since.date()),
              "n_names": len(by_ticker), "metric": metric, "dropped": dropped,
              "by_ticker": by_ticker, "pooled": pooled, "overfit_flags": overfit_flags}
    if log:
        _write_log(rid, result)
    return result


def _make_run_id(tag: str, cfg: dict) -> str:
    h = hashlib.sha1(json.dumps(cfg, sort_keys=True).encode()).hexdigest()[:6]
    return f"{tag}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{h}"


def _write_log(run_id: str, result: dict) -> Path:
    """Per-trial JSON log to data/signal_archive/wf_<run_id>.json (component 6)."""
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    compact = {
        "run_id": run_id, "config": result["config"], "since": result["since"],
        "metric": result["metric"], "n_names": result["n_names"],
        "dropped": result.get("dropped", {}),
        "pooled": result["pooled"], "overfit_flags": result["overfit_flags"],
        "by_ticker": {t: {"treat": d["treat"], "base": d["base"]}
                      for t, d in result["by_ticker"].items()},
    }
    fp = ARCHIVE / f"wf_{run_id}.json"
    fp.write_text(json.dumps(compact, indent=1, default=float))
    return fp


# ============================================================ gold-standard self-test
# The validated buy-filter vs raw confluence buys, as DAILY rich-mode callables.  Both
# arms share the SAME exit (CS|revSell) and the SAME stop, so the ONLY difference is which
# entries are taken — exactly the experiment the task asks for.
#
# LEAK-FREE ENTRY TIMING (the subtle part):
#   * RAW buy at 3D bar i (CB|revBuy) is known at bar i's close -> enter on the first daily
#     bar after bar i's known date.
#   * FILTERED "take" needs the reclaim-and-hold confirmation, which peeks at bar i+1 (trend)
#     or i+2 (counter-trend below-200 & weekly-down).  That verdict is only KNOWN at the
#     confirmation bar's close, so a take enters on the first daily bar after the CONFIRMATION
#     bar's known date — later and at a higher (held) price than the raw buy.  That delay is
#     part of the filter's mechanism (it buys only after the entry bar holds), so including it
#     is faithful, not a penalty.  block/pending -> no entry.
_SIG_CACHE: dict = {}                                 # gold-path memo (compute_signals is heavy)


def _cached_signals(daily: pd.Series):
    from confluence import compute_signals
    key = (len(daily), float(daily.iloc[0]), float(daily.iloc[-1]),
           int(daily.index[0].value), int(daily.index[-1].value))
    hit = _SIG_CACHE.get(key)
    if hit is None:
        sig = compute_signals(daily)
        if not sig.empty:
            sig = sig.dropna(subset=["macd", "sig", "k", "d", "rsi14"])
        _, kn = tf_bars(daily, 3)
        hit = (sig, kn.reindex(sig.index) if not sig.empty else kn)
        _SIG_CACHE[key] = hit
    return hit


def _gold_daily_frame(daily: pd.Series, mode: str) -> pd.DataFrame:
    """mode in {'raw','filtered','selection'}.
      raw       — every CB|revBuy, entered after bar i's known date (the baseline).
      filtered  — only filter-graded TAKE buys, entered after the i+1/i+2 CONFIRMATION bar's
                  known date (LEAK-FREE, the actually-tradeable filter — buys later/higher).
      selection — the SAME take subset as 'filtered' but entered at bar i like raw.  This is
                  NOT leak-free / NOT tradeable (the take verdict isn't known at bar i); it is
                  an ATTRIBUTION diagnostic only, to separate the filter's SELECTION effect
                  from its buy-later/higher timing cost.  Never a verdict."""
    from buy_filters import swing_highs, bearish_divergence, reclaim_and_hold
    sig, kn = _cached_signals(daily)
    if sig.empty:
        z = pd.Series(False, index=daily.index)
        return pd.DataFrame({"buy": z, "exit": z})
    c, macd, n = sig["close"], sig["macd"], len(sig)
    raw = (sig["CB"] | sig["revBuy"]).to_numpy()
    exit_known = kn[(sig["CS"] | sig["revSell"]).to_numpy()].dropna()
    exit_daily = _daily_events_after(exit_known.values, daily.index)

    if mode == "raw":
        buy_daily = _daily_events_after(kn[raw].dropna().values, daily.index)
        return pd.DataFrame({"buy": buy_daily, "exit": exit_daily})

    hi = swing_highs(c)
    buy_known = []
    for i in np.where(raw)[0]:
        if bearish_divergence(i, c, macd, hi):
            continue                                  # veto -> block
        ok, _ = reclaim_and_hold(i, sig, n)
        if ok is not True:
            continue                                  # block or pending -> no take
        if mode == "selection":                       # same entry bar as raw (attribution)
            buy_known.append(kn.iloc[i])
            continue
        below = (not bool(sig["above200"].iloc[i])) and (not bool(sig["w_bull"].iloc[i]))
        conf_bar = i + 2 if below else i + 1          # bar at which the take is KNOWN
        if conf_bar < n and pd.notna(kn.iloc[conf_bar]):
            buy_known.append(kn.iloc[conf_bar])
    buy_daily = _daily_events_after([k for k in buy_known if pd.notna(k)], daily.index)
    return pd.DataFrame({"buy": buy_daily, "exit": exit_daily})


def gold_signal_fn(close, high=None, low=None):      # filtered (treatment, tradeable)
    return _gold_daily_frame(close, "filtered")


def gold_baseline_fn(close, high=None, low=None):     # raw confluence buys (baseline)
    return _gold_daily_frame(close, "raw")


def gold_selection_fn(close, high=None, low=None):    # take-subset, raw entry (attribution)
    return _gold_daily_frame(close, "selection")


def _load_panel(tickers=None) -> dict:
    panel = {}
    for fp in sorted(glob.glob(str(DATA / "*.parquet"))):
        t = Path(fp).stem
        if tickers and t not in tickers:
            continue
        panel[t] = pd.read_parquet(fp)
    return panel


def run_gold(verbose: bool = True) -> dict:
    """Confirm the buy-filter REDUCES the stop-out rate vs raw confluence buys."""
    panel = _load_panel()
    res = walk_forward(gold_signal_fn, panel, DEFAULT_CFG,
                       baseline_fn=gold_baseline_fn, tag="gold", metric="stop_out_rate")
    cs = res["pooled"]["full"]
    bt = res["by_ticker"]

    def _avg(arm, view, k):
        return float(np.mean([d[arm][view][k] for d in bt.values() if d.get(arm)]))

    def _tw(arm):                                       # trade-weighted pooled stop-out rate
        num = sum(d[arm]["full"]["stop_out_rate"] * d[arm]["full"]["n_trades"]
                  for d in bt.values() if d.get(arm))
        den = sum(d[arm]["full"]["n_trades"] for d in bt.values() if d.get(arm))
        return num / den if den else float("nan")

    raw_so, flt_so = _avg("base", "full", "stop_out_rate"), _avg("treat", "full", "stop_out_rate")
    raw_tw, flt_tw = _tw("base"), _tw("treat")
    frac = cs.get("frac_improved")
    if verbose:
        print(f"\nGOLD-STANDARD — does the buy-filter cut the STOP-OUT rate?  "
              f"(run_id={res['run_id']}, n={res['n_names']} names, stop={DEFAULT_CFG['stop_pct']:.0%})")
        print(f"  {'metric (full sample)':28s}{'RAW buys':>12s}{'FILTERED':>12s}")
        print("  " + "-" * 52)
        rows = [("stop-out rate %  (PRIMARY)", "stop_out_rate", False),
                ("avg loss %", "avg_loss", False),
                ("worst trade %", "worst_loss", False),
                ("% trades below stop (gap)", "frac_below_stop", False),
                ("entry efficiency (0=low)", "entry_eff", False),
                ("expectancy %", "expectancy", False),
                ("win rate %", "win_rate", False),
                ("trades / name", "n_trades", False),
                ("[ctx] captured %", "captured", True),
                ("[ctx] with-stop strat max-DD %", "strat_max_dd", True),
                ("[ctx] no-stop loose-hold max-DD %", "nostop_max_dd", True)]
        for lbl, k, _ctx in rows:
            print(f"  {lbl:30s}{_avg('base','full',k):>11.2f}{_avg('treat','full',k):>11.2f}")
        print("  " + "-" * 52)
        print(f"  per-name stop-out (mean):    raw {raw_so:.1f}%  -> filtered {flt_so:.1f}%  "
              f"(filter lower on {100*frac:.0f}% of {cs.get('n_comparable')} comparable names)")
        print(f"  trade-weighted pooled:       raw {raw_tw:.1f}%  -> filtered {flt_tw:.1f}%")
        ok = (flt_so < raw_so) and (frac is not None and frac >= 0.70)
        print(f"  RESULT @ {DEFAULT_CFG['stop_pct']:.0%} stop: "
              f"{'✅ FILTER REDUCES STOP-OUTS (ship)' if ok else '⚠️ does NOT clear the 70% bar -> ship the simpler baseline'}")
        ko = res["overfit_flags"]
        print(f"\n  walk-forward OOS (the real generalisation verdict):")
        print(f"    frac improved  full={_fmt(ko['frac_improved_full'])}  "
              f"is={_fmt(ko['frac_improved_is'])}  oos={_fmt(ko['frac_improved_oos'])}")
        print(f"    decay_flag={ko['decay_flag']}   kill_rule={ko['kill_rule']['verdict']}")
        print(f"\n  log: data/signal_archive/wf_{res['run_id']}.json")

        # --- ATTRIBUTION (non-tradeable): does the take-SUBSET reduce stop-outs when entered
        # at the SAME bar/price as raw?  Isolates selection from the buy-later/higher timing. ---
        sel = walk_forward(gold_selection_fn, panel, DEFAULT_CFG, baseline_fn=gold_baseline_fn,
                           tag="goldsel", metric="stop_out_rate", log=False)
        scs = sel["pooled"]["full"]
        sel_so = float(np.mean([d["treat"]["full"]["stop_out_rate"]
                                for d in sel["by_ticker"].values() if d.get("treat")]))
        print(f"\n  ATTRIBUTION (NON-tradeable diagnostic — selection at raw entry bar):")
        print(f"    stop-out rate: raw {raw_so:.1f}% -> selection-only {sel_so:.1f}% "
              f"-> tradeable-filtered {flt_so:.1f}%")
        print(f"    selection-only lowers stop-out on {100*scs.get('frac_improved'):.0f}% of names "
              f"(vs {100*frac:.0f}% for the tradeable filter)")
        print(f"    => the gap between selection-only and tradeable isolates the buy-later/higher cost.")
    return res


def _fmt(x):
    return "n/a" if x is None else f"{x:.2f}"


def main():
    ap = argparse.ArgumentParser(description="Signal-engine STOP-AWARE walk-forward harness.")
    ap.add_argument("--gold", action="store_true", help="run the gold-standard stop-out test")
    a = ap.parse_args()
    if a.gold:
        run_gold()
    else:
        print(__doc__)


if __name__ == "__main__":
    main()

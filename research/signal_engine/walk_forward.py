"""Reusable WALK-FORWARD validation harness for the signal engine.

> READ research/signal_engine/CHARTER.md FIRST. This harness exists to enforce its
> §3 (metrics + validation discipline) and to make its §4 tripwires impossible to
> trip by accident. In one sentence: **this judges signals on RISK (drawdown,
> shake-outs, loss size, entry quality) — NEVER on total return or beat-buy-&-hold.**

What it gives you (the six components asked for):

  1. PURGED / EMBARGOED WALK-FORWARD.  Expanding train [0:Ti], test [Ti:Ti+test_len],
     rolled by `step`, with a `purge` gap between train and test and an `embargo` after
     test — so no test bar's information bleeds into a neighbouring split. No look-ahead.

  2. LEAK-FREE CROSS-GRID MAPPING (for multi-timeframe variants).  A TF bar's close is
     only KNOWN on the last daily date inside its bin (resample labels the bin's LEFT
     edge), so every TF bar is mapped to its true known-date and FILLED on the first
     daily close strictly AFTER that date.  Mirrors how confluence.py resamples with
     '3B' and re-uses tuning_harness.py's tf_bars/to_daily so 2D vs 3D compare fairly.

  3. RISK METRICS SUITE.  max drawdown, shake-out rate %, avg loss size, per-trade
     expectancy, win rate.  Total return is carried ONLY as a clearly-labelled context
     field (`captured`) and is NEVER used in any verdict (charter §4 tripwire #1).

  4. CROSS-SECTIONAL AGGREGATOR.  Percentile stats across the whole panel (110+ names)
     and the **% of names improved vs baseline** — never just a pooled mean (§3).

  5. OVERFIT GUARD.  In-sample vs out-of-sample comparison (a deflated-Sharpe-style
     decay flag, deflated for the number of trials searched) plus the pre-committed
     KILL RULE: reject an addition if <70% of held-out names improve on drawdown,
     and ship the simpler baseline instead (§3).

  6. PER-TRIAL JSON LOGS to data/signal_archive/wf_<run_id>.json.

Interface (the contract):

    walk_forward(signal_fn, panel, cfg, baseline_fn=None, ...) -> {by_ticker, pooled, overfit_flags}

  * signal_fn / baseline_fn : a SIGNAL CALLABLE.  Two accepted shapes —
      - simple:  fn(close: pd.Series, high=None, low=None) -> pd.Series[bool]
                 (daily BUY events on the daily index; the harness pairs them with a
                  default confluence exit and a leak-free next-daily-close fill.)
      - rich:    fn(close, high=None, low=None) -> pd.DataFrame[close, buy, exit]
                 (buy/exit/close on ANY eval grid — e.g. the native 3D grid; the
                  harness simulates on the returned grid.  Use this for a faithful
                  3D reproduction.)
  * panel : {ticker: DataFrame with at least 'close' (and optionally 'high','low')}.
  * cfg   : {train_len, test_len, step, purge, embargo}  (lengths in EVAL-GRID bars).

Gold-standard self-test:  `python3 walk_forward.py --gold`  runs the validated
confluence buy-filter on data/stocks/ and confirms it recovers the published result
(avg maxDD -23.7% -> -15.5%, shallower on ~84% of names; matches test_buyfilter.py).
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

# same-dir siblings (confluence.py, diagnose_v2.py, ...) — mirror how test_buyfilter imports
sys.path.insert(0, str(Path(__file__).resolve().parent))

warnings.filterwarnings("ignore")
logging.disable(logging.CRITICAL)

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "stocks"
ARCHIVE = ROOT / "data" / "signal_archive"

# Entries are counted from here (matches confluence.py / test_buyfilter.py SINCE).
SINCE = pd.Timestamp("2023-06-01")
SHAKE = 0.08          # shake-out = a trade that went >= -8% underwater from entry before exit
MIN_DECAY_TRADES = 3  # a name must trade >= this in BOTH is & oos to enter the decay population

# Default purged/embargoed walk-forward config, in EVAL-GRID bars (3D bars by default).
DEFAULT_CFG = {"train_len": 60, "test_len": 40, "step": 40, "purge": 3, "embargo": 3}

# --- metric direction + verdict policy (mechanical enforcement of charter §3/§4) -----
# A "verdict" metric is one that decides SHIP/REJECT.  TOTAL RETURN IS BANNED from any
# verdict (charter §4 tripwire #1: never judge on return / beat-buy-&-hold); it survives
# only as the labelled context field `captured`.
_RETURN_LIKE = {"captured", "cap"}
# higher value == better.  max_dd/avg_loss are negative, so "less negative" == higher == better.
_HIGHER_BETTER = {"max_dd", "avg_loss", "expectancy", "win_rate", "captured"}
# lower value == better.
_LOWER_BETTER = {"shake_rate", "n_trades"}


def _check_verdict_metric(metric: str) -> None:
    """Refuse to render a verdict on total return — makes the §4 tripwire un-trippable."""
    if metric in _RETURN_LIKE:
        raise ValueError(
            f"metric={metric!r} is TOTAL RETURN — banned from any verdict (charter §4 #1). "
            "This is a RISK harness: judge on max_dd / avg_loss / shake_rate / expectancy.")


def _is_better(treat: float, base: float, metric: str) -> bool:
    """Direction-aware 'did treatment improve on baseline' for `metric` (charter §3)."""
    if metric in _HIGHER_BETTER:
        return treat > base
    if metric in _LOWER_BETTER:
        return treat < base
    raise ValueError(f"unknown metric {metric!r}: add it to _HIGHER_BETTER/_LOWER_BETTER")


# ============================================================ cross-grid utils
# Re-used verbatim from tuning_harness.py so the leak-free TF->daily mapping is the
# SAME tested code (component 2).  A TF bar is labelled by its bin's LEFT edge but is
# only KNOWN on the last daily date in the bin; we map by that known date and fill on
# the first daily bar strictly after it.
def tf_bars(daily: pd.Series, n: int):
    """resample to n-business-day bars (faithful) and return, per bar, the true daily
    date its close became known (resample labels the bin's LEFT edge)."""
    if n == 1:
        return daily.copy(), pd.Series(daily.index, index=daily.index)
    s = daily.resample(f"{n}B").last().dropna()
    known = (daily.resample(f"{n}B")
                  .apply(lambda x: x.dropna().index.max())
                  .reindex(s.index).dropna())
    s = s.reindex(known.index)
    return s, pd.Series(pd.to_datetime(known.values), index=known.index)


def to_daily(tf_series: pd.Series, known: pd.Series, daily_index: pd.DatetimeIndex,
             how: str = "ffill") -> pd.Series:
    """Map a TF-bar series onto the daily index by its KNOWN date (leak-free).
    how='ffill' -> state held until the next bar; how='event' -> True only on the first
    daily bar on/after each known date where the TF value is True."""
    kd = pd.Series(tf_series.to_numpy(), index=pd.to_datetime(known.to_numpy()))
    kd = kd[~kd.index.duplicated(keep="last")].sort_index()
    if how == "ffill":
        return kd.reindex(daily_index, method="ffill")
    out = pd.Series(False, index=daily_index)
    pos = daily_index.searchsorted(kd.index, side="left")
    for p, v in zip(pos, kd.to_numpy()):
        if v and p < len(daily_index):
            out.iloc[p] = True
    return out


# ============================================================ core trade sim
def simulate_trades(close: np.ndarray, buy: np.ndarray, exit_: np.ndarray, *,
                    fill_lag: int = 1, start_idx: int = 0, close_open: bool = False):
    """Trade-LEVEL simulation, grid-agnostic (component-3 substrate).

    Long/flat as the owner trades it: when flat, enter on a buy event; when long, exit
    on an exit event.  Fill at `fill_lag` bars after the signal bar (next bar's close,
    conservative, no look-ahead).  Equity is marked-to-market every bar while long.

    This loop is a faithful generalisation of test_buyfilter.py's `sim`: equity curve
    seeded at 1.0, one mark per bar, entries gated to >= start_idx, and (by default)
    an open position at the end is NOT booked as a closed trade — only the equity curve
    carries it (so drawdown still reflects it).  validated at fill_lag=1.

    Returns (curve: np.ndarray length len(close), trades: list[dict]).
    Each trade dict: entry_i, exit_i, ret, mae (max adverse excursion from entry).
    """
    n = len(close)
    pos = 0
    ep = None          # entry price
    e_fill = None      # entry fill index (for MAE)
    trades: list[dict] = []
    eq = 1.0
    curve = [1.0]
    for i in range(n - 1):
        if pos == 1:
            eq *= close[i + 1] / close[i]
        curve.append(eq)
        if pos == 0:
            if i < start_idx:
                continue
            if buy[i] and i + fill_lag < n:
                pos, e_fill = 1, i + fill_lag
                ep = close[e_fill]
        elif exit_[i] and i + fill_lag < n:
            x_fill = i + fill_lag
            seg = close[e_fill:x_fill + 1]
            mae = float(seg.min()) / ep - 1.0 if len(seg) else 0.0
            trades.append({"entry_i": e_fill, "exit_i": x_fill,
                           "ret": close[x_fill] / ep - 1.0, "mae": mae})
            pos = 0
    if close_open and pos == 1 and e_fill is not None:
        seg = close[e_fill:]
        mae = float(seg.min()) / ep - 1.0 if len(seg) else 0.0
        trades.append({"entry_i": e_fill, "exit_i": n - 1,
                       "ret": close[-1] / ep - 1.0, "mae": mae})
    return np.asarray(curve), trades


def trade_metrics(curve: np.ndarray, trades: list[dict]) -> dict:
    """The RISK metrics suite (component 3).  Primary = max drawdown; then shake-out
    rate, avg loss, per-trade expectancy, win rate.  `captured` (total return) is
    context ONLY and must never enter a verdict (charter §4)."""
    if len(curve):
        dd = float((curve / np.maximum.accumulate(curve) - 1.0).min())
        cap = float(curve[-1] - 1.0)
    else:
        dd, cap = 0.0, 0.0
    if not trades:
        return {"n_trades": 0, "max_dd": 100 * dd, "shake_rate": 0.0, "avg_loss": 0.0,
                "expectancy": 0.0, "win_rate": 0.0, "captured": 100 * cap}
    r = np.array([t["ret"] for t in trades])
    mae = np.array([t["mae"] for t in trades])
    losses = r[r < 0]
    return {
        "n_trades": len(trades),
        "max_dd": 100 * dd,                                            # PRIMARY (risk)
        "shake_rate": 100 * float((mae <= -SHAKE).mean()),            # entry-quality risk
        "avg_loss": 100 * float(losses.mean()) if len(losses) else 0.0,
        "expectancy": 100 * float(r.mean()),
        "win_rate": 100 * float((r > 0).mean()),
        "captured": 100 * cap,                                        # CONTEXT ONLY
    }


# ============================================================ signal resolution
def default_confluence_exit(daily: pd.Series) -> pd.Series:
    """Shared daily exit for SIMPLE-mode signal callables: the baseline 3D oscillator
    SELL/cut, mapped to the daily grid by known date (leak-free).  Identical for every
    variant so only ENTRY timing differs.  (Same construction as tuning_harness.common_exit.)"""
    from confluence import compute_signals
    sig = compute_signals(daily)
    if sig.empty:
        return pd.Series(False, index=daily.index)
    s3 = sig["close"]
    _, kn = tf_bars(daily, 3)
    kn = kn.reindex(s3.index).dropna()
    ev = (sig["CS"] | sig["revSell"]).reindex(kn.index).fillna(False)
    return to_daily(ev, kn, daily.index, "event")


def _events_to_grid(daily_events: pd.Series, target_index: pd.DatetimeIndex) -> pd.Series:
    """Place each daily True event on the FIRST target-grid bar on/after its known date
    (leak-free).  Used when a rich-mode frame OMITS 'exit' and the eval grid is coarser
    than daily: ffill-reindexing a sparse daily event series onto a coarse grid would
    silently DROP most events (the True bars rarely coincide with a coarse bar), so we
    align by event date instead — lossless and never earlier than the known date."""
    out = pd.Series(False, index=target_index)
    if daily_events is None or not bool(daily_events.any()):
        return out
    ev_dates = pd.DatetimeIndex(daily_events.index[daily_events.to_numpy().astype(bool)])
    for p in target_index.searchsorted(ev_dates, side="left"):
        if p < len(target_index):
            out.iloc[p] = True
    return out


def _resolve(result, daily: pd.Series, exit_default: pd.Series):
    """Normalise a signal-callable return into (close, buy, exit) on a common grid.
    Series -> SIMPLE mode (daily buy events + default exit).  DataFrame -> RICH mode."""
    if isinstance(result, pd.DataFrame):
        if "buy" not in result.columns:
            raise ValueError("rich signal frame must have a 'buy' column")
        close = result["close"] if "close" in result.columns else daily.reindex(result.index)
        buy = result["buy"].astype(bool)
        if "exit" in result.columns:
            ex = result["exit"].astype(bool)
        else:                                      # default exit, event-aligned to this grid
            ex = _events_to_grid(exit_default, result.index)
        return close.astype(float), buy, ex
    # Series == simple mode (daily grid; default exit is already daily -> identity reindex)
    buy = result.reindex(daily.index).fillna(False).astype(bool)
    return daily.astype(float), buy, exit_default.reindex(daily.index).fillna(False).astype(bool)


def _start_index(idx: pd.DatetimeIndex, since: pd.Timestamp) -> int:
    return int((idx < since).sum())


# ============================================================ walk-forward splits
def make_windows(n: int, start_idx: int, cfg: dict):
    """Purged/embargoed expanding walk-forward splits over EVAL-GRID bar indices
    (component 1).  Returns list of (train_lo, train_hi, test_lo, test_hi) where
    train=[train_lo:train_hi] is purged (train_hi = Ti - purge), test=[test_lo:test_hi].
    Consecutive test blocks are separated by an `embargo` gap (step is floored at
    test_len + embargo so test windows can never overlap).

    NOTE on the train bounds: the harness evaluates GLOBALLY-COMPUTED, CAUSAL signals
    (every indicator at bar t uses only data <= t), so a value is identical whether
    computed on [0:t] or the full series — there is nothing to re-fit per window, and
    OOS-ness comes from (a) causal indicators, (b) entries MASKED to test-window bars,
    (c) leak-free fills.  The train_lo/train_hi bounds are therefore the documented
    seam for a FUTURE fitted-signal refit hook; they are intentionally not consumed by
    the non-fitted path.  Do NOT add a per-ticker P&L-fitted refit here (charter §4)."""
    train_len = int(cfg.get("train_len", DEFAULT_CFG["train_len"]))
    test_len = int(cfg.get("test_len", DEFAULT_CFG["test_len"]))
    step = int(cfg.get("step", DEFAULT_CFG["step"]))
    purge = int(cfg.get("purge", DEFAULT_CFG["purge"]))
    embargo = int(cfg.get("embargo", DEFAULT_CFG["embargo"]))
    windows = []
    ti = max(start_idx + train_len, train_len)
    while ti + 1 < n:
        test_lo, test_hi = ti, min(ti + test_len, n)
        if test_hi - test_lo < 5:                  # too small to be meaningful
            break
        train_lo, train_hi = 0, max(ti - purge, 0)
        windows.append((train_lo, train_hi, test_lo, test_hi))
        ti += max(step, test_len + embargo)        # embargo gap between test blocks
    return windows


# ============================================================ per-ticker eval
def _eval_one(close: pd.Series, buy: pd.Series, ex: pd.Series, start_idx: int, cfg: dict):
    """Evaluate one (close, buy, exit) frame: full-sample, walk-forward OOS (stitched
    over purged/embargoed test windows) and the in-sample burn-in region."""
    c = close.to_numpy(float)
    b = buy.to_numpy(bool)
    x = ex.to_numpy(bool)
    n = len(c)

    # ---- FULL SAMPLE (reproduces test_buyfilter.py: entries from SINCE, no close-out)
    curve, trades = simulate_trades(c, b, x, start_idx=start_idx, close_open=False)
    full = trade_metrics(curve, trades)

    # ---- WALK-FORWARD splits.  OOS and IS are each ONE continuous sim over the full
    # series with entries MASKED to the relevant bars (exits always allowed, no close-out).
    # A position spanning a window boundary is therefore booked exactly once (no per-window
    # double-counting) and drawdown is read off a single continuous equity curve.
    windows = make_windows(n, start_idx, cfg)
    first_test_lo = windows[0][2] if windows else n

    oos_mask = np.zeros(n, bool)
    for (_tr_lo, _tr_hi, te_lo, te_hi) in windows:   # train bounds intentionally unused (see make_windows)
        oos_mask[te_lo:te_hi] = True
    oc, ot = simulate_trades(c, b & oos_mask, x, start_idx=start_idx, close_open=False)
    oos = trade_metrics(oc, ot)

    is_mask = np.zeros(n, bool)
    is_mask[start_idx:first_test_lo] = True          # pre-first-test burn-in (the only non-OOS span)
    ic, it = simulate_trades(c, b & is_mask, x, start_idx=start_idx, close_open=False)
    is_ = trade_metrics(ic, it)
    return {"full": full, "oos": oos, "is": is_, "n_windows": len(windows)}


# ============================================================ cross-section
_PCTS = (10, 25, 50, 75, 90)


def cross_section(by_ticker: dict, view: str, metric: str = "max_dd") -> dict:
    """Cross-sectional aggregator (component 4): percentile distribution of `metric`
    for treatment and baseline + the % of names improved (never just a pooled mean).
    Improvement direction is metric-aware (`_is_better`), not a 2-name special case."""
    _check_verdict_metric(metric)
    treat, base = [], []
    improved = 0
    names = []
    for t, d in by_ticker.items():
        tv = d["treat"][view].get(metric)
        bv = d["base"][view].get(metric) if d.get("base") else None
        if tv is None:
            continue
        treat.append(tv)
        names.append(t)
        if bv is not None:
            base.append(bv)
            improved += int(_is_better(tv, bv, metric))
    treat = np.array(treat, float)

    def _pcts(a):
        if not len(a):
            return {}
        return {f"p{p}": float(np.percentile(a, p)) for p in _PCTS} | {"mean": float(a.mean())}

    out = {
        "view": view, "metric": metric, "n_names": len(treat),
        "treat": _pcts(treat),
        # context: the other risk metrics' panel means (treatment), labelled, no verdict
        "treat_means": {k: float(np.mean([by_ticker[n]["treat"][view].get(k, 0.0) for n in names]))
                        for k in ("max_dd", "shake_rate", "avg_loss", "expectancy",
                                  "win_rate", "n_trades", "captured")},
    }
    if base:
        out["base"] = _pcts(np.array(base, float))
        out["frac_improved"] = float(improved / len(base))
    return out


# ============================================================ overfit guard
def _mt_bump(n_trials: int) -> float:
    """Deflated-Sharpe-style multiple-testing bump on the fraction-improved bar: more
    configs searched -> a higher OOS bar to clear, so a lucky best-of-n can't pass."""
    if n_trials <= 1:
        return 0.0
    return min(0.20, 0.05 * np.log2(n_trials))   # capped so it never demands >90%


def overfit_guard(by_ticker: dict, n_trials: int = 1, metric: str = "max_dd",
                  min_frac: float = 0.70) -> dict:
    """In-sample vs out-of-sample decay flag + the pre-committed KILL RULE (component 5).

    The headline read is `frac_improved_oos` (all names with a baseline).  The IS->OOS
    decay is computed on a LIKE-FOR-LIKE population — names that actually traded
    (>= MIN_DECAY_TRADES) in BOTH the is and oos views, for BOTH arms — so the burn-in's
    many zero-trade (degenerate maxDD=0) names can't skew it.  For a non-fitted signal
    (n_trials=1) the decay is a drift smell only; the real search-overfitting guard is
    the multiple-testing `deflated_bar` driven by n_trials (deflated-Sharpe analogue)."""
    _check_verdict_metric(metric)
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
        "frac_improved_oos": cs_oos.get("frac_improved"),     # headline OOS read (all names)
        "decay_population": len(comparable),
        "frac_improved_is": frac_is,                          # like-for-like (comparable names)
        "frac_improved_oos_comparable": frac_oos_cmp,
        "is_oos_decay": decay,
        "decay_flag": (decay is not None and decay > 0.20),   # large IS->OOS drop = overfit smell
        "decay_note": ("drift smell on names traded in both windows; for n_trials=1 this is "
                       "informational — the search guard is deflated_bar (raises with n_trials)."),
        "deflated_bar": bar,
        "kill_rule": kill_rule(by_ticker, view="oos", metric=metric, min_frac=bar),
    }


def kill_rule(by_ticker: dict, view: str = "oos", metric: str = "max_dd",
              min_frac: float = 0.70) -> dict:
    """Pre-committed kill rule (charter §3): SHIP only if >= min_frac of held-out names
    improve on drawdown; otherwise REJECT and ship the simpler baseline."""
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
                 baseline_fn=None, since: pd.Timestamp = SINCE, n_trials: int = 1,
                 metric: str = "max_dd", run_id: str | None = None,
                 tag: str = "wf", log: bool = True) -> dict:
    """Run the harness over a panel.  Returns {run_id, config, by_ticker, pooled,
    overfit_flags}.  See module docstring for the signal-callable contract."""
    _check_verdict_metric(metric)
    cfg = {**DEFAULT_CFG, **(cfg or {})}
    by_ticker: dict = {}
    dropped: dict = {}                              # ticker -> reason (expected skip vs ERROR)
    for t, df in panel.items():
        try:
            daily = df["close"].dropna()
            if len(daily) < 400:
                dropped[t] = f"skip: thin history ({len(daily)} daily bars < 400)"
                continue
            high = df["high"].dropna() if "high" in df.columns else None
            low = df["low"].dropna() if "low" in df.columns else None
            exit_default = default_confluence_exit(daily)

            tc, tb, tx = _resolve(signal_fn(daily, high, low), daily, exit_default)
            if len(tc) == 0:
                dropped[t] = "skip: empty signal frame"
                continue
            start_idx = _start_index(tc.index, since)
            treat = _eval_one(tc, tb, tx, start_idx, cfg)

            base = None
            if baseline_fn is not None:
                bc, bb, bx = _resolve(baseline_fn(daily, high, low), daily, exit_default)
                base = _eval_one(bc, bb, bx, _start_index(bc.index, since), cfg)
            by_ticker[t] = {"treat": treat, "base": base}
        except Exception as e:                     # surfaced, NOT silently swallowed
            dropped[t] = f"ERROR: {type(e).__name__}: {e}"
            continue

    errs = {k: v for k, v in dropped.items() if v.startswith("ERROR")}
    if errs:
        print(f"[walk_forward] {len(errs)} name(s) dropped on UNEXPECTED errors: {errs}",
              file=sys.stderr)

    pooled = {v: cross_section(by_ticker, v, metric) for v in ("full", "oos", "is")}
    overfit_flags = overfit_guard(by_ticker, n_trials=n_trials, metric=metric)

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
    """Per-trial JSON log to data/signal_archive/wf_<run_id>.json (component 6).
    Stores compact per-ticker metrics + pooled + flags (drops bulky intermediates)."""
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
# The validated confluence buy-filter, expressed as RICH-mode signal callables that
# reproduce test_buyfilter.py EXACTLY: native 3D grid, enter on CB|revBuy (optionally
# filtered by refined_buy), exit on CS|revSell, fill at the next 3D close.
#
# FAITHFUL-REPRODUCTION CAVEAT (intentional): this mirrors the VALIDATED keeper as-is,
# including refined_buy's reclaim-and-hold peek at i+1/i+2 and divergence_at's centered
# swing pivots (a high at h is confirmed only at h+2).  That is a property of the rule
# the charter says to reproduce — NOT a harness bug — and is exactly why --gold recovers
# -23.7 -> -15.5 / 84%.  Production handles the last-bars confirmation lag separately
# (engine/signal_quality._buy_filter returns "pending").  NEW signals must use
# forward-only confirmed pivots (charter §3); do not copy the gold path's repaint.
def _gold_frame(daily: pd.Series, filtered: bool) -> pd.DataFrame:
    from confluence import compute_signals
    from diagnose_tencent_baba import swing_points, divergence_at
    from diagnose_v2 import refined_buy
    sig = compute_signals(daily)
    if sig.empty:
        return pd.DataFrame(columns=["close", "buy", "exit"])
    sig = sig.dropna(subset=["macd", "sig", "k", "d", "rsi14"])
    c, macd, n = sig["close"], sig["macd"], len(sig)
    cand = (sig["CB"] | sig["revBuy"]).to_numpy()
    buy = cand.copy()
    if filtered:
        hi, lo = swing_points(c)
        for i in np.where(cand)[0]:
            buy[i] = refined_buy(i, sig, divergence_at(i, c, macd, hi, lo), n)[0] == "TAKE"
    return pd.DataFrame({"close": c.to_numpy(float), "buy": buy,
                         "exit": (sig["CS"] | sig["revSell"]).to_numpy()}, index=sig.index)


def gold_signal_fn(close, high=None, low=None):     # filtered (treatment)
    return _gold_frame(close, filtered=True)


def gold_baseline_fn(close, high=None, low=None):    # raw confluence buys (baseline)
    return _gold_frame(close, filtered=False)


def _load_panel(tickers=None) -> dict:
    panel = {}
    for fp in sorted(glob.glob(str(DATA / "*.parquet"))):
        t = Path(fp).stem
        if tickers and t not in tickers:
            continue
        panel[t] = pd.read_parquet(fp)
    return panel


def run_gold(verbose: bool = True) -> dict:
    """Reproduce the published buy-filter result through the harness and check it."""
    panel = _load_panel()
    res = walk_forward(gold_signal_fn, panel, DEFAULT_CFG,
                       baseline_fn=gold_baseline_fn, tag="gold")
    cs = res["pooled"]["full"]
    raw_dd = np.mean([d["base"]["full"]["max_dd"] for d in res["by_ticker"].values()])
    flt_dd = cs["treat"]["mean"]
    frac = cs["frac_improved"]
    raw_wr = np.mean([d["base"]["full"]["win_rate"] for d in res["by_ticker"].values()])
    flt_wr = np.mean([d["treat"]["full"]["win_rate"] for d in res["by_ticker"].values()])
    raw_al = np.mean([d["base"]["full"]["avg_loss"] for d in res["by_ticker"].values()])
    flt_al = np.mean([d["treat"]["full"]["avg_loss"] for d in res["by_ticker"].values()])
    raw_n = np.mean([d["base"]["full"]["n_trades"] for d in res["by_ticker"].values()])
    flt_n = np.mean([d["treat"]["full"]["n_trades"] for d in res["by_ticker"].values()])
    if verbose:
        print(f"\nGOLD-STANDARD REPRODUCTION  (run_id={res['run_id']}, n={res['n_names']} names)")
        print(f"  avg maxDD:   RAW {raw_dd:6.1f}  ->  FILTERED {flt_dd:6.1f}   "
              f"(filter shallower on {100*frac:.0f}% of names)")
        print(f"  avg WR%:     RAW {raw_wr:6.0f}  ->  FILTERED {flt_wr:6.0f}")
        print(f"  avg loss%:   RAW {raw_al:6.1f}  ->  FILTERED {flt_al:6.1f}")
        print(f"  avg trades:  RAW {raw_n:6.1f}  ->  FILTERED {flt_n:6.1f}")
        print(f"\n  TARGET (test_buyfilter.py):  -23.7 -> -15.5, shallower on 84%")
        ok = (abs(raw_dd - (-23.7)) < 0.6 and abs(flt_dd - (-15.5)) < 0.6
              and abs(100 * frac - 84) < 3)
        print(f"  RESULT: {'✅ REPRODUCED' if ok else '❌ MISMATCH — harness is wrong'}")
        print(f"\n  walk-forward OOS read (the real generalisation verdict):")
        ko = res["overfit_flags"]
        print(f"    frac improved  full={ko['frac_improved_full']}  is={ko['frac_improved_is']}  "
              f"oos={ko['frac_improved_oos']}")
        print(f"    decay_flag={ko['decay_flag']}   kill_rule={ko['kill_rule']['verdict']}")
    return res


def main():
    ap = argparse.ArgumentParser(description="Signal-engine walk-forward harness.")
    ap.add_argument("--gold", action="store_true", help="run the gold-standard reproduction")
    a = ap.parse_args()
    if a.gold:
        run_gold()
    else:
        print(__doc__)


if __name__ == "__main__":
    main()

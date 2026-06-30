"""Faithful Python port of the "RSI-MACD x StochRSI MTF" confluence Pine, plus a
TRADE-LEVEL backtest (per-trade win-rate / expectancy vs buy&hold), run on the 3D.

WHY THIS FILE EXISTS
--------------------
Prior backtests (scripts/_bt_signals.py) scored fixed-horizon forward returns of
ladder STATES across the whole panel -- NOT the entry+exit system actually traded.
This simulates the strategy AS TRADED: enter on BUY*, exit on SELL* or cut-loss,
re-buy on the fast reversal. It also ports the EXACT indicators from the Pine:

  * "RSI-based MACD" (TH_RSIMACD+):  rsi=RSI(close,14); macd=EMA(rsi,14)-EMA(rsi,60);
    signal=EMA(macd,5).   << NOT the standard price MACD(12,26,9) in engine.cycles >>
  * StochRSI (high amplitude):  k = SMA(stoch(RSI(close,14),14), 3);  d = SMA(k, 3).

Default Pine settings reproduced (the live config):
  confW=8, useMTF=true (confirm TF = 1W), fromZoneOnly=false, useMaGate=false,
  useRsiBuyFilter=true (buy RSI<65), requireExtForSell=true (RSI>70 or %K>80),
  useReversal=true (revBars=3), lead/anchor gates OFF.

Run:  python3 research/signal_engine/confluence.py [TICKER ...]
"""
from __future__ import annotations

import sys
import glob
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "stocks"

# Pine default inputs (the live configuration)
RSI_LEN, FAST_LEN, BASE_LEN, SIG_LEN = 14, 14, 60, 5
STOCH_RSI_LEN, STOCH_LEN, SMOOTH_K, SMOOTH_D = 14, 14, 3, 3
OB, OS = 80, 20
CONF_W = 8
BUY_RSI_MAX = 65
EXT_RSI = 70
REV_BARS = 3


# ------------------------------------------------------------ indicators ----
def _rma(s: pd.Series, n: int) -> pd.Series:
    """Wilder's RMA (== Pine ta.rma): SMA seed over the first ``n`` valid values, then
    the recursive  rma = (x + (n-1)·rma_prev) / n.

    pandas ``ewm(alpha=1/n, adjust=True)`` (what this file used to do) does NOT match
    Pine — it forms a weighted average anchored on the first value, which shifts the
    early series and can flip near-threshold crosses. The SMA seed is the faithful one."""
    a = s.to_numpy(dtype="float64")
    out = np.full(a.shape, np.nan)
    fin = np.flatnonzero(np.isfinite(a))
    if fin.size < n:
        return pd.Series(out, index=s.index)
    start = fin[0]
    seed = start + n - 1
    out[seed] = np.mean(a[start:seed + 1])
    alpha = 1.0 / n
    for t in range(seed + 1, a.size):
        out[t] = alpha * a[t] + (1.0 - alpha) * out[t - 1]
    return pd.Series(out, index=s.index)


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    """Wilder's RSI (== Pine ta.rsi): RMA of gains over RMA of losses (SMA-seeded).

    Pine: rsi = down==0 ? 100 : up==0 ? 0 : 100-100/(1+up/down). The down==0 branch (an
    unbroken up-run after the seed) must read 100, not NaN. It never fires on the 2021+
    live feed, but the oracle also runs full-history symbols where thin early sessions can
    produce a >=n-bar zero-down run; without the mask those bars wrongly went NaN."""
    d = close.diff()
    up = _rma(d.clip(lower=0), n)
    dn = _rma(-d.clip(upper=0), n)
    rs = up / dn.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)              # up==0 (rs=0) already yields 0, matching Pine
    return out.mask(dn == 0, 100.0)         # down==0 -> 100 (and wins over up==0, per Pine)


def ema(s: pd.Series, span: int) -> pd.Series:
    """Pine ta.ema: recursive  ema = α·x + (1-α)·ema_prev  (α = 2/(span+1)), seeded with
    the first valid value.  == ewm(adjust=False); pandas' default adjust=True forms a
    weighted average that differs in the warm-up and can flip near-threshold crosses."""
    return s.ewm(span=span, adjust=False).mean()


def rsi_macd(close: pd.Series):
    """The Pine 'RSI-based MACD' — EMA of RSI minus slower EMA of RSI."""
    r = rsi(close, RSI_LEN)
    macd = ema(r, FAST_LEN) - ema(r, BASE_LEN)
    sig = ema(macd, SIG_LEN)
    return macd, sig


def stoch_rsi_kd(close: pd.Series):
    """Pine StochRSI (high amplitude): stochastic OF the RSI, then %K/%D smooth."""
    r = rsi(close, STOCH_RSI_LEN)
    lo = r.rolling(STOCH_LEN).min()
    hi = r.rolling(STOCH_LEN).max()
    rawk = (r - lo) / (hi - lo).replace(0, np.nan) * 100
    k = rawk.rolling(SMOOTH_K).mean()
    d = k.rolling(SMOOTH_D).mean()
    return k, d


def crossover(a: pd.Series, b: pd.Series) -> pd.Series:
    return (a > b) & (a.shift(1) <= b.shift(1))


def crossunder(a: pd.Series, b: pd.Series) -> pd.Series:
    return (a < b) & (a.shift(1) >= b.shift(1))


def bars_since(cond: pd.Series) -> pd.Series:
    """Bars since `cond` was last True (0 on a True bar; NaN before the first)."""
    pos = np.arange(len(cond))
    last = pd.Series(np.where(cond.to_numpy(), pos, np.nan), index=cond.index).ffill()
    return pd.Series(pos, index=cond.index) - last


# ------------------------------------------------------------ signals --------
def _3d_groups(daily_close: pd.Series, bar_anchor: int = 0):
    """Session-grouped 3D bars (the TradingView rule). Returns
    ``(open_dates, close_dates, close_px)`` so callers can reference a bar by its OPEN date
    (TV's bar timestamp) and still know its CLOSE session (needed to align the weekly gate).
    See ``_resample_3d`` for the anchoring rationale."""
    c = daily_close.dropna()
    n = len(c)
    if n == 0:
        empty = c.index[:0]
        return empty, empty, np.array([], dtype="float64")
    gi = np.arange(n) + int(bar_anchor)
    opens = np.empty(n, dtype=bool)
    opens[0] = True
    opens[1:] = (gi[:-1] % 3 == 0)          # a new bar opens the session after a close
    open_pos = np.flatnonzero(opens)
    close_pos = np.append(open_pos[1:] - 1, n - 1)   # each bar closes the session before the next opens
    vals = c.to_numpy()
    return c.index[open_pos], c.index[close_pos], vals[close_pos]


def _resample_3d(daily_close: pd.Series, bar_anchor: int = 0) -> pd.Series:
    """Build the 3D timeframe the way TradingView does: group TRADING SESSIONS (not
    calendar business days) three at a time, anchored so a bar CLOSES whenever the global
    session index is divisible by 3, and label each bar by its OPEN (first session) date —
    matching TV's 3D bar timestamps (verified 5/5 against TradingView NVDA-3D crosshairs).

    ``bar_anchor`` is the global session index — counted from the symbol's FIRST listed
    session (IPO) — of ``daily_close``'s first row. Pass 0 when ``daily_close`` IS the full
    history (the oracle contract / default); pass the offset when feeding a truncated window
    so the phase still matches a full-history TV chart.

    pandas ``resample("3B")`` (what this file used to do) is WRONG: it buckets by the Mon–Fri
    calendar and mis-splits real sessions around every holiday, scrambling which sessions
    share a 3D bar — and therefore every cross. On NVDA that moved ~80% of signal dates."""
    od, _cd, px = _3d_groups(daily_close, bar_anchor)
    return pd.Series(px, index=od, name=getattr(daily_close, "name", None))


def _resample_2w(daily_close: pd.Series, week_parity: int = 0) -> pd.Series:
    """2-week bars = calendar weeks paired two at a time (TV treats 2W as a calendar unit).

    Unlike 3D, the only freedom is the PAIRING PHASE: which weeks share a 2W bar. pandas
    ``resample("2W-FRI")`` anchors that phase to the series' first row, so a TRUNCATED feed
    pairs the opposite weeks from a full-history TV chart. ``week_parity`` (0/1) restores the
    full-history pairing — pass ``ipo_week_parity(feed, sym)`` for a truncated feed. The
    default 0 reproduces ``resample("2W-FRI")`` bar-for-bar on full history (verified).

    Confirmed against TradingView NVDA-2W (2026-06-29): the last CLOSED 2W bar spans the
    weeks ending 2026-06-05 and 2026-06-19 — full history already matches; the 6-yr feed
    needed parity=1. (2W only feeds the fixed=True backtest's ``bear_block``, never live CB/CS.)"""
    wk = daily_close.resample("W-FRI").last().dropna()
    n = len(wk)
    if n == 0:
        return wk
    gi = np.arange(n) + int(week_parity)
    opens = np.empty(n, dtype=bool)
    opens[0] = True
    opens[1:] = (gi[:-1] % 2 == 0)          # a 2W bar closes on even global-week index; next opens after
    close_pos = np.append(np.flatnonzero(opens)[1:] - 1, n - 1)
    return pd.Series(wk.to_numpy()[close_pos], index=wk.index[close_pos], name=wk.name)


def ipo_bar_anchor(feed_close: pd.Series, symbol: str) -> int:
    """The ``bar_anchor`` for a TRUNCATED feed: the global session index (counted from the
    symbol's IPO) of ``feed_close``'s first row, so ``compute_signals`` phases the 3D bars
    to a full-history TradingView chart instead of to the feed's own (arbitrary) start.

    The IPO session calendar is taken from the deep OHLC store (``DATA/<symbol>.parquet``),
    which shares the NYSE calendar with the live Polygon feed (verified bar-for-bar). Returns
    0 when the deep store is unavailable (e.g. the rsync VPS, or a non-US symbol not in the
    store) — the 3D bars are then anchored at the feed's first row: still session-grouped
    (fixing the resample('3B') bug) but possibly phase-shifted vs TV until full history is fed."""
    try:
        full = pd.read_parquet(DATA / f"{symbol}.parquet", columns=["close"]).index
        return int(full.searchsorted(feed_close.dropna().index[0]))
    except Exception:
        return 0


def ipo_week_parity(feed_close: pd.Series, symbol: str) -> int:
    """The ``week_parity`` for a TRUNCATED feed: the parity (0/1) of the global weekly-bar
    index — counted from the symbol's IPO — of the feed's first W-FRI week, so the 2W pairing
    matches a full-history TradingView chart (see ``_resample_2w``). Reads the deep store;
    returns 0 if unavailable (then 2W is anchored at the feed start, possibly off by one week
    — inert for live signals, it only shifts the fixed=True backtest's bear_block)."""
    try:
        full = pd.read_parquet(DATA / f"{symbol}.parquet", columns=["close"])["close"]
        fullwk = full.dropna().resample("W-FRI").last().dropna()
        feedwk = feed_close.dropna().resample("W-FRI").last().dropna()
        return int(fullwk.index.searchsorted(feedwk.index[0])) % 2
    except Exception:
        return 0


def compute_signals(daily_close: pd.Series, bar_anchor: int = 0, week_parity: int = 0) -> pd.DataFrame:
    """All trade-driving signals on the 3D timeframe, with a leak-free weekly
    (confirm-TF) trend gate. Returns a frame indexed by 3D bar OPEN dates.

    ``bar_anchor`` phases the session-grouped 3D bars to the symbol's full-history (IPO)
    anchor — see ``_resample_3d``. ``week_parity`` phases the 2-week confirm gate the same way
    (see ``_resample_2w``). Feed the symbol's FULL daily history (both 0) for TradingView
    parity, or pass ``ipo_bar_anchor`` / ``ipo_week_parity`` for a truncated feed. The weekly
    and monthly confirm timeframes stay plain calendar resamples (W / ME have no phase
    ambiguity; only daily-multiples and 2-week pairs do)."""
    open_dates, close_dates, close_px = _3d_groups(daily_close, bar_anchor)
    if len(open_dates) < 90:
        return pd.DataFrame()
    s3 = pd.Series(close_px, index=open_dates, name=getattr(daily_close, "name", None))

    macd, sig = rsi_macd(s3)
    k, d = stoch_rsi_kd(s3)
    r14 = rsi(s3, RSI_LEN)

    stoch_bull = crossover(k, d)
    stoch_bear = crossunder(k, d)
    macd_bull = crossover(macd, sig)
    macd_bear = crossunder(macd, sig)

    # ---- weekly confirm-TF gate (one step up from a 3D chart = "1W"), leak-free ----
    # Pine: macd_c = request.security(sym,"1W", macd[1], lookahead_off) = the PRIOR fully
    # closed weekly bar as of each 3D bar's CLOSE. Map each 3D bar to that weekly bar by a
    # session-aligned search — NOT shift(1)+ffill, which double-lags to W-2 on mid-week bars.
    wk = daily_close.resample("W-FRI").last().dropna()
    wmacd, wsig = rsi_macd(wk)
    wk_bull = (wmacd >= wsig).to_numpy()
    wk_bear = (wmacd <= wsig).to_numpy()       # inclusive on a tie, like Pine (>= and <=)
    if len(wk_bull):
        wpos = wk.index.searchsorted(close_dates, side="left") - 1   # last weekly closed before the bar
        wok = wpos >= 0
        wci = np.clip(wpos, 0, len(wk_bull) - 1)
        w_bull_on3 = pd.Series(wok & wk_bull[wci], index=open_dates)
        w_bear_on3 = pd.Series(wok & wk_bear[wci], index=open_dates)
    else:
        w_bull_on3 = pd.Series(False, index=open_dates)
        w_bear_on3 = pd.Series(False, index=open_dates)

    # ---- Pine confirmed-signal gates (live defaults) ----
    b1_from_os = d.rolling(CONF_W).min() < OS
    s1_from_ob = d.rolling(CONF_W).max() > OB
    recent_b1 = bars_since(stoch_bull) <= CONF_W
    recent_s1 = bars_since(stoch_bear) <= CONF_W

    confirm_bull = w_bull_on3 | b1_from_os
    confirm_bear = w_bear_on3 | s1_from_ob
    buy_regime_ok = r14 < BUY_RSI_MAX                         # useRsiBuyFilter, useMaGate off
    recent_extended = (k.rolling(CONF_W).max() >= OB) | (r14.rolling(CONF_W).max() >= EXT_RSI)

    cb = macd_bull & recent_b1 & confirm_bull & buy_regime_ok
    cs = macd_bear & recent_s1 & confirm_bear & recent_extended

    # ---- fast-reversal cut-loss / re-buy (the anti-shakeout feature) ----
    rev_exit_sell = macd_bear & (bars_since(cb) <= REV_BARS)   # BUY* failed -> cut long
    rev_exit_buy = macd_bull & (bars_since(cs) <= REV_BARS)    # SELL* failed -> re-buy

    # ===================== THE TWO FIXES (gates; toggled in simulate) =====================
    # 200-day MA, true daily MA mapped onto 3D bars (leak-free).
    ma200 = daily_close.rolling(200).mean()
    above200 = (s3 > ma200.reindex(s3.index).ffill()).fillna(False)
    # Monthly (investor-cycle) RSI-MACD trend, prior CLOSED month (no repaint).
    mo = daily_close.resample("ME").last().dropna()
    mmacd, msig = rsi_macd(mo)
    mo_bull = (mmacd >= msig).shift(1).reindex(s3.index, method="ffill").fillna(False).astype(bool)
    # 2-week RSI-MACD -- the IC-bottom RE-ENABLE the user proposed (TV-phased; see _resample_2w).
    w2 = _resample_2w(daily_close, week_parity)
    w2macd, w2sig = rsi_macd(w2)
    w2_bull = (w2macd >= w2sig).shift(1).reindex(s3.index, method="ffill").fillna(False).astype(bool)

    # PROBLEM 2 (shaken out longing bounces in a monthly bear): in a monthly bear
    # BELOW the 200d, block new longs UNTIL the 2W MACD turns up (IC-bottom confluence).
    bear_block = (~mo_bull) & (~above200) & (~w2_bull)
    # PROBLEM 1 (over-sells in a bull, can't re-buy): in a confirmed bull (weekly+
    # monthly up, above 200d) HOLD through oscillator-top sells. Cut-loss stays on.
    strong_bull = (w_bull_on3 & mo_bull & above200)

    return pd.DataFrame({
        "close": s3, "macd": macd, "sig": sig, "k": k, "d": d, "rsi14": r14,
        "CB": cb.fillna(False), "CS": cs.fillna(False),
        "revBuy": rev_exit_buy.fillna(False), "revSell": rev_exit_sell.fillna(False),
        "w_bull": w_bull_on3, "above200": above200, "mo_bull": mo_bull,
        "w2_bull": w2_bull, "bear_block": bear_block, "strong_bull": strong_bull,
    })


# ------------------------------------------------------------ trade sim ------
def simulate(sig: pd.DataFrame, fixed: bool = False) -> dict:
    """Long/flat as the user trades it: enter on CB or re-buy, exit on CS or cut.
    Fills at the NEXT 3D bar's close (conservative, no look-ahead).
    fixed=True applies the two regime/cycle gates (bear-block + hold-through-bull)."""
    rows = sig.dropna(subset=["macd", "sig", "k", "d", "rsi14"])
    if len(rows) < 20:
        return {}
    dates = rows.index.to_list()
    px = rows["close"]
    if fixed:
        # PROBLEM 2: no new longs while bear-blocked.  PROBLEM 1: hold through
        # oscillator-top sells in a strong bull (cut-loss still fires).
        enter = ((rows["CB"] | rows["revBuy"]) & ~rows["bear_block"]).to_numpy()
        exit_ = ((rows["CS"] & ~rows["strong_bull"]) | rows["revSell"]).to_numpy()
    else:
        enter = (rows["CB"] | rows["revBuy"]).to_numpy()
        exit_ = (rows["CS"] | rows["revSell"]).to_numpy()

    pos = 0
    entry_px = entry_dt = None
    trades = []
    equity = [1.0]
    eq = 1.0
    for i in range(len(rows) - 1):
        nxt = float(px.iloc[i + 1])
        # mark-to-market the open position on this bar's move
        if pos == 1:
            eq *= float(px.iloc[i + 1]) / float(px.iloc[i])
        equity.append(eq)
        if pos == 0 and enter[i]:
            pos = 1
            entry_px, entry_dt = nxt, dates[i + 1]
        elif pos == 1 and exit_[i]:
            ret = nxt / entry_px - 1
            trades.append((entry_dt, dates[i + 1], ret))
            pos = 0
    if pos == 1:  # close any open trade at the last bar
        ret = float(px.iloc[-1]) / entry_px - 1
        trades.append((entry_dt, dates[-1], ret))

    if not trades:
        return {"n": 0}
    rets = np.array([t[2] for t in trades])
    wins = rets[rets > 0]
    losses = rets[rets <= 0]
    eq_curve = np.array(equity)
    dd = (eq_curve / np.maximum.accumulate(eq_curve) - 1).min()
    bh = float(px.iloc[-1]) / float(px.iloc[0]) - 1
    bh_curve = (px / float(px.iloc[0])).to_numpy()
    bh_dd = (bh_curve / np.maximum.accumulate(bh_curve) - 1).min()
    span_yrs = (dates[-1] - dates[0]).days / 365.25
    in_mkt = sum((t[1] - t[0]).days for t in trades) / max((dates[-1] - dates[0]).days, 1)
    return {
        "n": len(trades),
        "wr": round(100 * (rets > 0).mean(), 1),
        "avg_win": round(100 * wins.mean(), 2) if len(wins) else 0.0,
        "avg_loss": round(100 * losses.mean(), 2) if len(losses) else 0.0,
        "expectancy": round(100 * rets.mean(), 2),
        "profit_factor": round(wins.sum() / -losses.sum(), 2) if losses.sum() < 0 else float("inf"),
        "strat_ret": round(100 * (eq_curve[-1] - 1), 1),
        "bh_ret": round(100 * bh, 1),
        "max_dd": round(100 * dd, 1),
        "bh_max_dd": round(100 * bh_dd, 1),
        "in_mkt_pct": round(100 * in_mkt, 0),
        "yrs": round(span_yrs, 1),
        "worst": round(100 * rets.min(), 1),
        "best": round(100 * rets.max(), 1),
    }


HDR = (f"{'ticker':8s}{'trades':>7s}{'WR%':>7s}{'expect':>8s}{'PF':>6s}"
       f"{'strat%':>9s}{'B&H%':>9s}{'maxDD':>7s}{'inMkt':>6s}")


def _print_table(label: str, results: list[tuple[str, dict]]) -> None:
    print(f"\n===== {label} =====")
    print(HDR)
    print("-" * len(HDR))
    for t, m in results:
        print(f"{t:8s}{m['n']:>7d}{m['wr']:>7}{m['expectancy']:>8}{m['profit_factor']:>6}"
              f"{m['strat_ret']:>9}{m['bh_ret']:>9}{m['max_dd']:>7}{m['in_mkt_pct']:>6}")
    if results:
        ms = [m for _, m in results]
        wts = [m["n"] for m in ms]
        wr = np.average([m["wr"] for m in ms], weights=wts)
        dd = np.mean([m["max_dd"] for m in ms])
        bhdd = np.mean([m["bh_max_dd"] for m in ms])
        pf = np.median([m["profit_factor"] for m in ms if np.isfinite(m["profit_factor"])])
        beat = sum(m["strat_ret"] > m["bh_ret"] for m in ms)
        beatdd = sum(m["max_dd"] > m["bh_max_dd"] for m in ms)   # less negative = shallower DD
        print("-" * len(HDR))
        print(f"  pooled WR {round(wr,1)}%  | avg maxDD {round(dd,1)}% vs B&H {round(bhdd,1)}%  | "
              f"median PF {round(pf,2)}  | beats B&H ret {beat}/{len(ms)}  | shallower DD than B&H {beatdd}/{len(ms)}")


def run(tickers: list[str]) -> None:
    avail = {Path(p).stem for p in glob.glob(str(DATA / "*.parquet"))}
    tickers = [t for t in tickers if t in avail]
    if not tickers:
        print("none of the requested tickers are in data/stocks/. available sample:",
              sorted(avail)[:20])
        return
    base, fix = [], []
    for t in tickers:
        sig = compute_signals(pd.read_parquet(DATA / f"{t}.parquet")["close"].dropna())
        if sig.empty:
            continue
        mb, mf = simulate(sig, fixed=False), simulate(sig, fixed=True)
        if mb.get("n"):
            base.append((t, mb))
        if mf.get("n"):
            fix.append((t, mf))
    _print_table("BASELINE (Pine as-is, mechanical)", base)
    _print_table("WITH THE TWO FIXES (bear-block + hold-through-bull)", fix)


if __name__ == "__main__":
    req = sys.argv[1:] or ["AAPL", "AMD", "AMZN", "AVGO", "NVDA", "META",
                           "MSFT", "TSLA", "GOOGL", "CRM"]
    run(req)

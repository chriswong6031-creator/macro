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
def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    """Wilder's RSI (== Pine ta.rsi == engine.technicals.rsi)."""
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, min_periods=n).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, min_periods=n).mean()
    rs = up / dn.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def ema(s: pd.Series, span: int) -> pd.Series:
    return s.ewm(span=span, min_periods=span).mean()


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
def compute_signals(daily_close: pd.Series) -> pd.DataFrame:
    """All trade-driving signals on the 3D timeframe, with a leak-free weekly
    (confirm-TF) trend gate. Returns a frame indexed by 3D bar dates."""
    s3 = daily_close.resample("3B").last().dropna()
    if len(s3) < 90:
        return pd.DataFrame()

    macd, sig = rsi_macd(s3)
    k, d = stoch_rsi_kd(s3)
    r14 = rsi(s3, RSI_LEN)

    stoch_bull = crossover(k, d)
    stoch_bear = crossunder(k, d)
    macd_bull = crossover(macd, sig)
    macd_bear = crossunder(macd, sig)

    # ---- weekly confirm-TF gate (one step up from 3D), leak-free ----
    wk = daily_close.resample("W-FRI").last().dropna()
    wmacd, wsig = rsi_macd(wk)
    w_bull = (wmacd >= wsig).shift(1)          # use the PRIOR closed week (no repaint)
    w_bull_on3 = w_bull.reindex(s3.index, method="ffill").fillna(False).astype(bool)
    w_bear_on3 = (~w_bull_on3)

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
    # 2-week RSI-MACD -- the IC-bottom RE-ENABLE the user proposed.
    w2 = daily_close.resample("2W-FRI").last().dropna()
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

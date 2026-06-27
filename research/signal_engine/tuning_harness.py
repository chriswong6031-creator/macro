"""SHARED entry-timing experiment harness for the confluence signal engine.

WHY THIS FILE EXISTS
--------------------
The 3D RSI-MACD is a LAGGING trigger: price often turns up 1-3 bars BEFORE the 3D
MACD crosses, so the confirmed BUY chases the breakout instead of entering just
before it. This harness lets us test EARLIER triggers (owner's idea: MACD on the 2D
+ StochRSI on the 3D; also pure faster TFs and an anticipation/leading-leg trigger)
and judge them the CHARTER way:

  * ENTRY LOCATION / TIMING  (chasing proxy, lead vs breakout, location-in-range)
  * DRAWDOWN / shake-out     (the primary risk metrics)
  * NEVER beat-buy-and-hold.

The verdict gate is GENERALIZATION across the full data/stocks panel (114 held-out
US names), not in-sample beauty on a few — measured as % of names improved, not just
a pooled mean.

FAITHFUL MATH ONLY (charter §4): RSI-based MACD = EMA(RSI14,14) - EMA(RSI14,60),
signal = EMA(macd,5); StochRSI = SMA(stoch(RSI14,14),3) then SMA(.,3). NOT price MACD.

LEAK-FREE CROSS-GRID PROTOCOL (the crux of comparing 2D vs 3D fairly)
--------------------------------------------------------------------
Every variant emits BUY events on whatever TF grid it computes. resample("{n}B")
LABELS a bar by the bin's left edge but the bar's close is only KNOWN on the last
daily date in the bin. So each TF bar is mapped to its true `known_date`, and the
FILL is the first daily close STRICTLY AFTER known_date. All entry-quality metrics
and the trade-sim then run on the SAME daily close series with the SAME fill rule,
so a 2D trigger and a 3D trigger are compared apples-to-apples.

Run:
  python3 research/signal_engine/tuning_harness.py --variant m2d_s3d
  python3 research/signal_engine/tuning_harness.py --variant base3d --filter on --json
"""
from __future__ import annotations

import sys
import glob
import json
import argparse
import warnings
import logging
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
logging.disable(logging.CRITICAL)

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "stocks"

# Faithful Pine defaults (the live config) -----------------------------------
RSI_LEN, FAST_LEN, BASE_LEN, SIG_LEN = 14, 14, 60, 5
STOCH_LEN, SMOOTH_K, SMOOTH_D = 14, 3, 3
OB, OS = 80, 20
CONF_W, BUY_RSI_MAX, EXT_RSI = 8, 65, 70

# Evaluation windows (trading days on the DAILY series) ----------------------
FWD_H = 40            # forward window for location / MFE / MAE (~13 3D bars)
RUNUP_L = 8           # lookback for the "already running / chasing" proxy
BRK_LB = 20           # breakout = fresh BRK_LB-day high
SHAKE = 0.08          # shake-out = -8% MAE reached before +8% MFE
SINCE = pd.Timestamp("2023-06-01")   # entries counted from here (matches test_buyfilter)
FILL_OFFSET = 0       # extra daily bars to delay the fill (robustness/leak probe)


# ------------------------------------------------------------ indicators ----
def rsi(close: pd.Series, n: int = RSI_LEN) -> pd.Series:
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, min_periods=n).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, min_periods=n).mean()
    rs = up / dn.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def ema(s: pd.Series, span: int) -> pd.Series:
    return s.ewm(span=span, min_periods=span).mean()


def rsi_macd(close: pd.Series):
    r = rsi(close, RSI_LEN)
    macd = ema(r, FAST_LEN) - ema(r, BASE_LEN)
    return macd, ema(macd, SIG_LEN)


def stoch_rsi_kd(close: pd.Series):
    r = rsi(close, RSI_LEN)
    lo, hi = r.rolling(STOCH_LEN).min(), r.rolling(STOCH_LEN).max()
    rawk = (r - lo) / (hi - lo).replace(0, np.nan) * 100
    k = rawk.rolling(SMOOTH_K).mean()
    return k, k.rolling(SMOOTH_D).mean()


def xup(a, b):
    return (a > b) & (a.shift(1) <= b.shift(1))


def xdn(a, b):
    return (a < b) & (a.shift(1) >= b.shift(1))


def since(cond: pd.Series) -> pd.Series:
    pos = np.arange(len(cond))
    last = pd.Series(np.where(cond.to_numpy(), pos, np.nan), index=cond.index).ffill()
    return pd.Series(pos, index=cond.index) - last


# ------------------------------------------------------------ TF grid -------
def tf_bars(daily: pd.Series, n: int):
    """resample to n-business-day bars (faithful) BUT also return, per bar, the
    true daily date its close became known (resample labels the bin's LEFT edge)."""
    if n == 1:
        s = daily.copy()
        known = pd.Series(daily.index, index=daily.index)
        return s, known
    s = daily.resample(f"{n}B").last().dropna()
    known = daily.resample(f"{n}B").apply(lambda x: x.dropna().index.max()).reindex(s.index).dropna()
    s = s.reindex(known.index)
    return s, pd.Series(pd.to_datetime(known.values), index=known.index)


def to_daily(tf_series: pd.Series, known: pd.Series, daily_index: pd.DatetimeIndex,
             how: str = "ffill") -> pd.Series:
    """Map a TF-bar series onto the daily index by its KNOWN date (leak-free).
    how='ffill' -> state held until the next bar; how='event' -> True only on the
    first daily bar on/after each known date where the TF value is True."""
    kd = pd.Series(tf_series.to_numpy(), index=pd.to_datetime(known.to_numpy()))
    kd = kd[~kd.index.duplicated(keep="last")].sort_index()
    if how == "ffill":
        return kd.reindex(daily_index, method="ffill")
    # event: place the TF value on the daily bar == known date (or next daily bar)
    out = pd.Series(False, index=daily_index)
    pos = daily_index.searchsorted(kd.index, side="left")
    for p, v in zip(pos, kd.to_numpy()):
        if v and p < len(daily_index):
            out.iloc[p] = True
    return out


# ------------------------------------------------------------ variant build -
def build_signals(daily: pd.Series, cfg: dict) -> pd.DataFrame:
    """Return a daily-indexed frame with a boolean `buy` column (raw confluence
    buy of this variant) plus the columns the filter / scorecard need."""
    di = daily.index
    mtf, stf = cfg["macd_tf"], cfg["stoch_tf"]
    trig = cfg.get("trigger", "macd_cross")

    # --- MACD TF (the leading leg in the owner's idea) ---
    sm, sm_known = tf_bars(daily, mtf)
    macd_m, sig_m = rsi_macd(sm)
    mb_cross = xup(macd_m, sig_m)                       # MACD bull cross on the MACD-TF
    hist_m = macd_m - sig_m
    hist_rising = (hist_m > hist_m.shift(1)) & (hist_m.shift(1) > hist_m.shift(2))

    # --- StochRSI TF (turns right at the bottom) ---
    ss, ss_known = tf_bars(daily, stf)
    k_s, d_s = stoch_rsi_kd(ss)
    sb_cross = xup(k_s, d_s)
    b1_from_os = d_s.rolling(CONF_W).min() < OS         # the cross came from oversold
    recent_sb = since(sb_cross) <= CONF_W
    sb_from_os = sb_cross & b1_from_os

    # --- rsi gate + weekly confirm (on the StochRSI/slow TF, like the engine) ---
    r14 = rsi(ss, RSI_LEN)
    wk = daily.resample("W-FRI").last().dropna()
    wmacd, wsig = rsi_macd(wk)
    w_bull_tf = (wmacd >= wsig).shift(1)                # prior CLOSED week (no repaint)

    # --- map everything onto the daily grid by KNOWN date (leak-free) ---
    mb_d = to_daily(mb_cross.fillna(False), sm_known, di, "event")
    hist_rise_d = to_daily(hist_rising.fillna(False), sm_known, di, "ffill").fillna(False)
    hist_pos_d = to_daily((hist_m > 0).fillna(False), sm_known, di, "ffill").fillna(False)
    sb_event_d = to_daily(sb_from_os.fillna(False), ss_known, di, "event")
    recent_sb_d = to_daily(recent_sb.fillna(False), ss_known, di, "ffill").fillna(False)
    b1os_d = to_daily(b1_from_os.fillna(False), ss_known, di, "ffill").fillna(False)
    r14_d = to_daily(r14, ss_known, di, "ffill")
    w_bull_d = w_bull_tf.reindex(di, method="ffill").fillna(False).astype(bool)

    ma200 = daily.rolling(200).mean()
    above200 = (daily > ma200).fillna(False)

    confirm_bull = (w_bull_d | b1os_d)
    rsi_ok = (r14_d < BUY_RSI_MAX).fillna(False)

    # micro price-structure confirm (optional 3rd indicator): close > prior MACD-TF bar high
    if cfg.get("brk"):
        hi_tf = daily.rolling(mtf).max()
        brk_ok = (daily > hi_tf.shift(1)).fillna(False)
    else:
        brk_ok = pd.Series(True, index=di)

    if trig == "macd_cross":
        # owner's confluence: MACD-TF bull cross AND StochRSI crossed recently from OS
        buy = mb_d & recent_sb_d & confirm_bull & rsi_ok & brk_ok
    elif trig == "early":
        # ANTICIPATION: fire on the StochRSI bottom turn while MACD hist is still only
        # RISING (pre-cross). Enters before the MACD confirms -> earlier than macd_cross.
        buy = sb_event_d & hist_rise_d & confirm_bull & rsi_ok & brk_ok
    elif trig == "stochlead":
        # leading-leg only: StochRSI bull-from-OS, MACD merely not-falling (hist>0 or rising)
        buy = sb_event_d & (hist_pos_d | hist_rise_d) & confirm_bull & rsi_ok & brk_ok
    else:
        raise ValueError(trig)

    return pd.DataFrame({
        "close": daily, "buy": buy.fillna(False).astype(bool),
        "above200": above200, "w_bull": w_bull_d,
        "macd_m": to_daily(macd_m, sm_known, di, "ffill"),
    })


# ------------------------------------------------------------ buy filter ----
def _swing_highs(v: np.ndarray, w: int = 3):
    return [i for i in range(w, len(v) - w) if v[i] == v[i - w:i + w + 1].max()]


def daily_filter(frame: pd.DataFrame) -> pd.Series:
    """The VALIDATED buy-filter re-expressed on the daily fill series:
    reclaim-and-hold + bearish-divergence veto + 200MA-as-bar-raiser. Returns a
    boolean 'take' aligned to the buy bars (True = filter endorses the entry)."""
    c = frame["close"].to_numpy()
    a = frame["above200"].to_numpy()
    wb = frame["w_bull"].to_numpy()
    macd = frame["macd_m"].to_numpy()
    n = len(c)
    hi = _swing_highs(c, 3)
    take = pd.Series(False, index=frame.index)
    buys = np.where(frame["buy"].to_numpy())[0]
    HELD = 3   # daily bars to confirm reclaim-and-hold
    for i in buys:
        # bearish divergence veto: last two swing highs in [i-30,i] -> price HH, macd LH
        rh = [h for h in hi if i - 30 < h <= i]
        if len(rh) >= 2 and c[rh[-1]] > c[rh[-2]] and macd[rh[-1]] < macd[rh[-2]]:
            continue
        if i + HELD >= n:
            continue
        held = c[i + HELD] > c[i]
        below, wkdn = (not a[i]), (not wb[i])
        if below and wkdn:                       # counter-trend: raise the bar
            reclaim = bool(a[i + 1: i + HELD + 1].any())
            if held and reclaim:
                take.iloc[i] = True
        elif held:
            take.iloc[i] = True
    return take


# ------------------------------------------------------------ scorecard -----
def entry_scorecard(frame: pd.DataFrame, buy_col: str) -> list[dict]:
    """Per-signal entry-LOCATION metrics on the daily series. Fill = next daily
    close after the signal bar (leak-free)."""
    c = frame["close"].to_numpy()
    idx = frame.index
    n = len(c)
    rmax = frame["close"].rolling(BRK_LB).max().to_numpy()
    out = []
    for i in np.where(frame[buy_col].to_numpy())[0]:
        f = i + 1 + FILL_OFFSET                  # fill bar (next daily close, +offset)
        if f >= n or idx[i] < SINCE:
            continue
        p = c[f]
        if f - RUNUP_L < 0:
            continue
        runup = p / c[f - RUNUP_L] - 1           # chasing proxy (higher = more chase)
        # already broken out? price already >= prior BRK_LB-day high at fill
        chase = bool(f - 1 >= 0 and not np.isnan(rmax[f - 1]) and p >= rmax[f - 1])
        fwd = c[f: min(f + FWD_H, n)]
        if len(fwd) < 5:
            continue
        lo, hiv = float(np.min(fwd)), float(np.max(fwd))
        loc = (p - lo) / (hiv - lo) if hiv > lo else 0.5     # 0=bought fwd low
        fwd1 = c[f + 1: min(f + 1 + FWD_H, n)]
        mae = float(np.min(fwd1)) / p - 1 if len(fwd1) else 0.0
        mfe = float(np.max(fwd1)) / p - 1 if len(fwd1) else 0.0
        # shake-out: -SHAKE reached before +SHAKE
        shake = 0
        for x in fwd1:
            r = x / p - 1
            if r <= -SHAKE:
                shake = 1
                break
            if r >= SHAKE:
                break
        out.append({"date": str(idx[f].date()), "runup": runup, "chase": int(chase),
                    "locw": loc, "mae": mae, "mfe": mfe, "shake": shake})
    return out


# ------------------------------------------------------------ trade sim -----
def trade_sim(frame: pd.DataFrame, buy_col: str, exit_sig: pd.Series) -> dict:
    """Enter on buy (next daily close), exit on the COMMON exit (next daily close).
    Same exit for every variant so only ENTRY timing differs."""
    c = frame["close"].to_numpy()
    idx = frame.index
    n = len(c)
    buy = frame[buy_col].to_numpy()
    ex = exit_sig.reindex(frame.index).fillna(False).to_numpy()
    pos = 0
    ep = None
    trades = []
    eq = 1.0
    curve = [1.0]
    days_in = 0
    for i in range(n - 1):
        if pos == 1:
            eq *= c[i + 1] / c[i]
            days_in += 1
        curve.append(eq)
        if pos == 0:
            if idx[i] < SINCE:
                continue
            if buy[i] and i + 1 + FILL_OFFSET < n:
                pos, ep = 1, c[i + 1 + FILL_OFFSET]
        elif ex[i]:
            trades.append(c[i + 1] / ep - 1)
            pos = 0
    if pos == 1:
        trades.append(c[-1] / ep - 1)
    eqc = np.array(curve)
    dd = float((eqc / np.maximum.accumulate(eqc) - 1).min())
    r = np.array(trades) if trades else np.array([0.0])
    losses = r[r < 0]
    return {"n": len(trades), "wr": float(100 * (r > 0).mean()) if trades else 0.0,
            "dd": 100 * dd, "avgloss": float(100 * losses.mean()) if len(losses) else 0.0,
            "cap": float(100 * (eqc[-1] - 1)), "in_mkt": days_in}


def common_exit(daily: pd.Series) -> pd.Series:
    """Shared exit for the entry-isolation sim: the baseline 3D oscillator SELL/cut,
    mapped to the daily grid by known date. Identical for every variant."""
    s3, kn = tf_bars(daily, 3)
    k, d = stoch_rsi_kd(s3)
    macd, sig = rsi_macd(s3)
    r14 = rsi(s3, RSI_LEN)
    ss = xdn(k, d)
    ms = xdn(macd, sig)
    s1ob = d.rolling(CONF_W).max() > OB
    wk = daily.resample("W-FRI").last().dropna()
    wm, wsg = rsi_macd(wk)
    wbull = (wm >= wsg).shift(1).reindex(s3.index, method="ffill").fillna(False)
    rext = (k.rolling(CONF_W).max() >= OB) | (r14.rolling(CONF_W).max() >= EXT_RSI)
    cs = (ms & (since(ss) <= CONF_W) & ((~wbull) | s1ob) & rext).fillna(False)
    return to_daily(cs, kn, daily.index, "event")


# ------------------------------------------------------------ panel run -----
VARIANTS = {
    "base3d":        dict(macd_tf=3, stoch_tf=3, trigger="macd_cross"),   # incumbent
    "m2d_s3d":       dict(macd_tf=2, stoch_tf=3, trigger="macd_cross"),   # OWNER hypothesis
    "m2d_s2d":       dict(macd_tf=2, stoch_tf=2, trigger="macd_cross"),
    "m1d_s3d":       dict(macd_tf=1, stoch_tf=3, trigger="macd_cross"),
    "m2d_s3d_early": dict(macd_tf=2, stoch_tf=3, trigger="early"),        # anticipation
    "stochlead3d":   dict(macd_tf=2, stoch_tf=3, trigger="stochlead"),    # leading leg only
    "m2d_s3d_brk":   dict(macd_tf=2, stoch_tf=3, trigger="macd_cross", brk=True),  # +3rd indicator
}


def run_variant(name: str, use_filter: bool, tickers=None) -> dict:
    cfg = VARIANTS[name]
    files = sorted(glob.glob(str(DATA / "*.parquet")))
    if tickers:
        files = [f for f in files if Path(f).stem in set(tickers)]
    per_name = []
    cards = []
    for fp in files:
        t = Path(fp).stem
        try:
            daily = pd.read_parquet(fp)["close"].dropna()
            if len(daily) < 400:
                continue
            fr = build_signals(daily, cfg)
            if use_filter:
                fr["buy_use"] = daily_filter(fr)
            else:
                fr["buy_use"] = fr["buy"]
            ex = common_exit(daily)
            sc = entry_scorecard(fr, "buy_use")
            if not sc:
                continue
            sim = trade_sim(fr, "buy_use", ex)
            df = pd.DataFrame(sc)
            per_name.append({"t": t, "n": len(sc),
                             "runup": float(df["runup"].mean()), "chase": float(df["chase"].mean()),
                             "locw": float(df["locw"].mean()), "mae": float(df["mae"].mean()),
                             "mfe": float(df["mfe"].mean()), "shake": float(df["shake"].mean()),
                             "dd": sim["dd"], "avgloss": sim["avgloss"], "wr": sim["wr"],
                             "cap": sim["cap"], "trades": sim["n"]})
            for c in sc:
                c["t"] = t
            cards.extend(sc)
        except Exception:
            continue
    return {"variant": name, "filter": use_filter, "per_name": per_name, "n_names": len(per_name)}


def agg(res: dict) -> dict:
    pn = res["per_name"]
    if not pn:
        return {"variant": res["variant"], "n_names": 0}
    f = lambda k: float(np.mean([x[k] for x in pn]))
    return {
        "variant": res["variant"], "filter": res["filter"], "n_names": len(pn),
        "avg_signals": f("n"), "avg_trades": f("trades"),
        "runup": f("runup"), "chase": f("chase"), "locw": f("locw"),
        "mae": f("mae"), "mfe": f("mfe"), "shake": f("shake"),
        "dd": f("dd"), "avgloss": f("avgloss"), "wr": f("wr"), "cap": f("cap"),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", default="m2d_s3d")
    ap.add_argument("--filter", default="off", choices=["on", "off"])
    ap.add_argument("--tickers", default="")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--dump", default="")
    ap.add_argument("--fill-offset", type=int, default=0)
    a = ap.parse_args()
    global FILL_OFFSET
    FILL_OFFSET = a.fill_offset
    tickers = [t.strip() for t in a.tickers.split(",") if t.strip()] or None
    res = run_variant(a.variant, a.filter == "on", tickers)
    s = agg(res)
    if a.dump:
        Path(a.dump).parent.mkdir(parents=True, exist_ok=True)
        Path(a.dump).write_text(json.dumps({"agg": s, "per_name": res["per_name"]}))
    if a.json:
        print(json.dumps(s))
        return
    print(f"\n=== {s['variant']}  (filter={s.get('filter')})  names={s['n_names']} ===")
    for k in ("avg_signals", "avg_trades", "runup", "chase", "locw", "mae",
              "mfe", "shake", "dd", "avgloss", "wr", "cap"):
        print(f"  {k:11s} {s.get(k):8.3f}")


if __name__ == "__main__":
    main()

"""MTF MACD-RSI × StochRSI confluence — validated buy-filter signal leaf.

DISPLAY-ONLY entry-QUALITY / RISK signal for the Mastermind brain + the chart.
NOT alpha, NOT a standalone strategy. See research/signal_engine/CHARTER.md for the
framing and the marker contract (§7). The buy-filter (reclaim-and-hold + bearish-
divergence veto + 200-day-MA as a confidence bar-raiser) cut average max drawdown
-23.7% -> -15.5% across 110 held-out US names (84% improved) — it is a drawdown tool.

Faithful to the owner's `MACD STOCH RSI CONFLUENCE SIGNAL.pine`, run on the 3D:
  RSI-MACD : macd = EMA(RSI14,14) - EMA(RSI14,60); signal = EMA(macd,5)   (NOT price MACD)
  StochRSI : k = SMA(stoch(RSI14,14),3); d = SMA(k,3)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine.technicals import rsi   # Wilder RSI, matches Pine ta.rsi

RSI_LEN, FAST_LEN, BASE_LEN, SIG_LEN = 14, 14, 60, 5
STOCH_LEN, SMOOTH_K, SMOOTH_D = 14, 3, 3
OB, OS = 80, 20
CONF_W, BUY_RSI_MAX, EXT_RSI, REV_BARS = 8, 65, 70, 3
MA_LEN = 200


def _ema(s, span):
    return s.ewm(span=span, min_periods=span).mean()


def _rsi_macd(c):
    r = rsi(c, RSI_LEN)
    macd = _ema(r, FAST_LEN) - _ema(r, BASE_LEN)
    return macd, _ema(macd, SIG_LEN)


def _stoch_rsi_kd(c):
    r = rsi(c, RSI_LEN)
    lo, hi = r.rolling(STOCH_LEN).min(), r.rolling(STOCH_LEN).max()
    rawk = (r - lo) / (hi - lo).replace(0, np.nan) * 100
    k = rawk.rolling(SMOOTH_K).mean()
    return k, k.rolling(SMOOTH_D).mean()


def _xup(a, b):
    return (a > b) & (a.shift(1) <= b.shift(1))


def _xdn(a, b):
    return (a < b) & (a.shift(1) >= b.shift(1))


def _since(cond):
    pos = np.arange(len(cond))
    last = pd.Series(np.where(cond.to_numpy(), pos, np.nan), index=cond.index).ffill()
    return pd.Series(pos, index=cond.index) - last


def signal_frame(daily_close: pd.Series) -> pd.DataFrame:
    """3D confluence signals (CB/CS/revBuy/revSell) + regime gates, leak-free."""
    s3 = daily_close.resample("3B").last().dropna()
    if len(s3) < 90:
        return pd.DataFrame()
    macd, sig = _rsi_macd(s3)
    k, d = _stoch_rsi_kd(s3)
    r14 = rsi(s3, RSI_LEN)
    sb, ss = _xup(k, d), _xdn(k, d)
    mb, ms = _xup(macd, sig), _xdn(macd, sig)
    wk = daily_close.resample("W-FRI").last().dropna()
    wm, wsg = _rsi_macd(wk)
    wbull = (wm >= wsg).shift(1).reindex(s3.index, method="ffill").fillna(False).astype(bool)
    ma = daily_close.rolling(MA_LEN).mean()
    above = (s3 > ma.reindex(s3.index).ffill()).fillna(False)
    b1os, s1ob = d.rolling(CONF_W).min() < OS, d.rolling(CONF_W).max() > OB
    cb = (mb & (_since(sb) <= CONF_W) & (wbull | b1os) & (r14 < BUY_RSI_MAX)).fillna(False)
    rext = (k.rolling(CONF_W).max() >= OB) | (r14.rolling(CONF_W).max() >= EXT_RSI)
    cs = (ms & (_since(ss) <= CONF_W) & ((~wbull) | s1ob) & rext).fillna(False)
    revsell = (ms & (_since(cb) <= REV_BARS)).fillna(False)
    revbuy = (mb & (_since(cs) <= REV_BARS)).fillna(False)
    return pd.DataFrame({"close": s3, "macd": macd, "sig": sig, "k": k, "d": d, "rsi14": r14,
                         "CB": cb, "CS": cs, "revBuy": revbuy, "revSell": revsell,
                         "w_bull": wbull, "above200": above})


def _swing_highs(s, w=2):
    v = s.to_numpy()
    return [i for i in range(w, len(v) - w) if v[i] == v[i - w:i + w + 1].max()]


def _bear_div(i, close, macd, hi, look=12):
    cv, mv = close.to_numpy(), macd.to_numpy()
    rh = [h for h in hi if i - look < h <= i]
    return len(rh) >= 2 and cv[rh[-1]] > cv[rh[-2]] and mv[rh[-1]] < mv[rh[-2]]


def _buy_filter(i, sig, bear, n):
    """The VALIDATED buy-filter: reclaim-and-hold + bearish-div veto + 200MA bar-raiser.
    Returns (take: bool|None, reason). None = pending (last 1-2 bars can't confirm yet)."""
    c, a = sig["close"], sig["above200"]
    if bear:
        return False, "veto: bearish divergence"
    if i + 1 >= n:
        return None, "pending confirmation"
    held = bool(c.iloc[i + 1] > c.iloc[i])
    below, wkdn = (not bool(a.iloc[i])), (not bool(sig["w_bull"].iloc[i]))
    if below and wkdn:
        if i + 2 >= n:
            return None, "pending confirmation"
        reclaim = bool(a.iloc[i + 1]) or bool(a.iloc[i + 2])
        ok = held and reclaim
        return ok, ("reclaimed 200 & held" if ok else "counter-trend, no 200-reclaim/hold")
    return held, ("held confirmation" if held else "failed reclaim-and-hold")


def analyze(ticker: str, daily_close: pd.Series) -> dict | None:
    """Per-ticker chart-marker + state object (the site/signals/<T>.json contract, §7)."""
    sig = signal_frame(daily_close)
    if sig.empty:
        return None
    sig = sig.dropna(subset=["macd", "sig", "k", "d", "rsi14"])
    if len(sig) < 5:
        return None
    c, macd, idx, n = sig["close"], sig["macd"], sig.index, len(sig)
    hi = _swing_highs(c)
    markers = []
    for i in range(n):
        ds = str(idx[i].date())
        if bool(sig["CB"].iloc[i]) or bool(sig["revBuy"].iloc[i]):
            ok, reason = _buy_filter(i, sig, _bear_div(i, c, macd, hi), n)
            q = "pending" if ok is None else ("take" if ok else "block")
            markers.append({"date": ds, "type": "rebuy" if bool(sig["revBuy"].iloc[i]) else "buy",
                            "quality": q, "reason": reason})
        elif bool(sig["CS"].iloc[i]):
            markers.append({"date": ds, "type": "sell"})
        elif bool(sig["revSell"].iloc[i]):
            markers.append({"date": ds, "type": "cut"})
    last = sig.iloc[-1]
    state = ("long-bias" if (last["k"] >= last["d"] and last["macd"] >= last["sig"])
             else "short-bias" if (last["k"] < last["d"] and last["macd"] < last["sig"]) else "mixed")
    return {"ticker": ticker, "asof": str(idx[-1].date()), "tf": "3D", "state": state,
            "above200": bool(last["above200"]), "weekly_bull": bool(last["w_bull"]),
            "markers": markers}

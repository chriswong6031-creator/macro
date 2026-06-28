"""The owner's WEIGHTED tier cascade for the Standout grids — extends signal_gate.

A single signal is one DOOR in a cascade (the sector-cycle engine + the owner's
leadership/rotation read are the other doors); this grades a name into the owner's
ladder, strongest-confirmed -> earliest, each tier weighted by its held-out balance of
earliness-vs-stop-out (research/signal_engine/TIERED_CASCADE.md, 110 held-out US names):

  TIER  WEIGHT  definition                                              held-out stop-out
  T1    1.00    3D MACD-RSI x 3D StochRSI, buy-filter endorsed (master)   38.3%   (= signal_gate TAKE)
  T2    0.80    2D MACD-RSI cross  & 3D StochRSI crossed (recent)         40.6%
  T3    0.60    2D MACD-RSI PROJECTED<=1-2d & 3D StochRSI already crossed 42.3%   (the early prediction)
  T4    0.40    2D MACD-RSI PROJECTED & 2D StochRSI crossed & ABOVE-200MA 43.1%   (earliest; anti-falling-knife)

The gradient is GENTLE (~5pp master->earliest) so the earlier tiers get REAL weight, not
token. `sub` = the StochRSI cross came from DEEP oversold (<20) vs a SHALLOW cross (>20).
The assessment found shallow crosses are NOT lower quality (lower stop-out, calmer pullback),
so `sub` is a DISPLAY modifier only — it never lowers the tier weight.

T1 is the validated master (passed in as `take_active` from signal_quality.analyze, so the
chart marker and the grid tier never disagree). T2/T3/T4 are computed here from the daily
close — faithful RSI-MACD (NOT price MACD), leak-free 2D/3D->daily known-date mapping,
close-only (works on every market incl. close-only HK/CN). T4's PROJECTION is leak-free: it
extrapolates the 2D MACD histogram forward from PAST bars only; it never reads the future.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine.technicals import rsi   # faithful Wilder RSI (== Pine ta.rsi)

RSI_LEN, FAST_LEN, BASE_LEN, SIG_LEN = 14, 14, 60, 5
STOCH_LEN, SMOOTH_K, SMOOTH_D = 14, 3, 3
OB, OS = 80, 20
CONF_W, BUY_RSI_MAX = 8, 65
RECENT_DAYS = 25                  # a T2 confirmed cross stays "active" this many trading days
EARLY_CROSS_BARS = 1.5            # 2D cross "projected within ~1-2 days" (bars-to-zero on the 2D grid)
MIN_HISTORY = 200

WEIGHTS = {"T1": 1.0, "T2": 0.8, "T3": 0.6, "T4": 0.4}
_BLANK = {"tier": None, "weight": 0.0, "sub": None, "eligible": False,
          "bars_to_cross": None, "asof": None}


def _ema(s, span):
    return s.ewm(span=span, min_periods=span).mean()


def _rsi_macd(c):
    r = rsi(c, RSI_LEN)
    m = _ema(r, FAST_LEN) - _ema(r, BASE_LEN)
    return m, _ema(m, SIG_LEN)


def _stoch_rsi_kd(c):
    r = rsi(c, RSI_LEN)
    lo, hi = r.rolling(STOCH_LEN).min(), r.rolling(STOCH_LEN).max()
    rawk = (r - lo) / (hi - lo).replace(0, np.nan) * 100
    k = rawk.rolling(SMOOTH_K).mean()
    return k, k.rolling(SMOOTH_D).mean()


def _xup(a, b):
    return (a > b) & (a.shift(1) <= b.shift(1))


def _since(cond):
    pos = np.arange(len(cond))
    last = pd.Series(np.where(cond.to_numpy(), pos, np.nan), index=cond.index).ffill()
    return pd.Series(pos, index=cond.index) - last


def _tf_bars(daily, n):
    s = daily.resample(f"{n}B").last().dropna()
    known = daily.resample(f"{n}B").apply(lambda x: x.dropna().index.max()).reindex(s.index).dropna()
    return s.reindex(known.index), pd.Series(pd.to_datetime(known.values), index=known.index)


def _to_daily(tf_series, known, di, how="ffill"):
    kd = pd.Series(tf_series.to_numpy(), index=pd.to_datetime(known.to_numpy()))
    kd = kd[~kd.index.duplicated(keep="last")].sort_index()
    if how == "ffill":
        return kd.reindex(di, method="ffill")
    out = pd.Series(False, index=di)
    pos = di.searchsorted(kd.index, side="left")
    for p, v in zip(pos, kd.to_numpy()):
        if v and p < len(di):
            out.iloc[p] = True
    return out


def cascade(daily_close: pd.Series, *, take_active: bool = False) -> dict:
    """Grade a close series into the weighted tier cascade. T1 = `take_active` (the validated
    master from signal_quality); T2/T3/T4 computed here. Highest active tier wins. Returns
    {tier, weight, sub (deep|shallow|None), eligible, bars_to_cross, asof}. Never raises."""
    try:
        c = daily_close.dropna()
        if not isinstance(c.index, pd.DatetimeIndex):
            c = c.copy(); c.index = pd.to_datetime(c.index)
        if len(c) < MIN_HISTORY:
            v = dict(_BLANK)
            if take_active:
                v.update(tier="T1", weight=WEIGHTS["T1"], eligible=True)
            return v
        di = c.index
        last = len(di) - 1

        # 2D RSI-MACD: confirmed cross (T2 leg) + imminent-cross projection (T3/T4 leg)
        sm, smk = _tf_bars(c, 2)
        m2, s2 = _rsi_macd(sm)
        h2 = m2 - s2
        mb2 = _xup(m2, s2)
        slope2 = h2 - h2.shift(1)
        btc = (-h2 / slope2)
        imm2 = ((h2 < 0) & (slope2 > 0) & (btc > 0) & (btc <= EARLY_CROSS_BARS)).fillna(False)

        # 3D StochRSI (T1/T2/T3 stoch leg) + 2D StochRSI (T4 leg)
        ss3, sk3 = _tf_bars(c, 3)
        k3, d3 = _stoch_rsi_kd(ss3)
        sb3 = _xup(k3, d3)
        recent3 = _since(sb3) <= CONF_W
        fromos3 = d3.rolling(CONF_W).min() < OS
        r14_3 = rsi(ss3, RSI_LEN)
        k2, d2 = _stoch_rsi_kd(sm)
        sb2 = _xup(k2, d2)
        recent2 = _since(sb2) <= CONF_W
        fromos2 = d2.rolling(CONF_W).min() < OS

        wk = c.resample("W-FRI").last().dropna()
        wm, ws = _rsi_macd(wk)
        wbull = (wm >= ws).shift(1)
        ma200 = c.rolling(200).mean()

        td = lambda s, kn, how="ffill": _to_daily(s, kn, di, how)
        mb2_d = td(mb2.fillna(False), smk, "event")
        imm2_d = td(imm2.fillna(False), smk).fillna(False)
        btc_d = td(btc, smk)
        m2_d, s2_d = td(m2, smk), td(s2, smk)
        recent3_d = td(recent3.fillna(False), sk3).fillna(False)
        fromos3_d = td(fromos3.fillna(False), sk3).fillna(False)
        k3_d, d3_d = td(k3, sk3), td(d3, sk3)
        r14_d = td(r14_3, sk3)
        recent2_d = td(recent2.fillna(False), smk).fillna(False)
        fromos2_d = td(fromos2.fillna(False), smk).fillna(False)
        wbull_d = wbull.reindex(di, method="ffill").fillna(False).astype(bool)
        above200 = (c > ma200).fillna(False)

        confirm3 = (wbull_d | fromos3_d)
        rsi_ok = (r14_d < BUY_RSI_MAX).fillna(False)
        long_bias = bool(m2_d.iloc[last] >= s2_d.iloc[last] and k3_d.iloc[last] >= d3_d.iloc[last])

        # T2 = a 2D-MACD-cross x 3D-stoch buy that fired within RECENT_DAYS and is still long-bias
        t2_buy = (mb2_d & recent3_d & confirm3 & rsi_ok).fillna(False)
        idx2 = np.where(t2_buy.to_numpy())[0]
        t2_active = bool(len(idx2) and (last - int(idx2[-1])) <= RECENT_DAYS and long_bias)
        # T3 = 2D MACD projected <=1-2d AND 3D stoch already crossed (the early prediction)
        t3_active = bool((imm2_d & recent3_d & confirm3 & rsi_ok).iloc[last])
        # T4 = 2D MACD projected AND 2D stoch crossed AND above the 200MA (anti-falling-knife)
        confirm2 = (wbull_d | fromos2_d)
        t4_active = bool((imm2_d & recent2_d & above200 & confirm2 & rsi_ok).iloc[last])

        # highest active tier wins
        if take_active:
            tier, deep = "T1", bool(fromos3_d.iloc[last])
        elif t2_active:
            tier, deep = "T2", bool(fromos3_d.iloc[last])
        elif t3_active:
            tier, deep = "T3", bool(fromos3_d.iloc[last])
        elif t4_active:
            tier, deep = "T4", bool(fromos2_d.iloc[last])
        else:
            return dict(_BLANK, asof=str(di[last].date()))
        btc_last = btc_d.iloc[last]
        return {
            "tier": tier, "weight": WEIGHTS[tier], "eligible": True,
            "sub": ("deep" if deep else "shallow"),
            "bars_to_cross": (round(float(btc_last), 2)
                              if (tier in ("T3", "T4") and pd.notna(btc_last)) else None),
            "asof": str(di[last].date()),
        }
    except Exception:
        return dict(_BLANK)

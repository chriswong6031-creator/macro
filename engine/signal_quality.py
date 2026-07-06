"""MTF MACD-RSI × StochRSI confluence — validated buy-filter signal leaf.

DISPLAY-ONLY entry-QUALITY / RISK signal for the Mastermind brain + the chart.
NOT alpha, NOT a standalone strategy. See research/signal_engine/CHARTER.md for the
framing and the marker contract (§7). The buy-filter (reclaim-and-hold + bearish-
divergence veto + 200-day-MA as a confidence bar-raiser) cut average max drawdown
-23.7% -> -15.5% across 110 held-out US names (84% improved) — it is a drawdown tool.

Faithful to the owner's `MACD STOCH RSI CONFLUENCE SIGNAL.pine`, run on the 3D:
  RSI-MACD : macd = EMA(RSI14,14) - EMA(RSI14,60); signal = EMA(macd,5)   (NOT price MACD)
  StochRSI : k = SMA(stoch(RSI14,14),3); d = SMA(k,3)

EXITS — the mechanical sell/cut stay the SIMPLE validated baseline (oscillator SELL* =>
`sell`; fast-reversal cut-loss => `cut`). A cross-sectional exit bake-off
(research/signal_engine/diagnose_v5_exits.py) tested Chandelier-ATR and close-below-EMA
trailing stops as REPLACEMENTS and they did NOT generalize: on the held-out US panel the
best (close<EMA8) improved drawdown on only ~58-69% of names and the joint drawdown-AND-
capture gate was ~37-43% — below the pre-committed 70%. So per the kill rule we ship the
simpler baseline (this echoes the CHARTER §5 killed regime-router: drawdown control is an
ENTRY problem, not an exit-routing one). The one robust finding: a close-below-EMA8 breach
is a TAIL-risk protector (rescues drawdown on 81-92% of the deepest-drawdown-quartile names
across two windows, at some capture cost). We surface it ONLY as a display-only `risk_flags`
date list + current `trail_breach`/`trail_stop` state fields — kept OUT of the validated
trade-marker stream, never an auto-sell, never per-ticker, never routed. EMA8 is CLOSE-ONLY
by construction, so the flag needs no high/low and works identically on the close-only names
(Tencent 0700.HK, BABA) — that, plus simplicity and the better tail, is why we chose it over
a high/low Chandelier ATR.
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
TRAIL_SPAN = 8   # 3D close-below-EMA8 trailing trend — the display-only tail-risk flag (see below)


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


def signal_frame(daily_close: pd.Series, daily_high: pd.Series | None = None,
                 daily_low: pd.Series | None = None) -> pd.DataFrame:
    """3D confluence signals (CB/CS/revBuy/revSell) + regime gates, leak-free.

    Every confluence value stays CLOSE-driven (faithful to the owner's Pine source).
    If a daily ``high``/``low`` is supplied — true OHLC for US deep names, or a
    conservative reconstruction for close-only names (engine.ohlc_reconstruct) — it
    is resampled onto the 3D grid (high=max, low=min over each bucket) and exposed
    as ``high``/``low`` so swing-high & bearish-divergence can read intrabar extremes.
    With NO high/low given, ``high``/``low`` collapse to ``close`` — i.e. the original
    close-only behaviour is preserved EXACTLY (the validated buy-filter default)."""
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
    ema_trail = s3.ewm(span=TRAIL_SPAN, min_periods=TRAIL_SPAN).mean()   # close-only; no high/low
    b1os, s1ob = d.rolling(CONF_W).min() < OS, d.rolling(CONF_W).max() > OB
    cb = (mb & (_since(sb) <= CONF_W) & (wbull | b1os) & (r14 < BUY_RSI_MAX)).fillna(False)
    rext = (k.rolling(CONF_W).max() >= OB) | (r14.rolling(CONF_W).max() >= EXT_RSI)
    cs = (ms & (_since(ss) <= CONF_W) & ((~wbull) | s1ob) & rext).fillna(False)
    revsell = (ms & (_since(cb) <= REV_BARS)).fillna(False)
    revbuy = (mb & (_since(cs) <= REV_BARS)).fillna(False)
    # ---- DISPLAY-ONLY early-anticipation leg (the 2D-MACD pre-cross advance warning) ----
    # Validated as m2d_s3d_early (research/signal_engine/CONFLUENCE_TUNING.md §3): the 3D
    # StochRSI bottom-turn (from oversold) WHILE the faster 2D RSI-MACD histogram is only
    # RISING (pre-cross) fires ~5 trading days BEFORE the confirmed CB and enters ~2% cheaper.
    # It does NOT improve drawdown/location out-of-sample (acting early is empirically WORSE
    # entry quality — deeper drawdown, the §5b guard avenue could not fix it), so it is surfaced
    # ONLY as a display-only advance-warning, NEVER scored, NEVER auto-traded, NEVER a buy
    # `quality`. Leak-free: 2D histogram uses the prior CLOSED 2D bar (.shift(1), no repaint).
    s2 = daily_close.resample("2B").last().dropna()
    m2, sg2 = _rsi_macd(s2)
    hist2 = m2 - sg2
    rising2 = ((hist2 > hist2.shift(1)) & (hist2.shift(1) > hist2.shift(2))).shift(1)
    rising2_on3 = rising2.reindex(s3.index, method="ffill").fillna(False).astype(bool)
    early = (sb & b1os & rising2_on3 & (wbull | b1os) & (r14 < BUY_RSI_MAX)).fillna(False)
    if daily_high is not None and daily_low is not None:
        # align high/low onto the close's daily index FIRST so the 3B resample shares
        # s3's bucket anchor; otherwise a leading-NaN/short high|low would resample on
        # a different anchor and silently collapse the band back to close.
        hl = pd.DataFrame({"high": daily_high, "low": daily_low}).reindex(daily_close.index)
        h3 = hl["high"].resample("3B").max().reindex(s3.index)
        l3 = hl["low"].resample("3B").min().reindex(s3.index)
        h3 = pd.concat([h3, s3], axis=1).max(axis=1)   # 3D high never below its close
        l3 = pd.concat([l3, s3], axis=1).min(axis=1)   # 3D low never above its close
    else:
        h3 = l3 = s3
    return pd.DataFrame({"close": s3, "high": h3, "low": l3,
                         "macd": macd, "sig": sig, "k": k, "d": d, "rsi14": r14,
                         "CB": cb, "CS": cs, "revBuy": revbuy, "revSell": revsell,
                         "w_bull": wbull, "above200": above, "ema_trail": ema_trail,
                         "early": early})


def fresh_breach_mask(daily_close: pd.Series) -> pd.Series:
    """Return a boolean Series (3B-indexed) of fresh EMA8 breaches.

    A 'fresh breach' fires on the 3B bar where:
      (1) close < ema_trail  (below)
      (2) previous 3B bar was NOT below (first time under)
      (3) ema_trail was rising into the breach (slope: bar-1 > bar-3)

    The result index is the 3B-resample end-dates.  Reindex to a daily
    index with method='ffill' to map breach dates back to daily bars.

    This is the canonical single source of truth for the fresh_breach
    construction used by both analyze() and dump_breakdown_events.py.
    """
    sf = signal_frame(daily_close)
    if sf.empty:
        return pd.Series(dtype=bool)
    trail = sf["ema_trail"]
    c = sf["close"]
    below = c < trail
    prev_below = below.shift(1, fill_value=False)
    rising_into = (trail.shift(1) > trail.shift(3))
    return (below & ~prev_below & rising_into).fillna(False)


def _swing_highs(s, w=2):
    v = s.to_numpy()
    return [i for i in range(w, len(v) - w) if v[i] == v[i - w:i + w + 1].max()]


def _bear_div(i, price, macd, hi, look=12):
    """Bearish divergence: price prints a HIGHER swing-high while the RSI-MACD prints
    a LOWER one. ``price`` is the 3D HIGH when available (true OHLC / reconstruction),
    else the close; MACD stays close-based (faithful to the Pine confluence)."""
    pv, mv = price.to_numpy(), macd.to_numpy()
    rh = [h for h in hi if i - look < h <= i]
    return len(rh) >= 2 and pv[rh[-1]] > pv[rh[-2]] and mv[rh[-1]] < mv[rh[-2]]


def _buy_filter(i, sig, bear, n):
    """The VALIDATED buy-filter: reclaim-and-hold + bearish-div veto + 200MA bar-raiser.
    Returns (take: bool|None, reason). None = pending (last 1-2 bars can't confirm yet).

    ⚠ MARKER-DATE GRADING IS FORBIDDEN (CN-1 masterplan §W6-CN). The ``held``/``reclaim`` tests
    below read bars i+1/i+2 — i.e. the label at bar ``i`` is knowable only in the FUTURE relative to
    ``i``. A 'take' marker therefore carries +5.7pp/10d of look-ahead (measured: +9.47%/10d 84.7%
    from marker dates vs +3.77%/61.5% from the confirmation-day close). Any forward-return grader,
    backtest, or chart-marker hit-rate MUST anchor on the first close at which the label was
    KNOWABLE — never on the marker date itself. The china_standout_track ledger enforces this by
    anchoring on the board-date close (post-confirmation) and measuring from the T+1 fill; see
    tests/test_signal_quality_no_leak.py which pins that any grade off ``analyze`` markers overstates
    forward returns. Do NOT grade forward returns from ``marker['date']``."""
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


def analyze(ticker: str, daily_close: pd.Series, daily_high: pd.Series | None = None,
            daily_low: pd.Series | None = None) -> dict | None:
    """Per-ticker chart-marker + state object (the site/signals/<T>.json contract, §7).

    Optional ``daily_high``/``daily_low`` let swing-high & bearish-divergence read
    intrabar extremes (true OHLC for US; a conservative reconstruction for close-only
    names — see engine.ohlc_reconstruct). Omit them for the close-only default."""
    sig = signal_frame(daily_close, daily_high, daily_low)
    if sig.empty:
        return None
    sig = sig.dropna(subset=["macd", "sig", "k", "d", "rsi14"])
    if len(sig) < 5:
        return None
    c, macd, idx, n = sig["close"], sig["macd"], sig.index, len(sig)
    hi = _swing_highs(sig["high"])
    # close-only trailing trend + its fresh breaches. A breach of a trail that was RISING
    # INTO it = an uptrend's trailing trend breaking down (the tail-risk event we want to
    # surface). NB: below.shift(1, fill_value=False) keeps BOOL dtype — plain .shift(1)
    # returns object dtype, where ~ does integer bitwise-not (~True == -2, truthy) and
    # silently corrupts the mask. The breach BAR itself can't be "rising" (its sub-trail
    # close pulls the EMA down), so we test the slope leading into it.
    trail = sig["ema_trail"]
    below = (c < trail)
    prev_below = below.shift(1, fill_value=False)
    rising_into = (trail.shift(1) > trail.shift(3))
    fresh_breach = (below & ~prev_below & rising_into).fillna(False)
    # `markers` is the validated TRADE stream (buy/sell/cut/rebuy), one per bar -> strictly
    # date-ascending (the §7 contract / validate_signals.py invariant). The trail-stop breach
    # is a DISTINCT display-only risk layer in its OWN `risk_flags` date list, so it can co-
    # occur with a sell/cut on the same bar without violating the one-marker-per-bar rule.
    # `early_markers` is a SECOND display-only date list (like risk_flags): the 2D-MACD pre-cross
    # advance-warning. Kept OUT of the validated trade stream; suppressed on a confirmed-buy bar
    # (then it is no longer "early"). Advance-warning ONLY — not every one is followed by a buy.
    markers, risk_flags, early_markers = [], [], []
    for i in range(n):
        ds = str(idx[i].date())
        is_buy = bool(sig["CB"].iloc[i]) or bool(sig["revBuy"].iloc[i])
        if is_buy:
            ok, reason = _buy_filter(i, sig, _bear_div(i, sig["high"], macd, hi), n)
            q = "pending" if ok is None else ("take" if ok else "block")
            markers.append({"date": ds, "type": "rebuy" if bool(sig["revBuy"].iloc[i]) else "buy",
                            "quality": q, "reason": reason})
        elif bool(sig["CS"].iloc[i]):
            markers.append({"date": ds, "type": "sell"})
        elif bool(sig["revSell"].iloc[i]):
            markers.append({"date": ds, "type": "cut"})
        if bool(fresh_breach.iloc[i]):
            risk_flags.append(ds)
        if bool(sig["early"].iloc[i]) and not is_buy:
            early_markers.append(ds)
    last = sig.iloc[-1]
    state = ("long-bias" if (last["k"] >= last["d"] and last["macd"] >= last["sig"])
             else "short-bias" if (last["k"] < last["d"] and last["macd"] < last["sig"]) else "mixed")
    t_last = float(trail.iloc[-1])
    return {"ticker": ticker, "asof": str(idx[-1].date()), "tf": "3D", "state": state,
            "above200": bool(last["above200"]), "weekly_bull": bool(last["w_bull"]),
            "trail_stop": round(t_last, 4) if pd.notna(t_last) else None,
            "trail_breach": bool(pd.notna(t_last) and last["close"] < t_last),
            "markers": markers, "risk_flags": risk_flags,
            "early_markers": early_markers, "early_now": bool(last["early"])}

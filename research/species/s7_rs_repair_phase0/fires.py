"""S7 RS-Repair Phase-0 — fire detectors.

F1: base3d confluence fires (reused definitions from research/signal_engine/).
F2: Codex 1W-MACD × 2W-StochRSI trigger per SPEC §3.

Both return a list of fire-date Timestamps on the daily index.
Fill convention: next close after fire date (t+1).

TIMING DISCIPLINE:
- All indicator inputs use only data known at bar close t.
- Fill is the first daily close strictly after the fire bar (t+1).
- Cooldown is enforced AFTER the fill bar, not after the fire bar.

CAUTIONARY TALE: research/bottom_signal_backtest/ had same-bar fill and
ffill timing bugs.  This module does NOT import from that package.
"""
from __future__ import annotations

import logging
from typing import Callable

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────
# Indicator helpers (faithful Pine math — copied from research/signal_engine/
# confluence.py and tuning_harness.py with provenance comments)
# ──────────────────────────────────────────────────────────────────────────

# Pine defaults (matching confluence.py exactly)
_RSI_LEN   = 14
_FAST_LEN  = 14
_BASE_LEN  = 60
_SIG_LEN   = 5
_STOCH_LEN = 14
_SMOOTH_K  = 3
_SMOOTH_D  = 3
_OB        = 80
_OS        = 20
_CONF_W    = 8
_BUY_RSI_MAX = 65
_EXT_RSI   = 70
_REV_BARS  = 3


def _ema(s: pd.Series, span: int) -> pd.Series:
    # Provenance: tuning_harness.py ema() — ewm adjust=False seeds at first valid
    return s.ewm(span=span, min_periods=span, adjust=False).mean()


def _rsi(close: pd.Series, n: int = _RSI_LEN) -> pd.Series:
    # Provenance: tuning_harness.py rsi() — ewm alpha=1/n, min_periods=n
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, min_periods=n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, min_periods=n, adjust=False).mean()
    rs = up / dn.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def _rsi_macd(close: pd.Series):
    # Provenance: tuning_harness.py rsi_macd()
    r = _rsi(close, _RSI_LEN)
    macd = _ema(r, _FAST_LEN) - _ema(r, _BASE_LEN)
    return macd, _ema(macd, _SIG_LEN)


def _stoch_rsi_kd(close: pd.Series):
    # Provenance: tuning_harness.py stoch_rsi_kd()
    r = _rsi(close, _RSI_LEN)
    lo = r.rolling(_STOCH_LEN).min()
    hi = r.rolling(_STOCH_LEN).max()
    rawk = (r - lo) / (hi - lo).replace(0, np.nan) * 100
    k = rawk.rolling(_SMOOTH_K).mean()
    return k, k.rolling(_SMOOTH_D).mean()


def _xup(a: pd.Series, b: pd.Series) -> pd.Series:
    return (a > b) & (a.shift(1) <= b.shift(1))


def _since(cond: pd.Series) -> pd.Series:
    # Provenance: tuning_harness.py since()
    pos = np.arange(len(cond))
    last = pd.Series(np.where(cond.to_numpy(), pos, np.nan), index=cond.index).ffill()
    return pd.Series(pos, index=cond.index) - last


# ──────────────────────────────────────────────────────────────────────────
# F1: base3d fires
# Reuses the exact base3d logic from research/signal_engine/tuning_harness.py
# variant "base3d": macd_tf=3, stoch_tf=3, trigger="macd_cross"
# ──────────────────────────────────────────────────────────────────────────

def _tf_bars(daily: pd.Series, n: int):
    """Resample to n-business-day bars; return (bars, known_dates).
    For n==1 returns the daily series itself.
    Provenance: tuning_harness.py tf_bars().
    """
    if n == 1:
        known = pd.Series(daily.index, index=daily.index)
        return daily.copy(), known
    s = daily.resample(f"{n}B").last().dropna()
    known = (daily.resample(f"{n}B")
             .apply(lambda x: x.dropna().index.max())
             .reindex(s.index)
             .dropna())
    s = s.reindex(known.index)
    return s, pd.Series(pd.to_datetime(known.values), index=known.index)


def _to_daily_event(tf_bool: pd.Series, known: pd.Series,
                    daily_index: pd.DatetimeIndex) -> pd.Series:
    """Place True on the first daily bar on/after each known date where tf_bool=True.
    Provenance: tuning_harness.py to_daily(how='event').
    """
    out = pd.Series(False, index=daily_index)
    kd = pd.Series(tf_bool.to_numpy(), index=pd.to_datetime(known.to_numpy()))
    kd = kd[~kd.index.duplicated(keep="last")].sort_index()
    pos = daily_index.searchsorted(kd.index, side="left")
    for p, v in zip(pos, kd.to_numpy()):
        if v and p < len(daily_index):
            out.iloc[p] = True
    return out


def _to_daily_ffill(tf_series: pd.Series, known: pd.Series,
                    daily_index: pd.DatetimeIndex) -> pd.Series:
    """Map a TF state series onto the daily grid (ffill from known date).
    Provenance: tuning_harness.py to_daily(how='ffill').
    """
    kd = pd.Series(tf_series.to_numpy(), index=pd.to_datetime(known.to_numpy()))
    kd = kd[~kd.index.duplicated(keep="last")].sort_index()
    return kd.reindex(daily_index, method="ffill")


def compute_base3d_fires(daily_close: pd.Series,
                         cooldown: int = 5) -> pd.Series:
    """Compute F1 (base3d) buy fire dates on the daily index.

    Returns a boolean pd.Series aligned to daily_close.index.
    'base3d' = RSI-MACD bull cross (3D) AND StochRSI bull-from-OS recently (3D)
    AND weekly confirm AND RSI<65.  Identical logic to tuning_harness.py
    VARIANTS['base3d'] with trigger='macd_cross', macd_tf=3, stoch_tf=3.

    cooldown: minimum daily bars between fires on the same ticker (default 5 = ~1 week).
    """
    di = daily_close.index
    if len(di) < 150:
        return pd.Series(False, index=di)

    # MACD on 3D
    sm, sm_known = _tf_bars(daily_close, 3)
    macd_m, sig_m = _rsi_macd(sm)
    mb_cross = _xup(macd_m, sig_m)

    # StochRSI on 3D
    ss, ss_known = _tf_bars(daily_close, 3)  # same TF
    k_s, d_s = _stoch_rsi_kd(ss)
    sb_cross = _xup(k_s, d_s)
    b1_from_os = d_s.rolling(_CONF_W).min() < _OS
    sb_from_os = sb_cross & b1_from_os
    recent_sb = _since(sb_cross) <= _CONF_W

    # RSI gate
    r14 = _rsi(ss, _RSI_LEN)

    # Weekly confirm (prior closed week)
    wk = daily_close.resample("W-FRI").last().dropna()
    wmacd, wsig = _rsi_macd(wk)
    w_bull_wk = (wmacd >= wsig).shift(1)
    w_bull_d = w_bull_wk.reindex(di, method="ffill").fillna(False).astype(bool)

    # Map to daily grid (event = fire on the first daily bar at/after known date)
    mb_d     = _to_daily_event(mb_cross.fillna(False), sm_known, di)
    rsb_d    = _to_daily_ffill(recent_sb.fillna(False), ss_known, di).fillna(False)
    b1os_d   = _to_daily_ffill(b1_from_os.fillna(False), ss_known, di).fillna(False)
    r14_d    = _to_daily_ffill(r14, ss_known, di)

    confirm_bull = (w_bull_d | b1os_d.astype(bool))
    rsi_ok = (r14_d < _BUY_RSI_MAX).fillna(False)

    raw_buy = (mb_d & rsb_d.astype(bool) & confirm_bull & rsi_ok).fillna(False)

    # Apply cooldown
    return _apply_cooldown(raw_buy, cooldown)


# ──────────────────────────────────────────────────────────────────────────
# F2: Codex 1W × 2W trigger per SPEC §3
# ──────────────────────────────────────────────────────────────────────────

def _resample_weekly(daily_close: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Resample to W-FRI completed bars.  Returns (bars, known_dates).
    The known_date for a weekly bar is the Friday close date itself
    (label='right', closed='right' — bar closes on Friday; known on that day)."""
    s = daily_close.resample("W-FRI", label="right", closed="right").last().dropna()
    # known_date = the last daily bar in that week
    known = (daily_close.resample("W-FRI", label="right", closed="right")
             .apply(lambda x: x.dropna().index.max())
             .reindex(s.index)
             .dropna())
    s = s.reindex(known.index)
    return s, pd.Series(pd.to_datetime(known.values), index=known.index)


def _resample_2weekly(daily_close: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Resample to 2W-FRI completed bars (label='right', closed='right').
    Returns (bars, known_dates)."""
    s = daily_close.resample("2W-FRI", label="right", closed="right").last().dropna()
    known = (daily_close.resample("2W-FRI", label="right", closed="right")
             .apply(lambda x: x.dropna().index.max())
             .reindex(s.index)
             .dropna())
    s = s.reindex(known.index)
    return s, pd.Series(pd.to_datetime(known.values), index=known.index)


def compute_codex_fires(daily_close: pd.Series,
                        cooldown: int = 21) -> pd.Series:
    """Compute F2 (Codex) buy fire dates on the daily index.

    Trigger: completed 1W MACD bull cross within 10 trading days of a
    completed 2W StochRSI bull cross from sub-20 oversold.

    FIX applied vs original Codex: the oversold window INCLUDES the cross bar
    (i.e., d < 20 on the cross bar itself counts), matching SPEC §3 note.
    No recent_os.shift(1) quirk.

    cooldown: 21 trading bars (SPEC §3).
    """
    di = daily_close.index
    if len(di) < 200:
        return pd.Series(False, index=di)

    # 1W MACD bull cross
    wk_s, wk_known = _resample_weekly(daily_close)
    wk_macd, wk_sig = _rsi_macd(wk_s)
    wk_bull_cross = _xup(wk_macd, wk_sig)  # completed 1W bar

    # 2W StochRSI bull cross from OS<20
    # SPEC §3 fix: 3-bar window on min(K,D), cross bar included (shift-quirk fix).
    # Uses elementwise min(K2,D2) then .rolling(3).min() < 20 — no shift(1).
    w2_s, w2_known = _resample_2weekly(daily_close)
    k2, d2 = _stoch_rsi_kd(w2_s)
    w2_bull_cross = _xup(k2, d2)
    w2_recent_os = pd.concat([k2, d2], axis=1).min(axis=1).rolling(3, min_periods=1).min() < 20
    w2_from_os = w2_bull_cross & w2_recent_os

    # Map to daily — event = first daily bar on/after the known close date
    wk_cross_d = _to_daily_event(wk_bull_cross.fillna(False), wk_known, di)
    w2_from_os_d = _to_daily_event(w2_from_os.fillna(False), w2_known, di)

    # Condition: 1W MACD cross within 10 td of a 2W StochRSI-from-OS cross
    # Build "2W cross event in last 10 td" flag
    w2_recent_d = _recent_within(w2_from_os_d, 10)

    raw_buy = (wk_cross_d & w2_recent_d).fillna(False)
    return _apply_cooldown(raw_buy, cooldown)


def _recent_within(events: pd.Series, n_bars: int) -> pd.Series:
    """True if any True in events within the last n_bars bars (inclusive of current)."""
    v = events.astype(float).to_numpy()
    out = np.zeros(len(v), dtype=bool)
    for i in range(len(v)):
        start = max(0, i - n_bars + 1)
        out[i] = v[start: i + 1].any()
    return pd.Series(out, index=events.index)


def _apply_cooldown(buy: pd.Series, cooldown: int) -> pd.Series:
    """Apply per-ticker cooldown: after a fire at bar i, suppress fires for
    the next `cooldown` bars."""
    arr = buy.to_numpy(dtype=bool)
    out = np.zeros(len(arr), dtype=bool)
    last_fire = -cooldown - 1
    for i, v in enumerate(arr):
        if v and (i - last_fire) > cooldown:
            out[i] = True
            last_fire = i
    return pd.Series(out, index=buy.index)


def get_fires(daily_close: pd.Series,
              fire_type: str = "F1",
              cooldown: int | None = None) -> list[pd.Timestamp]:
    """High-level entry point.  Returns a sorted list of fire dates.

    fire_type: 'F1' (base3d) or 'F2' (codex).
    cooldown: override; defaults to 5 for F1, 21 for F2.
    """
    if daily_close is None or daily_close.empty:
        return []
    if fire_type == "F1":
        cd = cooldown if cooldown is not None else 5
        s = compute_base3d_fires(daily_close, cooldown=cd)
    elif fire_type == "F2":
        cd = cooldown if cooldown is not None else 21
        s = compute_codex_fires(daily_close, cooldown=cd)
    else:
        raise ValueError(f"Unknown fire_type: {fire_type!r}")
    return list(s[s].index)

"""Pick Lab 1D and 2D grid oscillators.

Computes per-ticker latest oscillator values for two resampling grids:
  d1 — raw daily bars
  d2 — 2-SESSION bars on the market's absolute session calendar
       (engine.session_anchor.session_positions // 2; era pl-abs-session-2026-08-06)

For each grid g ∈ {d1, d2}, returns:
  {g}_macd         — RSI-MACD value (EMA14 − EMA60 of RSI14)
  {g}_sig          — signal line (EMA5 of macd)
  {g}_macd_xup_bars — bars since most recent macd > sig cross-up (null if none within 15)
  {g}_k            — StochRSI K (SMA3 of raw stoch)
  {g}_d            — StochRSI D (SMA3 of K)
  {g}_kd_xup_bars  — bars since most recent k > d cross-up (null if none within 15)
  {g}_from_os      — True if d < 20 within 8 bars (deep/from-oversold confirmation)
  {g}_ob           — True if k >= 80 or d >= 80 (overbought veto)

Shared math: _ema, _rsi_macd, _stoch_rsi_kd, _xup, _since — private helpers
in engine.signal_quality are not importable (they are module-private, prefixed _).
We re-implement the same math here (identical semantics, verified by inspection of
signal_quality.py lines 44–73) and note: RSI_LEN=14, FAST_LEN=14, BASE_LEN=60,
SIG_LEN=5, STOCH_LEN=14, SMOOTH_K=3, SMOOTH_D=3 — constants from spec §1 and
signal_quality.py lines 36–39.

The rsi() function is imported from engine.technicals (same as signal_quality.py).

Vectorized: operates on full close panels (DataFrame, columns=tickers) without
per-ticker Python loops over full history. Loops over tickers only for the final
scalar extraction.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from engine import session_anchor
from engine.technicals import rsi   # Wilder RSI — shared with signal_quality.py

log = logging.getLogger(__name__)

#: Era stamp for the session-anchored re-bucket of the resampled grids (this module's
#: d2 grid on every region's panel, plus build_hk_library's 3-session d3 site, which
#: buckets through :func:`session_bucket_last` below). DT-R16 family — a dated
#: graded-population change, labelled forever, never silent. Snapshot rows carry it as
#: the ``pl_anchor_era`` column; rows logged before the era keep a null there and are
#: never edited (keep-first dedup), so the column fences the cohorts. Sibling stamps:
#: ``abs-session-2026-08-06`` (confluence cascade), ``sq-abs-session-2026-08-06``
#: (§7 marker engine) — each charter labels only its own grids.
ANCHOR_ERA = "pl-abs-session-2026-08-06"

# Constants — identical to signal_quality.py §1 / spec §1
RSI_LEN   = 14
FAST_LEN  = 14   # EMA span for RSI-MACD fast leg
BASE_LEN  = 60   # EMA span for RSI-MACD slow leg
SIG_LEN   = 5    # EMA span for signal line
STOCH_LEN = 14
SMOOTH_K  = 3
SMOOTH_D  = 3
OB        = 80   # overbought level (veto)
OS        = 20   # oversold level
CONF_W    = 8    # confirmation window (bars)
XBAR_WIN  = 15   # max bars back to look for a recent cross


# ------------------------------------------------------------------ helpers ---

def _ema(s: pd.Series, span: int) -> pd.Series:
    """Exponential moving average.  Mirror of signal_quality._ema."""
    return s.ewm(span=span, min_periods=span).mean()


def _rsi_macd(c: pd.Series) -> tuple[pd.Series, pd.Series]:
    """RSI-MACD and its signal line for a single price series.

    Mirror of signal_quality._rsi_macd — EMA14−EMA60 of RSI14, signal EMA5.
    rsi() is the imported Wilder RSI from engine.technicals.
    """
    r = rsi(c, RSI_LEN)
    macd = _ema(r, FAST_LEN) - _ema(r, BASE_LEN)
    return macd, _ema(macd, SIG_LEN)


def _stoch_rsi_kd(c: pd.Series) -> tuple[pd.Series, pd.Series]:
    """StochRSI K and D for a single price series.

    Mirror of signal_quality._stoch_rsi_kd — 14/3/3 parameterisation.
    OB=80, OS=20 as per spec §1 / signal_quality.py.
    """
    r = rsi(c, RSI_LEN)
    lo = r.rolling(STOCH_LEN).min()
    hi = r.rolling(STOCH_LEN).max()
    rawk = (r - lo) / (hi - lo).replace(0, np.nan) * 100
    k = rawk.rolling(SMOOTH_K).mean()
    return k, k.rolling(SMOOTH_D).mean()


def _xup(a: pd.Series, b: pd.Series) -> pd.Series:
    """Boolean series: True on the bar where a crosses above b.

    Mirror of signal_quality._xup (line 63).
    """
    return (a > b) & (a.shift(1) <= b.shift(1))


def _since(cond: pd.Series) -> pd.Series:
    """Bars since the most recent True in cond.

    Mirror of signal_quality._since (lines 71–73): 0 = current bar is True,
    NaN = never fired (or fired before available history).
    """
    pos = np.arange(len(cond))
    last = pd.Series(
        np.where(cond.to_numpy(), pos, np.nan),
        index=cond.index,
    ).ffill()
    return pd.Series(pos, index=cond.index) - last


def session_bucket_last(panel: pd.DataFrame, n: int, market: str = "US") -> pd.DataFrame:
    """Last value per ``n``-SESSION bucket on the market's ABSOLUTE session calendar.

    ``bucket(date) = session_anchor.session_positions(date, market) // n`` — a function
    of (reference calendar, date) only, never of the panel's first row, so any two
    windows of the same history agree on every bucket. This replaces
    ``panel.resample(f"{n}B")``, whose bin edges anchored to the PANEL's first date and
    mis-split real session pairs at every market holiday (bdate bins): one dropped
    leading row moved d2 scalars on 60/60 measured deep US names (2026-08-06).

    ONE positions computation per panel, shared by every column — per-name windows
    (leading NaNs from late listings) cannot phase a neighbour's buckets, because the
    grid never depends on the data at all. ``.last()`` takes each bucket's final
    non-null value per column, exactly as ``Resampler.last`` did, so a bucket's value
    is fixed once its final traded session is in-window — the invariance property the
    grids' start-invariance battery pins.

    The result is indexed by absolute bucket ordinal (int). Downstream consumers are
    positional (``iloc``-based); the ordinals are for debuggability, not a label
    contract.

    A missing CN/HK/CA reference store raises ``FileNotFoundError`` (session_anchor's
    no-fallback law) — callers' additive never-fatal blocks log it and ship null
    oscillators for the night rather than silently re-bucketing on the wrong calendar.
    """
    pos = session_anchor.session_positions(panel.index, market)
    return panel.groupby(pos // n).last()


# ------------------------------------------------- per-series computation ---

def _grid_scalars(c: pd.Series) -> dict:
    """Compute all oscillator scalars for one ticker's price series.

    Returns a dict with keys macd, sig, macd_xup_bars, k, d, kd_xup_bars,
    from_os, ob — all as Python scalars (float / bool / None).
    Null if the series is too short (< BASE_LEN + SIG_LEN + STOCH_LEN bars).
    """
    null = dict(macd=None, sig=None, macd_xup_bars=None,
                k=None, d=None, kd_xup_bars=None,
                from_os=None, ob=None)
    min_bars = BASE_LEN + SIG_LEN + STOCH_LEN + CONF_W + 5
    c = c.dropna()
    if len(c) < min_bars:
        return null

    try:
        macd, sig = _rsi_macd(c)
        k, d = _stoch_rsi_kd(c)
    except Exception as exc:
        log.debug("_grid_scalars compute error: %s", exc)
        return null

    # bars since cross-up (null if no cross within XBAR_WIN)
    mx = _since(_xup(macd, sig))
    kx = _since(_xup(k, d))

    # only retain cross if it happened within the window
    mx_val = float(mx.iloc[-1]) if pd.notna(mx.iloc[-1]) else None
    kx_val = float(kx.iloc[-1]) if pd.notna(kx.iloc[-1]) else None
    if mx_val is not None and mx_val > XBAR_WIN:
        mx_val = None
    if kx_val is not None and kx_val > XBAR_WIN:
        kx_val = None

    # from_os: d < OS within CONF_W bars
    from_os_val = bool(d.iloc[-CONF_W:].min() < OS) if len(d) >= CONF_W else None

    # ob: k or d >= OB on the latest bar
    ob_val = None
    if pd.notna(k.iloc[-1]) and pd.notna(d.iloc[-1]):
        ob_val = bool(k.iloc[-1] >= OB or d.iloc[-1] >= OB)

    return dict(
        macd=float(macd.iloc[-1]) if pd.notna(macd.iloc[-1]) else None,
        sig=float(sig.iloc[-1]) if pd.notna(sig.iloc[-1]) else None,
        macd_xup_bars=mx_val,
        k=float(k.iloc[-1]) if pd.notna(k.iloc[-1]) else None,
        d=float(d.iloc[-1]) if pd.notna(d.iloc[-1]) else None,
        kd_xup_bars=kx_val,
        from_os=from_os_val,
        ob=ob_val,
    )


# ---------------------------------------------------------- public API ------

def compute_grids(
    close_panel: pd.DataFrame,
    market: str = "US",
) -> pd.DataFrame:
    """Compute 1D and 2D oscillator latest values for all tickers.

    Parameters
    ----------
    close_panel : pd.DataFrame
        Columns = ticker symbols, index = trading dates (DatetimeIndex or
        date-parseable index), values = adjusted close prices.
    market : str
        Session calendar the d2 buckets are anchored to — ``"US"`` (rules-computed
        NYSE reference), ``"CN"``, ``"HK"``, ``"CA"`` (index reference stores). Each
        regional builder passes its own region; the panel is single-region by
        construction. d1 never buckets, so it is market-independent.

    Returns
    -------
    pd.DataFrame
        Index = tickers, columns = {d1,d2}_{macd,sig,macd_xup_bars,k,d,
        kd_xup_bars,from_os,ob} plus ``pl_anchor_era`` (the bucket-geometry era
        stamp, constant :data:`ANCHOR_ERA` — stamped on every row this code emits,
        including null-scalar short-history rows: null UNDER THE NEW GEOMETRY is
        still the new geometry). NaN where insufficient history.
    """
    if close_panel.empty:
        return pd.DataFrame()

    panel = close_panel.copy()
    if not isinstance(panel.index, pd.DatetimeIndex):
        panel.index = pd.to_datetime(panel.index)
    panel = panel.sort_index()

    # d2 panel: 2-session buckets on the absolute session calendar (one positions
    # computation for the whole panel, reused across every column).
    panel_d2 = session_bucket_last(panel, 2, market=market)

    records: list[dict] = []
    for ticker in panel.columns:
        row: dict = {"ticker": ticker, "pl_anchor_era": ANCHOR_ERA}
        for grid, ser in (("d1", panel[ticker]), ("d2", panel_d2[ticker])):
            scalars = _grid_scalars(ser)
            for key, val in scalars.items():
                row[f"{grid}_{key}"] = val
        records.append(row)

    result = pd.DataFrame(records).set_index("ticker")
    return result

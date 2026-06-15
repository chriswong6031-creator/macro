"""Physical petroleum-balance CONTEXT helpers — a DISPLAY-ONLY read over the EIA
Weekly Petroleum Status Report.  LEAF: never imported by the scoring path, never
feeds conviction / alerts / MRS / latest.json.  Pure functions + thin callers.

WHY THIS IS DISPLAY-ONLY (and uses seasonal anomalies, not raw levels)
The original oil-supply read ranked crude stocks by a *raw* trailing percentile and
colored a 4-week draw green ("bullish") / build red.  Two problems that this module
fixes:

  * RAW LEVELS ARE A CALENDAR.  US crude/gasoline/distillate stocks have a large,
    deterministic annual cycle (refinery turnarounds, summer driving, heating oil).
    A raw z/percentile mostly measures the time of year.  We instead z-score the
    *seasonal anomaly* — today's deviation from the same-week-of-year climatology over
    a trailing 5y window — so the number reflects balance, not the calendar.

  * DRAW ≠ BULLISH.  The weekly EIA print is the most-arbitraged number in oil: it is
    released Wed 10:30 ET and the surprise-vs-consensus reprices within minutes, then
    it is gone.  Inventory *levels/draws* have weak forward-return predictability — the
    same single-asset-timing trap that sank the backwardation leg (see
    commodity_carry_context: 63d IC −0.16).  So this panel is neutral-colored and
    explicitly framed as physical BALANCE, not a price call.

Sign convention: seasonal-z is in NATURAL inventory units — NEGATIVE z = stocks below
their 5y seasonal norm = physically TIGHT; POSITIVE z = above norm = AMPLE.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# Surfaced verbatim on the panel — the honesty layer.
SUPPLY_CAVEAT = {
    "en": ("Physical balance ≠ price direction. EIA weekly inventories are the most-"
           "arbitraged number in oil — the surprise reprices at the 10:30 ET release, "
           "not after — so this is a supply-tightness CONTEXT read, not a buy signal. "
           "Shown as deviation from the 5y seasonal norm (a draw in winter is normal)."),
    "zh": ("实物供需≠价格方向。EIA 每周库存是原油市场最被套利的数字——意外会在 10:30(美东)"
           "公布瞬间被price in，而非之后——故此为供给松紧的背景参考，而非买入信号。"
           "以相对5年季节常态的偏离展示（冬季去库本属正常）。"),
}


def _weekly(s: pd.Series | None) -> pd.Series | None:
    """Coerce a stored EIA series to a clean, datetime-indexed, sorted weekly series."""
    if s is None:
        return None
    s = pd.Series(s).copy()
    s.index = pd.to_datetime(s.index, errors="coerce")
    s = s[s.index.notna()].sort_index()
    s = pd.to_numeric(s, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    return s if not s.empty else None


def last_value(s: pd.Series | None) -> float | None:
    """Latest finite value of a stored series, or None — NaN/empty safe."""
    s = _weekly(s)
    return None if s is None else float(s.iloc[-1])


def seasonal_z(s: pd.Series | None, years: int = 5) -> float | None:
    """Z-score of the latest value's SEASONAL ANOMALY vs the same-week-of-year
    climatology over a trailing `years` window.

    anomaly_t = value_t − mean(value | ISO-week(t), trailing window);
    z = anomaly_latest / std(anomalies).  Negative = below-season (tight).

    Returns None when there is too little history (< ~2y) or no dispersion."""
    s = _weekly(s)
    if s is None or len(s) < 104:                  # need ≥ ~2y of weekly prints
        return None
    window = s.iloc[-(years * 53):]                # ~5y of weekly obs (53 to cover ISO-53)
    woy = window.index.isocalendar().week.astype(int)
    clim = window.groupby(woy.values).transform("mean")   # per-week-of-year mean
    anom = window - clim
    sd = float(anom.std(ddof=0))
    if not np.isfinite(sd) or sd == 0:
        return None
    return float(anom.iloc[-1] / sd)


def delta_4w(s: pd.Series | None) -> float | None:
    """Latest minus ~4 weekly prints ago, in the series' native units (e.g. kbbl)."""
    s = _weekly(s)
    if s is None or len(s) < 2:
        return None
    return float(s.iloc[-1] - s.iloc[-min(5, len(s))])     # 4 steps back (inclusive guard)


def days_of_supply(stocks: pd.Series | None, demand: pd.Series | None,
                   weeks: int = 4) -> float | None:
    """Days of forward cover = latest stocks (kbbl) ÷ trailing-`weeks` mean daily
    demand (kbbl/d). Crude → refinery net inputs; products → product supplied.
    Returns None if either series is missing or demand is non-positive."""
    st = _weekly(stocks)
    dm = _weekly(demand)
    if st is None or dm is None:
        return None
    daily = float(dm.iloc[-weeks:].mean())
    if not np.isfinite(daily) or daily <= 0:
        return None
    return round(float(st.iloc[-1]) / daily, 1)


def balance_z(zmap: dict[str, float | None]) -> float | None:
    """Composite physical-balance gauge = mean of the available inventory seasonal-z's.
    Natural sign (negative = tight). DISPLAY summary only — never a scored leg."""
    vals = [v for v in zmap.values() if v is not None and np.isfinite(v)]
    if not vals:
        return None
    return float(np.mean(vals))


def balance_word(z: float | None) -> str:
    """Neutral 3-state label for the composite — NO directional (green/red) meaning."""
    if z is None:
        return "n/a"
    if z <= -0.5:
        return "tight"
    if z >= 0.5:
        return "ample"
    return "balanced"

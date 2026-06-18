"""Per-country feature frames for the International comparative dashboard.

Reads Plane A (group `intl`: index + FX closes, yfinance) and Plane B (group
`intl_macro`: FRED OECD CSV + ECB) and builds ONE uniform business-day frame per
country so every economy is scored on the SAME axes. Cross-asset cyclical inputs
(copper/gold, oil) come from the shared `yahoo` group already collected for the US
dashboard. Missing series yield NaN columns — the engine renormalizes over what
exists (degrade-don't-crash), which is how Taiwan (thin on keyless macro) and any
unresolved FRED id are handled.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from lib import config, store

log = logging.getLogger(__name__)

# macro metrics fetched per country (collectors/intl_macro stores "<CC>_<metric>")
_METRICS = ["yield_10y", "short_3m", "cpi_yoy", "unemployment", "gdp", "m2"]
# shared euro-area / periphery / anchor cols (collectors/intl_macro extra_series)
_EXTRAS = ["ez_depo_rate", "de_10y", "it_10y", "es_10y", "fr_10y", "us_10y", "us_2y"]


def countries() -> dict:
    return config.load()["intl"]["countries"]


def _intl_closes() -> pd.DataFrame:
    """Index + FX closes (group `intl`)."""
    cfg = config.load()["intl"]["countries"]
    tickers: list[str] = []
    for c in cfg.values():
        tickers += list(c.get("indices") or {c["index"]: None})
        tickers.append(c["fx"])
    cols = {}
    for t in dict.fromkeys(tickers):
        df = store.read("intl", t)
        if df is not None and "close" in df.columns:
            cols[t] = df["close"]
    return pd.DataFrame(cols).sort_index()


def read_intl_macro_col(col: str) -> pd.Series | None:
    """One `intl_macro` stored column as a clean Series (None if absent/empty).
    Shared single-column reader (engine.intl_rates + engine.intl_compare)."""
    df = store.read("intl_macro", col)
    return df.iloc[:, 0].dropna() if (df is not None and not df.empty) else None


def _macro_frame() -> pd.DataFrame:
    parts = []
    cc_metrics = [f"{cc}_{m}" for cc in countries() for m in _METRICS]
    for s in cc_metrics + _EXTRAS:
        df = store.read("intl_macro", s)
        if df is not None and not df.empty:
            parts.append(df)
    if not parts:
        return pd.DataFrame()
    out = pd.concat(parts, axis=1)
    return out[~out.index.duplicated(keep="last")].sort_index()


def _shared_ratio(num: str, den: str) -> pd.Series | None:
    a, b = store.read("yahoo", num), store.read("yahoo", den)
    if a is None or b is None or "close" not in a.columns or "close" not in b.columns:
        return None
    return (a["close"] / b["close"]).dropna()


def _shared_close(t: str) -> pd.Series | None:
    df = store.read("yahoo", t)
    return df["close"].dropna() if (df is not None and "close" in df.columns) else None


def country_frame(cc: str, closes: pd.DataFrame | None = None,
                  macro: pd.DataFrame | None = None) -> pd.DataFrame:
    """Uniform per-country daily feature frame (business-day indexed)."""
    c = countries()[cc]
    if closes is None:
        closes = _intl_closes()
    if macro is None:
        macro = _macro_frame()

    idx_col = c["index"]
    if idx_col not in closes or closes[idx_col].dropna().empty:
        return pd.DataFrame()
    px = closes[idx_col].dropna()
    end = px.index.max()
    bidx = pd.bdate_range(px.index.min(), end)
    f = pd.DataFrame(index=bidx)

    def put(name: str, s: pd.Series | None, ffill_limit: int | None = 5) -> None:
        if s is None or s.dropna().empty:
            f[name] = np.nan
            return
        s = s[~s.index.duplicated(keep="last")].sort_index()
        s = s.reindex(bidx.union(s.index))
        s = s.ffill(limit=ffill_limit) if ffill_limit else s
        f[name] = s.reindex(bidx)

    # --- market (always present) ----------------------------------------------
    put("index", px, ffill_limit=3)
    ret = px.pct_change(fill_method=None)
    put("realvol", ret.rolling(21).std() * np.sqrt(252) * 100, ffill_limit=3)  # annualised %
    dd = px / px.rolling(c_high_window(), min_periods=60).max() - 1.0
    put("drawdown", dd * 100, ffill_limit=3)                                   # % from 1y high

    fx = closes.get(c["fx"])
    put("fx", fx, ffill_limit=3)
    if fx is not None and not fx.dropna().empty:
        # currency STRESS direction: rising USD/XXX (invert) OR falling XXX/USD = weaker
        sgn = -1.0 if c.get("fx_invert") else 1.0
        put("fx_strength_3m", sgn * fx.pct_change(63) * 100, ffill_limit=3)

    # --- macro (per country; degrade per series) ------------------------------
    def mcol(metric: str) -> pd.Series | None:
        col = f"{cc}_{metric}"
        return macro[col] if (not macro.empty and col in macro.columns) else None

    # rates ffill generously (monthly source -> daily frame) so the curve / policy
    # stance reach the latest day; the direction diffs still span real changes.
    put("yield_10y", mcol("yield_10y"), ffill_limit=130)
    put("short_3m", mcol("short_3m"), ffill_limit=130)
    # CPI: some sources are an INDEX (2015=100), others already YoY %. Auto-detect
    # by level and compute YoY for index series. ffill is short, so a STALE CPI
    # (FRED's OECD MEI series are discontinued for several economies) goes NaN at
    # recent dates and is dropped from scoring — only fresh CPI drives the axis.
    cpi_raw = mcol("cpi_yoy")
    if cpi_raw is not None and not cpi_raw.dropna().empty:
        cs = cpi_raw.dropna()
        cpi_yoy = (cs.pct_change(12) * 100) if float(cs.median()) > 40 else cs
        put("cpi_yoy", cpi_yoy, ffill_limit=70)
    else:
        f["cpi_yoy"] = np.nan
    put("unemployment", mcol("unemployment"), ffill_limit=90)
    gdp = mcol("gdp")
    if gdp is not None and not gdp.dropna().empty:
        g = gdp.dropna()
        per = 4 if _is_quarterly(g) else 12                # quarterly vs monthly level
        put("gdp_yoy", g.pct_change(per) * 100, ffill_limit=160)
    else:
        f["gdp_yoy"] = np.nan
    m2 = mcol("m2")
    put("m2_yoy", (m2.dropna().pct_change(12) * 100) if (m2 is not None and not m2.dropna().empty) else None,
        ffill_limit=90)

    # EZ policy comes from the ECB deposit rate (no 3m interbank short leg)
    if cc == "EZ" and not macro.empty and "ez_depo_rate" in macro.columns:
        put("policy_rate", macro["ez_depo_rate"], ffill_limit=130)
    else:
        f["policy_rate"] = f["short_3m"]

    # --- derived rate reads ---------------------------------------------------
    f["curve"] = f["yield_10y"] - f["short_3m"]            # term slope
    f["real_yield"] = f["yield_10y"] - f["cpi_yoy"]        # ex-ante real 10y

    # --- shared global cyclical / inflation pulse -----------------------------
    put("copper_gold", _shared_ratio("HG=F", "GC=F"))
    put("oil", _shared_close("CL=F"))
    return f


def _is_quarterly(s: pd.Series) -> bool:
    d = s.index.to_series().diff().dt.days.dropna()
    return bool(len(d) and d.median() > 45)


def c_high_window() -> int:
    return int(config.load()["intl"]["engine"]["equity_risk"]["high_window_d"])


def latest_macro_snapshot(cc: str, f: pd.DataFrame) -> dict:
    """Latest-day comparison metrics for one country (levels + short-horizon dir)."""
    def lvl(col: str, nd: int = 2):
        if col not in f or f[col].dropna().empty:
            return None
        return round(float(f[col].dropna().iloc[-1]), nd)

    def chg(col: str, n: int = 63, nd: int = 2):
        if col not in f or f[col].dropna().empty:
            return None
        s = f[col].dropna()
        if len(s) <= n:
            return None
        return round(float(s.iloc[-1] - s.iloc[-1 - n]), nd)

    def real_yield():
        # real 10y = 10y − CPI, but ONLY when CPI is recent. Several keyless OECD
        # CPI series are discontinued (JP ends 2021, KR 2023), so the real_yield
        # column's last-valid value can be a years-old composite — showing it as a
        # current "real yield" would be a mislabel. Gate on the CPI leg being fresh.
        if "real_yield" not in f or "cpi_yoy" not in f:
            return None
        cpi = f["cpi_yoy"].dropna()
        ry = f["real_yield"].dropna()
        if cpi.empty or ry.empty:
            return None
        if (f.index[-1] - cpi.index[-1]).days > 490:      # CPI print >~16mo stale
            return None
        return round(float(ry.iloc[-1]), 2)

    return {
        "yield_10y": lvl("yield_10y"), "yield_10y_chg3m": chg("yield_10y"),
        "short_3m": lvl("short_3m"), "policy_rate": lvl("policy_rate"),
        "curve": lvl("curve"), "real_yield": real_yield(),
        "cpi_yoy": lvl("cpi_yoy"), "cpi_chg3m": chg("cpi_yoy"),
        "gdp_yoy": lvl("gdp_yoy"), "unemployment": lvl("unemployment"),
        "unemployment_chg6m": chg("unemployment", 126),
        "m2_yoy": lvl("m2_yoy"),
        "fx": lvl("fx", 4), "fx_strength_3m": lvl("fx_strength_3m"),
        "realvol": lvl("realvol", 1), "drawdown": lvl("drawdown", 1),
    }


def macro_freshness(cc: str, macro: pd.DataFrame | None = None) -> dict:
    """Last real-observation month per lagged macro metric — for honest dating in
    the comparison grid. FRED's OECD CPI series are discontinued for several
    economies, so a stale month is SHOWN (greyed) rather than silently hidden."""
    if macro is None:
        macro = _macro_frame()
    out = {}
    for metric in ("cpi_yoy", "gdp", "unemployment", "yield_10y"):
        col = f"{cc}_{metric}"
        s = macro[col].dropna() if (not macro.empty and col in macro.columns) else None
        out[metric] = str(s.index[-1].date())[:7] if (s is not None and not s.empty) else None
    return out

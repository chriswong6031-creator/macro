"""Rates / curve / carry desk for the International dashboard.

Takes the rates story the comparison grid showed as two bare numbers (10y, curve)
and turns it into a proper desk: per-country curve shape (10y-3m), real yield
(10y-CPI), the 3-month direction of the long end, and the CARRY each market's 10y
offers over the US 10y anchor (the single biggest pull on global fixed-income
flows). Plus a 10y-yield history sparkline, an ECB balance-sheet liquidity-impulse
context read, and a pass-through of the existing Eurozone BTP-Bund periphery panel.

DISPLAY-ONLY / descriptive. Macro series are monthly OECD/ECB on FRED and several
lag or are discontinued (JP CPI ends 2021, EZ unemployment 2023) — every leg
degrades independently and stale values are dated, not hidden.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from engine import intl_compare, intl_inputs
from engine.ird_velocity import velocity_fields_bp as _ird_velocity
from lib import config, store

log = logging.getLogger(__name__)


def _rcfg() -> dict:
    return config.load()["intl"]["engine"].get("rates", {}) or {}


_series = intl_inputs.read_intl_macro_col   # shared single-column intl_macro reader


# US anchor: the intl_macro seed doesn't always carry us_10y/us_2y, but the daily
# US Treasury series (DGS10/DGS2) are always present in the `fred` group for the US
# dashboard — fall back to those so carry is never silently None.
def _us_series(intl_col: str, fred_id: str) -> pd.Series | None:
    s = _series(intl_col)
    if s is not None and not s.empty:
        return s
    df = store.read("fred", fred_id)
    return df.iloc[:, 0].dropna() if (df is not None and not df.empty) else None


def _spark(s: pd.Series | None, n: int = 48, years: int = 6) -> list[float]:
    if s is None:
        return []
    s = s.dropna()
    if s.empty:
        return []
    s = s[s.index >= (s.index[-1] - pd.DateOffset(years=years))]
    if len(s) < 6:
        return []
    step = max(1, len(s) // n)
    return [round(float(v), 3) for v in s.iloc[::step]]


def _curve_shape(slope: float | None) -> tuple[str, str, str]:
    if slope is None:
        return "na", "—", "—"
    if slope < 0:
        return "inverted", "inverted", "倒挂"
    if slope < 0.5:
        return "flat", "flat", "平坦"
    if slope < 2.0:
        return "normal", "normal", "正常"
    return "steep", "steep", "陡峭"


def us_anchor() -> dict:
    """Latest US 2y / 10y / curve — the global rate yard-stick every carry is vs."""
    us10 = _us_series("us_10y", "DGS10")
    us2 = _us_series("us_2y", "DGS2")
    v10 = float(us10.iloc[-1]) if us10 is not None and not us10.empty else None
    v2 = float(us2.iloc[-1]) if us2 is not None and not us2.empty else None
    asof = None
    if us10 is not None and not us10.empty:
        asof = str(us10.index[-1].date())
    return {"y10": round(v10, 2) if v10 is not None else None,
            "y2": round(v2, 2) if v2 is not None else None,
            "curve": round(v10 - v2, 2) if (v10 is not None and v2 is not None) else None,
            "asof": asof, "spark": _spark(us10)}


def rates_desk(records: list[dict]) -> dict:
    """Per-country rates row + the US anchor + ECB liquidity impulse + periphery."""
    anchor = us_anchor()
    us10 = anchor.get("y10")
    rows: list[dict] = []
    for r in records:
        cc = r["cc"]
        m = r.get("macro") or {}
        af = r.get("macro_asof") or {}
        y10 = m.get("yield_10y")
        slope = m.get("curve")
        shape_key, shape_en, shape_zh = _curve_shape(slope)
        carry = round(y10 - us10, 2) if (y10 is not None and us10 is not None) else None
        # IRD-R13 velocity fields on the 10y series (fail-open)
        y10_series = _series(f"{cc}_yield_10y")
        vel = _ird_velocity(y10_series) if y10_series is not None else {"vel_5d_bp": None, "vel_20d_bp": None, "vel_20d_z": None, "window_days": None}
        rows.append({
            "cc": cc, "name": r["name"], "name_zh": r.get("name_zh", r["name"]),
            "flag": r["flag"], "region": r.get("region"),
            "y10": y10, "short": m.get("short_3m"), "policy": m.get("policy_rate"),
            "curve": slope, "shape": shape_key, "shape_en": shape_en, "shape_zh": shape_zh,
            "real_yield": m.get("real_yield"), "cpi": m.get("cpi_yoy"),
            "y10_chg3m": m.get("yield_10y_chg3m"), "carry_vs_us": carry,
            "stance": r.get("liquidity"),
            "y10_asof": af.get("yield_10y"), "cpi_asof": af.get("cpi_yoy"),
            "spark": _spark(_series(f"{cc}_yield_10y")),
            # IRD-R13 velocity (basis-point changes; window_days disclosed)
            "vel_5d_bp": vel["vel_5d_bp"],
            "vel_20d_bp": vel["vel_20d_bp"],
            "vel_20d_z": vel["vel_20d_z"],
            "vel_window_days": vel["window_days"],
        })
    # rank by carry (highest real pull first) where present
    have_carry = [r for r in rows if r["carry_vs_us"] is not None]
    have_carry.sort(key=lambda r: r["carry_vs_us"], reverse=True)
    return {"anchor": anchor, "rows": rows,
            "carry_ranked": [r["cc"] for r in have_carry],
            "liquidity": ecb_liquidity_impulse(),
            "periphery": intl_compare.periphery_panel()}


def ecb_liquidity_impulse() -> dict | None:
    """ECB balance-sheet impulse — the euro-area liquidity tide. 13- & 52-week %
    change of ECB total assets. Honest scope: ECB only (the one major CB with a
    clean keyless weekly series here); a falling balance sheet = QT drain."""
    s = _series("ez_cb_assets")
    if s is None or len(s) < 60:
        return None
    s = s[~s.index.duplicated(keep="last")].sort_index()
    w = s.resample("W").last().ffill()
    if len(w) < 54:
        return None
    last = float(w.iloc[-1])
    chg13 = float(w.iloc[-1] / w.iloc[-14] - 1.0) * 100 if len(w) > 14 else None
    chg52 = float(w.iloc[-1] / w.iloc[-53] - 1.0) * 100 if len(w) > 53 else None
    drain = bool(chg52 is not None and chg52 < 0)
    return {"asof": str(w.index[-1].date()),
            "level_eur_tn": round(last / 1e6, 2),   # source is EUR millions -> trillions
            "chg_13w": round(chg13, 1) if chg13 is not None else None,
            "chg_52w": round(chg52, 1) if chg52 is not None else None,
            "draining": drain,
            "read_en": ("QT — balance sheet still draining" if drain else "Balance sheet stabilising / expanding"),
            "read_zh": ("缩表 — 资产负债表仍在收缩" if drain else "资产负债表企稳／扩张"),
            "spark": _spark(w, n=52, years=4)}

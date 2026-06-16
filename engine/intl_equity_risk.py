"""Per-market equity-health / risk reads for the International dashboard
(DISPLAY-ONLY, descriptive).

For each country's primary index: distance from the 1y high, 50/200-day trend,
realised vol, RSI, and an own-history extension grade (reusing engine.extension —
the same in-trend/stretched/parabolic lens as the US Top-Picks board) for a
bubble / over-extension read. A 0-100 `drawdown_risk` gauge blends drawdown depth
+ below-trend + elevated vol with history-anchored bands. None of this is a
backtested signal — it is a cross-country market-stress comparator.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine import intl_inputs
from engine.extension import extension_signals
from engine.technicals import rsi
from lib import config


def _band(x: float | None) -> str:
    if x is None or np.isnan(x):
        return "n/a"
    if x >= 60:
        return "elevated"
    if x >= 35:
        return "watch"
    return "low"


def index_matrix() -> pd.DataFrame:
    closes = intl_inputs._intl_closes()
    cols = {cc: closes[c["index"]] for cc, c in intl_inputs.countries().items()
            if c["index"] in closes}
    return pd.DataFrame(cols).sort_index()


def equity_risk_all(mat: pd.DataFrame | None = None) -> dict[str, dict]:
    if mat is None:
        mat = index_matrix()
    if mat.empty:
        return {}
    out: dict[str, dict] = {}
    for cc in mat.columns:
        px = mat[cc].dropna()
        if len(px) < 60:
            continue
        # per-index extension (own series only — avoids cross-market NaN holes
        # when one market trades on a day another doesn't)
        ex = extension_signals(px.to_frame(cc)).get(cc, {})
        last = float(px.iloc[-1])
        hi52 = float(px.rolling(252, min_periods=60).max().iloc[-1])
        off_high = (last / hi52 - 1.0) * 100 if hi52 else 0.0
        ma50 = float(px.rolling(50, min_periods=25).mean().iloc[-1])
        ma200 = float(px.rolling(200, min_periods=100).mean().iloc[-1]) if len(px) >= 100 else np.nan
        rv = float(px.pct_change(fill_method=None).rolling(21).std().iloc[-1]) * np.sqrt(252) * 100
        rsi_v = float(rsi(px).iloc[-1])

        dd_leg = np.clip(-off_high / 25.0, 0, 1)              # 0 at high, 1 at -25%
        trend_leg = 1.0 if (not np.isnan(ma200) and last < ma200) else 0.0
        vol_leg = np.clip((rv - 15.0) / 25.0, 0, 1)           # vol above 15% annualised
        ddrisk = round((0.5 * dd_leg + 0.3 * trend_leg + 0.2 * vol_leg) * 100, 0)

        grade = ex.get("grade", "na")
        bubble = grade in ("stretched", "parabolic") or (rsi_v >= 72 and off_high > -3)
        out[cc] = {
            "price": round(last, 2), "off_52w_high": round(off_high, 1),
            "above_50d": bool(last > ma50),
            "above_200d": bool(not np.isnan(ma200) and last > ma200),
            "realvol": round(rv, 1), "rsi": round(rsi_v, 0),
            "ext_z": ex.get("ext_z"), "ext_grade": grade,
            "drawdown_risk": ddrisk, "drawdown_band": _band(ddrisk),
            "bubble_flag": bool(bubble),
        }
    return out

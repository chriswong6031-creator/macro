"""engine/rotation_velocity.py — per-series velocity board (Family F, Rotation Events v2).

One row per velocity_series: RS-relative momentum, accel, mtf_agree, and attached flow
receipts. Flow columns are RECEIPT-ONLY — never used in any classifier or creation gate
(Constraint 8). They are labeled "context, not a trigger" in the UI.

Stance ceiling for this board: "Early sign — watch, don't chase."

velocity_board(universe, closes, flow_receipts, bench_key) — pure, no I/O.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from engine.rotation_universe import PARAMS_V2

log = logging.getLogger(__name__)


def velocity_board(
    universe: dict,
    closes: dict[str, pd.Series],
    flow_receipts: dict[str, dict] | None = None,
    bench_key: str = "spy",
) -> dict:
    """Build the velocity board — one row per velocity_series.

    Each row: {series, label_en, label_zh, rs: {d5,d10,d20,d60}, accel10, accel_sign,
               mtf_agree, flow: {...}}.

    RS values are SPY-relative (broad rally/selloff does not paint all rows the same).
    mtf_agree = fraction of mom windows where the RS is positive (0–1 float).
    accel_sign = "pos" | "neg" | "flat".

    Flow columns: attached as receipts (context, not triggers). Never used in any
    classification path inside this module.

    Returns {"bench": bench_key, "asof": "YYYY-MM-DD", "rows": [...], "n": int}.
    """
    vs = universe.get("velocity_series", [])
    series_index = {s["key"]: s for s in universe.get("series", [])}
    bench = closes.get(bench_key)
    fr = flow_receipts or {}

    rows = []
    asof = None

    for key in vs:
        spec = series_index.get(key)
        if spec is None:
            continue
        s = closes.get(key)
        if s is None or len(s) < 65:
            continue

        label_en = spec.get("label_en", key)
        label_zh = spec.get("label_zh", key)

        # RS-relative momentum per window
        rs_vals: dict = {}
        mom_vals: dict = {}
        for w in PARAMS_V2["mom_windows"]:
            mom = s.pct_change(w)
            mom_vals[w] = float(mom.iloc[-1]) if mom.notna().any() else float("nan")
            if bench is not None and len(bench) >= w + 1:
                bm = bench.reindex(s.index).ffill().pct_change(w)
                rs = mom - bm
            else:
                rs = mom
            rs_last = float(rs.iloc[-1]) if rs.notna().any() else float("nan")
            rs_vals[w] = round(rs_last, 4) if np.isfinite(rs_last) else None

        # accel10 = 2*mom5 - mom10
        m5 = mom_vals.get(5, float("nan"))
        m10 = mom_vals.get(10, float("nan"))
        if np.isfinite(m5) and np.isfinite(m10):
            accel10 = round(2 * m5 - m10, 4)
            accel_sign = "pos" if accel10 > 0.002 else ("neg" if accel10 < -0.002 else "flat")
        else:
            accel10 = None
            accel_sign = "flat"

        # mtf_agree = fraction of RS windows that are positive
        valid_rs = [v for v in rs_vals.values() if v is not None and np.isfinite(v)]
        mtf_agree = round(sum(1 for v in valid_rs if v > 0) / len(valid_rs), 2) if valid_rs else None

        # asof from the series last date
        s_asof = str(s.index[-1].date()) if hasattr(s.index[-1], "date") else str(s.index[-1])
        if asof is None or s_asof > asof:
            asof = s_asof

        row = {
            "series": key,
            "label_en": label_en,
            "label_zh": label_zh,
            "rs": {
                "d5": rs_vals.get(5),
                "d10": rs_vals.get(10),
                "d20": rs_vals.get(20),
                "d60": rs_vals.get(60),
            },
            "accel10": accel10,
            "accel_sign": accel_sign,
            "mtf_agree": mtf_agree,
            # flow is receipt-only: attached for display context, not classification
            "flow": fr.get(key, {}),
        }
        rows.append(row)

    return {
        "bench": bench_key,
        "asof": asof,
        "rows": rows,
        "n": len(rows),
        # Stance ceiling: these signals are tape-onset tier only
        "_stance_ceiling": "Early sign — watch, don't chase",
    }

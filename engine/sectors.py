"""Sector relative-strength ranking + the quad preference mapping layer.

For every sector/pair: RS ratio vs benchmark, 20d/60d momentum, position vs
200d trend, 252d percentile. The dashboard compares framework-preferred
sectors for the current quad against ACTUAL ranks — agreement strengthens
conviction; disagreement is itself a transition signal.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine.inputs import yahoo_closes
from lib import config


def rs_table(asof: pd.Timestamp | None = None) -> pd.DataFrame:
    cfg = config.load()
    ecfg = cfg["engine"]["rs_ranking"]
    bench = ecfg["benchmark"]
    closes = yahoo_closes()
    if asof is not None:
        closes = closes[closes.index <= asof]

    universe = (cfg["yahoo"]["tickers"]["sectors"]
                + [t for t in ["SMH", "IWM", "RSP"] if t in closes.columns])
    rows = []
    for t in universe:
        if t not in closes.columns or bench not in closes.columns:
            continue
        rs = (closes[t] / closes[bench]).dropna()
        if len(rs) < ecfg["trend_window"]:
            continue
        m20 = rs.pct_change(ecfg["momentum_windows"][0]).iloc[-1] * 100
        m60 = rs.pct_change(ecfg["momentum_windows"][1]).iloc[-1] * 100
        ma200 = rs.rolling(ecfg["trend_window"]).mean().iloc[-1]
        pct = (rs.iloc[-ecfg["percentile_lookback_d"]:]
               .rank(pct=True).iloc[-1] * 100)
        rows.append({"ticker": t, "rs": rs.iloc[-1], "mom_20d_pct": round(m20, 2),
                     "mom_60d_pct": round(m60, 2),
                     "above_200d_trend": bool(rs.iloc[-1] > ma200),
                     "pctile_252d": round(pct, 1)})
    df = pd.DataFrame(rows).set_index("ticker")
    df["rank"] = df["mom_60d_pct"].rank(ascending=False).astype(int)
    return df.sort_values("rank")


def preference_check(quad: str, table: pd.DataFrame) -> dict:
    prefs = config.load()["engine"]["sector_preferences"].get(quad, [])
    in_table = [p for p in prefs if p in table.index]
    if not in_table:
        return {"quad": quad, "preferred": prefs, "agreement": None,
                "note": "no preferred tickers in RS table"}
    half = len(table) / 2
    top_half_hits = sum(1 for p in in_table if table.loc[p, "rank"] <= half)
    agreement = top_half_hits / len(in_table)
    return {
        "quad": quad,
        "preferred": prefs,
        "actual_ranks": {p: int(table.loc[p, "rank"]) for p in in_table},
        "agreement": round(agreement, 2),
        "disagreement_flag": agreement < 0.5,
        "note": ("framework and tape agree" if agreement >= 0.5 else
                 "tape disagrees with framework-preferred sectors — treat as a transition signal"),
    }


def pair_ratios_snapshot(f: pd.DataFrame) -> dict:
    out = {}
    for col in ["xly_xlp", "xlk_xlu", "hyg_lqd", "sphb_splv", "vix_ratio", "copper_gold"]:
        if col in f and not f[col].dropna().empty:
            s = f[col].dropna()
            out[col] = {"level": round(float(s.iloc[-1]), 4),
                        "chg_20d_pct": round(float(s.pct_change(20).iloc[-1] * 100), 2)}
    return out

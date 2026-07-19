"""engine/vex_engine.py — vega exposure (VEX): the volatility-feedback map.

Voltick Gamma-Levels program, Phase B. GEX maps how dealer hedging reacts to PRICE moving
(engine/options_hub.compute_gex). VEX maps how hedging reacts to VOLATILITY moving: when
dealers are (assumed) short vega, a volatility jump forces hedging that can fuel multi-day
moves; when long vega, vol spikes get absorbed. Same board, one toggle — GEX for today's
terrain, VEX for what a vol shock would do to it.

This mirrors compute_gex exactly (OI[t-1] merge, dealer-sign convention, spot from
underlying_price median, ±20% strike window) but weights each contract by VEGA instead of
gamma. The output ``options_hub.vex/v1`` payload carries the same shape as the gex payload
so the same board machinery renders the GEX↔VEX toggle.

DISPLAY-TIER: VEX is a positioning proxy under an ASSUMED long-call/short-put dealer-sign
convention, not measured dealer inventory. Positive net VEX ≈ vol spikes absorbed
(stabilizing); negative ≈ vol moves amplified. Positioning, not prophecy — never a signal or
a trade.

PURE: no I/O, no clock. The nightly hub builder reconstructs greeks_df + oi_prev_df and calls
compute_vex here, exactly as it calls compute_gex.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine.options_hub import MULT, _f  # same contract multiplier + rounding helper

SCHEMA = "options_hub.vex/v1"
# Vega is d(option value)/d(IV) per share; VEX_PM scales to a 1 vol-point (1% IV) move,
# parallel to GEX's PM=0.01 for a 1% price move. The board topology (walls, flip) is
# scale-invariant, so the constant sets units ($mn per vol-point), not structure.
VEX_PM = 0.01


def _empty_vex(root: str, asof: str) -> dict:
    return {
        "schema": SCHEMA, "asof": asof, "root": root, "spot_ref": None,
        "net_vex_mm": None, "vex_flip": None, "pos_vex_wall": None, "neg_vex_wall": None,
        "by_strike": [], "by_strike_full_n": 0, "by_expiry": [],
        "convention": "dealer-sign per engine/gex_model (long-call/short-put), vega-weighted",
        "coverage": {"n_contracts": 0, "asof": asof, "oi_date": "t-1", "n_days": 0, "since": asof},
    }


def _find_vex_flip(by_k: pd.DataFrame, spot: float) -> float | None:
    """Interpolated strike where cumulative net VEX (bottom strike upward) crosses zero,
    nearest to spot. Mirrors options_hub._find_gamma_flip's convention for VEX.
    """
    if by_k.empty:
        return None
    d = by_k.sort_values("K")
    ks = d["K"].to_numpy(float)
    cum = np.cumsum(d["vex_net"].to_numpy(float))
    crossings: list[float] = []
    for i in range(1, len(cum)):
        a, b = cum[i - 1], cum[i]
        if a == 0.0:
            crossings.append(ks[i - 1])
        elif (a < 0) != (b < 0):
            x0, x1 = ks[i - 1], ks[i]
            crossings.append(x0 - a * (x1 - x0) / (b - a) if b != a else x0)
    if not crossings:
        return None
    return min(crossings, key=lambda x: abs(x - spot))


def compute_vex(greeks_df: pd.DataFrame, oi_prev_df: pd.DataFrame, asof: str, root: str) -> dict:
    """Build the ``options_hub.vex/v1`` payload (vega exposure by strike).

    Same inputs and PIT discipline as compute_gex: greeks_df carries vega + underlying_price
    for `asof`; oi_prev_df is the t-1 OI. Returns honest empties (never raises) when the
    board can't be built.
    """
    if greeks_df is None or greeks_df.empty or "date" not in greeks_df.columns:
        return _empty_vex(root, asof)
    g = greeks_df.copy()
    g["date"] = pd.to_datetime(g["date"]).dt.date.astype(str)
    g = g[g["date"] == asof]
    if g.empty:
        return _empty_vex(root, asof)

    spot_vals = g["underlying_price"].dropna()
    spot = float(spot_vals.median()) if not spot_vals.empty else float("nan")
    if not np.isfinite(spot) or spot <= 0:
        return _empty_vex(root, asof)

    # OI[t-1] merge (identical to compute_gex)
    if oi_prev_df is not None and not oi_prev_df.empty:
        oi = oi_prev_df[["expiration", "strike", "right", "open_interest"]].copy()
        oi["expiration"] = pd.to_datetime(oi["expiration"]).dt.date.astype(str)
        oi["strike"] = oi["strike"].astype(float)
        g["expiration"] = pd.to_datetime(g["expiration"]).dt.date.astype(str)
        g["strike"] = g["strike"].astype(float)
        g = g.merge(oi.rename(columns={"open_interest": "oi_prev"}),
                    on=["expiration", "strike", "right"], how="left")
        g["oi_prev"] = pd.to_numeric(g["oi_prev"], errors="coerce").fillna(0.0)
    else:
        g["oi_prev"] = 0.0
    g = g[g["oi_prev"] > 0].copy()
    if g.empty:
        return _empty_vex(root, asof)

    g["is_call"] = g["right"].str.upper() == "C"
    g["K"] = g["strike"].astype(float)

    raw_vega = (pd.to_numeric(g["vega"], errors="coerce")
                if "vega" in g.columns else pd.Series(np.nan, index=g.index))
    vega = raw_vega.to_numpy(float)
    vega = np.where(np.isfinite(vega), vega, 0.0)
    sign = np.where(g["is_call"], 1.0, -1.0)
    oi_arr = g["oi_prev"].to_numpy(float)

    # net VEX = sign * vega * OI * MULT * VEX_PM  ($ per 1 vol-point move)
    g["_net_vex"] = sign * vega * oi_arr * MULT * VEX_PM

    net_vex_mm = float(g["_net_vex"].sum() / 1e6)

    by_k = g.groupby("K").agg(vex_net=("_net_vex", "sum")).reset_index()
    vex_flip = _find_vex_flip(by_k, spot)

    above = by_k[(by_k["K"] > spot) & (by_k["vex_net"] > 0)]
    below = by_k[(by_k["K"] < spot) & (by_k["vex_net"] < 0)]
    pos_vex_wall = float(above.loc[above["vex_net"].idxmax(), "K"]) if not above.empty else None
    neg_vex_wall = float(below.loc[below["vex_net"].idxmin(), "K"]) if not below.empty else None

    by_strike_full_n = int(len(by_k))
    by_k_win = by_k[((by_k["K"] / spot - 1).abs() <= 0.20)].copy()
    if len(by_k_win) > 160:
        by_k_win = (by_k_win.assign(_d=(by_k_win["K"] - spot).abs())
                    .nsmallest(160, "_d").drop(columns=["_d"]).sort_values("K"))

    by_strike_rows = [
        {"strike": _f(row.K), "vex_net": _f(row.vex_net / 1e6, 4)}  # $mn, 4dp
        for row in by_k_win.itertuples()
    ]

    by_exp = g.groupby("expiration").agg(vex_net=("_net_vex", "sum")).reset_index()
    by_exp["expiration"] = pd.to_datetime(by_exp["expiration"]).dt.date.astype(str)
    by_expiry_rows = sorted(
        ({"exp": row.expiration, "vex_net": _f(row.vex_net / 1e6, 4)} for row in by_exp.itertuples()),
        key=lambda r: r["exp"],
    )

    greeks_dates = sorted(g["date"].unique())
    return {
        "schema": SCHEMA,
        "asof": asof,
        "root": root,
        "spot_ref": _f(spot),
        "net_vex_mm": _f(net_vex_mm, 4),
        "vex_flip": _f(vex_flip),
        "pos_vex_wall": _f(pos_vex_wall),
        "neg_vex_wall": _f(neg_vex_wall),
        "by_strike": by_strike_rows,
        "by_strike_full_n": by_strike_full_n,
        "by_expiry": by_expiry_rows,
        "convention": "dealer-sign per engine/gex_model (long-call/short-put), vega-weighted",
        "coverage": {"n_contracts": int(len(g)), "asof": asof, "oi_date": "t-1",
                     "n_days": len(greeks_dates), "since": greeks_dates[0] if greeks_dates else asof},
    }

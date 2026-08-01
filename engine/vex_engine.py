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

from engine.greeks import SQRT2PI
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


def _find_vex_flip(g: pd.DataFrame, spot: float) -> float | None:
    """Zero-vega-exposure spot — the hypothetical price at which the book, RE-PRICED
    there, carries zero net dealer VEX. Same ±25% / 101-point grid the gamma flip uses.

    ⚠️ HISTORY — do not revert. Until 2026-08-01 this summed ``vex_net`` along the
    STRIKE ladder and returned the cumulative zero-crossing, faithfully mirroring
    ``options_hub._find_gamma_flip`` — which was itself the wrong estimator. The bug
    propagated here through that function's (false) docstring claim to mirror
    ``gex_engine._gamma_flip``. Analysis: charting-app
    ``docs/audits/2026-08-01-market-structure-core/gamma-flip-defect-rca.md``.

    Vega is call/put-identical, so under the dealer-sign convention net VEX at a trial
    spot is (call-side vega·OI) − (put-side vega·OI) with every contract re-valued at
    that spot; the crossing is where the two balance. Returns the crossing nearest
    spot, or ``None`` when the profile never changes sign over the grid.
    """
    if not (spot and spot > 0) or g.empty:
        return None
    c = pd.DataFrame({
        "K": pd.to_numeric(g["K"], errors="coerce"),
        "T": pd.to_numeric(g.get("T"), errors="coerce"),
        "iv": pd.to_numeric(g.get("iv"), errors="coerce"),
        "oi": pd.to_numeric(g["oi_prev"], errors="coerce"),
        "is_call": g["is_call"].astype(bool),
    }).dropna(subset=["K", "T", "iv", "oi"])
    w, maxT = 0.25, 365.0 / 365.0
    c = c[(c["T"] > 0) & (c["T"] <= maxT)
          & c["K"].between(spot * (1 - w), spot * (1 + w))
          & (c["iv"] > 0) & (c["oi"] > 0)]
    if len(c) < 20:
        return None

    K = c["K"].to_numpy(float); T = c["T"].to_numpy(float)
    sig = c["iv"].to_numpy(float); oi = c["oi"].to_numpy(float)
    sgn = np.where(c["is_call"].to_numpy(bool), 1.0, -1.0)
    sqrtT = np.sqrt(T)
    grid = spot * np.linspace(0.75, 1.25, 101)
    net = np.empty(len(grid))
    for i, Sx in enumerate(grid):
        d1 = (np.log(Sx / K) + 0.5 * sig * sig * T) / (sig * sqrtT)
        # vega = S·pdf(d1)·√T  (r = q = 0, matching gex_engine DEFAULTS)
        vega = Sx * np.exp(-0.5 * d1 * d1) / SQRT2PI * sqrtT
        net[i] = float(np.sum(sgn * vega * oi * MULT * VEX_PM))
    flips: list[float] = []
    for i in range(len(grid) - 1):
        if net[i] == 0.0 or (net[i] < 0) != (net[i + 1] < 0):
            x0, x1, y0, y1 = grid[i], grid[i + 1], net[i], net[i + 1]
            flips.append(x0 - y0 * (x1 - x0) / (y1 - y0) if y1 != y0 else x0)
    if not flips:
        return None
    return float(min(flips, key=lambda f: abs(f - spot)))


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
    # T + iv are needed by the spot-grid VEX flip (they were never prepared here while
    # the flip was a cumulative-across-strikes sum). Same derivation as compute_gex.
    _today = pd.Timestamp(asof).date()
    g["T"] = pd.to_numeric(
        pd.to_datetime(g["expiration"]).dt.date.map(lambda e: (e - _today).days / 365.0),
        errors="coerce",
    ).clip(lower=0.0)
    g["iv"] = pd.to_numeric(
        g.get("implied_vol", pd.Series(np.nan, index=g.index)), errors="coerce"
    )

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
    vex_flip = _find_vex_flip(g, spot)

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

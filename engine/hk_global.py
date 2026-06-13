"""Global Risk Overlay — the PRIMARY Hong Kong driver.

HK is ~2x more globally sensitive than the Mainland (measured: SPY beta ~0.55 vs
~0.30; stronger dollar/USDCNY/VIX correlations — see research/HK_DATA_AUDIT.md and
memory `china-global-factors`). HK is the transmission intermediary of US monetary-
policy and volatility shocks into China, and the HKD peg makes HK rates shadow the
Fed. So a composite global risk-on/off gauge is the single most important
high-frequency input for the HK regime — surfaced as the dashboard hero.

The composite is a weighted mean of per-factor direction scores (each mapped to
-1/0/+1 via the same slope_z / score_from_z machinery the rest of the engine uses,
so backtest == live), with each factor's sign flipping rising-is-risk-on vs
rising-is-risk-off:
  DXY(-)  VIX(-)  SPY(+)  copper/gold(+)  USDCNY(-)  EEM(+)
Plus the HKD peg distance (7.75 strong-side inflow ↔ 7.85 weak-side outflow) as a
capital-flow gauge the HKMA actively defends.

Framed as a CONCURRENT risk STATE, not a forecast — global factors are coincident,
not leading, at weekly frequency. calibrate_hk.py measures whether the state
actually differentiates HSI forward returns; it ships honestly with that record.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from engine.indicators import score_from_z, slope_z
from lib import config, store

log = logging.getLogger(__name__)

# factor -> human label (EN); zh via engine.i18n where shown
FACTOR_LABELS = {
    "dxy": "US Dollar (DXY)", "vix": "Volatility (VIX)", "spy": "S&P 500",
    "copper_gold": "Copper / Gold", "usdcny": "USD / CNY", "eem": "EM equity (EEM)",
}


def _gcfg() -> dict:
    return config.load()["hk"]["global_factors"]


def factor_series() -> dict[str, pd.Series]:
    """Read each configured global factor's close from its store group.
    `copper_gold` is computed from yahoo HG=F / GC=F (global cyclical pulse)."""
    out: dict[str, pd.Series] = {}
    comps = _gcfg()["components"]
    for name, c in comps.items():
        if name == "copper_gold":
            cu = store.read("yahoo", "HG=F")
            au = store.read("yahoo", "GC=F")
            if cu is not None and au is not None:
                ratio = (cu["close"] / au["close"]).dropna()
                if not ratio.empty:
                    out[name] = ratio
            continue
        df = store.read(c["group"], c["ticker"])
        if df is not None and "close" in df.columns and not df["close"].dropna().empty:
            out[name] = df["close"].dropna()
    return out


def _factor_z(s: pd.Series) -> pd.Series:
    g = _gcfg()
    use_log = bool(s.min() > 0)          # ratios/levels are positive; log keeps it scale-free
    return slope_z(s, g["slope_window"], g["baseline_window"], use_log=use_log)


def composite(idx: pd.DatetimeIndex) -> pd.DataFrame:
    """Per-day risk-on/off composite over the index. Returns columns:
    global_score (-1..+1, weighted net of factor direction), risk_state
    (Risk-on/Risk-off/Neutral), plus the peg sub-state from HKD=X."""
    g = _gcfg()
    comps = g["components"]
    series = factor_series()
    out = pd.DataFrame(index=idx)

    signed, weights = {}, {}
    for name, c in comps.items():
        s = series.get(name)
        if s is None:
            continue
        z = _factor_z(s).reindex(idx.union(s.index)).ffill(limit=5).reindex(idx)
        fscore = score_from_z(z, g["z_threshold"])
        signed[name] = fscore * float(c.get("sign", 1.0))
        weights[name] = float(c.get("weight", 1.0))

    if signed:
        sc = pd.DataFrame(signed)
        w = pd.Series(weights)[sc.columns]
        avail = sc.notna()
        wsum = avail.mul(w, axis=1).sum(axis=1)
        out["global_score"] = sc.fillna(0).mul(w, axis=1).sum(axis=1) / wsum.replace(0, np.nan)
    else:
        out["global_score"] = np.nan

    thr = g["risk_on_z"]
    state = pd.Series("Neutral", index=idx)
    state[out["global_score"] > thr] = "Risk-on"
    state[out["global_score"] < -thr] = "Risk-off"
    state[out["global_score"].isna()] = "unknown"
    out["risk_state"] = state

    # peg sub-state (HKD=X), if present
    hkd = store.read("hk", "HKD=X")
    if hkd is not None and "close" in hkd.columns:
        peg = peg_frame(hkd["close"].dropna().reindex(idx.union(hkd.index)).ffill(limit=5).reindex(idx))
        out = out.join(peg)
    return out


def peg_frame(usdhkd: pd.Series) -> pd.DataFrame:
    """HKD convertibility-band position. 7.75 strong-side (inflow/easing) <-> 7.85
    weak-side (outflow/HSI headwind, HKMA defends). pressure 0..1 toward weak-end."""
    p = _gcfg()["peg"]
    lo, hi = p["strong"], p["weak"]
    dist = ((usdhkd - lo) / (hi - lo)).clip(0, 1)        # 0 = strong-side, 1 = weak-side
    pressure = dist                                       # higher = more outflow pressure
    state = pd.Series("mid-band", index=usdhkd.index)
    state[dist >= (p["pressure_pct"] / 100.0 * 0 + 0.75)] = "weak-side (outflow)"
    state[dist <= 0.25] = "strong-side (inflow)"
    state[usdhkd.isna()] = "unknown"
    return pd.DataFrame({"peg_distance": dist, "peg_pressure": pressure, "peg_state": state})


def snapshot(asof: pd.Timestamp | None = None) -> dict:
    """Latest-day per-factor contributions for the hero panel."""
    series = factor_series()
    comps = _gcfg()["components"]
    if not series:
        return {"score": None, "state": "unknown", "factors": [], "peg": None}
    end = asof or min((s.index.max() for s in series.values()), default=None)
    idx = pd.bdate_range(min(s.index.min() for s in series.values()), end)
    comp = composite(idx)
    row = comp.dropna(subset=["global_score"]).iloc[-1] if not comp["global_score"].dropna().empty else None

    factors = []
    for name, c in comps.items():
        s = series.get(name)
        if s is None:
            continue
        z = float(_factor_z(s).dropna().iloc[-1]) if not _factor_z(s).dropna().empty else 0.0
        contribution = float(np.sign(z) * (1 if abs(z) > _gcfg()["z_threshold"] else 0) * c.get("sign", 1.0))
        factors.append({
            "key": name, "label": FACTOR_LABELS.get(name, name),
            "z": round(z, 2), "sign": c.get("sign", 1.0),
            "risk": "on" if contribution > 0 else ("off" if contribution < 0 else "neutral"),
            "level": round(float(s.iloc[-1]), 4),
        })

    peg = None
    hkd = store.read("hk", "HKD=X")
    if hkd is not None and "close" in hkd.columns:
        u = hkd["close"].dropna()
        pf = peg_frame(u)
        if not pf.empty:
            peg = {"level": round(float(u.iloc[-1]), 4),
                   "distance": round(float(pf["peg_distance"].iloc[-1]), 2),
                   "state": str(pf["peg_state"].iloc[-1])}

    return {
        "score": round(float(row["global_score"]), 3) if row is not None else None,
        "state": str(row["risk_state"]) if row is not None else "unknown",
        "factors": factors, "peg": peg,
        "asof": str(end.date()) if end is not None else None,
    }

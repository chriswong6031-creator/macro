"""Commodity / CAD / BoC-vs-Fed cross-asset overlay — the PRIMARY Canada driver.

The TSX is ~70% Financials + Energy + Materials with almost no mega-cap tech, and
CAD is a commodity/petro currency, so the single most important high-frequency read
for the Canada regime is a commodity-and-currency risk gauge — surfaced as the
dashboard hero. Mirrors engine/hk_global.py (same slope_z / score_from_z machinery,
so backtest == live), with Canada's factor set:

  WTI oil(+)  gold(+)  copper/gold(+)  USDCAD(-, i.e. CAD strength is risk-on)
  S&P 500(+)  VIX(-)  DXY(-)

All inputs already collected in the shared `yahoo` group. Framed as a CONCURRENT
risk STATE (coincident, not a forecast). DISPLAY-FIRST: it informs the read and the
dashboard hero but is not scored into the growth/inflation quad pre-validation.
Adds a terms-of-trade tag (oil + gold vs CAD) and a BoC-vs-Fed coupling read
(GoC-vs-UST 2y/10y spreads; degrades when the FRED US legs are absent).
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from engine.indicators import score_from_z, slope_z
from lib import config, store

log = logging.getLogger(__name__)

FACTOR_LABELS = {
    "oil": "WTI crude oil", "gold": "Gold", "copper_gold": "Copper / Gold",
    "usdcad": "USD / CAD", "spy": "S&P 500", "vix": "Volatility (VIX)",
    "dxy": "US Dollar (DXY)",
}


def _gcfg() -> dict:
    return config.load()["canada"]["global_factors"]


def factor_series() -> dict[str, pd.Series]:
    """Read each configured factor's close from its store group. `copper_gold` is
    computed from yahoo HG=F / GC=F (global cyclical pulse)."""
    out: dict[str, pd.Series] = {}
    for name, c in _gcfg()["components"].items():
        if name == "copper_gold":
            cu, au = store.read("yahoo", "HG=F"), store.read("yahoo", "GC=F")
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
    use_log = bool(s.min() > 0)
    return slope_z(s, g["slope_window"], g["baseline_window"], use_log=use_log)


def composite(idx: pd.DatetimeIndex) -> pd.DataFrame:
    """Per-day risk-on/off composite over the index. Columns: global_score
    (-1..+1, weighted net of factor direction) + risk_state."""
    g = _gcfg()
    series = factor_series()
    out = pd.DataFrame(index=idx)

    signed, weights = {}, {}
    for name, c in g["components"].items():
        s = series.get(name)
        if s is None:
            continue
        z = _factor_z(s).reindex(idx.union(s.index)).ffill(limit=5).reindex(idx)
        signed[name] = score_from_z(z, g["z_threshold"]) * float(c.get("sign", 1.0))
        weights[name] = float(c.get("weight", 1.0))

    if signed:
        sc = pd.DataFrame(signed)
        w = pd.Series(weights)[sc.columns]
        avail = sc.notna()
        wsum = avail.mul(w, axis=1).sum(axis=1)
        gscore = sc.fillna(0).mul(w, axis=1).sum(axis=1) / wsum.replace(0, np.nan)
        min_f = int(g.get("min_factors", 3))
        out["global_score"] = gscore.where(avail.sum(axis=1) >= min_f, np.nan)
    else:
        out["global_score"] = np.nan

    thr = g["risk_on_z"]
    state = pd.Series("Neutral", index=idx)
    state[out["global_score"] > thr] = "Risk-on"
    state[out["global_score"] < -thr] = "Risk-off"
    state[out["global_score"].isna()] = "unknown"
    out["risk_state"] = state
    return out


def _terms_of_trade(factors: dict[str, float]) -> str:
    """Commodity terms-of-trade tag from oil + gold direction vs CAD strength.
    Rising commodities + strengthening CAD = improving (a TSX tailwind)."""
    oil, gold = factors.get("oil", 0.0), factors.get("gold", 0.0)
    cad_strength = -factors.get("usdcad", 0.0)     # usdcad z>0 = CAD weaker; invert
    commod = (oil + gold) / 2.0
    if commod > 0 and cad_strength >= 0:
        return "improving"
    if commod < 0 and cad_strength <= 0:
        return "deteriorating"
    return "mixed"


def coupling_snapshot() -> dict:
    """BoC-vs-Fed read: BoC policy rate level + GoC-vs-UST 2y/10y spreads. The UST
    legs come from FRED comparables (canada_macro us_2y/us_10y) and degrade to None
    when absent (FRED is unreachable from some sandboxes; present in CI)."""
    cp = _gcfg().get("coupling", {})

    def last(col):
        df = store.read("canada_macro", col)
        if df is None or df.empty:
            return None
        return float(df.iloc[-1, 0])

    boc = last(cp.get("boc_rate", "policy_rate"))
    goc2, goc10 = last(cp.get("goc_2y", "goc_2y")), last(cp.get("goc_10y", "goc_10y"))
    us2, us10 = last(cp.get("us_2y", "us_2y")), last(cp.get("us_10y", "us_10y"))
    spread_2y = round(goc2 - us2, 2) if (goc2 is not None and us2 is not None) else None
    spread_10y = round(goc10 - us10, 2) if (goc10 is not None and us10 is not None) else None
    return {"boc_rate": boc, "goc_2y": goc2, "goc_10y": goc10,
            "us_2y": us2, "us_10y": us10,
            "goc_minus_ust_2y": spread_2y, "goc_minus_ust_10y": spread_10y,
            "goc_curve_2s10s": round(goc10 - goc2, 2) if (goc2 is not None and goc10 is not None) else None}


def snapshot(asof: pd.Timestamp | None = None) -> dict:
    """Latest-day per-factor contributions for the dashboard hero + terms-of-trade
    + BoC-vs-Fed coupling."""
    series = factor_series()
    comps = _gcfg()["components"]
    if not series:
        return {"score": None, "state": "unknown", "factors": [],
                "terms_of_trade": None, "coupling": coupling_snapshot()}
    end = asof or min((s.index.max() for s in series.values()), default=None)
    series = {k: v[v.index <= end] for k, v in series.items()}
    series = {k: v for k, v in series.items() if not v.empty}
    idx = pd.bdate_range(min(s.index.min() for s in series.values()), end)
    comp = composite(idx)
    row = comp.dropna(subset=["global_score"]).iloc[-1] if not comp["global_score"].dropna().empty else None

    factors, contrib_by_key = [], {}
    for name, c in comps.items():
        s = series.get(name)
        if s is None:
            continue
        zser = _factor_z(s).dropna()
        z = float(zser.iloc[-1]) if not zser.empty else 0.0
        contrib = float(np.sign(z) * (1 if abs(z) > _gcfg()["z_threshold"] else 0) * c.get("sign", 1.0))
        contrib_by_key[name] = float(np.sign(z) * (1 if abs(z) > _gcfg()["z_threshold"] else 0))
        factors.append({
            "key": name, "label": FACTOR_LABELS.get(name, name),
            "z": round(z, 2), "sign": c.get("sign", 1.0),
            "risk": "on" if contrib > 0 else ("off" if contrib < 0 else "neutral"),
            "level": round(float(s.iloc[-1]), 4),
        })

    return {
        "score": round(float(row["global_score"]), 3) if row is not None else None,
        "state": str(row["risk_state"]) if row is not None else "unknown",
        "factors": factors,
        "terms_of_trade": _terms_of_trade(contrib_by_key),
        "coupling": coupling_snapshot(),
        "asof": str(end.date()) if end is not None else None,
    }

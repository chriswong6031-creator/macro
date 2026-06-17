"""Per-index DIRECTIONAL model — the honest directional brain for equity indexes.

Today the Anticipation cone's direction is a measured coin-flip. This module replaces
the direction CENTER — for indexes only, at MEDIUM/LONG, and only behind the Phase-0
gate — with a sign-restricted COMBINATION forecast of return predictors that beat the
expanding historical mean OUT-OF-SAMPLE (Clark-West), mapped to P(up) through the same
volatility the risk cone uses.

Design (research/INDEX_DIRECTION.md), honesty rules baked in:
- Each leg is oriented so higher = more BULLISH; its a-priori sign is +1 (Campbell-
  Thompson). A univariate expanding-window regression fits b; if rolling b flips
  negative the leg is DROPPED (collapses to the mean) — never a wrong-sign bet.
- Combination = fixed-tier WEIGHTED MEAN of surviving legs (Rapach-Strauss-Zhou),
  NEVER a joint multivariate regression (kitchen-sink overfits ~3-7 cycles).
- P(up) = Φ(r̂ / σ_h) via vol_forecast.cone_vol_ann (ties direction to the risk σ),
  clamped to an honest band — an index 1-3mo |P(up)-0.5| rarely exceeds ~5-8pts.
- Per-index manifests: validation NEVER transfers; each index has its own gate block
  and defaults display-only. Short stays a coin-flip (handled in anticipation.py).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from engine import indicators, vol_forecast
from engine.cross_asset_trend import tsmom_alloc
from engine.validation import _norm_cdf

# Per-index MEDIUM-horizon predictor manifest (weight tiers; all legs oriented bullish,
# a-priori sign +1). LONG needs a Shiller/valuation collector (deferred); SHORT stays a
# coin-flip. Each leg name maps to a column built by build_legs().
TIER = {"HIGH": 1.0, "MED": 0.6, "LOW": 0.3, "ZERO": 0.0}
INDEX_PRESETS = {
    "SPY": {"medium": {"vrp": "HIGH", "tsmom": "MED", "netliq": "MED", "credit": "LOW", "term": "LOW"}},
    "QQQ": {"medium": {"vrp": "HIGH", "real_rate": "HIGH", "tsmom": "MED", "netliq": "LOW"}},
    "IWM": {"medium": {"credit": "HIGH", "credit_vel": "HIGH", "anfci": "HIGH", "term": "MED", "tsmom": "MED", "vrp": "MED"}},
    "DIA": {"medium": {"term": "MED", "tsmom": "MED", "vrp": "MED", "credit": "LOW"}},
}
# Sector SPDRs — each tied to a SPECIFIC driver (the per-asset edge). All legs oriented
# bullish (sign +1); validation never transfers, each gets its own gate block + Phase-0.
SECTOR_PRESETS = {
    "XLK": {"medium": {"real_rate": "HIGH", "vrp": "HIGH", "tsmom": "MED", "netliq": "MED"}},   # tech ~ QQQ (duration)
    "XLF": {"medium": {"term": "HIGH", "credit": "HIGH", "credit_vel": "MED", "tsmom": "MED", "vrp": "MED"}},  # banks: curve+credit
    "XLE": {"medium": {"oil_mom": "HIGH", "dollar": "MED", "tsmom": "MED", "vrp": "LOW"}},        # energy: oil
    "XLU": {"medium": {"real_rate": "HIGH", "term": "MED", "vrp": "MED"}},                        # utilities: bond proxy
    "XLRE": {"medium": {"real_rate": "HIGH", "term": "MED", "credit": "MED", "vrp": "LOW"}},      # REITs: rates+credit
    "XLB": {"medium": {"dollar": "HIGH", "oil_mom": "MED", "term": "MED", "tsmom": "MED"}},       # materials: dollar/commod
    "XLI": {"medium": {"term": "MED", "tsmom": "MED", "oil_mom": "LOW", "credit": "LOW"}},        # industrials: cyclical
    "XLY": {"medium": {"credit": "MED", "real_rate": "MED", "tsmom": "MED", "vrp": "LOW"}},       # discretionary
    "XLP": {"medium": {"real_rate": "MED", "vrp": "MED", "tsmom": "LOW"}},                        # staples (defensive)
    "XLV": {"medium": {"vrp": "MED", "tsmom": "MED", "real_rate": "LOW"}},                        # health (defensive)
    "XLC": {"medium": {"real_rate": "MED", "tsmom": "MED", "credit": "LOW"}},                     # comm services
}
# Unified per-ticker directional presets (indexes + sectors). The engine + Phase-0 key
# off membership here; sectors default display-only until their own block passes Phase-0.
PRESETS = {**INDEX_PRESETS, **SECTOR_PRESETS}
MEDIUM_TD = 42
# honest P(up) band for a scored medium-horizon index lean (the equity-premium drift
# alone gives ~0.55-0.58; a real conditional tilt nudges modestly around it)
P_BAND = (0.40, 0.62)
_Z_WIN = 756            # 3y rolling z for stationary, point-in-time leg standardization
_MKT: dict | None = None


def _col0(p: Path) -> pd.Series:
    d = pd.read_parquet(p)
    return d[d.columns[0]]


def _market() -> dict:
    """Shared market series (cached): VIX, net-liquidity inputs, real rate, HY OAS,
    term spread, ANFCI. Best-effort — a missing file yields an empty series and its
    legs simply drop out."""
    global _MKT
    if _MKT is not None:
        return _MKT
    F, Y = Path("data/fred"), Path("data/yahoo")

    def g(rel: Path) -> pd.Series:
        try:
            return _col0(rel)
        except Exception:
            return pd.Series(dtype=float)
    vix = g(F / "VIXCLS.parquet")
    if vix.empty:
        try:
            vix = pd.read_parquet(Y / "_VIX.parquet")["close"].replace(0, np.nan)
        except Exception:
            vix = pd.Series(dtype=float)
    oil = g(F / "DCOILWTICO.parquet")
    if oil.empty:
        try:
            oil = pd.read_parquet(Y / "CL_F.parquet")["close"]
        except Exception:
            oil = pd.Series(dtype=float)
    _MKT = {"vix": vix, "walcl": g(F / "WALCL.parquet"), "rrp": g(F / "RRPONTSYD.parquet"),
            "real10": g(F / "DFII10.parquet"), "hy_oas": g(F / "BAMLH0A0HYM2.parquet"),
            "t10y3m": g(F / "T10Y3M.parquet"), "anfci": g(F / "ANFCI.parquet"),
            "dollar": g(F / "DTWEXBGS.parquet"), "oil": oil}
    return _MKT


def _z(s: pd.Series, win: int = _Z_WIN) -> pd.Series:
    m = s.rolling(win, min_periods=252)
    return (s - m.mean()) / m.std(ddof=0).replace(0, np.nan)


def build_legs(close: pd.Series) -> pd.DataFrame:
    """Every candidate directional leg for an index, oriented so HIGHER = more bullish
    forward (a-priori sign +1), point-in-time. Market legs are shared; tsmom + vrp use
    the index's own price."""
    idx = close.index
    mkt = _market()
    R = lambda s: s.reindex(idx).ffill()
    out = pd.DataFrame(index=idx)
    rv = close.pct_change(fill_method=None).rolling(22).std(ddof=0) * np.sqrt(252) * 100.0
    vix = R(mkt["vix"])
    out["vrp"] = _z(vix - rv)                                   # implied minus realized vol → +
    out["tsmom"] = tsmom_alloc(close)                          # signed trend ∈[-1,1] → +
    if not mkt["walcl"].empty and not mkt["rrp"].empty:
        netliq = R(mkt["walcl"]) / 1e6 - R(mkt["rrp"])
        out["netliq"] = indicators.slope_z(netliq, 20, 60, use_log=False)   # expanding → +
    if not mkt["real10"].empty:
        out["real_rate"] = -_z(R(mkt["real10"]).diff(60))      # falling real rate → +
    if not mkt["hy_oas"].empty:
        out["credit"] = -_z(R(mkt["hy_oas"]))                  # tight credit → +
        out["credit_vel"] = -indicators.slope_z(R(mkt["hy_oas"]), 20, 60, use_log=False)  # narrowing → +
    if not mkt["t10y3m"].empty:
        out["term"] = _z(R(mkt["t10y3m"]))                     # steep curve → +
    if not mkt["anfci"].empty:
        out["anfci"] = -_z(R(mkt["anfci"]))                    # loose conditions → +
    if not mkt.get("oil", pd.Series(dtype=float)).empty:
        oil = R(mkt["oil"]).replace(0, np.nan)
        out["oil_mom"] = _z(oil.pct_change(60, fill_method=None))   # rising oil → energy/materials +
    if not mkt.get("dollar", pd.Series(dtype=float)).empty:
        out["dollar"] = -_z(R(mkt["dollar"]).diff(60))         # FALLING broad $ → commodities/materials +
    return out


def fwd_return(close: pd.Series, h: int) -> pd.Series:
    """Forward h-day simple return in % (NaN in the last h rows — never look-ahead)."""
    return 100.0 * (close.shift(-h) / close - 1.0)


def _ols_sign(x: np.ndarray, y: np.ndarray, sign: int = 1):
    """Univariate OLS (a,b) with the b-coefficient sign-clipped to `sign`; returns
    (a, b) or None if the slope robustly has the wrong sign (drop the leg)."""
    if len(x) < 60:
        return None
    xm, ym = x.mean(), y.mean()
    vx = float(np.sum((x - xm) ** 2))
    if vx <= 0:
        return None
    b = float(np.sum((x - xm) * (y - ym)) / vx)
    if b * sign < 0:                # wrong-sign → drop (collapse to the mean)
        return None
    a = float(ym - b * xm)
    return a, b


def fit_predict_latest(leg: pd.Series, fwd: pd.Series, sign: int = 1) -> float | None:
    """Expanding (= full history up to now, PIT since now is the last bar) sign-restricted
    univariate forecast of the latest forward return for one leg. None if the leg is
    unavailable now or its sign flipped."""
    j = pd.concat([leg.rename("x"), fwd.rename("y")], axis=1)
    train = j.dropna()
    if len(train) < 252:
        return None
    fit = _ols_sign(train["x"].to_numpy(), train["y"].to_numpy(), sign)
    x_now = leg.dropna()
    if fit is None or x_now.empty:
        return None
    a, b = fit
    return a + b * float(x_now.iloc[-1])


def combination_forecast(legs: pd.DataFrame, close: pd.Series, weights: dict, h: int,
                         go_legs: set | None = None) -> dict:
    """Sign-restricted, fixed-tier WEIGHTED-MEAN combination of the available legs →
    r̂ for horizon h. If go_legs is given, only those legs contribute to the scored
    forecast (others are display-only). Falls back to the historical mean when no leg
    survives. Returns {r_hat, used, all_legs}."""
    fwd = fwd_return(close, h)
    per_leg, used = {}, []
    for leg, tier in weights.items():
        if leg not in legs.columns:
            continue
        f = fit_predict_latest(legs[leg], fwd, sign=1)
        if f is None:
            continue
        per_leg[leg] = {"f": round(f, 3), "w": TIER.get(tier, 0.0)}
        if go_legs is None or leg in go_legs:
            used.append(leg)
    hist_mean = float(fwd.dropna().mean()) if fwd.notna().any() else 0.0
    if not used:
        return {"r_hat": round(hist_mean, 3), "used": [], "all_legs": per_leg, "fallback": True}
    num = sum(per_leg[l]["f"] * per_leg[l]["w"] for l in used)
    den = sum(per_leg[l]["w"] for l in used)
    r_hat = num / den if den else hist_mean
    return {"r_hat": round(float(r_hat), 3), "used": used, "all_legs": per_leg, "fallback": False}


def forecast_to_p_up(r_hat: float, sigma_h: float, platt: dict | None = None,
                     band: tuple = P_BAND) -> float:
    """P(up over h) = Φ(r̂/σ_h), optional Platt recalibration (logit a·z+b), clamped to
    the honest band. σ_h in the SAME % units as r̂."""
    if sigma_h is None or not np.isfinite(sigma_h) or sigma_h <= 0:
        return 0.5
    z = r_hat / sigma_h
    p = _norm_cdf(z)
    if platt and platt.get("a") is not None:
        a, b = platt["a"], platt.get("b", 0.0)
        lg = np.log(min(max(p, 1e-4), 1 - 1e-4) / (1 - min(max(p, 1e-4), 1 - 1e-4)))
        p = 1.0 / (1.0 + np.exp(-(a * lg + b)))
    return float(min(max(p, band[0]), band[1]))


def sigma_h(close: pd.Series, h: int) -> float:
    """Annualized cone vol scaled to the h-day horizon, in % (matches r̂ units)."""
    cv = vol_forecast.cone_vol_ann(close)
    if cv.dropna().empty:
        return float("nan")
    return float(cv.dropna().iloc[-1]) * np.sqrt(h / 252.0) * 100.0


def forecast(close: pd.Series, *, asset: str, gate: dict | None = None) -> dict:
    """Live per-index directional read for the scored horizons. Returns {} if the asset
    has no preset. `gate` = the INDEX_DIRECTION[asset] block (None ⇒ display-only)."""
    preset = PRESETS.get(asset)
    close = close.dropna().astype(float)
    if not preset or len(close) < 800:
        return {}
    legs = build_legs(close)
    g = gate or {}
    horizons = {}
    for hname, weights in preset.items():
        h = MEDIUM_TD if hname == "medium" else MEDIUM_TD
        gblock = g.get(hname, {})
        scored = bool(gblock.get("scored"))
        go_legs = {l for l, v in (gblock.get("legs") or {}).items() if v == "GO"} if scored else set()
        comb = combination_forecast(legs, close, weights, h, go_legs=(go_legs or None) if scored else set())
        sh = sigma_h(close, h)
        p_up = forecast_to_p_up(comb["r_hat"], sh, gblock.get("platt"),
                                tuple(gblock.get("p_up_band", P_BAND)))
        if not scored:
            p_up = 0.5            # display-only until the gate says GO
        horizons[hname] = {
            "r_hat": comb["r_hat"], "p_up": round(p_up, 3), "sigma_h": round(sh, 2) if np.isfinite(sh) else None,
            "scored": scored, "used": comb["used"], "legs": comb["all_legs"],
            "direction": ("up-lean" if p_up > 0.52 else ("down-lean" if p_up < 0.48 else "neutral")),
            "oos_r2": gblock.get("oos_r2"), "cw_p": gblock.get("cw_p"),
        }
    return {"asset": asset, "horizons": horizons,
            "trust": "scored (Clark-West OOS-R²>0)" if any(h["scored"] for h in horizons.values())
                     else "display-only (not yet validated OOS)"}

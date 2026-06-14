"""Cross-asset risk budgeting + crisis stress-replay (Phase D, additive).

Point 4 of the institutional-grade plan: "combine signals as UNCORRELATED bets,
size by conviction, cap risk." The live per-asset ladders size each market in
isolation; this module adds the missing cross-asset view on top of the same
correlation structure engine/cross_asset.py already measures:

  • RISK BUDGETING — equal-weight vs inverse-vol vs equal-risk-contribution (ERC)
    weights across the six markets, with each scheme's portfolio vol, per-market
    risk contributions, and the diversification ratio. ERC is the honest "no single
    bet dominates the risk" allocation; the gap between naive 1/n risk-contributions
    and ERC shows how concentrated an equal-weight expression of all six views is.
  • STRESS REPLAY — in the named crisis windows (GFC / 2018Q4 / COVID / 2022 bear /
    2015-16 China), each market's drawdown and what an equal-weight book of the then-
    available markets did. The point: in a stress everything correlates to 1, so the
    "diversified" six-view book still craters — the tail cost of the concentration
    that cross_asset.absorption flags in calm times.

ADDITIVE / leaf — nothing in the scoring path imports it; engine.run writes the
snapshot to latest.json["portfolio"]. Weights are a RISK-BUDGET REFERENCE, not a
trade list; daily closes across US/Asia/24-7 crypto carry the same timezone caveat
as cross_asset.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from engine.cross_asset import returns_frame
from lib import config

log = logging.getLogger(__name__)

TRADING_YEAR = 252

# Named crisis windows for the stress replay (markets without data in a window are
# simply excluded from that window's book).
CRISIS_WINDOWS = {
    "2008 GFC": ("2008-09-01", "2009-03-31"),
    "2015-16 China": ("2015-08-01", "2016-02-15"),
    "2018 Q4": ("2018-10-01", "2018-12-31"),
    "2020 COVID": ("2020-02-19", "2020-04-30"),
    "2022 bear": ("2022-01-01", "2022-10-31"),
}


def _cfg() -> dict:
    base = {"window_d": 126, "erc_iters": 2000, "erc_tol": 1e-9}
    return {**base, **(config.load().get("engine", {}).get("portfolio", {}) or {})}


def _ann_vol(w: np.ndarray, cov: np.ndarray) -> float:
    return float(np.sqrt(max(w @ cov @ w, 0.0)) * np.sqrt(TRADING_YEAR))


def _risk_contrib(w: np.ndarray, cov: np.ndarray) -> np.ndarray:
    """Per-asset share of total portfolio variance (sums to 1)."""
    pv = float(w @ cov @ w)
    if pv <= 0:
        return np.full(len(w), np.nan)
    return (w * (cov @ w)) / pv


def erc_weights(cov: np.ndarray, iters: int = 2000, tol: float = 1e-9,
                damp: float = 0.5) -> np.ndarray:
    """Equal-risk-contribution weights via the DAMPED multiplicative fixed point
    (Maillard-Roncalli-Teiletche): w_i ← w_i · (mean RC / RC_i)^damp, renormalized.
    The damping exponent (0.5) is essential — the undamped update diverges for a
    covariance with one very high-vol leg (crypto) and collapses onto a 2-asset
    corner; damped, it converges in ~25 iters to equalized risk contributions. Falls
    back to inverse-vol if it still hasn't converged."""
    n = cov.shape[0]
    vol = np.sqrt(np.clip(np.diag(cov), 1e-18, None))
    iv = (1.0 / vol) / (1.0 / vol).sum()
    w = iv.copy()
    for _ in range(int(iters)):
        rc = _risk_contrib(w, cov)
        if not np.all(np.isfinite(rc)):
            return iv
        if float(rc.max() - rc.min()) < tol:
            return w
        w = w * (rc.mean() / np.clip(rc, 1e-18, None)) ** damp
        w = np.clip(w, 0.0, None)
        s = w.sum()
        if s <= 0:
            return iv
        w = w / s
    # did not fully converge — accept only if risk is reasonably balanced, else fall back
    rc = _risk_contrib(w, cov)
    return w if np.isfinite(rc).all() and float(rc.max()) < 2.0 / n else iv


def _scheme(name: str, w: np.ndarray, cov: np.ndarray, cols: list) -> dict:
    rc = _risk_contrib(w, cov)
    avg_vol = float(np.dot(w, np.sqrt(np.clip(np.diag(cov), 0, None))) * np.sqrt(TRADING_YEAR))
    pvol = _ann_vol(w, cov)
    return {
        "scheme": name,
        "weights": {c: round(float(w[i]), 3) for i, c in enumerate(cols)},
        "risk_contrib": {c: round(float(rc[i]), 3) for i, c in enumerate(cols)},
        "port_vol_ann": round(pvol, 3),
        "diversification_ratio": round(avg_vol / pvol, 2) if pvol else None,
        "max_risk_contrib": round(float(np.nanmax(rc)), 3),
    }


def risk_budget(rets: pd.DataFrame, window: int, cfg: dict) -> dict | None:
    r = rets.dropna().tail(window)
    if len(r) < max(40, window // 2) or r.shape[1] < 3:
        return None
    cols = list(r.columns)
    cov = np.cov(r.values, rowvar=False)
    n = len(cols)
    ew = np.full(n, 1.0 / n)
    iv = 1.0 / np.sqrt(np.clip(np.diag(cov), 1e-18, None))
    iv = iv / iv.sum()
    erc = erc_weights(cov, cfg["erc_iters"], cfg["erc_tol"])
    return {"window_d": window, "markets": cols,
            "equal_weight": _scheme("equal_weight", ew, cov, cols),
            "inverse_vol": _scheme("inverse_vol", iv, cov, cols),
            "erc": _scheme("erc", erc, cov, cols)}


def _maxdd(equity: pd.Series) -> float:
    return float((equity / equity.cummax() - 1.0).min())


def stress_replay(rets: pd.DataFrame) -> list:
    out = []
    for name, (lo, hi) in CRISIS_WINDOWS.items():
        win = rets.loc[lo:hi]
        cols = [c for c in win.columns if win[c].notna().sum() >= 10]
        if len(cols) < 2:
            continue
        w = win[cols].fillna(0.0)
        per_mkt = {c: round(float((1 + w[c]).prod() - 1) * 100, 1) for c in cols}
        # equal-weight daily-rebalanced book of the available markets
        book = w.mean(axis=1)
        eq = (1 + book).cumprod()
        worst = min(per_mkt, key=per_mkt.get)
        best = max(per_mkt, key=per_mkt.get)
        out.append({
            "crisis": name, "span": f"{lo}..{hi}", "markets": cols,
            "book_return_pct": round(float(eq.iloc[-1] - 1) * 100, 1),
            "book_maxdd_pct": round(_maxdd(eq) * 100, 1),
            "worst_market": {worst: per_mkt[worst]}, "best_market": {best: per_mkt[best]},
            "per_market_pct": per_mkt,
        })
    return out


def snapshot() -> dict:
    """Latest risk-budget + stress-replay read for latest.json."""
    cfg = _cfg()
    rets = returns_frame()
    if rets.empty:
        return {"verdict": "unknown", "headline": "fewer than 3 markets have data"}
    rb = risk_budget(rets, int(cfg["window_d"]), cfg)
    if rb is None:
        return {"verdict": "unknown", "headline": "insufficient overlapping history",
                "markets": list(rets.columns)}

    ew_mrc = rb["equal_weight"]["max_risk_contrib"]
    erc_w = rb["erc"]["weights"]
    n = len(rb["markets"])
    heavy = max(erc_w, key=erc_w.get)
    headline = (f"Equal-weighting all {n} market views puts {round(ew_mrc * 100)}% of "
                f"portfolio RISK in one market (vs {round(100 / n)}% if truly balanced); "
                f"ERC rebalances to ~equal risk (heaviest weight: {heavy} {erc_w[heavy]}). "
                f"Diversification ratio {rb['erc']['diversification_ratio']}.")
    return {
        "asof": str(rets.dropna().index[-1].date()),
        "headline": headline,
        "risk_budget": rb,
        "stress_replay": stress_replay(rets),
        "evidence": ("Risk budgeting on the trailing covariance: equal-weight vs inverse-vol "
                     "vs equal-risk-contribution. Stress replay = equal-weight book of the "
                     "then-available markets through named crises. A risk-budget reference, "
                     "not a trade list; same timezone caveat as cross_asset."),
    }

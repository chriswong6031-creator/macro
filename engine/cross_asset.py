"""Cross-asset concentration — the "are the six markets secretly one bet?" detector.

The dashboard presents six markets (US equity, crypto, China A-shares, Hong Kong,
commodities, the dollar) as if they were independent reads. Point 3/4 of the
institutional-grade plan warns they are often the SAME liquidity/risk bet wearing
six hats — and stacking correlated views feels like diversification while doubling
the same exposure. This module measures it:

  • a rolling cross-market correlation matrix (risk-on-oriented, so + = same bet);
  • the ABSORPTION RATIO (Kritzman-Page) — the share of total variance explained by
    the first principal component. ~1/n means the markets move independently; →1
    means a single factor drives everything (a fragile, one-bet regime that has
    historically preceded drawdowns);
  • which markets load on that dominant factor (the cluster that's really one trade);
  • a percentile of today's absorption vs its own history → DIVERSIFIED / CONVERGING
    / CONCENTRATED verdict.

ADDITIVE / leaf module — nothing in the scoring path imports it; engine.run writes
its snapshot to latest.json["cross_asset"], degrading to verdict="unknown" if too
few markets have data. Daily closes span US/HK/China/24-7 crypto, so same-day
correlations carry a known timezone lead/lag — read this as a coarse regime gauge,
not a precise hedge ratio.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from engine.validation import top_correlated_pairs
from lib import config, store

log = logging.getLogger(__name__)

# market -> (store group, series, +1 if rising=risk-on else -1 to orient the sign).
# The dollar is inverted so a positive correlation reads as "same risk-on bet".
DEFAULT_MARKETS = {
    "US":          ("yahoo", "SPY", 1),
    "Crypto":      ("yahoo", "BTC-USD", 1),
    "China":       ("china", "510300.SS", 1),
    "HK":          ("hk", "_HSI", 1),
    "Commodities": ("yahoo", "HG=F", 1),   # copper — the cyclical/global-growth commodity
    "Dollar":      ("yahoo", "DX-Y.NYB", -1),
}


def _cfg() -> dict:
    base = {"window_d": 63, "ar_lookback_d": 252 * 5, "concentrated_pctile": 0.80,
            "diversified_pctile": 0.40, "loading_thresh": 0.40}
    return {**base, **(config.load().get("engine", {}).get("cross_asset", {}) or {})}


def _markets() -> dict:
    cfg = config.load().get("engine", {}).get("cross_asset", {}) or {}
    m = cfg.get("markets")
    return {k: tuple(v) for k, v in m.items()} if m else DEFAULT_MARKETS


def returns_frame() -> pd.DataFrame:
    """Aligned daily returns, oriented so + = risk-on, one column per available market."""
    cols = {}
    for name, (grp, sid, sign) in _markets().items():
        df = store.read(grp, sid)
        if df is None or "close" not in getattr(df, "columns", []):
            continue
        r = df["close"].astype(float).pct_change(fill_method=None) * sign
        s = r.dropna()
        if len(s) > 60:
            cols[name] = s
    if len(cols) < 3:
        return pd.DataFrame()
    return pd.DataFrame(cols).dropna(how="all")


def _absorption_ratio(corr: np.ndarray) -> float:
    """Share of variance in the largest principal component of a correlation matrix
    (Kritzman-Page absorption ratio). n^-1 = independent; →1 = one factor."""
    w = np.linalg.eigvalsh(corr)
    w = w[np.isfinite(w)]
    return float(w.max() / w.sum()) if w.size and w.sum() > 0 else float("nan")


def absorption_series(rets: pd.DataFrame, window: int) -> pd.Series:
    """Rolling absorption ratio. Computed on rows where all present markets have a
    return (so the correlation matrix is well-defined)."""
    r = rets.dropna()
    if len(r) < window + 5 or r.shape[1] < 3:
        return pd.Series(dtype=float)
    out = {}
    vals = r.values
    idx = r.index
    for i in range(window, len(r) + 1):
        c = np.corrcoef(vals[i - window:i], rowvar=False)
        out[idx[i - 1]] = _absorption_ratio(c)
    return pd.Series(out)


def snapshot() -> dict:
    """Latest cross-asset concentration read for latest.json."""
    c = _cfg()
    rets = returns_frame()
    if rets.empty:
        return {"verdict": "unknown", "headline": "fewer than 3 markets have data"}
    window = int(c["window_d"])
    aligned = rets.dropna()
    if len(aligned) < window + 5:
        return {"verdict": "unknown", "headline": "insufficient overlapping history",
                "markets": list(rets.columns)}

    recent = aligned.tail(window)
    corr = recent.corr()
    cm = corr.values
    ar = _absorption_ratio(cm)

    ar_hist = absorption_series(rets, window).tail(int(c["ar_lookback_d"]))
    ar_pctile = float((ar_hist <= ar).mean()) if len(ar_hist) else None

    # dominant factor: PC1 loadings — markets above the threshold ARE the one bet
    evals, evecs = np.linalg.eigh(cm)
    pc1 = evecs[:, int(np.argmax(evals))]
    if float(np.nansum(pc1)) < 0:           # orient PC1 so loadings read positive
        pc1 = -pc1
    loadings = {m: round(float(pc1[i]), 2) for i, m in enumerate(corr.columns)}
    cluster = sorted([m for m, l in loadings.items() if abs(l) >= c["loading_thresh"]],
                     key=lambda m: -abs(loadings[m]))

    # off-diagonal mean |corr|
    n = cm.shape[0]
    off = cm[~np.eye(n, dtype=bool)]
    mean_abs_corr = float(np.nanmean(np.abs(off))) if off.size else float("nan")

    if ar_pctile is not None and ar_pctile >= c["concentrated_pctile"]:
        verdict = "concentrated"
        headline = (f"CONCENTRATED — {len(cluster)} of {n} markets are one bet "
                    f"({', '.join(cluster)}). Cross-asset correlation is in the top "
                    f"{round((1 - ar_pctile) * 100)}% of its 5y range: stacking these "
                    f"views is doubling one liquidity/risk exposure, not diversifying.")
    elif ar_pctile is not None and ar_pctile <= c["diversified_pctile"]:
        verdict = "diversified"
        headline = (f"DIVERSIFIED — the {n} markets are moving largely independently "
                    f"(correlation in the bottom {round(ar_pctile * 100)}% of its 5y "
                    f"range); separate views are genuinely separate bets.")
    else:
        verdict = "converging"
        headline = (f"CONVERGING — cross-asset correlation is mid-range; the dominant "
                    f"cluster ({', '.join(cluster) or '—'}) is partly one bet.")

    return {
        "asof": str(aligned.index[-1].date()),
        "verdict": verdict,                 # diversified | converging | concentrated | unknown
        "headline": headline,
        "window_d": window,
        "markets": list(corr.columns),
        "absorption_ratio": round(ar, 3),
        "absorption_pctile_5y": None if ar_pctile is None else round(ar_pctile, 2),
        "absorption_floor": round(1.0 / n, 3),     # the independent-markets baseline
        "mean_abs_corr": round(mean_abs_corr, 3),
        "pc1_loadings": loadings,
        "dominant_cluster": cluster,
        "top_pairs": top_correlated_pairs(recent, k=6, thresh=0.5),
        "corr_matrix": {a: {b: round(float(corr.loc[a, b]), 2) for b in corr.columns}
                        for a in corr.columns},
        "evidence": ("Absorption ratio = PC1 variance share (Kritzman-Page 2010): high/rising "
                     "absorption marks a fragile one-factor regime that has historically led "
                     "drawdowns. Daily closes across US/Asia/24-7 crypto carry a timezone "
                     "lead/lag — a coarse regime gauge, not a hedge ratio."),
    }

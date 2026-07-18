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

from engine.validation import benjamini_hochberg, newey_west_tstat, top_correlated_pairs
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
            "diversified_pctile": 0.40, "loading_thresh": 0.40,
            # --- lead/lag transmission gauge ---
            "ll_window_d": 252, "ll_lags": [1, 2, 3, 5, 10], "ll_hac_lags": 10,
            "ll_alpha": 0.10, "ll_min_abs_r": 0.06, "ll_top": 8}
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

    # absorption_spark_w: weekly (W-FRI last) resample of ar_hist, tail 104, rounded 3dp
    _ar_spark_w: list = []
    _ar_spark_asof: str | None = None
    if len(ar_hist):
        try:
            _weekly = ar_hist.resample("W-FRI").last().dropna().tail(104)
            _ar_spark_w = [round(float(v), 3) for v in _weekly]
            _ar_spark_asof = str(_weekly.index[-1].date()) if len(_weekly) else None
        except Exception:  # noqa: BLE001 — additive, never fatal
            pass

    return {
        "asof": str(aligned.index[-1].date()),
        "verdict": verdict,                 # diversified | converging | concentrated | unknown
        # Pre-baked one-liner so a naive consumer can't reduce this leaf to a bare ratio.
        "summary": (f"{verdict.upper()} · {round(ar_pctile, 2)} 5y-pctile"
                    if ar_pctile is not None else verdict.upper()),
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
        # Weekly absorption sparkline (zero new compute — resampled from ar_hist above)
        "absorption_spark_w": _ar_spark_w,
        "absorption_spark_asof": _ar_spark_asof,
        "evidence": ("Absorption ratio = PC1 variance share (Kritzman-Page 2010): high/rising "
                     "absorption marks a fragile one-factor regime that has historically led "
                     "drawdowns. Daily closes across US/Asia/24-7 crypto carry a timezone "
                     "lead/lag — a coarse regime gauge, not a hedge ratio."),
    }


def leadlag_pairs(rets: pd.DataFrame, lags, window: int, hac_lags: int = 10,
                  alpha: float = 0.10) -> list[dict]:
    """HAC-gated lead/lag cross-correlations for every ORDERED market pair.

    For leader L and follower F at lag k>=1, the daily series

        prod_t = z_F(t) * z_L(t-k)

    has mean ~= corr(F_t, L_{t-k}): does the leader's PAST move predict the
    follower's present? Its Newey-West (HAC) t-stat tests mean != 0 while
    correcting for the volatility-clustering autocorrelation that would otherwise
    overstate significance, and a Benjamini-Hochberg pass across the whole
    (pair x lag) panel controls the false-discovery rate from screening many
    pairs. z-scores are taken over the window so each mean is a standardized,
    correlation-like quantity comparable across pairs.
    """
    r = rets.dropna()
    lags = [int(k) for k in lags if int(k) >= 1]
    if r.shape[1] < 3 or not lags:
        return []
    if len(r) > window:
        r = r.tail(window)
    if len(r) < max(60, max(lags) + 40):
        return []
    Z = {}
    for c in r.columns:
        sd = float(r[c].std())
        if sd and np.isfinite(sd) and sd > 0:
            Z[c] = (r[c] - r[c].mean()) / sd
    cols = list(Z.keys())
    recs, pvals = [], {}
    for L in cols:
        for F in cols:
            if L == F:
                continue
            for k in lags:
                prod = (Z[F] * Z[L].shift(k)).dropna()       # z_F(t) * z_L(t-k)
                if len(prod) < 30:
                    continue
                nw = newey_west_tstat(prod, lags=hac_lags)
                if nw["t"] is None:
                    continue
                key = f"{L}>{F}@{k}"
                pvals[key] = nw["p"]
                recs.append({"leader": L, "follower": F, "lag": k,
                             "r": round(float(prod.mean()), 3), "t": nw["t"],
                             "p": nw["p"], "n": nw["n"], "_key": key})
    bh = benjamini_hochberg(pvals, alpha=alpha)
    for rec in recs:
        q = bh.get(rec.pop("_key"), {})
        rec["q"] = q.get("q")
        rec["sig"] = bool(q.get("reject"))
    return recs


def leadlag_snapshot() -> dict:
    """Which asset is leading the others right now, by how many days, with what
    confidence — a DESCRIPTIVE transmission/regime gauge, never a hedge ratio.

    Daily lead/lag is unstable and inflates t-stats on overlapping windows, so
    every link is HAC-corrected and FDR-gated, a stability check re-tests the
    prior window, and the honest default verdict is "contemporaneous" (no pair
    survives). The one structural link we expect is the timezone one: the US
    close leads the next Asia session by a day.
    """
    c = _cfg()
    rets = returns_frame()
    window, lags = int(c["ll_window_d"]), c["ll_lags"]
    min_r, hac, alpha = float(c["ll_min_abs_r"]), int(c["ll_hac_lags"]), float(c["ll_alpha"])

    if rets.empty:
        return {"verdict": "unknown", "headline": "fewer than 3 markets have data"}
    aligned = rets.dropna()
    if len(aligned) < window + max(int(k) for k in lags) + 5:
        return {"verdict": "unknown", "headline": "insufficient overlapping history",
                "markets": list(rets.columns)}

    recs = leadlag_pairs(rets, lags, window, hac_lags=hac, alpha=alpha)
    sig = sorted([x for x in recs if x["sig"] and abs(x["r"]) >= min_r],
                 key=lambda x: -abs(x["t"]))

    base = {"asof": str(aligned.index[-1].date()), "window_d": window, "lags": lags,
            "markets": list(aligned.columns), "n_tested": len(recs), "n_significant": len(sig),
            "evidence": ("Lead/lag = mean of z_follower(t)·z_leader(t−k), Newey-West (HAC) "
                         "t-stat, Benjamini-Hochberg FDR across all ordered pairs×lags. Daily "
                         "lead/lag is noisy and partly timezone-driven (the US closes before "
                         "Asia opens) — a transmission/regime gauge, NOT a tradeable hedge ratio.")}

    if not sig:
        return {**base, "verdict": "contemporaneous", "links": [], "lead_asset": None,
                "headline": (f"No stable cross-asset lead over the last {window}d — moves are "
                             "broadly contemporaneous at daily frequency (no pair survives "
                             "HAC + FDR).")}

    score: dict[str, list[str]] = {}
    for x in sig:
        score.setdefault(x["leader"], []).append(x["follower"])
    lead = max(score.items(), key=lambda kv: len(kv[1]))
    lead_asset = {"name": lead[0], "n_followers": len(set(lead[1])),
                  "followers": sorted(set(lead[1]))}

    # stability: re-test the PRIOR window — does the top link keep its sign and
    # clear conventional significance (|HAC t|>=2)? (A softer, fairer bar than the
    # full-panel FDR, which over-penalises a single-lag re-test.)
    top = sig[0]
    held, prior_t = None, None
    if len(aligned) >= 2 * window:
        prior = aligned.iloc[-(2 * window):-window]
        pr = leadlag_pairs(prior, [top["lag"]], len(prior), hac_lags=hac, alpha=alpha)
        m = next((x for x in pr if x["leader"] == top["leader"]
                  and x["follower"] == top["follower"]), None)
        if m and m["t"] is not None:
            prior_t = m["t"]
            held = bool(np.sign(m["r"]) == np.sign(top["r"]) and abs(m["t"]) >= 2.0)
    stable = held is True

    lag_word = "1 day" if top["lag"] == 1 else f"{top['lag']} days"
    head = (f"{top['leader']} is leading {top['follower']} by ~{lag_word} "
            f"(r={top['r']:+.2f}, HAC t={top['t']:+.1f}, FDR q={top['q']}). ")
    if lead_asset["n_followers"] >= 2:
        head += f"{lead_asset['name']} leads {lead_asset['n_followers']} markets. "
    head += ("Held sign+significance in the prior window."
             if stable else "Unstable across the prior window — treat as tentative.")

    return {**base, "verdict": "lead" if stable else "weak_lead", "headline": head,
            "links": [{k: x[k] for k in ("leader", "follower", "lag", "r", "t", "q")}
                      for x in sig[: int(c["ll_top"])]],
            "lead_asset": lead_asset,
            "stability": {"top_link": f"{top['leader']}→{top['follower']}@{top['lag']}d",
                          "held_prior_window": held, "prior_t": prior_t}}

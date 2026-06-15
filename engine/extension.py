"""Per-name extension / exhaustion read for the Top-Picks board (display-only).

The Top-Picks rank stays the validated `alpha_led` conviction blend — momentum is the
edge and folding mean-reversion/value INTO the rank measurably hurts (reports/top-picks-
phase0.md). But the rank's top is, by construction, the most-extended momentum names, and
the user's worry is "sharp pullbacks, especially in a bubble." That is a per-name RISK
question. We answer it with an extension axis that NEVER touches the score.

What the Phase-0 downside test established (reports/top-picks-freshness-phase0.md,
138 PIT rebalances, long-only, drawdown-aware):
  * NO basket screen reduces drawdown — requiring "freshness / near-highs" actually makes
    it WORSE (it just concentrates the book). So there is no honest "fresh-leaders rotation"
    to sell; the extension read is a PER-NAME risk-placement lens, not a return claim.
  * The danger is concentrated and per-name: the PARABOLIC tail (ext_z > 2 — more than 2σ
    above the name's own normal distance from its 200-day average) is radioactive — in the
    backtest that cohort ran 9% return on 50% vol with a −94% drawdown, −1.37 skew and
    1.64 crashes/yr, vs the full top cohort's 18.9% / 25% / −49% / 0.41. THAT stark gap is
    the validated basis for the parabolic flag.

So this module is descriptive, graded, honest:

  ext_z      price/SMA200 − 1, z-scored vs the name's OWN trailing 252d  (own-history extension)
  near_52wh  price / trailing-252d max                                   (George-Hwang proximity)
  id_score   −[sgn(PRET)·(%neg − %pos)] over the 12-1 window             (frog-in-the-pan continuity)
  grade      in-trend / steady / stretched / parabolic                   (the display chip)
  val        current earnings-yield vs the name's own ~3y history        (valuation-vs-own, coarse)

All from the daily close matrix the page already loads — NO new data, NEVER scored.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# grade thresholds — ext_z>2 is the validated parabolic flag; 1..2 stretched.
PARABOLIC_Z = 2.0
STRETCHED_Z = 1.0
INTREND_NEAR = 0.85        # within 15% of its own 52w high
INTREND_MAX_Z = 1.0        # ...and not stretched vs its own trend

# grade: (label_en, label_zh, css, is_caution)
GRADES = {
    "intrend":   ("In-trend",  "趋势内", "ex-intrend",   False),  # leader in its range, not stretched
    "steady":    ("Steady",    "平稳",   "ex-steady",    False),
    "stretched": ("Stretched", "拉伸",   "ex-stretched", True),
    "parabolic": ("Parabolic", "抛物",   "ex-parabolic", True),   # the validated radioactive flag
    "na":        ("—",         "—",      "ex-na",        False),
}

VAL_LABELS = {
    # label key: (en, zh, css)
    "cheap":    ("Cheap vs own", "相对自身偏低", "val-cheap"),
    "rich":     ("Rich vs own",  "相对自身偏高", "val-rich"),
    "richest":  ("Richest in 3y", "近3年最贵",   "val-richest"),
}


def grade(ext_z: float | None, near_52wh: float | None) -> str:
    """Descriptive extension grade from own-history extension. Risk-placement, not a
    return/drawdown claim (the Phase-0 test showed freshness does NOT cut drawdown)."""
    if ext_z is None or (isinstance(ext_z, float) and np.isnan(ext_z)):
        return "na"
    if ext_z >= PARABOLIC_Z:
        return "parabolic"
    if ext_z >= STRETCHED_Z:
        return "stretched"
    if near_52wh is not None and not np.isnan(near_52wh) \
            and near_52wh >= INTREND_NEAR and ext_z < 0.5:
        return "intrend"
    return "steady"


def _latest(s: pd.Series) -> float | None:
    if s is None or s.empty:
        return None
    v = s.iloc[-1]
    return float(v) if pd.notna(v) else None


def extension_signals(closes: pd.DataFrame) -> dict[str, dict]:
    """Latest per-ticker {ext, ext_z, near_52wh, id_score, grade, parabolic} from a daily
    close matrix (date × ticker). Mirrors scripts/top_picks_freshness_phase0.price_signals
    so the live chip equals the back-tested quantity. Names with too little history are
    omitted (the page degrades to no chip)."""
    if closes is None or closes.empty:
        return {}
    px = closes.sort_index()
    R = px.pct_change(fill_method=None)

    sma200 = px.rolling(200, min_periods=100).mean()
    ext = px / sma200 - 1.0
    ext_z = (ext - ext.rolling(252, min_periods=120).mean()) \
        / ext.rolling(252, min_periods=120).std().replace(0, np.nan)
    near = px / px.rolling(252, min_periods=120).max()

    pret = px.shift(21) / px.shift(252) - 1.0
    sgn = np.sign(R)
    win = 252 - 21
    pos = (sgn > 0).rolling(win, min_periods=120).mean().shift(21)
    neg = (sgn < 0).rolling(win, min_periods=120).mean().shift(21)
    id_score = -(np.sign(pret) * (neg - pos))

    ext_l, ez_l, near_l, id_l = ext.iloc[-1], ext_z.iloc[-1], near.iloc[-1], id_score.iloc[-1]
    out: dict[str, dict] = {}
    for t in px.columns:
        ez = ez_l.get(t)
        nr = near_l.get(t)
        if ez is None or pd.isna(ez):
            continue
        g = grade(float(ez), float(nr) if pd.notna(nr) else None)
        out[t] = {
            "ext": round(float(ext_l[t]) * 100, 1) if pd.notna(ext_l.get(t)) else None,
            "ext_z": round(float(ez), 2),
            "near_52wh": round(float(nr), 3) if pd.notna(nr) else None,
            "id_score": round(float(id_l[t]), 3) if pd.notna(id_l.get(t)) else None,
            "grade": g,
            "parabolic": g == "parabolic",
        }
    return out


def valuation_vs_history(closes: pd.DataFrame, panel: pd.DataFrame) -> dict[str, dict]:
    """Per-ticker current earnings-yield percentile vs the name's OWN history over the
    price window available. EY_t = EPS_known_at_t / price_t, where EPS steps on each annual
    filing (PIT via asof_date) — so it reflects both price AND earnings, not price alone.

    Returns {ticker: {ey_pctile, val_label}} only for names where the read is meaningful
    (>=120 daily obs). Coarse (annual EPS) and window-limited — a display/context flag,
    never scored. `val_label` is set only at the tails (cheap / rich / richest)."""
    if closes is None or closes.empty or panel is None or panel.empty:
        return {}
    p = panel.dropna(subset=["asof_date"]).copy()
    p["asof_date"] = pd.to_datetime(p["asof_date"])
    p = p.sort_values("asof_date")
    px = closes.sort_index()
    idx = px.index
    out: dict[str, dict] = {}
    for t, grp in p.groupby("ticker"):
        if t not in px.columns:
            continue
        price = px[t].dropna()
        if len(price) < 120:
            continue
        g = grp[["asof_date", "ni", "shares"]].dropna()
        g = g[(g["shares"] > 0)]
        if g.empty:
            continue
        # step EPS series aligned to the price index (latest filing with asof_date <= date)
        eps = (g.set_index("asof_date")["ni"] / g.set_index("asof_date")["shares"])
        eps = eps[~eps.index.duplicated(keep="last")].sort_index()
        eps_daily = eps.reindex(idx, method="ffill")
        ey = (eps_daily / price).replace([np.inf, -np.inf], np.nan).dropna()
        ey = ey[ey != 0]
        if len(ey) < 120:
            continue
        cur = ey.iloc[-1]
        pct = float((ey <= cur).mean() * 100)        # high pct = cheap (high earnings yield)
        label = None
        if pct >= 66:
            label = "cheap"
        elif pct <= 10:
            label = "richest"
        elif pct <= 33:
            label = "rich"
        out[t] = {"ey_pctile": round(pct), "val_label": label}
    return out


def cohort_stretch(readings: list[dict]) -> dict:
    """Board-level fragility gauge from the top-conviction cohort's extension readings.
    DISPLAY-ONLY sizing context — crowding/stretch raises crash *probability*, it does not
    time the market (Asness: factor timing is hard). Never a fade, never gates the rank.

    `readings` = per-name dicts (the top-conviction slice) with ext_z / near_52wh / grade.
    Returns {state, median_ext_z, pct_parabolic, pct_stretched, pct_at_highs, n}."""
    ez = [r["ext_z"] for r in readings if r.get("ext_z") is not None]
    if len(ez) < 8:
        return {"state": "na", "n": len(ez)}
    n = len(ez)
    med = float(np.median(ez))
    pct_parab = 100 * sum(1 for r in readings if r.get("grade") == "parabolic") / n
    pct_stretch = 100 * sum(1 for r in readings
                            if r.get("grade") in ("stretched", "parabolic")) / n
    pct_highs = 100 * sum(1 for r in readings
                          if (r.get("near_52wh") or 0) >= 0.95) / n
    # state: descriptive tiers on how stretched the leadership cohort is vs its own norms
    if med >= 1.0 or pct_stretch >= 45 or pct_parab >= 12:
        state = "stretched"
    elif med >= 0.5 or pct_stretch >= 30:
        state = "elevated"
    else:
        state = "normal"
    return {"state": state, "median_ext_z": round(med, 2),
            "pct_parabolic": round(pct_parab), "pct_stretched": round(pct_stretch),
            "pct_at_highs": round(pct_highs), "n": n}

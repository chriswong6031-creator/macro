"""Per-instrument technicals + seasonality, and the confluence score.

Everything is computed from EOD closes already in the store. The confluence
score is a TRANSPARENT weighted checklist (weights in config.yml), not a
black box — and its "certainty" is measured, not asserted: the same score is
computed across all of history and calibrated against forward 63-day excess
returns, so each score band displays its actual historical hit rate.

Seasonality is shown as separate context and kept OUT of the calibrated score:
scoring history with full-sample seasonal stats would peek at the future.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from lib import config

log = logging.getLogger(__name__)


# ------------------------------------------------------------- indicators ----

def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    up = delta.clip(lower=0).ewm(alpha=1 / n, min_periods=n).mean()
    dn = (-delta.clip(upper=0)).ewm(alpha=1 / n, min_periods=n).mean()
    rs = up / dn.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def macd_hist(close: pd.Series) -> pd.Series:
    ema12 = close.ewm(span=12, min_periods=12).mean()
    ema26 = close.ewm(span=26, min_periods=26).mean()
    macd = ema12 - ema26
    return macd - macd.ewm(span=9, min_periods=9).mean()


def tech_frame(close: pd.Series) -> pd.DataFrame:
    """Daily technical state, full history (used both live and for calibration)."""
    f = pd.DataFrame(index=close.index)
    f["close"] = close
    f["sma50"] = close.rolling(50).mean()
    f["sma200"] = close.rolling(200).mean()
    f["above50"] = close > f["sma50"]
    f["above200"] = close > f["sma200"]
    f["rsi14"] = rsi(close)
    f["macd_pos"] = macd_hist(close) > 0
    roll_hi = close.rolling(252, min_periods=200).max()
    roll_lo = close.rolling(252, min_periods=200).min()
    f["off_52w_high_pct"] = (close / roll_hi - 1) * 100
    f["above_52w_low_pct"] = (close / roll_lo - 1) * 100
    return f


def snapshot(close: pd.Series) -> dict:
    t = tech_frame(close).iloc[-1]
    return {
        "price": round(float(t["close"]), 2),
        "above50": bool(t["above50"]), "above200": bool(t["above200"]),
        "pct_vs_50dma": round(float(t["close"] / t["sma50"] - 1) * 100, 1)
        if pd.notna(t["sma50"]) else None,
        "pct_vs_200dma": round(float(t["close"] / t["sma200"] - 1) * 100, 1)
        if pd.notna(t["sma200"]) else None,
        "rsi14": round(float(t["rsi14"]), 0) if pd.notna(t["rsi14"]) else None,
        "macd_pos": bool(t["macd_pos"]),
        "off_52w_high_pct": round(float(t["off_52w_high_pct"]), 1),
    }


# ------------------------------------------------------------- seasonality ----

def seasonality(close: pd.Series, min_years: int = 10) -> dict:
    """Calendar-month tendencies from the instrument's own full history.
    Weak evidence by nature — displayed as context, never scored."""
    monthly = close.resample("ME").last().pct_change(fill_method=None).dropna()
    if len(monthly) < min_years * 12 * 0.7:
        return {}
    out = {}
    for m in range(1, 13):
        r = monthly[monthly.index.month == m]
        if len(r) >= min_years * 0.7:
            out[m] = {"avg_pct": round(float(r.mean() * 100), 2),
                      "hit_pct": round(float((r > 0).mean() * 100), 0),
                      "n": int(len(r))}
    return out


def season_line(seas: dict, month: int, zh: bool = False) -> str | None:
    s = seas.get(month)
    if not s:
        return None
    if zh:
        return f"{month}月：平均 {s['avg_pct']:+.1f}%，{s['hit_pct']:.0f}% 的年份上涨（n={s['n']}）"
    import calendar
    name = calendar.month_abbr[month]
    return f"{name}: {s['avg_pct']:+.1f}% avg, up {s['hit_pct']:.0f}% of years (n={s['n']})"


# ---------------------------------------------------------------- scoring ----

def _score_components(aligned: bool, dial_score: int, stage: str, extended: bool,
                      tech: dict, rs_pctile: float) -> dict:
    """Transparent checklist. Returns each sub-score so the UI can show its work."""
    w = config.load()["engine"]["confluence"]

    regime = w["regime_aligned"] if aligned else w["regime_neutral"]
    if aligned and dial_score >= 1:
        regime = w["regime_aligned_risk_on"]

    tape = {"leading": w["tape_leading"], "improving": w["tape_improving"],
            "weakening": w["tape_weakening"], "lagging": w["tape_lagging"]}[stage]
    if extended:
        tape = w["tape_extended"]

    tech_pts = 0
    if tech.get("above200"):
        tech_pts += w["tech_above200"]
    if tech.get("above50"):
        tech_pts += w["tech_above50"]
    if tech.get("macd_pos"):
        tech_pts += w["tech_macd"]
    r = tech.get("rsi14")
    if r is not None:
        if w["rsi_sweet_lo"] <= r <= w["rsi_sweet_hi"]:
            tech_pts += w["tech_rsi_sweet"]
        elif r > w["rsi_overbought"]:
            tech_pts += 0
        else:
            tech_pts += w["tech_rsi_ok"]

    crowding = 0
    if rs_pctile >= w["crowding_hard_pctile"]:
        crowding = -w["crowding_hard_penalty"]
    elif rs_pctile >= w["crowding_soft_pctile"]:
        crowding = -w["crowding_soft_penalty"]

    total = max(0, min(100, regime + tape + tech_pts + crowding))
    return {"score": total, "regime": regime, "tape": tape,
            "technicals": tech_pts, "crowding": crowding}


# ------------------------------------------------------------- calibration ----

def calibrate(closes: pd.DataFrame, regime: pd.DataFrame) -> dict:
    """Compute the (seasonality-free) score across history, weekly-sampled,
    and measure forward 63d excess vs SPY per score band. THE honesty layer:
    whatever these numbers say is what the UI shows."""
    w = config.load()["engine"]["confluence"]
    bench = config.load()["engine"]["rs_ranking"]["benchmark"]
    prefs = config.load()["engine"]["sector_preferences"]
    sectors = [t for t in config.load()["yahoo"]["tickers"]["sectors"]
               if t in closes.columns]
    quad = regime["quad"].reindex(closes.index)
    liq = regime["liquidity"].reindex(closes.index)
    state = regime["transition_state"].reindex(closes.index) \
        if "transition_state" in regime.columns else pd.Series("STABLE", index=closes.index)
    # simplified historical dial: risk-on quad & stable (+1), liquidity (+/-1), Q3 (-1)
    dial = (quad.isin(["Q1", "Q2"]) & (state == "STABLE")).astype(int) \
        + (liq == "expanding").astype(int) - (liq == "contracting").astype(int) \
        - (quad == "Q3").astype(int)

    spy_fwd = closes[bench].pct_change(63).shift(-63)
    weekly = pd.Series(False, index=closes.index)
    weekly.iloc[::5] = True

    scores_all, fwd_all = [], []
    for t in sectors:
        close = closes[t]
        tf = tech_frame(close)
        rs = close / closes[bench]
        ma = rs.rolling(200).mean()
        mom20 = rs.pct_change(20)
        pct = rs.rolling(252).rank(pct=True) * 100
        above = rs > ma
        aligned = quad.map(lambda q: isinstance(q, str) and t in prefs.get(q, [])).fillna(False)

        regime_pts = np.where(aligned & (dial >= 1), w["regime_aligned_risk_on"],
                              np.where(aligned, w["regime_aligned"], w["regime_neutral"]))
        tape_pts = np.select(
            [above & (mom20 > 0) & (pct >= w["crowding_hard_pctile"]),
             above & (mom20 > 0), above, (~above) & (mom20 > 0)],
            [w["tape_extended"], w["tape_leading"], w["tape_weakening"],
             w["tape_improving"]], default=w["tape_lagging"])
        rsi_s = tf["rsi14"]
        tech_pts = (tf["above200"].astype(int) * w["tech_above200"]
                    + tf["above50"].astype(int) * w["tech_above50"]
                    + tf["macd_pos"].astype(int) * w["tech_macd"]
                    + np.where((rsi_s >= w["rsi_sweet_lo"]) & (rsi_s <= w["rsi_sweet_hi"]),
                               w["tech_rsi_sweet"],
                               np.where(rsi_s > w["rsi_overbought"], 0, w["tech_rsi_ok"])))
        crowd = np.where(pct >= w["crowding_hard_pctile"], -w["crowding_hard_penalty"],
                         np.where(pct >= w["crowding_soft_pctile"],
                                  -w["crowding_soft_penalty"], 0))
        score = pd.Series(regime_pts + tape_pts + tech_pts + crowd,
                          index=closes.index).clip(0, 100)
        fwd_ex = close.pct_change(63).shift(-63) - spy_fwd
        ok = weekly & fwd_ex.notna() & score.notna() & quad.notna()
        scores_all.append(score[ok])
        fwd_all.append(fwd_ex[ok])

    s = pd.concat(scores_all)
    fx = pd.concat(fwd_all)
    bands = [(0, 40, "0-39"), (40, 55, "40-54"), (55, 70, "55-69"), (70, 101, "70+")]
    out = {}
    for lo, hi, label in bands:
        m = (s >= lo) & (s < hi)
        if m.sum() >= 50:
            v = fx[m]
            out[label] = {"n": int(m.sum()),
                          "hit_pct": round(100 * (v > 0).mean(), 1),
                          "avg_excess_pct": round(100 * v.mean(), 2)}
    return out


def band_for(score: float) -> str:
    if score >= 70:
        return "70+"
    if score >= 55:
        return "55-69"
    if score >= 40:
        return "40-54"
    return "0-39"

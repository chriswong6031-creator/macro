"""Term-structure (roll-yield) CONTEXT helpers — the validated honesty layer over
the existing carry display panel.  LEAF: never imported by the scoring path, never
feeds conviction.  Pure functions + a thin loader.

WHY THIS EXISTS
The commodities page already shows a "Term structure (carry)" line (backwardation /
contango + annualized roll yield).  scripts/commodity_carry_phase0.py validated that
signal on 38 years of EIA WTI futures and found:

  * Backwardation DOES pay positive roll carry to a long (mechanically true), BUT
  * it does NOT predict spot going up — the opposite: the basis→forward-spot IC is
    robustly NEGATIVE (63d IC -0.16, t_HAC -4.6, both halves), i.e. extreme
    backwardation is a spot MEAN-REVERSION warning, not a bullish tell.  Crediting the
    carry roughly cancels the spot reversal (total-return IC ~+0.15) — which is why
    cross-sectional carry harvesting works but single-asset directional timing sees the
    reversal.

So the panel must distinguish CARRY (backwardation = +carry) from DIRECTION
(backwardation = reversion risk).  This module supplies (a) that validated caveat text
and (b) a DEEP historical percentile for oil (the panel otherwise ranks today's roll
yield against only ~18 months of the live Yahoo collector; EIA gives 38 years).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

_EIA_CACHE = Path(__file__).resolve().parent.parent / "data" / "commodity_carry" / "eia_wti_termstructure.parquet"

# Validated caveat (bilingual) — surfaced verbatim on the carry line.
CARRY_CAVEAT = {
    "en": ("Carry ≠ direction: backwardation pays positive roll to longs, but on 38y of "
           "WTI it was a spot mean-reversion warning (backwardated → +0.4%/21d vs "
           "contango +1.3%; 63d IC −0.16). Context, not a buy signal."),
    "zh": ("套利≠方向：现货升水（backwardation）对多头有正展期收益，但38年WTI数据显示它是现货均值"
           "回归的警示（升水后21天 +0.4%，对比期货升水 +1.3%；63天IC −0.16）。仅为背景，非买入信号。"),
}


def historical_pctile(today_value: float, hist: pd.Series) -> dict | None:
    """Where today's roll yield ranks within a deep historical distribution.
    `hist` = a long series of annualized roll yields (e.g. EIA WTI 1986-2024).
    Returns the percentile (0-100), span years, and a plain regime band."""
    if today_value is None or hist is None:
        return None
    h = pd.Series(hist).replace([np.inf, -np.inf], np.nan).dropna()
    if len(h) < 250:
        return None
    pct = float((h < today_value).mean())
    years = round(len(h) / 252.0, 0)
    return {"deep_pctile": int(round(pct * 100)), "deep_years": int(years),
            "extreme": pct >= 0.9 or pct <= 0.1}


def eia_roll_yield_history() -> pd.Series | None:
    """Annualized 1-month roll yield from the cached deep EIA WTI futures stack
    (front C1 vs second C2). Static research dataset (EIA hist_xls froze 2024-04);
    used only as a historical reference distribution, never as a live price."""
    if not _EIA_CACHE.exists():
        return None
    try:
        df = pd.read_parquet(_EIA_CACHE)
    except Exception:  # noqa: BLE001 — degrade, never raise
        return None
    if not {"c1", "c2"}.issubset(df.columns):
        return None
    with np.errstate(invalid="ignore", divide="ignore"):
        basis = np.log(df["c1"] / df["c2"]).replace([np.inf, -np.inf], np.nan).dropna()
    return (basis * 12.0).rename("roll_yield_ann")   # match the live collector's annualization


def deep_oil_context(roll_ann_today_pct: float) -> dict | None:
    """Convenience: deep-history percentile for oil given today's roll yield in
    PERCENT/yr (the unit the build's _carry_read already produces). Degrades to
    None when the cache is absent."""
    hist = eia_roll_yield_history()
    if hist is None:
        return None
    return historical_pctile(roll_ann_today_pct / 100.0, hist)

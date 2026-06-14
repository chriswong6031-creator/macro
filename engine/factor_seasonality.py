"""Factor seasonality from the Ken French Data Library (collectors/french.py).

The deep-history answer to "which calendar months has each factor STYLE tended to
pay?" — computed on academic total-US-market long/short factor returns going back
to 1926-1963, decades longer than our ~3yr S&P-1500 price cache. For each French
factor and each calendar month we report mean, median and hit-rate (% of months
positive), over BOTH the full history AND a trailing 30-year window.

DELIBERATELY UNSCORED context, mirroring engine/technicals.seasonality: full-sample
seasonal stats peek at the future, so this never enters a calibrated/PIT score —
it is displayed as the long-run seasonal CLIMATE of a style. And it is a DEFINITION
MISMATCH vs our own factors: French HML/RMW/CMA are value-weighted long/short
portfolios over the whole US market, not our winsorized cross-sectional z-score
quintiles over the S&P 1500. The page discloses both caveats.
"""
from __future__ import annotations

import logging

import pandas as pd

from lib import store

log = logging.getLogger(__name__)

# our-facing key -> (French column, our live factor or None if context-only, EN label, ZH label)
SEASON_MAP = [
    ("value",         "hml",    "value",         "Value (HML)",        "价值 (HML)"),
    ("profitability", "rmw",    "profitability", "Profitability (RMW)", "盈利 (RMW)"),
    ("investment",    "cma",    "investment",    "Investment (CMA)",   "投资 (CMA)"),
    ("momentum",      "mom",    None,            "Momentum (Mom)",     "动量 (Mom)"),
    ("size",          "smb",    None,            "Size (SMB)",         "规模 (SMB)"),
    ("market",        "mkt_rf", None,            "Market (Mkt-RF)",    "市场 (Mkt-RF)"),
]

_TRAILING_YEARS = 30
_MIN_PER_MONTH = 3                      # need at least this many observations of a calendar month


def _month_stats(s: pd.Series, years: int | None = None) -> dict:
    """Per-calendar-month mean / median / hit-rate / n for a monthly return series."""
    s = s.dropna()
    if years and not s.empty:
        s = s[s.index > s.index.max() - pd.DateOffset(years=years)]
    out = {}
    for m in range(1, 13):
        r = s[s.index.month == m]
        if len(r) >= _MIN_PER_MONTH:
            out[m] = {"mean": round(float(r.mean()), 2),
                      "median": round(float(r.median()), 2),
                      "hit": round(float((r > 0).mean() * 100)),
                      "n": int(len(r))}
    return out


def compute_factor_seasonality() -> dict | None:
    """Build the factor-seasonality payload from data/french/factors.parquet.
    Returns None (panel hides) if the French data is absent — degrade-never-raise."""
    df = store.read("french", "factors")
    if df is None or df.empty:
        return None
    df = df.copy()
    df.index = pd.to_datetime(df.index)

    factors = []
    for key, col, our, label_en, label_zh in SEASON_MAP:
        if col not in df.columns:
            continue
        s = df[col].dropna()
        if s.empty:
            continue
        factors.append({
            "key": key, "french": col, "our_factor": our,
            "label_en": label_en, "label_zh": label_zh,
            "context_only": our is None,
            "start": s.index.min().strftime("%Y-%m"),
            "n_months": int(len(s)),
            "full": _month_stats(s),
            "trailing_30y": _month_stats(s, years=_TRAILING_YEARS),
        })
    if not factors:
        return None

    return {
        "as_of": df.index.max().strftime("%Y-%m"),
        "source": "Ken French Data Library (Dartmouth), monthly factor returns",
        "trailing_years": _TRAILING_YEARS,
        "disclosure_en": (
            "These are Ken French TOTAL-US-MARKET academic factor portfolios (value-"
            "weighted long/short, 1926/1963+), NOT our S&P-1500 winsorized z-score "
            "quintiles. A month's seasonal tendency describes the long-run CLIMATE of "
            "the style — it is not a forecast of our daily factor leadership, and it is "
            "deliberately kept out of every calibrated score."),
        "disclosure_zh": (
            "这些是 Ken French 的全市场学术因子组合（市值加权多空，1926/1963 年至今），"
            "并非我们对标普 1500 的去极值 z 分数分位。某月的季节性倾向描述的是该风格的长期"
            "气候，而非对我们每日因子领先的预测，且刻意不纳入任何校准评分。"),
        "factors": factors,
    }

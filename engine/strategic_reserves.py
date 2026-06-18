"""Strategic-reserve CONTEXT helpers — a DISPLAY-ONLY read for site/spr.html.

LEAF: never imported by the scoring path. Never feeds conviction / alerts / MRS /
latest.json scoring. Pure functions over two inputs:

  * the live EIA weekly US SPR series (data/eia/spr_stocks, kbbl), and
  * live JODI monthly TOTAL closing crude stocks per country (data/jodi/crude_<iso>, kbbl),

paired with a curated, dated strategic-reserve reference table (config.strategic_reserves).

WHY DISPLAY-ONLY (and never a price signal):
A strategic reserve is a POLITICAL supply lever, not a forecasting variable. SPR
releases (e.g. the 2022 ~180 MMbbl drawdown) and refills are coincident supply/demand
events whose forward-return content is weak and regime-dependent — drawing the reserve
down does not reliably push oil one way. So this module is neutral-framed: it reports
levels, fill, cover and change, never a buy/sell.

HONEST DATA BOUNDARIES (surfaced verbatim on the page):
  * Only the US (EIA, weekly) and Japan (METI) break out GOVERNMENT strategic stocks.
  * JODI = TOTAL national stocks (govt + industry + commercial), not strategic-only,
    and lags ~1-2 months. China reports nothing to JODI → curated estimate only.

Units: helpers are unit-agnostic; callers pass kbbl series and convert to MMbbl
(÷1000) for display. `days_of_cover` mirrors commodity_supply_context.days_of_supply.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# Surfaced verbatim on the page — the honesty layer.
SPR_CAVEAT = {
    "en": ("A strategic reserve is a political supply lever, not a price signal. Releases "
           "and refills are coincident supply/demand events with weak, regime-dependent "
           "forward-return content — so this is context, not a buy/sell. Only the US (EIA, "
           "weekly) and Japan break out government strategic stocks; JODI figures are TOTAL "
           "national crude stocks (government + industry + commercial), lag ~1-2 months, and "
           "China does not report to JODI (curated estimate shown)."),
    "zh": ("战略储备是政治性的供给杠杆，而非价格信号。释放与回补属于同步发生的供需事件，其对未来"
           "收益的预测力较弱且依赖于市场环境——故此为背景参考，而非买卖建议。仅美国（EIA，每周）"
           "与日本单独披露政府战略储备；JODI 数据为各国原油总库存（政府+行业+商业），滞后约1-2个月，"
           "且中国不向 JODI 报送（此处显示估算值）。"),
}

KBBL_PER_MB = 1000.0   # 1 million barrels = 1000 thousand barrels (kbbl)
ASSESS_WORD = {1: "reported", 2: "preliminary", 3: "estimate"}
ASSESS_WORD_ZH = {1: "官方报送", 2: "初步", 3: "估算"}


def series(df: pd.DataFrame | pd.Series | None, col: str = "level") -> pd.Series | None:
    """Coerce a stored frame/series to a clean, datetime-indexed, sorted numeric series."""
    if df is None:
        return None
    s = df[col] if (isinstance(df, pd.DataFrame) and col in df.columns) else (
        df.iloc[:, 0] if isinstance(df, pd.DataFrame) else df)
    s = pd.Series(s).copy()
    s.index = pd.to_datetime(s.index, errors="coerce")
    s = s[s.index.notna()].sort_index()
    s = pd.to_numeric(s, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    return s if not s.empty else None


def last_value(s: pd.Series | None) -> float | None:
    s = series(s)
    return None if s is None else float(s.iloc[-1])


def fill_pct(level: float | None, capacity: float | None) -> float | None:
    """Percent of capacity (any consistent unit). None-safe."""
    if level is None or not capacity:
        return None
    return round(100.0 * float(level) / float(capacity), 1)


def change(s: pd.Series | None, periods: int) -> float | None:
    """Latest minus `periods` steps back, in the series' native units. None-safe."""
    s = series(s)
    if s is None or len(s) < 2:
        return None
    k = min(periods, len(s) - 1)
    return float(s.iloc[-1] - s.iloc[-1 - k])


def pct_change(s: pd.Series | None, periods: int) -> float | None:
    s = series(s)
    if s is None or len(s) < 2:
        return None
    k = min(periods, len(s) - 1)
    base = float(s.iloc[-1 - k])
    if base == 0:
        return None
    return round(100.0 * (float(s.iloc[-1]) / base - 1.0), 1)


def days_of_cover(level: float | None, daily_demand: float | None) -> float | None:
    """Days of forward cover = level (kbbl) ÷ daily demand (kbbl/d). None / non-positive safe."""
    if level is None or daily_demand is None:
        return None
    daily = float(daily_demand)
    if not np.isfinite(daily) or daily <= 0:
        return None
    return round(float(level) / daily, 1)


def trend_word(s: pd.Series | None, months: int = 6, eps_pct: float = 1.0) -> str:
    """Coarse rising/falling/flat over the last `months` (by % change). Neutral label."""
    pc = pct_change(s, months)
    if pc is None:
        return "—"
    if pc > eps_pct:
        return "rising"
    if pc < -eps_pct:
        return "falling"
    return "flat"


def assess_word(code: float | int | None, lang: str = "en") -> str:
    try:
        c = int(code)
    except (TypeError, ValueError):
        return ""
    return (ASSESS_WORD_ZH if lang == "zh" else ASSESS_WORD).get(c, "")


def global_aggregate(jodi_crude: dict[str, pd.Series | pd.DataFrame]) -> dict:
    """Sum of the latest reported country crude stocks (MMbbl) + how many reported."""
    total_kbbl, n = 0.0, 0
    for s in jodi_crude.values():
        v = last_value(s)
        if v is not None:
            total_kbbl += v
            n += 1
    return {"total_mb": round(total_kbbl / KBBL_PER_MB, 0) if n else None, "n_reporting": n}


def merge_country_row(cfg: dict, jodi_crude: pd.DataFrame | pd.Series | None,
                      live_level_mb: float | None = None) -> dict:
    """Build one comparison-table row: curated strategic figure + live JODI TOTAL crude.

    `cfg` is one entry of config.strategic_reserves.countries.
    `jodi_crude` is the stored data/jodi/crude_<iso> frame (kbbl) or None.
    `live_level_mb` overrides the strategic headline with a live value (US SPR), MMbbl.
    """
    row = {
        "iso": cfg["iso"], "name": cfg["name"], "name_zh": cfg.get("name_zh", cfg["name"]),
        "flag": cfg.get("flag", ""),
        "strategic_mb": (round(live_level_mb, 0) if live_level_mb is not None
                         else cfg.get("strategic_mb")),
        "strategic_type": cfg.get("strategic_type", ""),
        "capacity_mb": cfg.get("capacity_mb"),
        "industry_mb": cfg.get("industry_mb"),
        "days_cover": cfg.get("days_cover"),
        "days_basis_en": cfg.get("days_basis_en", ""), "days_basis_zh": cfg.get("days_basis_zh", ""),
        "ownership_en": cfg.get("ownership_en", ""), "ownership_zh": cfg.get("ownership_zh", ""),
        "source": cfg.get("source", ""), "as_of": cfg.get("as_of", ""),
        "live": bool(live_level_mb is not None),
        "fill_pct": fill_pct(live_level_mb if live_level_mb is not None else cfg.get("strategic_mb"),
                             cfg.get("capacity_mb")),
        "curated_total_mb": cfg.get("total_mb"),   # e.g. China's est. total onshore crude
    }
    # live JODI TOTAL national crude stocks (display: MMbbl), MoM, 12m trend, quality
    s = series(jodi_crude)
    if s is not None and not cfg.get("no_jodi"):
        row["jodi_total_mb"] = round(float(s.iloc[-1]) / KBBL_PER_MB, 1)
        mom = change(s, 1)
        row["jodi_mom_mb"] = None if mom is None else round(mom / KBBL_PER_MB, 1)
        row["jodi_trend"] = trend_word(s, months=12)
        row["jodi_yoy_pct"] = pct_change(s, 12)
        row["jodi_as_of"] = s.index.max().strftime("%Y-%m")
        try:
            code = jodi_crude["assess"].iloc[-1] if (
                isinstance(jodi_crude, pd.DataFrame) and "assess" in jodi_crude.columns) else None
        except Exception:  # noqa: BLE001
            code = None
        row["jodi_assess"] = None if code is None else int(code)
    else:
        row["jodi_total_mb"] = None
    return row

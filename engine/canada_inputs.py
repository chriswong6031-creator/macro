"""Assemble the daily Canada feature frame from the parquet store.

Mirror of engine/china_inputs.py for the S&P/TSX dashboard. Reads Plane A (prices,
group `canada`/`canada_breadth`) and Plane B (macro, group `canada_macro`: BoC VALET
+ StatsCan + FRED comparables), aligns everything onto a business-day index, and
exposes the derived ratios the Canada regime axes consume. Cross-asset commodity
inputs (copper/gold) and the US relative (TSX/SPX) are read from the shared `yahoo`
group (already collected for the US dashboard). Missing sources yield NaN columns —
the engine renormalizes over what exists (same degrade-don't-crash contract).
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from engine.indicators import basket_index
from lib import config, store

log = logging.getLogger(__name__)

# canada_macro stores one parquet per column (BoC + StatsCan + FRED comparables)
MACRO_COLS = ["policy_rate", "corra", "cpi_yoy", "goc_2y", "goc_5y", "goc_10y",
              "goc_long", "goc_rrb", "usdcad_boc", "unemployment", "gdp_monthly",
              "cpi_index", "house_prices", "cad_reer", "us_2y", "us_10y"]


def canada_closes() -> pd.DataFrame:
    cfg = config.load()["canada"]["yahoo"]
    tickers = list(cfg["indices"]) + list(cfg["sector_etfs"]) + list(cfg["fx"])
    cols = {}
    for t in tickers:
        df = store.read("canada", t)
        if df is not None and "close" in df.columns:
            cols[t] = df["close"]
    return pd.DataFrame(cols).sort_index()


def _macro_frame() -> pd.DataFrame:
    """Wide macro frame (one column per series), date-indexed. Ragged frequency
    (daily yields vs monthly CPI/jobs) is fine — build_features ffills per column."""
    parts = []
    for s in MACRO_COLS:
        df = store.read("canada_macro", s)
        if df is not None and not df.empty:
            parts.append(df)
    if not parts:
        return pd.DataFrame()
    out = pd.concat(parts, axis=1)
    return out[~out.index.duplicated(keep="last")].sort_index()


def build_features() -> pd.DataFrame:
    cfg = config.load()["canada"]
    ycfg = cfg["yahoo"]
    closes = canada_closes()
    if closes.empty:
        raise RuntimeError("no canada price data in store — run collectors first")

    bench = ycfg["benchmark"]
    end = closes[bench].last_valid_index() if bench in closes else closes.index.max()
    idx = pd.bdate_range(closes.index.min(), end)
    f = pd.DataFrame(index=idx)

    def put(name: str, s: pd.Series | None, ffill_limit: int | None = 5) -> None:
        if s is None or s.empty:
            f[name] = np.nan
            return
        s = s[~s.index.duplicated(keep="last")].sort_index()
        union = idx.union(s.index)
        s = s.reindex(union)
        s = s.ffill(limit=ffill_limit) if ffill_limit else s
        f[name] = s.reindex(idx)

    # --- price levels & ratios -------------------------------------------------
    for t in list(ycfg["indices"]) + list(ycfg["sector_etfs"]):
        put(t, closes.get(t))
    put("usdcad", closes.get("USDCAD=X"))
    put("market_index", closes.get(ycfg["market_index"]))

    ecfg = cfg["engine"]
    g = ecfg["growth_axis"]
    cyc = basket_index(closes, g["cyclical_basket"]).reindex(idx).ffill(limit=5)
    dfn = basket_index(closes, g["defensive_basket"]).reindex(idx).ffill(limit=5)
    f["cyc_def"] = cyc / dfn
    ia = ecfg["inflation_axis"]
    ib_long = basket_index(closes, ia["inflation_long_basket"]).reindex(idx).ffill(limit=5)
    ib_short = basket_index(closes, ia["inflation_short_basket"]).reindex(idx).ffill(limit=5)
    f["infl_basket"] = ib_long / ib_short

    # TSX vs S&P 500 relative (commodity-cyclical leadership vs the US) — yahoo group
    spy = store.read("yahoo", "SPY")
    if spy is not None and bench in closes:
        sp = spy["close"][~spy["close"].index.duplicated(keep="last")].sort_index()
        ratio = (closes[bench] / sp.reindex(closes.index).ffill()).dropna()
        put("tsx_spx", ratio)
    else:
        f["tsx_spx"] = np.nan

    # copper/gold global cyclical pulse — yahoo group (HG=F / GC=F)
    cu, au = store.read("yahoo", "HG=F"), store.read("yahoo", "GC=F")
    if cu is not None and au is not None:
        put("copper_gold", (cu["close"] / au["close"]).dropna())
    else:
        f["copper_gold"] = np.nan

    # --- macro (BoC daily yields + StatsCan/BoC monthly + FRED comparables) -----
    m = _macro_frame()
    if not m.empty and "gdp_monthly" in m.columns:
        put("gdp_yoy", m["gdp_monthly"].dropna().pct_change(12) * 100, ffill_limit=40)
    else:
        f["gdp_yoy"] = np.nan
    put("cpi_yoy", m["cpi_yoy"] if (not m.empty and "cpi_yoy" in m.columns) else None, ffill_limit=40)
    put("unemployment", m["unemployment"] if (not m.empty and "unemployment" in m.columns) else None, ffill_limit=40)
    for col in ["policy_rate", "corra", "goc_2y", "goc_5y", "goc_10y", "goc_long",
                "goc_rrb", "us_2y", "us_10y"]:
        put(col, m[col] if (not m.empty and col in m.columns) else None, ffill_limit=10)

    # derived rate spreads (curve slope + market breakeven inflation)
    f["curve_2s10s"] = f["goc_10y"] - f["goc_2y"]
    f["breakeven"] = f["goc_10y"] - f["goc_rrb"]

    # --- breadth ---------------------------------------------------------------
    br = store.read("canada_breadth", "breadth")
    for col in ["pct_above_50", "pct_above_200", "nh", "nl", "ad_line"]:
        put(col, br[col] if (br is not None and col in br.columns) else None)

    return f


# --------------------------------------------------------- sector RS (Canada) ---

def rs_table(asof: pd.Timestamp | None = None) -> pd.DataFrame:
    """Relative-strength rank of each Canada sector ETF vs the S&P/TSX Composite.
    Same math as engine/china_inputs.rs_table, Canadian universe + benchmark."""
    cfg = config.load()["canada"]
    ecfg = cfg["engine"]["rs_ranking"]
    bench = ecfg["benchmark"]
    names = cfg["yahoo"]["sector_etfs"]
    closes = canada_closes()
    if asof is not None:
        closes = closes[closes.index <= asof]
    rows = []
    for t in names:
        if t not in closes.columns or bench not in closes.columns:
            continue
        rs = (closes[t] / closes[bench]).dropna()
        if len(rs) < ecfg["trend_window"]:
            continue
        m20 = rs.pct_change(ecfg["momentum_windows"][0]).iloc[-1] * 100
        m60 = rs.pct_change(ecfg["momentum_windows"][1]).iloc[-1] * 100
        ma200 = rs.rolling(ecfg["trend_window"]).mean().iloc[-1]
        pct = rs.iloc[-ecfg["percentile_lookback_d"]:].rank(pct=True).iloc[-1] * 100
        rows.append({"ticker": t, "name": names[t][0], "rs": rs.iloc[-1],
                     "mom_20d_pct": round(m20, 2), "mom_60d_pct": round(m60, 2),
                     "above_200d_trend": bool(rs.iloc[-1] > ma200),
                     "pctile_252d": round(pct, 1)})
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows).set_index("ticker")
    df["rank"] = df["mom_60d_pct"].rank(ascending=False).astype(int)
    return df.sort_values("rank")


def preference_check(quad_name: str, table: pd.DataFrame) -> dict:
    """Canada sector_preferences are keyed by plain quad name (Goldilocks etc.) and
    list sector-ETF tickers (which are the rs_table index)."""
    prefs = config.load()["canada"]["engine"]["sector_preferences"].get(quad_name, [])
    in_table = [p for p in prefs if p in table.index]
    if not in_table or table.empty:
        return {"quad": quad_name, "preferred": prefs, "agreement": None,
                "note": "no preferred tickers in RS table"}
    half = len(table) / 2
    hits = sum(1 for p in in_table if table.loc[p, "rank"] <= half)
    agreement = hits / len(in_table)
    return {"quad": quad_name, "preferred": prefs,
            "actual_ranks": {p: int(table.loc[p, "rank"]) for p in in_table},
            "agreement": round(agreement, 2), "disagreement_flag": agreement < 0.5,
            "note": ("framework and tape agree" if agreement >= 0.5 else
                     "tape disagrees with framework-preferred sectors — treat as a transition signal")}


def pair_ratios_snapshot(f: pd.DataFrame) -> dict:
    out = {}
    for col in ["cyc_def", "infl_basket", "tsx_spx", "usdcad", "copper_gold"]:
        if col in f and not f[col].dropna().empty:
            s = f[col].dropna()
            out[col] = {"level": round(float(s.iloc[-1]), 4),
                        "chg_20d_pct": round(float(s.pct_change(20).iloc[-1] * 100), 2)}
    return out

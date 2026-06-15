"""Assemble the daily China feature frame from the parquet store.

Mirror of engine/inputs.py for the China A-share dashboard. Reads Plane A
(prices, group `china`/`china_breadth`) and Plane B (macro, group `china_macro`),
aligns everything onto a business-day index, and exposes the derived ratios the
China regime axes consume. Missing sources yield NaN columns — the engine
renormalizes over what exists (same degrade-don't-crash contract as the US side).
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from engine.indicators import basket_index
from lib import config, store

log = logging.getLogger(__name__)

MACRO_SERIES = ["pmi", "cpi", "ppi", "money_supply", "indpro", "rates", "gdp", "lpr_rate"]


def china_closes() -> pd.DataFrame:
    cfg = config.load()["china"]["yahoo"]
    tickers = list(cfg["indices"]) + list(cfg["sector_etfs"]) + list(cfg["fx"])
    cols = {}
    for t in tickers:
        df = store.read("china", t)
        if df is not None and "close" in df.columns:
            cols[t] = df["close"]
    return pd.DataFrame(cols).sort_index()


def _macro_frame() -> pd.DataFrame:
    """Wide monthly macro frame (one column per indicator), date-indexed."""
    parts = []
    for s in MACRO_SERIES:
        df = store.read("china_macro", s)
        if df is not None and not df.empty:
            parts.append(df)
    if not parts:
        return pd.DataFrame()
    out = pd.concat(parts, axis=1, sort=False)
    return out[~out.index.duplicated(keep="last")].sort_index()


def build_features() -> pd.DataFrame:
    cfg = config.load()["china"]
    ycfg = cfg["yahoo"]
    closes = china_closes()
    if closes.empty:
        raise RuntimeError("no china price data in store — run collectors first")

    bench = ycfg["benchmark"]
    end = closes[bench].last_valid_index() if bench in closes else closes.index.max()
    idx = pd.bdate_range(closes.index.min(), end)
    f = pd.DataFrame(index=idx)

    def put(name: str, s: pd.Series | None, ffill_limit: int | None = 5) -> None:
        if s is None or s.empty:
            f[name] = np.nan
            return
        s = s[~s.index.duplicated(keep="last")].sort_index()
        union = idx.union(s.index)          # monthly prints stamped off-session survive the reindex
        s = s.reindex(union)
        s = s.ffill(limit=ffill_limit) if ffill_limit else s
        f[name] = s.reindex(idx)

    # --- price levels & ratios -------------------------------------------------
    for t in list(ycfg["indices"]) + list(ycfg["sector_etfs"]):
        put(t, closes.get(t))
    put("usdcny", closes.get("CNY=X"))
    put("usdcnh", closes.get("CNH=F"))      # offshore yuan (onshore CNY=X is PBoC-pinned)
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
    if "510500.SS" in closes and "510300.SS" in closes:
        f["smallcap_largecap"] = (closes["510500.SS"] / closes["510300.SS"]).reindex(idx).ffill(limit=5)
    else:
        f["smallcap_largecap"] = np.nan

    # --- macro (monthly; step-fill across the month like US payrolls/INDPRO) ----
    m = _macro_frame()
    for col in ["pmi_mfg", "pmi_nonmfg", "cpi_yoy", "ppi_yoy", "m2_yoy", "m1_yoy", "indpro_yoy"]:
        put(col, m[col] if (not m.empty and col in m.columns) else None, ffill_limit=40)
    for col in ["rate_3m", "rate_1y"]:
        put(col, m[col] if (not m.empty and col in m.columns) else None, ffill_limit=10)
    # quarterly GDP + event-dated LPR step-fill across their long cadence
    put("gdp_yoy", m["gdp_yoy"] if (not m.empty and "gdp_yoy" in m.columns) else None, ffill_limit=130)
    for col in ["lpr_1y", "lpr_5y"]:
        put(col, m[col] if (not m.empty and col in m.columns) else None, ffill_limit=260)

    # --- breadth ---------------------------------------------------------------
    br = store.read("china_breadth", "breadth")
    for col in ["pct_above_50", "pct_above_200", "nh", "nl", "ad_line"]:
        put(col, br[col] if (br is not None and col in br.columns) else None)

    # --- Stock Connect (context; northbound direction frozen since 2024-08-16) --
    # The `china_connect` store holds raw daily net per leg; cumulate here. Southbound
    # is live; northbound_cum freezes flat after 2024-08-16 (no NET disclosed beyond that).
    for cum, leg in [("southbound_cum", "southbound"), ("northbound_cum", "northbound")]:
        cf = store.read("china_connect", leg)
        if cf is not None and "net" in cf.columns:
            put(cum, cf["net"].dropna().cumsum(), ffill_limit=5)

    return f


# --------------------------------------------------------- sector RS (China) ----

def rs_table(asof: pd.Timestamp | None = None) -> pd.DataFrame:
    """Relative-strength rank of each China sector ETF vs the CSI300 benchmark.
    Same math as engine/sectors.rs_table, China universe + benchmark."""
    cfg = config.load()["china"]
    ecfg = cfg["engine"]["rs_ranking"]
    bench = ecfg["benchmark"]
    names = cfg["yahoo"]["sector_etfs"]
    closes = china_closes()
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
    """China sector_preferences are keyed by plain quad name (Goldilocks etc.)."""
    prefs = config.load()["china"]["engine"]["sector_preferences"].get(quad_name, [])
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
    for col in ["cyc_def", "infl_basket", "smallcap_largecap", "usdcny"]:
        if col in f and not f[col].dropna().empty:
            s = f[col].dropna()
            out[col] = {"level": round(float(s.iloc[-1]), 4),
                        "chg_20d_pct": round(float(s.pct_change(20).iloc[-1] * 100), 2)}
    return out

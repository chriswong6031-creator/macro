"""Assemble the daily Hong Kong feature frame from the parquet store.

Mirror of engine/china_inputs.py, re-thought for HK. Reads:
  - Plane A (group `hk`): Hang Seng indices, HS-TECH/HSI ETF proxy, HKD=X.
  - Plane B (group `china_macro`, REUSED): PMI/CPI/PPI/M2 — HSI earnings are
    China-driven, so the HK growth/inflation read uses the Mainland fundamentals.
    Stock-Connect SOUTHBOUND flow (mainland money into HK) is the HK-specific
    capital-flow input.
  - Global factors (engine.hk_global): copper/gold enters the growth axis as the
    global cyclical pulse; the full risk-on/off composite + HKD peg are attached
    as overlays in hk_regime (not quad axes).
  - Breadth (group `hk_breadth`) computed from the curated constituent universe.

Missing sources yield NaN columns — the engine renormalizes over what exists
(same degrade-don't-crash contract as the US/China sides). The cyclical/defensive
and inflation-beta baskets are built from the ~3y constituent close cache (recent
momentum is what those daily ratios capture); the deep classification rests on
PMI + H-share leadership + copper/gold, which all reach back to ~2000-2006.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from engine.indicators import basket_index
from lib import config, store

log = logging.getLogger(__name__)


def hk_closes() -> pd.DataFrame:
    """Index + ETF-proxy + FX closes from the `hk` store group."""
    ycfg = config.load()["hk"]["yahoo"]
    tickers = list(ycfg["indices"]) + list(ycfg.get("etf_proxies", {})) + list(ycfg.get("fx", {}))
    cols = {}
    for t in tickers:
        df = store.read("hk", t)
        if df is not None and "close" in df.columns:
            cols[t] = df["close"]
    return pd.DataFrame(cols).sort_index()


def constituent_closes() -> pd.DataFrame:
    """~3y constituent close matrix (the hk_breadth live cache) for the synthetic
    sector baskets, RS table and the search library."""
    cache = config.data_dir() / "hk_breadth" / "_closes_cache.parquet"
    return pd.read_parquet(cache) if cache.exists() else pd.DataFrame()


def _macro_frame() -> pd.DataFrame:
    """Wide monthly China macro frame (reused for HK — HSI is China-driven)."""
    parts = []
    for s in ["pmi", "cpi", "ppi", "money_supply", "indpro"]:
        df = store.read("china_macro", s)
        if df is not None and not df.empty:
            parts.append(df)
    if not parts:
        return pd.DataFrame()
    out = pd.concat(parts, axis=1)
    return out[~out.index.duplicated(keep="last")].sort_index()


def build_features() -> pd.DataFrame:
    cfg = config.load()["hk"]
    ycfg = cfg["yahoo"]
    closes = hk_closes()
    if closes.empty:
        raise RuntimeError("no hk price data in store — run collectors first")
    cc = constituent_closes()

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

    # --- index levels + HK-internal structure ratios ---------------------------
    for t in list(ycfg["indices"]) + list(ycfg.get("etf_proxies", {})):
        put(t, closes.get(t))
    put("market_index", closes.get(ycfg["market_index"]))
    put("usdhkd", closes.get("HKD=X"))

    if "^HSCE" in closes and "^HSI" in closes:
        f["hshare_hsi"] = (closes["^HSCE"] / closes["^HSI"]).reindex(idx).ffill(limit=5)
    else:
        f["hshare_hsi"] = np.nan
    tp = ycfg.get("tech_proxy")
    if tp and tp in closes and "^HSI" in closes:
        f["tech_hsi"] = (closes[tp] / closes["^HSI"]).reindex(idx).ffill(limit=5)
    else:
        f["tech_hsi"] = np.nan

    # cyclical/defensive + inflation-beta baskets from the constituent cache
    ecfg = cfg["engine"]
    g = ecfg["growth_axis"]
    if not cc.empty:
        cyc = basket_index(cc, g["cyclical_basket"]).reindex(idx).ffill(limit=5)
        dfn = basket_index(cc, g["defensive_basket"]).reindex(idx).ffill(limit=5)
        f["cyc_def"] = cyc / dfn
        ia = ecfg["inflation_axis"]
        ib_long = basket_index(cc, ia["inflation_long_basket"]).reindex(idx).ffill(limit=5)
        ib_short = basket_index(cc, ia["inflation_short_basket"]).reindex(idx).ffill(limit=5)
        f["infl_basket"] = ib_long / ib_short
    else:
        f["cyc_def"] = np.nan
        f["infl_basket"] = np.nan

    # global cyclical pulse (copper/gold) — enters the growth axis; the full
    # risk-on/off composite is attached as an overlay in hk_regime
    cu = store.read("yahoo", "HG=F")
    au = store.read("yahoo", "GC=F")
    if cu is not None and au is not None:
        put("copper_gold", (cu["close"] / au["close"]).dropna())
    else:
        f["copper_gold"] = np.nan

    # --- China macro (monthly; step-fill across the month) ---------------------
    m = _macro_frame()
    for col in ["pmi_mfg", "pmi_nonmfg", "cpi_yoy", "ppi_yoy", "m2_yoy", "m1_yoy"]:
        put(col, m[col] if (not m.empty and col in m.columns) else None, ffill_limit=40)

    # --- breadth ---------------------------------------------------------------
    br = store.read("hk_breadth", "breadth")
    for col in ["pct_above_50", "pct_above_200", "nh", "nl", "ad_line"]:
        put(col, br[col] if (br is not None and col in br.columns) else None)

    # --- Stock-Connect SOUTHBOUND (mainland money into HK; HK-specific flow) ----
    # Primary source is the `china_connect` store; the china_macro/connect_flow store
    # (now also live off the datacenter report) is the fallback. Either way we build
    # southbound_cum = cumulative daily net flow; its 20d change is the inflow(+)/
    # outflow(−) direction the dual-liquidity overlay reads. Data starts 2014-11, so
    # this leg renormalizes in from then (the overlay degrades gracefully meanwhile).
    sb = store.read("china_connect", "southbound")
    if sb is not None and "net" in sb.columns and not sb["net"].dropna().empty:
        put("southbound_cum", sb["net"].dropna().cumsum(), ffill_limit=5)
    else:
        cf = store.read("china_macro", "connect_flow")   # fallback (datacenter report)
        if cf is not None and "southbound_net" in cf.columns and not cf["southbound_net"].dropna().empty:
            put("southbound_cum", cf["southbound_net"].dropna().cumsum(), ffill_limit=5)
        else:
            f["southbound_cum"] = np.nan

    return f


# --------------------------------------------------------- sector RS (HK) -------

def sector_basket(cc: pd.DataFrame, members: list[str]) -> pd.Series:
    """Equal-weight synthetic basket index for one HK sector."""
    return basket_index(cc, members)


def rs_table(asof: pd.Timestamp | None = None) -> pd.DataFrame:
    """Relative-strength rank of each HK synthetic sector basket vs ^HSI.
    Same math as engine/sectors.rs_table; HK universe = deep constituent baskets."""
    cfg = config.load()["hk"]
    ecfg = cfg["engine"]["rs_ranking"]
    bench_t = ecfg["benchmark"]
    sectors = cfg["sectors"]
    cc = constituent_closes()
    idx_df = store.read("hk", bench_t)
    if cc.empty or idx_df is None:
        return pd.DataFrame()
    bench = idx_df["close"].dropna()
    if asof is not None:
        cc = cc[cc.index <= asof]
        bench = bench[bench.index <= asof]

    rows = []
    for name, meta in sectors.items():
        basket = sector_basket(cc, meta["members"]).dropna()
        if basket.empty:
            continue
        common = basket.index.intersection(bench.index)
        if len(common) < ecfg["trend_window"]:
            continue
        rs = (basket.reindex(common) / bench.reindex(common)).dropna()
        if len(rs) < ecfg["trend_window"]:
            continue
        m20 = rs.pct_change(ecfg["momentum_windows"][0]).iloc[-1] * 100
        m60 = rs.pct_change(ecfg["momentum_windows"][1]).iloc[-1] * 100
        ma200 = rs.rolling(ecfg["trend_window"]).mean().iloc[-1]
        pct = rs.iloc[-ecfg["percentile_lookback_d"]:].rank(pct=True).iloc[-1] * 100
        rows.append({"ticker": name, "name": name, "tv": meta.get("tv", ""),
                     "rs": rs.iloc[-1], "mom_20d_pct": round(m20, 2),
                     "mom_60d_pct": round(m60, 2), "above_200d_trend": bool(rs.iloc[-1] > ma200),
                     "pctile_252d": round(pct, 1)})
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows).set_index("ticker")
    df["rank"] = df["mom_60d_pct"].rank(ascending=False).astype(int)
    return df.sort_values("rank")


def preference_check(quad_name: str, table: pd.DataFrame) -> dict:
    """HK sector_preferences are keyed by plain quad name (Goldilocks etc.)."""
    prefs = config.load()["hk"]["engine"]["sector_preferences"].get(quad_name, [])
    in_table = [p for p in prefs if p in table.index]
    if not in_table or table.empty:
        return {"quad": quad_name, "preferred": prefs, "agreement": None,
                "note": "no preferred sectors in RS table"}
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
    for col in ["hshare_hsi", "tech_hsi", "cyc_def", "infl_basket", "usdhkd"]:
        if col in f and not f[col].dropna().empty:
            s = f[col].dropna()
            out[col] = {"level": round(float(s.iloc[-1]), 4),
                        "chg_20d_pct": round(float(s.pct_change(20).iloc[-1] * 100), 2)}
    return out

"""Assemble the daily feature frame from the parquet store.

Everything downstream (axes, transition detector, sector ranks, backtest)
reads this one aligned business-day DataFrame. Missing sources simply yield
NaN columns — the engine renormalizes weights over what exists and degrades
confidence instead of crashing.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from engine.indicators import basket_index
from lib import config, store

log = logging.getLogger(__name__)


def _yahoo_close(name: str) -> pd.Series | None:
    df = store.read("yahoo", name)
    if df is None or "close" not in df.columns:
        return None
    return df["close"]


def _fred(col_by_sid: dict[str, str]) -> dict[str, pd.Series]:
    out = {}
    for sid, col in col_by_sid.items():
        df = store.read("fred", sid)
        if df is not None and not df.empty:
            out[col] = df.iloc[:, 0]
    return out


def yahoo_closes() -> pd.DataFrame:
    cfg = config.load()["yahoo"]["tickers"]
    cols = {}
    for grp in cfg.values():
        for t in grp:
            s = _yahoo_close(t.replace("^", "_").replace("=", "_").replace("/", "_"))
            if s is not None:
                cols[t] = s
    return pd.DataFrame(cols).sort_index()


def build_features() -> pd.DataFrame:
    cfg = config.load()
    ecfg = cfg["engine"]
    closes = yahoo_closes()
    if closes.empty:
        raise RuntimeError("no yahoo data in store — run collectors first")

    # futures rows can be stamped one day ahead of the equity session — the
    # frame ends on the last day the equity benchmark actually printed
    end = closes["SPY"].last_valid_index() if "SPY" in closes else closes.index.max()
    idx = pd.bdate_range(closes.index.min(), end)
    f = pd.DataFrame(index=idx)

    def put(name: str, s: pd.Series | None, ffill_limit: int | None = 5) -> None:
        if s is None or s.empty:
            f[name] = np.nan
            return
        s = s[~s.index.duplicated(keep="last")].sort_index()
        # fill on the union first: monthly series stamped on weekends/holidays
        # (e.g. PAYEMS on a Sunday the 1st) must survive the business-day reindex
        union = idx.union(s.index)
        s = s.reindex(union)
        s = s.ffill(limit=ffill_limit) if ffill_limit else s
        f[name] = s.reindex(idx)

    # --- price levels & ratios -------------------------------------------------
    for t in ["SPY", "IWM", "RSP", "QQQ", "XLY", "XLP", "XLE", "XLK", "XLU",
              "HYG", "LQD", "SPHB", "SPLV"]:
        put(t, closes.get(t))
    # US equity size & style: small (Russell 2000), mid (S&P 400), growth/value
    put("RUT", closes.get("^RUT"))        # true Russell 2000 index level
    put("IJH", closes.get("IJH"))         # S&P MidCap 400 — mid-cap leg
    put("IWF", closes.get("IWF"))         # Russell 1000 Growth
    put("IWD", closes.get("IWD"))         # Russell 1000 Value
    put("oil", closes.get("CL=F"))
    put("copper", closes.get("HG=F"))
    put("gold", closes.get("GC=F"))
    put("dxy", closes.get("DX-Y.NYB"))
    put("vix", closes.get("^VIX"))
    put("vix3m", closes.get("^VIX3M"))
    put("vix9d", closes.get("^VIX9D"))
    put("move", closes.get("^MOVE"))
    put("zq_front", closes.get("ZQ=F"))

    f["copper_gold"] = f["copper"] / f["gold"]
    f["xly_xlp"] = f["XLY"] / f["XLP"]
    f["iwm_spy"] = f["IWM"] / f["SPY"]          # small caps vs large (risk appetite / breadth)
    f["mid_spy"] = f["IJH"] / f["SPY"]          # mid caps vs large
    f["growth_value"] = f["IWF"] / f["IWD"]     # growth vs value leadership (style rotation)
    f["energy_rs"] = f["XLE"] / f["SPY"]
    f["xlk_xlu"] = f["XLK"] / f["XLU"]
    f["sphb_splv"] = f["SPHB"] / f["SPLV"]
    f["hyg_lqd"] = f["HYG"] / f["LQD"]
    f["vix_ratio"] = f["vix"] / f["vix3m"]

    g = ecfg["growth_axis"]
    cyc = basket_index(closes, g["cyclical_basket"]).reindex(idx).ffill(limit=5)
    dfn = basket_index(closes, g["defensive_basket"]).reindex(idx).ffill(limit=5)
    f["cyc_def"] = cyc / dfn
    ia = ecfg["inflation_axis"]
    ib_long = basket_index(closes, ia["inflation_long_basket"]).reindex(idx).ffill(limit=5)
    ib_short = basket_index(closes, ia["inflation_short_basket"]).reindex(idx).ffill(limit=5)
    f["infl_basket"] = ib_long / ib_short

    # --- FRED ------------------------------------------------------------------
    fred_map = {}
    for grp in cfg["fred"]["series"].values():
        fred_map.update(grp)
    series = _fred(fred_map)
    for col in ["us2y", "us10y", "spread_2s10s", "us10y_real", "breakeven_10y",
                "breakeven_5y5y", "fed_funds", "hy_oas", "ig_oas", "vix_close"]:
        put(col, series.get(col))
    # archived OAS history (pre rolling-window) is merged underneath live data
    for col, arch in [("hy_oas", "BAMLH0A0HYM2"), ("ig_oas", "BAMLC0A0CM")]:
        a = store.read("archive", arch)
        if a is not None and not a.empty:
            s = a.iloc[:, 0].reindex(idx).ffill(limit=5)
            f[col] = f[col].combine_first(s)
    # monthly econ confirmations: step-fill forward (released with lag; we use
    # direction only, ffill across the month is the honest representation)
    # 60 bdays: INDPRO is stamped on the reference month but published ~6 weeks
    # later, so the previous print must carry until its successor arrives
    put("payrolls", series.get("payrolls"), ffill_limit=60)
    put("indpro", series.get("indpro" if "indpro" in series else "industrial_prod"), ffill_limit=60)
    # derived fallbacks when the published composite series is unavailable
    effr = store.read("nyfed", "effr")
    if effr is not None:
        f["fed_funds"] = f["fed_funds"].combine_first(
            effr.iloc[:, 0].reindex(idx).ffill(limit=5))
    f["spread_2s10s"] = f["spread_2s10s"].combine_first(f["us10y"] - f["us2y"])
    f["tips_nominal_spread"] = f["us10y"] - f["us10y_real"]
    f["breakeven_10y"] = f["breakeven_10y"].combine_first(f["tips_nominal_spread"])
    # rate-cut pricing proxy (LOW CONFIDENCE — no free FedWatch API): negative
    # values = market prices cuts over the next ~2y; ZQ front adds a 30d view
    f["rate_expectations_proxy"] = f["us2y"] - f["fed_funds"]
    f["zq_implied_rate"] = 100 - f["zq_front"]

    # --- Quant-factor expansion: Fed-research feeds (research/QUANT_FACTOR_EXPANSION.md)
    # Financial-conditions indices (weekly) — a ready broad risk gauge.
    for col in ["nfci", "anfci", "nfci_risk", "nfci_credit", "nfci_leverage", "stlfsi"]:
        put(col, series.get(col), ffill_limit=7)
    # Recession reads: Sahm + smoothed prob (monthly, ~6wk publication lag), ACM
    # term premium (daily). 70 bdays carries a monthly print until its successor.
    put("sahm", series.get("sahm"), ffill_limit=70)
    put("recession_prob", series.get("recession_prob"), ffill_limit=70)
    put("term_premium_10y", series.get("term_premium_10y"), ffill_limit=5)
    # Real-time growth nowcasts: WEI (weekly), GDPNow (quarterly on FRED).
    put("wei", series.get("wei"), ffill_limit=10)
    put("gdpnow", series.get("gdpnow"), ffill_limit=95)
    # Underlying-inflation indices (monthly): persistent (sticky) vs transitory (flexible).
    for col in ["sticky_cpi", "core_sticky_cpi", "flex_cpi"]:
        put(col, series.get(col), ffill_limit=45)
    put("median_cpi", series.get("median_cpi"), ffill_limit=45)
    # Household sentiment / inflation expectations (monthly).
    put("umich_sentiment", series.get("umich_sentiment"), ffill_limit=45)
    put("umich_infl_exp", series.get("umich_infl_exp"), ffill_limit=45)
    # Fuller curve + 5y inflation leg.
    for col in ["us3m", "us6m", "us5y", "us30y", "spread_10y3m", "breakeven_5y", "us5y_real"]:
        put(col, series.get(col))
    f["spread_10y3m"] = f["spread_10y3m"].combine_first(f["us10y"] - f["us3m"])
    # term-premium-adjusted curve slope: strips the term-premium distortion that
    # mechanically inverted the curve in 2019 and 2022-24 without a recession.
    f["curve_tp_adj"] = f["spread_2s10s"] + f["term_premium_10y"].fillna(0)

    # CBOE SKEW (tail-risk pricing) + EBP (credit risk appetite).
    skew = store.read("cboe", "skew")
    put("skew", skew["skew"] if skew is not None and "skew" in skew.columns else None)
    ebp = store.read("fedboard", "ebp")
    if ebp is not None:
        put("ebp", ebp["ebp"] if "ebp" in ebp.columns else None, ffill_limit=45)
        put("ebp_recession_prob", ebp["est_prob"] if "est_prob" in ebp.columns else None, ffill_limit=45)
    else:
        f["ebp"] = np.nan
        f["ebp_recession_prob"] = np.nan

    # --- liquidity ($bn) — FRED merged with official NY Fed / Board sources -------
    walcl = series.get("fed_balance_sheet")
    h41 = store.read("nyfed", "h41_assets")
    if h41 is not None:
        walcl = h41.iloc[:, 0].combine_first(walcl) if walcl is not None else h41.iloc[:, 0]
    put("walcl_bn", walcl / 1000 if walcl is not None else None, ffill_limit=7)  # weekly
    rrp = series.get("on_rrp")
    nyrrp = store.read("nyfed", "rrp")
    if nyrrp is not None:
        rrp = nyrrp.iloc[:, 0].combine_first(rrp) if rrp is not None else nyrrp.iloc[:, 0]
    put("rrp_bn", rrp, ffill_limit=5)
    tga = store.read("treasury", "tga")
    put("tga_bn", tga.iloc[:, 0] / 1000 if tga is not None else None, ffill_limit=5)
    f["net_liquidity_bn"] = f["walcl_bn"] - f["rrp_bn"].fillna(0) - f["tga_bn"]
    iss = store.read("treasury", "net_issuance")
    if iss is not None:
        put("net_issuance_mn", iss.iloc[:, 0], ffill_limit=None)

    # --- breadth -----------------------------------------------------------------
    br = store.read("breadth", "breadth")
    if br is not None:
        for col in ["pct_above_50", "pct_above_200", "nh", "nl", "ad_line"]:
            if col in br.columns:
                put(col, br[col])
    else:
        for col in ["pct_above_50", "pct_above_200", "nh", "nl", "ad_line"]:
            f[col] = np.nan
    # small-cap participation (S&P 600) — same columns, sc_ prefix. Stays NaN
    # through history until the collector has run; engine degrades gracefully.
    scb = store.read("smallcap_breadth", "breadth")
    for col in ["pct_above_50", "pct_above_200", "nh", "nl", "ad_line"]:
        alias = f"sc_{col}"
        if scb is not None and col in scb.columns:
            put(alias, scb[col])
        else:
            f[alias] = np.nan

    # --- GEX (live only; NaN through history) --------------------------------------
    gex = store.read("cboe", "gex")
    if gex is not None:
        for col in ["net_gex_bn", "flip_strike", "spot_vs_flip_pct"]:
            if col in gex.columns:
                put(col, gex[col], ffill_limit=3)
    else:
        for col in ["net_gex_bn", "flip_strike", "spot_vs_flip_pct"]:
            f[col] = np.nan

    return f

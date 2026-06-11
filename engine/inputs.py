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

    idx = pd.bdate_range(closes.index.min(), closes.index.max())
    f = pd.DataFrame(index=idx)

    def put(name: str, s: pd.Series | None, ffill_limit: int | None = 5) -> None:
        if s is None or s.empty:
            f[name] = np.nan
            return
        s = s[~s.index.duplicated(keep="last")].sort_index().reindex(idx)
        f[name] = s.ffill(limit=ffill_limit) if ffill_limit else s

    # --- price levels & ratios -------------------------------------------------
    for t in ["SPY", "IWM", "RSP", "QQQ", "XLY", "XLP", "XLE", "XLK", "XLU",
              "HYG", "LQD", "SPHB", "SPLV"]:
        put(t, closes.get(t))
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
    f["iwm_spy"] = f["IWM"] / f["SPY"]
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
    put("payrolls", series.get("payrolls"), ffill_limit=40)
    put("indpro", series.get("indpro" if "indpro" in series else "industrial_prod"), ffill_limit=40)
    f["tips_nominal_spread"] = f["us10y"] - f["us10y_real"]

    # --- liquidity ($bn) ---------------------------------------------------------
    walcl = series.get("fed_balance_sheet")
    put("walcl_bn", walcl / 1000 if walcl is not None else None, ffill_limit=7)  # weekly
    rrp = series.get("on_rrp")
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

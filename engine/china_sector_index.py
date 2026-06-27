"""China sector-index construction + the leak-free driver panel — the shared data
layer behind the Sector Desk (engine.china_sector_desk), the evidence-gated pathway
engine (engine.china_sector_pathway) and the Phase-0 research harness
(scripts.china_sector_pathway_phase0).

THREE views of every sector, mirroring the Bloomberg GS China sector baskets:
  1. Shenwan (申万) L1 index  — the authoritative deep sector index (1999/2014->),
     group `china_sectors` (collectors/china_sectors.py). The headline series.
  2. Cap-weighted constituent basket — a GS-faithful, static-cap-weighted index built
     from the curated large-caps (config.china.constituents) over the china_search
     close cache (~5y). HONEST BY CONSTRUCTION: descriptive, not an OOS backtest.
  3. ETF proxy — the tradeable sector ETF (config.china.yahoo.sector_etfs), the leg
     the live.js intraday tape patches.

The four GS-style headline baskets the user named map as:
  Banks=801780  ·  Real Estate=801180  ·  Auto=801880  ·  Consumption=composite.

Everything here is point-in-time / leak-free so the research harness and the live
engine compute identically (house rule: live == backtest).
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from lib import config, store

log = logging.getLogger(__name__)

BENCHMARK = "000001.SS"   # Shanghai Composite — deep (1999->), matches Shenwan history

# dashboard sector name (= config.china.constituents key & sector_etfs name[0]) -> Shenwan L1
SECTOR_SW: dict[str, str] = {
    "Banks": "801780",
    "Securities & Brokers": "801790",
    "Baijiu & Liquor": "801120",
    "Consumer Staples": "801120",
    "Healthcare": "801150",
    "Innovative Drugs": "801150",
    "Semiconductors": "801080",
    "Technology": "801750",
    "New-Energy Vehicle": "801730",
    "Solar & Photovoltaic": "801730",
    "Defense & Military": "801740",
    "Nonferrous Metals": "801050",
    "Coal": "801950",
    "Real Estate": "801180",
    "Automobiles": "801880",
    "Media": "801760",
}

# The four GS-style headline baskets (the predictive/pathway focus). Single Shenwan
# code, or an equal-weight composite of L1 industries. `constituents` keys index the
# curated cap-weighted cross-check basket (config.china.constituents).
GS_BASKETS: dict[str, dict] = {
    "banks": {
        "en": "China Banks", "zh": "中国银行", "bbg": "GSXACHBA",
        "sw": "801780", "etf": "512800.SS", "constituents": ["Banks"],
    },
    "consumption": {
        "en": "China Consumption", "zh": "中国消费", "bbg": "GSXACCON",
        # food&bev + appliances + retail + consumer-services + beauty + textiles + light-mfg
        "sw_composite": ["801120", "801110", "801200", "801210", "801980", "801130", "801140"],
        "etf": ["159928.SZ", "512690.SS"], "constituents": ["Baijiu & Liquor", "Consumer Staples"],
    },
    "real_estate": {
        "en": "China Real Estate", "zh": "中国地产", "bbg": "GSXACNRE",
        "sw": "801180", "etf": "512200.SS", "constituents": ["Real Estate"],
    },
    "auto": {
        "en": "China Auto", "zh": "中国汽车", "bbg": "GSXACNAU",
        "sw": "801880", "etf": "515250.SS", "constituents": ["Automobiles"],
    },
}


# --------------------------------------------------------------- series loaders ----

def sw_close(code: str) -> pd.Series | None:
    """Daily close of one Shenwan L1 index (group china_sectors)."""
    df = store.read("china_sectors", code)
    if df is None or "close" not in df.columns:
        return None
    return df["close"].dropna().sort_index()


def composite_index(codes: list[str]) -> pd.Series | None:
    """Equal-weight (daily-return) composite of several Shenwan indices, cumulated to
    a level rebased to 1000 at the first day all legs are live."""
    legs = [sw_close(c) for c in codes]
    legs = [s for s in legs if s is not None and not s.empty]
    if not legs:
        return None
    rets = pd.concat([s.pct_change() for s in legs], axis=1).mean(axis=1)
    rets = rets.loc[rets.first_valid_index():]
    return 1000.0 * (1.0 + rets.fillna(0.0)).cumprod()


def gs_index(key: str) -> pd.Series | None:
    """Headline Shenwan (or composite) level for a GS basket key."""
    b = GS_BASKETS.get(key)
    if not b:
        return None
    if b.get("sw_composite"):
        return composite_index(b["sw_composite"])
    return sw_close(b["sw"])


def benchmark_close() -> pd.Series | None:
    df = store.read("china", BENCHMARK)
    if df is None or "close" not in df.columns:
        return None
    return df["close"].dropna().sort_index()


# ------------------------------------------------------ cap-weighted constituents ----

def _search_closes() -> pd.DataFrame | None:
    p = config.data_dir() / "china_search" / "closes.parquet"
    if not p.exists():
        return None
    df = pd.read_parquet(p)
    df.index = pd.DatetimeIndex(df.index)
    return df.sort_index()


def _members() -> pd.DataFrame | None:
    p = config.data_dir() / "china_search" / "members.parquet"
    return pd.read_parquet(p) if p.exists() else None


def cap_weighted_basket(constituent_keys: list[str]) -> pd.Series | None:
    """Static-cap-weighted constituent index over the china_search cache for one or
    more config.china.constituents sector buckets. Weights = members.mktcap_yi (a
    recent snapshot) — descriptive, GS-faithful in shape, NOT an OOS backtest."""
    closes = _search_closes()
    mem = _members()
    if closes is None or mem is None:
        return None
    cons = config.load()["china"]["constituents"]
    tickers: list[str] = []
    for k in constituent_keys:
        tickers += list(cons.get(k, []))
    present = [t for t in tickers if t in closes.columns]
    if len(present) < 3:
        return None
    px = closes[present].dropna(how="all")
    caps = mem["mktcap_yi"].reindex(present).fillna(0.0) if "mktcap_yi" in mem.columns else None
    if caps is None or caps.sum() <= 0:
        w = pd.Series(1.0 / len(present), index=present)
    else:
        w = caps / caps.sum()
    rets = px.pct_change(fill_method=None)
    # renormalize weights each day across names with a return (handles late listings)
    mask = rets.notna()
    wmat = mask.mul(w, axis=1)
    wmat = wmat.div(wmat.sum(axis=1).replace(0.0, np.nan), axis=0)
    port = (rets * wmat).sum(axis=1, min_count=1)
    port = port.loc[port.first_valid_index():]
    return 1000.0 * (1.0 + port.fillna(0.0)).cumprod()


def etf_close(ticker: str | list[str]) -> pd.Series | None:
    """Sector-ETF close (or equal blend of several) from group china."""
    syms = ticker if isinstance(ticker, list) else [ticker]
    legs = []
    for s in syms:
        df = store.read("china", s)
        if df is not None and "close" in df.columns:
            legs.append(df["close"].pct_change())
    if not legs:
        return None
    rets = pd.concat(legs, axis=1).mean(axis=1)
    rets = rets.loc[rets.first_valid_index():]
    return 1000.0 * (1.0 + rets.fillna(0.0)).cumprod()


# ----------------------------------------------------------------- turn detection ----

def zigzag_turns(close: pd.Series, pct: float = 0.25) -> list[dict]:
    """Major alternating tops/bottoms via a percent-retracement zigzag. A new pivot
    is confirmed once price reverses `pct` (e.g. 25%) off the running extreme. Returns
    [{date, kind: 'top'|'bottom', price}] in chronological order. Confirmation-lagged
    by construction (we only know a pivot after the reversal), so it is non-anticipating
    for any test that uses the pivot DATE as an event anchor."""
    s = close.dropna()
    if len(s) < 30:
        return []
    vals = s.values
    idx = s.index
    pivots: list[dict] = []
    trend = 0                       # +1 = up-leg (seeking a top), -1 = down-leg
    hi_v, hi_i = vals[0], 0         # running high since last bottom (top candidate)
    lo_v, lo_i = vals[0], 0         # running low since last top (bottom candidate)
    for i in range(1, len(vals)):
        v = vals[i]
        if trend >= 0:              # up-leg or undecided: watch for a top
            if v > hi_v:
                hi_v, hi_i = v, i
            if v <= hi_v * (1.0 - pct):
                if hi_i > 0:        # never call the first observation a pivot (data-edge artifact)
                    pivots.append({"date": idx[hi_i], "kind": "top", "price": float(hi_v)})
                trend, lo_v, lo_i = -1, v, i
                continue
        if trend <= 0:              # down-leg or undecided: watch for a bottom
            if v < lo_v:
                lo_v, lo_i = v, i
            if v >= lo_v * (1.0 + pct):
                if lo_i > 0:
                    pivots.append({"date": idx[lo_i], "kind": "bottom", "price": float(lo_v)})
                trend, hi_v, hi_i = 1, v, i
    return pivots


# -------------------------------------------------------- leak-free driver panel ----

def _monthly_last(s: pd.Series | None, grid: pd.DatetimeIndex) -> pd.Series:
    if s is None or s.empty:
        return pd.Series(np.nan, index=grid)
    m = s.dropna().resample("ME").last()
    return m.reindex(grid, method="ffill")


def _monthly_macro(group: str, name: str, col: str, grid: pd.DatetimeIndex,
                   lag: int = 1) -> pd.Series:
    """Month-end value of a monthly macro column, lagged `lag` months for the
    publication delay (a print for month M is only known ~mid-M+1)."""
    df = store.read(group, name)
    if df is None or col not in df.columns:
        return pd.Series(np.nan, index=grid)
    m = df[col].dropna()
    m.index = pd.to_datetime(m.index)
    m = m.resample("ME").last().shift(lag)
    return m.reindex(grid, method="ffill")


def driver_panel(grid: pd.DatetimeIndex | None = None) -> pd.DataFrame:
    """Market-wide, point-in-time monthly driver panel. Sector-specific technicals
    (RS, distance-from-trend, drawdown) are added per sector by callers.

    Columns (all leak-free at the month-end stamp):
      credit_impulse  YoY of trailing-12m TSF sum   (the classic China credit lead)
      tsf_yoy         YoY of monthly TSF total
      m1_yoy, m2_yoy, m1_m2_gap   money aggregates (M1-M2 scissors is an A-share lead)
      pmi_mfg         manufacturing PMI level (50 = neutral)
      cpi_yoy, ppi_yoy
      margin_roc3     3-month % change in financing balance (positioning ramp)
      margin_pct_float  financing as % of float mktcap (crowding level)
      qvix            300ETF implied vol (fear; 50ETF fallback)
      south_net_3m    trailing-3m southbound net (亿) — onshore-via-HK demand
      breadth_pct200  whole-A % above 200-DMA
    """
    if grid is None:
        bench = benchmark_close()
        end = bench.index.max() if bench is not None else pd.Timestamp.today()
        grid = pd.date_range("2008-01-31", end, freq="ME")

    f = pd.DataFrame(index=grid)

    # -- credit / money (monthly, publication-lagged) --------------------------
    tsf = store.read("china_credit", "tsf")
    if tsf is not None and "tsf_total" in tsf.columns:
        t = tsf["tsf_total"].dropna()
        t.index = pd.to_datetime(t.index)
        roll12 = t.rolling(12).sum()
        ci = (roll12 / roll12.shift(12) - 1.0) * 100.0
        f["credit_impulse"] = ci.resample("ME").last().shift(1).reindex(grid, method="ffill")
        ty = (t / t.shift(12) - 1.0) * 100.0
        f["tsf_yoy"] = ty.resample("ME").last().shift(1).reindex(grid, method="ffill")
    f["m1_yoy"] = _monthly_macro("china_macro", "money_supply", "m1_yoy", grid)
    f["m2_yoy"] = _monthly_macro("china_macro", "money_supply", "m2_yoy", grid)
    f["m1_m2_gap"] = f["m1_yoy"] - f["m2_yoy"]
    f["pmi_mfg"] = _monthly_macro("china_macro", "pmi", "pmi_mfg", grid)
    f["cpi_yoy"] = _monthly_macro("china_macro", "cpi", "cpi_yoy", grid)
    f["ppi_yoy"] = _monthly_macro("china_macro", "ppi", "ppi_yoy", grid)

    # -- positioning / flow / vol (daily -> month-end last, same-day known) -----
    mb = store.read("china_margin", "balance")
    if mb is not None:
        if "fin_balance" in mb.columns:
            fb = mb["fin_balance"].dropna()
            f["margin_roc3"] = (fb / fb.shift(63) - 1.0).mul(100.0).reindex(
                fb.index).pipe(lambda x: _monthly_last(x, grid))
        if "fin_pct_float" in mb.columns:
            f["margin_pct_float"] = _monthly_last(mb["fin_pct_float"], grid)
    qv = store.read("china_qvix", "qvix300")
    if qv is None or qv.empty:
        qv = store.read("china_qvix", "qvix50")
    if qv is not None and "close" in qv.columns:
        f["qvix"] = _monthly_last(qv["close"], grid)
    sb = store.read("china_connect", "southbound")
    if sb is not None and "net" in sb.columns:
        n = sb["net"].dropna()
        f["south_net_3m"] = _monthly_last(n.rolling(63).sum(), grid)
    br = store.read("china_breadth", "breadth")
    if br is not None and "pct_above_200" in br.columns:
        f["breadth_pct200"] = _monthly_last(br["pct_above_200"], grid)

    return f


def sector_technicals(close: pd.Series, bench: pd.Series | None,
                      grid: pd.DatetimeIndex) -> pd.DataFrame:
    """Per-sector point-in-time technical drivers on the month-end grid."""
    s = close.dropna()
    out = pd.DataFrame(index=grid)
    ma200 = s.rolling(200).mean()
    out["dist_200d"] = _monthly_last((s / ma200 - 1.0) * 100.0, grid)
    hi252 = s.rolling(252).max()
    out["dd_from_high"] = _monthly_last((s / hi252 - 1.0) * 100.0, grid)
    out["ret_3m"] = _monthly_last(s.pct_change(63) * 100.0, grid)
    out["ret_6m"] = _monthly_last(s.pct_change(126) * 100.0, grid)
    if bench is not None:
        rs = (s / bench.reindex(s.index).ffill()).dropna()
        out["rs_mom_3m"] = _monthly_last(rs.pct_change(63) * 100.0, grid)
        out["rs_mom_6m"] = _monthly_last(rs.pct_change(126) * 100.0, grid)
    return out

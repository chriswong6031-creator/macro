"""Bitcoin Vector input layer: loads stored series, splices price sources, and
computes the derived identities (D41: realized cap = mcap/MVRV, NUPL = 1-1/MVRV,
SSR = mcap/stablecoins). Everything returns daily naive-UTC indexed frames.

Sources of truth (see research/VECTOR_DATA_AUDIT.md for depth):
  price daily  : Yahoo BTC-USD (2014-09->) spliced with Coinbase OHLCV (2015->)
  price hourly : Coinbase (2016->) — intraday/interday vol split
  on-chain     : CoinMetrics (2010->), bgeo (4y window, SOPR spliced 2011->)
  derivatives  : bgeo funding/OI, Deribit DVOL, OKX tail
  flows/sent.  : ETF flows, DefiLlama stablecoins, F&G, dominance
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from lib import store

log = logging.getLogger(__name__)


def _col(group: str, name: str, col: str | None = None) -> pd.Series | None:
    df = store.read(group, name)
    if df is None or df.empty:
        log.warning("btc_inputs: missing %s/%s", group, name)
        return None
    s = df[col] if col else df.iloc[:, 0]
    s.index = pd.to_datetime(s.index)
    return s[~s.index.duplicated(keep="last")].sort_index()


def load_price() -> pd.DataFrame:
    """Daily OHLCV: Coinbase quality where available, Yahoo for the 2014-15 tail."""
    cb = store.read("coinbase", "btc_daily")
    ya = store.read("yahoo", "BTC-USD")
    if cb is None and ya is None:
        raise RuntimeError("no BTC price data stored")
    frames = []
    if ya is not None:
        y = ya.rename(columns=str.lower)
        cols = {c: c for c in ("open", "high", "low", "close", "volume") if c in y.columns}
        if "close" not in cols and "adj close" in y.columns:
            y["close"] = y["adj close"]
        frames.append(y[[c for c in ("open", "high", "low", "close", "volume") if c in y.columns]])
    if cb is not None:
        frames.append(cb[["open", "high", "low", "close", "volume"]])
    px = pd.concat(frames)
    px.index = pd.to_datetime(px.index).normalize()
    px = px[~px.index.duplicated(keep="last")].sort_index()  # coinbase wins overlap
    return px.dropna(subset=["close"])


def load_hourly() -> pd.DataFrame | None:
    return store.read("coinbase", "btc_hourly")


def intraday_vol_daily(hourly: pd.DataFrame | None) -> pd.Series | None:
    """Parkinson estimator per calendar day from hourly bars -> daily series."""
    if hourly is None or hourly.empty:
        return None
    g = hourly.groupby(hourly.index.normalize())
    hi, lo = g["high"].max(), g["low"].min()
    pk = np.sqrt(np.log(hi / lo).pow(2) / (4 * np.log(2)))
    pk.name = "intraday_vol"
    return pk


def load_all() -> dict[str, pd.Series | pd.DataFrame | None]:
    px = load_price()
    hourly = load_hourly()
    mcap = _col("coinmetrics", "mcap_usd")
    mvrv = _col("coinmetrics", "mvrv")
    stables = _col("defillama", "stablecoins")

    d: dict = {
        "price": px,
        "hourly": hourly,
        "intraday_vol": intraday_vol_daily(hourly),
        "mvrv": mvrv,
        "mcap": mcap,
        "active_addresses": _col("coinmetrics", "active_addresses"),
        "hashrate": _col("coinmetrics", "hashrate"),          # hash ribbons (2010->)
        "issuance_usd": _col("coinmetrics", "issuance_usd"),  # Puell multiple (2010->)
        "supply": _col("coinmetrics", "supply"),              # normalize supply_in_profit
        "sopr": _col("bgeo", "sopr"),
        "sth_sopr": _col("bgeo", "sth_sopr"),
        "lth_sopr": _col("bgeo", "lth_sopr"),
        "sth_realized_price": _col("bgeo", "sth_realized_price"),
        "realized_price": _col("bgeo", "realized_price"),
        "supply_in_profit": _col("bgeo", "supply_in_profit"),
        "miner_sell_pressure": _col("bgeo", "miner_sell_pressure"),
        "miner_df": store.read("bgeo", "miner_sell_pressure"),  # outflow/reserve cols for MPI
        "coinbase_premium": _col("bgeo", "coinbase_premium",
                                 "coinbase_premium_coinbasePremiumIndex"),  # US institutional demand
        "funding": _col("bgeo", "funding_rate"),
        "open_interest": _col("bgeo", "open_interest_futures"),
        "open_interest_df": store.read("bgeo", "open_interest_futures"),  # all 15 venue cols
        "etf_flow": _col("bgeo", "etf_flow_btc"),
        "btc_dominance": _col("bgeo", "btc_dominance"),
        "stablecoins": stables,
        "stablecoin_peg": _col("defillama", "stablecoin_peg"),  # peg-deviation veto (D-vec-PEG)
        "fear_greed": _col("sentiment_crypto", "fear_greed"),
        "reserve_risk": _col("checkonchain", "reserve_risk"),  # deep cycle-bottom (2010->)
        "vdd_multiple": _col("checkonchain", "vdd_multiple"),  # spending-behaviour axis (2011->)
        "dvol": _col("deribit", "dvol", "dvol_close"),
        "options_structure": store.read("deribit", "options_structure"),  # forward-accumulating snapshot
        "eth": _col("yahoo", "ETH-USD", None),
        "sol": _col("yahoo", "SOL-USD", None),
        # Tier-3 macro overlay (shared macro parquet store; D10 net-liquidity inputs)
        "walcl": _col("fred", "WALCL"),           # Fed balance sheet ($mn, weekly)
        "rrp": _col("fred", "RRPONTSYD"),         # reverse repo ($bn)
        "tga": _col("treasury", "tga"),           # Treasury general account ($mn)
        "real_yield": _col("fred", "DFII10"),     # 10y real yield (%)
        "hy_oas": _col("fred", "BAMLH0A0HYM2"),   # high-yield credit spread (%)
        "vix": _col("fred", "VIXCLS"),
        "dxy": _col("yahoo", "DX-Y.NYB", "close"),
        # New-factor hunt: positioning + cross-asset (all on disk already)
        "cot_net_pct": _col("cot", "cot_bitcoin", "net_spec_pct_oi"),  # CME net-spec % of OI
        "spx": _col("yahoo", "SPY", "close"),
        "gold": _col("yahoo", "GC_F", "close"),
        "us_m2": _col("fred", "M2SL", "us_m2"),                 # broad money (US, $bn)
        "china_m2_yoy": _col("china_macro", "money_supply", "m2_yoy"),  # PBoC M2 growth %
    }
    # derived identities (D41)
    if mvrv is not None and mcap is not None:
        d["realized_cap"] = (mcap / mvrv).rename("realized_cap")
        d["nupl"] = (1 - 1 / mvrv).rename("nupl")
    if mcap is not None and stables is not None:
        ssr = (mcap / stables.reindex(mcap.index).ffill()).rename("ssr")
        d["ssr"] = ssr
    # supply-in-profit as a FRACTION (bgeo gives it in BTC; CM supply normalizes).
    sip, sup = d.get("supply_in_profit"), d.get("supply")
    if sip is not None and sup is not None:
        frac = (sip / sup.reindex(sip.index).ffill()).clip(0, 1)
        d["supply_in_profit_pct"] = frac.rename("supply_in_profit_pct")
    return d

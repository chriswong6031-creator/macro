"""Commodity Vector input layer.

Loads, for each of the core four (gold/silver/oil/copper), the price series and
COT spec positioning, plus the SHARED macro driver series (real yields, dollar,
breakevens, growth) once. Everything returns daily naive-UTC indexed frames.
Mirrors engine/btc_inputs.py. See research/COMMODITY_DATA_AUDIT.md.

Sources of truth (all already in the store):
  price   : Yahoo front futures GC=F/SI=F/CL=F/HG=F (close+volume, 2000->)
  cot     : CFTC legacy futures-only spec net % of OI (1995->)
  drivers : FRED real yields/breakevens/rates/balance-sheet + Yahoo DXY
"""
from __future__ import annotations

import logging

import pandas as pd

from lib import config, store

log = logging.getLogger(__name__)

# yield-type drivers move in absolute terms (diff); price-type in pct (pct_change).
YIELD_DRIVERS = {"real_yield", "us10y", "us2y", "breakeven10", "breakeven5y5y"}


def _col(group: str, name: str, col: str | None = None) -> pd.Series | None:
    df = store.read(group, name)
    if df is None or df.empty:
        log.warning("commodity_inputs: missing %s/%s", group, name)
        return None
    s = df[col] if (col and col in df.columns) else df.iloc[:, 0]
    s = pd.to_numeric(s, errors="coerce").copy()
    s.index = pd.to_datetime(s.index)
    return s[~s.index.duplicated(keep="last")].sort_index().dropna()


def load_drivers(cfg: dict | None = None) -> dict[str, pd.Series]:
    cfg = cfg or config.load()["commodities"]
    out: dict[str, pd.Series] = {}
    for name, spec in cfg["drivers"].items():
        group, sname = spec[0], spec[1]
        s = _col(group, sname)
        if s is not None:
            out[name] = s.rename(name)
    return out


def load_price(ticker: str) -> pd.DataFrame:
    """Daily price. Yahoo stores close+volume only — synthesize OHLC from close so
    the ported price-structure functions (which key off swing windows of close)
    work unchanged."""
    df = store.read("yahoo", ticker)
    if df is None or df.empty:
        raise RuntimeError(f"no price stored for {ticker}")
    px = df.rename(columns=str.lower).copy()
    px.index = pd.to_datetime(px.index).normalize()
    px = px[~px.index.duplicated(keep="last")].sort_index().dropna(subset=["close"])
    for c in ("open", "high", "low"):
        if c not in px.columns:
            px[c] = px["close"]
    keep = ["open", "high", "low", "close"] + (["volume"] if "volume" in px.columns else [])
    return px[keep]


def load_cot_positioning(cot_name: str) -> pd.Series | None:
    cot = store.read("cot", cot_name)
    if cot is None or cot.empty or "net_spec_pct_oi" not in cot.columns:
        log.warning("commodity_inputs: missing/!net_spec_pct_oi %s", cot_name)
        return None
    s = pd.to_numeric(cot["net_spec_pct_oi"], errors="coerce")
    s.index = pd.to_datetime(s.index)
    return s[~s.index.duplicated(keep="last")].sort_index().dropna().rename("net_spec_pct_oi")


def load_asset(asset: str, drivers: dict | None = None, cfg: dict | None = None) -> dict:
    cfg = cfg or config.load()["commodities"]
    ticker, cot_name, klass = cfg["assets"][asset]
    return {
        "asset": asset,
        "class": klass,
        "ticker": ticker,
        "price": load_price(ticker),
        "cot_net_pct_oi": load_cot_positioning(cot_name),
        "drivers": drivers if drivers is not None else load_drivers(cfg),
    }


def load_all(cfg: dict | None = None) -> dict[str, dict]:
    """Load all four assets, sharing one driver load."""
    cfg = cfg or config.load()["commodities"]
    drivers = load_drivers(cfg)
    out = {a: load_asset(a, drivers, cfg) for a in cfg["assets"]}
    # oil only: Brent front future for the Brent-WTI microstructure signal
    if "oil" in out:
        try:
            out["oil"]["brent"] = load_price("BZ=F")["close"].rename("brent")
        except Exception as e:  # noqa: BLE001 — optional enrichment, degrade gracefully
            log.warning("commodity_inputs: brent unavailable (%s)", e)
    return out

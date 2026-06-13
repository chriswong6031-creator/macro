"""Forex Vector input layer.

Loads, per currency pair, the canonical BASE-vs-USD price (Yahoo spot, inverted
when the symbol quotes USD as base, e.g. USD/JPY -> JPY-vs-USD = 1/price), the
foreign short rate for the carry differential, and COT spec positioning — plus
the SHARED macro driver series (broad dollar + legs, US rates, VIX, OAS, NFCI,
commodity overlays, EM-equity proxy) loaded once. Mirrors engine/commodity_inputs.py.

Sources of truth (all already in the store after scripts.collect):
  price   : Yahoo FX spot EURUSD=X / USDJPY=X / ... (close, 1996/2003->)
  rates   : FRED policy/short rates (DFF + ECBDFR/IR3TIB01* etc.) for carry
  cot     : CFTC legacy futures-only spec net % of OI per currency (1995->)
  drivers : FRED broad-dollar + legs / US curve / VIX / OAS + Yahoo DXY/commods
"""
from __future__ import annotations

import logging

import pandas as pd

from lib import config, store

log = logging.getLogger(__name__)


def _col(group: str, name: str, col: str | None = None) -> pd.Series | None:
    df = store.read(group, name)
    if df is None or df.empty:
        log.warning("forex_inputs: missing %s/%s", group, name)
        return None
    s = df[col] if (col and col in df.columns) else df.iloc[:, 0]
    s = pd.to_numeric(s, errors="coerce").copy()
    s.index = pd.to_datetime(s.index)
    return s[~s.index.duplicated(keep="last")].sort_index().dropna()


def _short_rate_sid_map(cfg_fred: dict | None = None) -> dict[str, str]:
    """col-name -> FRED series_id for fx_rates_short (asset.short_rate names the col)."""
    cfg_fred = cfg_fred or config.load()["fred"]["series"]
    return {colname: sid for sid, colname in cfg_fred.get("fx_rates_short", {}).items()}


def load_drivers(cfg: dict | None = None) -> dict[str, pd.Series]:
    cfg = cfg or config.load()["forex"]
    out: dict[str, pd.Series] = {}
    for name, spec in cfg["drivers"].items():
        s = _col(spec[0], spec[1])
        if s is not None:
            out[name] = s.rename(name)
    return out


def load_price(meta: dict) -> pd.DataFrame:
    """Canonical BASE-vs-USD daily price. Yahoo stores close (+vol); synthesize
    OHLC from close so the ported price-structure functions work unchanged. When
    meta['invert'] (symbol quotes USD as base, USD/xxx), take 1/close so a RISING
    series always = the base currency strengthening vs the dollar (LONG-base up)."""
    ticker = meta["yahoo"]
    df = store.read("yahoo", ticker)
    if df is None or df.empty:
        raise RuntimeError(f"no price stored for {ticker}")
    px = df.rename(columns=str.lower).copy()
    px.index = pd.to_datetime(px.index).normalize()
    px = px[~px.index.duplicated(keep="last")].sort_index().dropna(subset=["close"])
    close = px["close"].astype(float)
    if meta.get("invert"):
        close = (1.0 / close.replace(0, pd.NA)).dropna()
    out = pd.DataFrame({"close": close})
    for c in ("open", "high", "low"):
        out[c] = close
    return out[["open", "high", "low", "close"]]


def load_cot_positioning(cot_name: str | None) -> pd.Series | None:
    if not cot_name:
        return None
    cot = store.read("cot", cot_name)
    if cot is None or cot.empty or "net_spec_pct_oi" not in cot.columns:
        log.warning("forex_inputs: missing/!net_spec_pct_oi %s", cot_name)
        return None
    s = pd.to_numeric(cot["net_spec_pct_oi"], errors="coerce")
    s.index = pd.to_datetime(s.index)
    return s[~s.index.duplicated(keep="last")].sort_index().dropna().rename("net_spec_pct_oi")


def load_short_rate(meta: dict, sid_map: dict[str, str]) -> pd.Series | None:
    """Foreign short/policy rate (%) for the carry differential vs US (DFF).
    Step-function rates -> ffill is economically correct (handled downstream)."""
    if meta.get("carry") == "context" or "short_rate" not in meta:
        return None
    col = meta["short_rate"]
    sid = sid_map.get(col)
    if not sid:
        log.warning("forex_inputs: no FRED series for short_rate col %s", col)
        return None
    return _col("fred", sid, col)


def load_asset(pair: str, drivers: dict | None = None, cfg: dict | None = None,
               sid_map: dict[str, str] | None = None) -> dict:
    cfg = cfg or config.load()["forex"]
    meta = cfg["assets"][pair]
    sid_map = sid_map if sid_map is not None else _short_rate_sid_map()
    ai = {
        "pair": pair,
        "meta": meta,
        "archetype": meta.get("archetype", "major"),
        "base": meta.get("base", pair),
        "price": load_price(meta),
        "short_rate": load_short_rate(meta, sid_map),
        "cot_net_pct_oi": load_cot_positioning(meta.get("cot")),
        "drivers": drivers if drivers is not None else load_drivers(cfg),
    }
    # commodity-dollar overlay (AUD<-copper/gold, CAD<-oil) for the terms-of-trade leg
    overlay = meta.get("commodity") or []
    if overlay:
        cols = {}
        for tkr in overlay:
            s = _col("yahoo", tkr, "close")
            if s is not None:
                cols[tkr] = s
        if cols:
            ai["commodity"] = cols
    return ai


def load_all(cfg: dict | None = None, active_only: bool = True) -> dict[str, dict]:
    """Load pairs (active board by default), sharing one driver load."""
    cfg = cfg or config.load()["forex"]
    drivers = load_drivers(cfg)
    sid_map = _short_rate_sid_map()
    pairs = cfg["active"] if active_only else list(cfg["assets"].keys())
    out: dict[str, dict] = {}
    for p in pairs:
        try:
            out[p] = load_asset(p, drivers, cfg, sid_map)
        except Exception as e:  # noqa: BLE001 — one bad pair must not kill the board
            log.warning("forex_inputs: skipping %s (%s)", p, e)
    return out

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


def _col_sid(group: str, cfg_fred: dict | None = None) -> dict[str, str]:
    """col-name -> FRED series_id for a fred.series group (assets name the col)."""
    cfg_fred = cfg_fred or config.load()["fred"]["series"]
    return {colname: sid for sid, colname in cfg_fred.get(group, {}).items()}


def _sid_maps() -> dict[str, dict[str, str]]:
    fred = config.load()["fred"]["series"]
    return {grp: _col_sid(grp, fred) for grp in ("fx_rates_short", "fx_rates_long", "fx_reer")}


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
    series always = the base currency strengthening vs the dollar (LONG-base up).

    fred_fallback: when the Yahoo series has < 300 rows (e.g. USD/CNH has only a
    current print), fall back to the FRED reference rate (meta['fred']) for history."""
    ticker = meta["yahoo"]
    df = store.read("yahoo", ticker)
    if (df is None or len(df) < 300) and meta.get("fred_fallback") and meta.get("fred"):
        fr = store.read("fred", meta["fred"])
        if fr is not None and not fr.empty:
            df = fr.iloc[:, [0]].rename(columns={fr.columns[0]: "close"})
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


def load_rate(meta: dict, meta_key: str, group: str, sid_maps: dict) -> pd.Series | None:
    """Foreign rate / REER series named by a column in meta -> its FRED parquet.
    Short/policy rates are step functions (ffill correct); REER/10y are monthly +
    lagged (the signal engine shifts them by the configured pub_lag before use).

    Discontinued-series splice: when meta carries ``<meta_key>_hist`` +
    ``<meta_key>_splice`` (e.g. GBP short_rate: gb_sonia live, gb_short = the
    upstream-frozen OECD 3m interbank for history), the hist series is used up to
    and including the splice date and the live series strictly after. This is a
    LEVEL splice — carry consumes the level, so no seam return exists here; any
    consumer differencing across the seam must mask the straddling window
    (flow_regime.py DXY/DTWEXBGS splice-masking)."""
    col = meta.get(meta_key)
    if not col:
        return None
    sid = sid_maps.get(group, {}).get(col)
    if not sid:
        log.warning("forex_inputs: no FRED series for %s col %s", meta_key, col)
        return None
    live = _col("fred", sid, col)
    hist_col = meta.get(f"{meta_key}_hist")
    if not hist_col:
        return live
    hist_sid = sid_maps.get(group, {}).get(hist_col)
    hist = _col("fred", hist_sid, hist_col) if hist_sid else None
    if hist is None:
        return live
    if live is None:  # live leg not landed yet (pre-first-collection) — stale hist beats nothing
        log.warning("forex_inputs: %s live leg %s absent — using %s history alone",
                    meta_key, col, hist_col)
        return hist
    splice = pd.Timestamp(meta.get(f"{meta_key}_splice") or hist.index.max())
    out = pd.concat([hist[hist.index <= splice], live[live.index > splice]])
    return out.rename(col).sort_index()


def load_asset(pair: str, drivers: dict | None = None, cfg: dict | None = None,
               sid_maps: dict | None = None) -> dict:
    cfg = cfg or config.load()["forex"]
    meta = cfg["assets"][pair]
    sid_maps = sid_maps if sid_maps is not None else _sid_maps()
    short = None if meta.get("carry") == "context" else load_rate(meta, "short_rate", "fx_rates_short", sid_maps)
    ai = {
        "pair": pair,
        "meta": meta,
        "archetype": meta.get("archetype", "major"),
        "base": meta.get("base", pair),
        "price": load_price(meta),
        "short_rate": short,
        "long_rate": load_rate(meta, "long_rate", "fx_rates_long", sid_maps),
        "reer": load_rate(meta, "reer", "fx_reer", sid_maps),
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
    sid_maps = _sid_maps()
    pairs = cfg["active"] if active_only else list(cfg["assets"].keys())
    out: dict[str, dict] = {}
    for p in pairs:
        try:
            out[p] = load_asset(p, drivers, cfg, sid_maps)
        except Exception as e:  # noqa: BLE001 — one bad pair must not kill the board
            log.warning("forex_inputs: skipping %s (%s)", p, e)
    return out

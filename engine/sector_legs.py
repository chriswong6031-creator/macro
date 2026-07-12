"""engine/sector_legs.py — the sector LEG registry + leg composite closes (Rotation Command W1).

config/sector_legs.json declares, per US sector, the LEGS whose disagreement makes the
cap-weighted sector aggregate unrepresentative (the 2026-06-25 lesson: XLK read Topping/SELL
for eleven sessions while its mega-cap leg ran +11% and its memory leg crashed −20%). Legs
resolve to daily close series three ways:

  • basket legs  — members from data/baskets/ohlcv membership (data/baskets/membership.json),
                   composited by engine.basket_index.consolidated_candle (equal-weight,
                   CURRENT membership over full history, pit=False — the same "technical read
                   of the basket as constituted today" the subsector-confluence desk uses);
  • ticker legs  — small cohorts (META+GOOGL, AMZN+TSLA) fall below consolidated_candle's
                   3-member floor, so they get a plain equal-weight daily-rebalanced return
                   composite here (identical construction, no candle/volume);
  • the sector ETF — straight from the yahoo store, the aggregate the legs are compared to.

Consumed by engine.rotation_events (RC-R1) and engine.sector_fragmentation (RC-R6).
DISPLAY/CONTEXT TIER inputs only — nothing here ranks, gates, or sizes.
"""
from __future__ import annotations

import json
import logging

import pandas as pd

from engine import basket_index
from lib import config

log = logging.getLogger(__name__)

REGISTRY_PATH = "config/sector_legs.json"
MIN_TICKER_MEMBERS = 2      # a ticker leg needs at least this many members with data
MIN_BARS = 300              # a leg/ETF series shorter than this is unusable for the z-machinery


def load_registry() -> dict:
    """The frozen leg registry. Raises if missing/unparseable — the callers' brun wrapper
    treats that as a failed (non-fatal) step rather than silently building an empty desk."""
    return json.loads((config.ROOT / REGISTRY_PATH).read_text())


def load_membership() -> dict:
    """data/baskets/membership.json → {basket_key: {members: [...]}} (tolerates the
    {"baskets": {...}} wrapper)."""
    mp = config.data_dir() / "baskets" / "membership.json"
    mem = json.loads(mp.read_text())
    return mem.get("baskets") or mem


def _ew_close(tickers: list[str]) -> tuple[pd.Series | None, dict]:
    """Equal-weight daily-rebalanced close LEVEL (from 1.0) for a small ticker cohort.
    Mirrors consolidated_candle's return-space construction: each member contributes its
    daily close return while live (from its own first traded bar); the mean return
    compounds into the level. None if fewer than MIN_TICKER_MEMBERS members resolve."""
    cols = {}
    for t in tickers:
        df = basket_index._load_member_ohlcv(t)
        if df is not None and "close" in df and not df["close"].dropna().empty:
            cols[t] = df["close"]
    if len(cols) < MIN_TICKER_MEMBERS:
        return None, {"n_members": len(cols), "n_declared": len(tickers)}
    px = pd.DataFrame(cols).sort_index()
    filled = px.ffill()
    live = filled.notna()
    r = filled.pct_change().where(live)
    n_live = live.sum(axis=1)
    R = r.mean(axis=1).where(n_live >= MIN_TICKER_MEMBERS)
    first = R.first_valid_index()
    if first is None:
        return None, {"n_members": len(cols), "n_declared": len(tickers)}
    lvl = (1.0 + R.loc[first:].fillna(0.0)).cumprod()
    return lvl, {"n_members": len(cols), "n_declared": len(tickers)}


def _basket_close(basket_key: str, membership: dict) -> tuple[pd.Series | None, dict]:
    """Equal-weight composite close for a curated basket (deep calendar, pit=False)."""
    entry = membership.get(basket_key) or {}
    members = entry.get("members") or []
    if not members:
        return None, {"n_members": 0, "n_declared": 0, "missing_basket": basket_key}
    idx = basket_index.deep_calendar(members)
    if idx.empty:
        return None, {"n_members": 0, "n_declared": len(members)}
    cand, meta = basket_index.consolidated_candle(members, idx, mode="equal", pit=False)
    if cand is None or cand["close"].dropna().empty:
        return None, {"n_members": meta.get("n_with_ohlcv", 0), "n_declared": len(members)}
    return cand["close"].dropna(), {"n_members": meta.get("n_with_ohlcv"),
                                    "n_declared": len(members)}


def leg_close(leg: dict, membership: dict) -> tuple[pd.Series | None, dict]:
    """Resolve one registry leg to a daily close series (+ coverage meta)."""
    if leg.get("basket"):
        s, meta = _basket_close(leg["basket"], membership)
    elif leg.get("tickers"):
        s, meta = _ew_close(leg["tickers"])
    elif leg.get("etf"):
        df = basket_index._load_member_ohlcv(leg["etf"])
        s = df["close"].dropna() if df is not None and "close" in df else None
        meta = {"n_members": 1, "n_declared": 1}
    else:
        return None, {"error": "leg has no basket/tickers/etf"}
    if s is not None and len(s) < MIN_BARS:
        meta["thin_history"] = len(s)
        log.warning("sector_legs: leg %s has only %d bars (<%d) — dropped",
                    leg.get("key"), len(s), MIN_BARS)
        return None, meta
    return s, meta


def sector_closes(registry: dict | None = None) -> dict:
    """Resolve the whole registry → {sector_key: {"cfg", "etf_close", "legs": {leg_key: close},
    "leg_meta": {leg_key: meta}}}. Legs that fail to resolve are dropped with a warning —
    a thin pull degrades visibly (coverage in the payload), never silently."""
    registry = registry or load_registry()
    membership = load_membership()
    out: dict = {}
    for sec in registry.get("sectors", []):
        etf_df = basket_index._load_member_ohlcv(sec["etf"])
        etf_close = etf_df["close"].dropna() if etf_df is not None and "close" in etf_df else None
        if etf_close is None or len(etf_close) < MIN_BARS:
            log.warning("sector_legs: sector %s ETF %s unavailable — sector skipped",
                        sec["key"], sec["etf"])
            continue
        legs: dict = {}
        leg_meta: dict = {}
        for leg in sec.get("legs", []):
            s, meta = leg_close(leg, membership)
            leg_meta[leg["key"]] = meta
            if s is not None:
                legs[leg["key"]] = s
        out[sec["key"]] = {"cfg": sec, "etf_close": etf_close,
                           "legs": legs, "leg_meta": leg_meta}
    return out

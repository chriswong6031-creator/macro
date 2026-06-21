"""China namespace spine — the join key the three surfaces lack.

LEAF · PURE · KEYLESS · context-only join (no scored output, never imported by any
scoring/regime/allocation path). News tags cn_* baskets, the radar fires on sector ETFs,
and alt-data ranks individual tickers — three disjoint identifier namespaces. This module
loads `data/baskets_china/membership.json` ONCE and exposes the bridges between them so the
central-intelligence engine can fuse surfaces:

  etf_to_basket()   513.SS -> ["cn_metals","cn_rare_earth"]   (LIST — some ETFs map to 2 baskets)
  ticker_to_basket() member.ticker -> basket_id               (active members only)
  basket_members(b) -> [tickers]                              (active)
  basket_label(b)   -> (en, zh)
  ticker_name(t)    -> 中文 name | None

Every accessor degrades to empty/None and never raises. See research/CHINA_INTEL_POWERHOUSE.md §5.
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache

from lib import config

log = logging.getLogger(__name__)

SCHEMA = "china_basket_spine.v1"


@lru_cache(maxsize=1)
def _baskets() -> dict:
    """The {basket_id: basket} dict from membership.json, or {} on any failure."""
    try:
        p = config.data_dir() / "baskets_china" / "membership.json"
        if not p.exists():
            return {}
        return json.loads(p.read_text()).get("baskets", {}) or {}
    except Exception as e:  # noqa: BLE001 — degrade, never raise
        log.warning("china_basket_spine: membership unreadable (%s)", e)
        return {}


@lru_cache(maxsize=1)
def etf_to_basket() -> dict[str, list[str]]:
    """ETF proxy ticker -> list of basket ids it represents (some ETFs back 2 baskets)."""
    out: dict[str, list[str]] = {}
    for bid, b in _baskets().items():
        etf = b.get("etf_proxy")
        if etf:
            out.setdefault(etf, []).append(bid)
    return out


@lru_cache(maxsize=1)
def ticker_to_basket() -> dict[str, str]:
    """Active member ticker -> basket id (first basket wins on the rare cross-listing)."""
    out: dict[str, str] = {}
    for bid, b in _baskets().items():
        for m in b.get("members", []):
            if m.get("removed"):
                continue
            t = m.get("ticker")
            if t:
                out.setdefault(str(t), bid)
    return out


@lru_cache(maxsize=1)
def _ticker_names() -> dict[str, str]:
    out: dict[str, str] = {}
    for b in _baskets().values():
        for m in b.get("members", []):
            t, nm = m.get("ticker"), m.get("name_zh")
            if t and nm:
                out.setdefault(str(t), str(nm))
    return out


def basket_members(bid: str) -> list[str]:
    """Active member tickers of a basket (empty if unknown)."""
    b = _baskets().get(bid) or {}
    return [str(m["ticker"]) for m in b.get("members", [])
            if m.get("ticker") and not m.get("removed")]


def basket_label(bid: str) -> tuple[str, str]:
    """(en, zh) display label for a basket id; falls back to the id itself."""
    b = _baskets().get(bid) or {}
    return (b.get("name", bid), b.get("name_zh", bid))


def basket_ids() -> list[str]:
    return list(_baskets().keys())


def ticker_name(t: str) -> str | None:
    return _ticker_names().get(str(t))

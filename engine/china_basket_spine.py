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
  ticker_name(t)    -> 中文 name | None                        (curated first, THS fallback)

v2 adds a parallel THS layer over `data/baskets_china_ths/membership.json` (237 同花顺
concept boards; ~3x the ticker coverage of the curated set — the "603129-hole": names that
live ONLY in THS boards were invisible to every spine join). THS boards have NO etf_proxy,
so the ETF bridge stays curated-only; membership there is many-to-many:

  ths_ticker_to_baskets() member.ticker -> [ths basket ids]   (active; a name sits in several boards)
  ths_basket_members(b)   -> [tickers]                        (active)
  ths_basket_label(b)     -> (en, zh)
  ths_basket_ids()        -> [ids]
  member_tickers_all()    -> frozenset(curated ∪ THS active members)

Every accessor degrades to empty/None and never raises. See research/CHINA_INTEL_POWERHOUSE.md §5.
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache

from lib import config

log = logging.getLogger(__name__)

SCHEMA = "china_basket_spine.v2"


def _load_membership(subdir: str) -> dict:
    """The {basket_id: basket} dict from data/<subdir>/membership.json, or {} on any failure."""
    try:
        p = config.data_dir() / subdir / "membership.json"
        if not p.exists():
            return {}
        return json.loads(p.read_text()).get("baskets", {}) or {}
    except Exception as e:  # noqa: BLE001 — degrade, never raise
        log.warning("china_basket_spine: %s membership unreadable (%s)", subdir, e)
        return {}


@lru_cache(maxsize=1)
def _baskets() -> dict:
    return _load_membership("baskets_china")


@lru_cache(maxsize=1)
def _ths_baskets() -> dict:
    return _load_membership("baskets_china_ths")


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


@lru_cache(maxsize=1)
def _ths_ticker_names() -> dict[str, str]:
    out: dict[str, str] = {}
    for b in _ths_baskets().values():
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
    """中文 name for a member ticker — curated membership first, THS fallback."""
    return _ticker_names().get(str(t)) or _ths_ticker_names().get(str(t))


# --------------------------------------------------------------------------- #
# THS concept-board layer (same contract; many-to-many membership, no ETF proxies)
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=1)
def ths_ticker_to_baskets() -> dict[str, list[str]]:
    """Active member ticker -> LIST of THS basket ids (concept boards overlap heavily —
    collapsing to one id would silently drop most of the join, so this stays a list)."""
    out: dict[str, list[str]] = {}
    for bid, b in _ths_baskets().items():
        for m in b.get("members", []):
            if m.get("removed"):
                continue
            t = m.get("ticker")
            if t:
                out.setdefault(str(t), []).append(bid)
    return out


def ths_basket_members(bid: str) -> list[str]:
    """Active member tickers of a THS basket (empty if unknown)."""
    b = _ths_baskets().get(bid) or {}
    return [str(m["ticker"]) for m in b.get("members", [])
            if m.get("ticker") and not m.get("removed")]


def ths_basket_label(bid: str) -> tuple[str, str]:
    """(en, zh) display label for a THS basket id; falls back to the id itself."""
    b = _ths_baskets().get(bid) or {}
    return (b.get("name", bid), b.get("name_zh", bid))


def ths_basket_ids() -> list[str]:
    return list(_ths_baskets().keys())


@lru_cache(maxsize=1)
def member_tickers_all() -> frozenset:
    """Every active member ticker across curated ∪ THS baskets — the full set of names
    that live on SOME basket surface (the honest on-desk universe for discovery tagging)."""
    return frozenset(ticker_to_basket()) | frozenset(ths_ticker_to_baskets())

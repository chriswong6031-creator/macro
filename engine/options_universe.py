"""engine/options_universe.py — the underlyings we snapshot option chains / flow for.

ONE place that resolves the effective options universe so the per-strike GEX accrual
(scripts/build_polygon_gex) and the measured-flow desk (scripts/build_options_flow) read
the SAME set. The universe is the config anchors (the index ETFs + mega-caps that always
have to be there) optionally UNIONED with every active single name in the baskets we trade
(data/baskets/membership.json) — so the per-name flow / positioning / GEX reads extend to
the whole optionable set, not just 10 names.

This is pure additional massive.com REST calls on the existing entitlement (no new cost),
but the daily raw-chain parquet (committed by build_polygon_gex) grows ~linearly with the
universe, so the count is bounded by a config cap (`max_underlyings`). Anchors keep their
priority slots within the cap. Everything degrades gracefully: a missing membership file or
a non-optionable ticker just drops out (the snapshot skips an empty chain).
"""
from __future__ import annotations

import json
import logging

from lib import config

log = logging.getLogger(__name__)

# anchors that must always be in the universe even if config omits them (the index-ETF
# gamma backbone + the most-traded single names) — the historical DEFAULT list.
DEFAULT_ANCHORS = ["SPY", "QQQ", "IWM", "DIA", "NVDA", "AAPL", "TSLA", "AMD", "META", "MSFT"]


def baskets_universe() -> list[str]:
    """Active single-name tickers across every thematic basket (data/baskets/membership.json).
    'Active' = not removed (removed is None). Deduped, ordered. [] if the file is absent."""
    try:
        p = config.data_dir() / "baskets" / "membership.json"
        if not p.exists():
            return []
        doc = json.loads(p.read_text())
    except Exception as e:  # noqa: BLE001 — a missing/broken file must never break the build
        log.warning("options_universe: membership read failed (%s)", e)
        return []
    baskets = doc.get("baskets") or {}
    items = baskets.values() if isinstance(baskets, dict) else baskets
    seen: dict[str, None] = {}
    for b in items:
        for m in ((b.get("members") if isinstance(b, dict) else None) or []):
            if isinstance(m, dict):
                if m.get("removed"):           # dropped from the basket -> don't accrue it
                    continue
                t = m.get("ticker")
            else:
                t = m
            if t and isinstance(t, str):
                seen.setdefault(t.upper(), None)
    return list(seen)


def gex_symbols(cfg: dict | None = None) -> list[str]:
    """The effective options universe = config anchors (`polygon.gex.symbols`, or the
    DEFAULT_ANCHORS) optionally unioned with the baskets universe (`include_baskets`), deduped
    with anchors first, capped at `max_underlyings`. Anchors are never dropped by the cap (they
    take the first slots). Pure function of config + the membership file."""
    if cfg is None:
        cfg = (config.load().get("polygon", {}) or {}).get("gex", {}) or {}
    anchors = list(cfg.get("symbols") or DEFAULT_ANCHORS)
    out: list[str] = []
    seen: set[str] = set()
    for t in anchors:                          # anchors first — they keep their slots under the cap
        u = str(t).upper()
        if u not in seen:
            seen.add(u); out.append(u)
    n_anchors = len(out)
    if cfg.get("include_baskets", False):
        for t in baskets_universe():
            if t not in seen:
                seen.add(t); out.append(t)
    cap = int(cfg.get("max_underlyings", 400) or 400)
    capped = out[:max(cap, n_anchors)]         # never let the cap drop an anchor
    if len(out) > len(capped):
        log.info("options_universe: %d underlyings capped to %d (max_underlyings=%d)",
                 len(out), len(capped), cap)
    return capped

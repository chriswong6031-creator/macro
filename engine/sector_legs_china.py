"""engine/sector_legs_china.py — China sector-leg registry loader (RC-R14).

Reads ``config/sector_legs_china.json`` and constructs close series from the
normalized level chart data already embedded in ``site/chinabasketdata/baskets.json``
(the same series that subsector_rotation_china.py reads for RRG — so no new data
dependency).  Returns a ``sectors`` dict in the SAME shape that ``engine.rotation_events.run_nightly``
expects, with one structural difference: China sectors have no ETF (the config
``etf: null``), so we synthesise a pseudo-etf_close as the equal-weight mean of
the sector's legs — only used for ``coldstart_replay``'s calendar union, not
rendered or displayed.

Region coupling is strictly in this file and ``config/sector_legs_china.json``.
``engine.rotation_events`` is region-agnostic — all three detector functions
(blowoff_crash / turn_up / pair_confirm / evaluate_pair) operate on pd.Series
and carry no hard-coded US paths.

DISPLAY/CONTEXT TIER only — no rank, gate, size, or stance changes anywhere.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from lib import config

log = logging.getLogger(__name__)

REGISTRY_PATH = "config/sector_legs_china.json"
MIN_BARS = 200  # shorter than the US 300 — CN basket history starts 2021-06


def load_registry() -> dict:
    """Raise if missing/unparseable (callers treat as non-fatal step failure)."""
    return json.loads((config.ROOT / REGISTRY_PATH).read_text())


def _load_basket_series(baskets_json_path: Path) -> tuple[list[str], dict[str, list]]:
    """Return (dates, {basket_id: [float|None, ...]}) from site/chinabasketdata/baskets.json."""
    raw = json.loads(baskets_json_path.read_text())
    chart = raw.get("chart") or {}
    dates: list[str] = chart.get("dates") or []
    baskets: dict[str, list] = chart.get("baskets") or {}
    return dates, baskets


def _series_from_levels(dates: list[str], values: list) -> pd.Series | None:
    """Convert a normalized level series (list of float|None, aligned to dates)
    to a DatetimeIndex pd.Series, stripping leading NaNs and entries without
    a valid date."""
    if not dates or not values or len(dates) != len(values):
        return None
    idx = pd.to_datetime(dates)
    s = pd.Series(values, index=idx, dtype=float).dropna()
    if len(s) < MIN_BARS:
        return None
    return s


def sector_closes(site_dir: Path | None = None,
                  registry: dict | None = None) -> dict:
    """Resolve the China legs registry → the same ``{sector_key: {...}}`` shape
    that ``engine.rotation_events.run_nightly`` consumes.

    ``site_dir`` defaults to ``config.ROOT / config.load()["storage"]["site_dir"]``.
    The only external dependency is ``site_dir / "chinabasketdata" / "baskets.json"``
    — present in every runner checkout because it is git-tracked.
    """
    if site_dir is None:
        site_dir = config.ROOT / config.load()["storage"]["site_dir"]
    registry = registry or load_registry()

    baskets_path = site_dir / "chinabasketdata" / "baskets.json"
    if not baskets_path.exists():
        log.warning("sector_legs_china: baskets.json missing at %s — returning empty", baskets_path)
        return {}

    dates, basket_chart = _load_basket_series(baskets_path)
    log.info("sector_legs_china: loaded %d dates, %d basket series from baskets.json",
             len(dates), len(basket_chart))

    out: dict = {}
    for sec in registry.get("sectors", []):
        skey = sec["key"]
        legs: dict = {}
        leg_meta: dict = {}
        for leg in sec.get("legs", []):
            basket_id = leg.get("basket_cn") or leg.get("key")
            raw_vals = basket_chart.get(basket_id)
            if raw_vals is None:
                log.warning("sector_legs_china: basket_id %r not found in chart — leg %s skipped",
                            basket_id, leg["key"])
                leg_meta[leg["key"]] = {"error": f"basket_id {basket_id!r} absent from baskets.json chart"}
                continue
            s = _series_from_levels(dates, raw_vals)
            if s is None:
                log.warning("sector_legs_china: leg %s has too few bars (<%d) — dropped",
                            leg["key"], MIN_BARS)
                leg_meta[leg["key"]] = {"thin_history": True, "n": len([v for v in raw_vals if v is not None])}
                continue
            legs[leg["key"]] = s
            leg_meta[leg["key"]] = {"n_bars": len(s), "basket_id": basket_id}

        if len(legs) < 2:
            log.warning("sector_legs_china: sector %s has fewer than 2 legs — skipped", skey)
            continue

        # Synthesise a pseudo-ETF close as equal-weight mean of legs (calendar anchor only).
        # This is never rendered or used as a price signal — it satisfies coldstart_replay's
        # need for an etf_close series to build the calendar union.
        aligned = pd.DataFrame({k: s for k, s in legs.items()}).sort_index().ffill()
        etf_close = aligned.mean(axis=1).dropna()
        # Mirror the 'cfg' shape that step_pairs / severity / _copy expect
        cfg = {
            "key": skey,
            "etf": None,
            "name_en": sec["name_en"],
            "name_zh": sec["name_zh"],
            "legs": sec["legs"],
        }
        out[skey] = {"cfg": cfg, "etf_close": etf_close,
                     "legs": legs, "leg_meta": leg_meta}
        log.debug("sector_legs_china: sector %s — %d legs resolved", skey, len(legs))

    log.info("sector_legs_china: %d sectors, %d total legs resolved",
             len(out), sum(len(s["legs"]) for s in out.values()))
    return out

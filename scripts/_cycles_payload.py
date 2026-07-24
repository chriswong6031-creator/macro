"""Split a cycle-map data payload into a light core + a heavy series chunk.

The cycle pages (sector_cycles / country_cycles / sector_cycles_china +
their two _central hubs) ship one multi-MB ``window.SECTOR_CYCLES`` blob whose
default first paint (sectors family, oscillator mode) needs only ~15% of it.
``split_cycles_payload`` peels the heavy per-entity arrays into a second file that
the page hydrates AFTER first paint (see templates/sector_cycles.js _scheduleSeries):

  * ``price``   — stripped from EVERY entity (only the sparklines / price-mode chart
                  need it, and the default view is oscillator mode);
  * ``osc`` + ``turns`` — stripped from NON-``sectors`` families (baskets / nasdaq /
                  russell / country baskets); the ``sectors`` family keeps both so the
                  default sectors-osc paint and the sector mini-cyc board work with core
                  alone;
  * ``fx`` + ``usd_record`` — stripped from the ``sectors`` family when present (the
                  country page's 24 markets carry a ~1.2MB currency card consumed only by
                  the focus panel).

The split is LOSSLESS per entity id: ``core`` + ``series`` recombine to the input
(``Object.assign(core_entity, series[id])`` on the client). The input dict is NEVER
mutated — the full model is still written to the features json unchanged.

``FAMILY_KEYS`` names the entity lists to process; only those present are touched.
Entities are keyed by their ``id`` field; an entity missing an ``id`` is left whole in
core and contributes nothing to series (it can still render from core).
"""
from __future__ import annotations

import copy
from typing import Any, Dict, Tuple

# entity lists this splitter knows how to peel; only those present in `data` are touched
FAMILY_KEYS = ("sectors", "baskets", "nasdaq", "russell")

# heavy arrays pulled into the series chunk, by family class
_HEAVY_ALL = ("price",)                              # every family
_HEAVY_NON_SECTORS = ("osc", "turns")                # baskets / nasdaq / russell
_HEAVY_SECTORS = ("fx", "usd_record")                # only the sectors family (country FX card)


def _heavy_keys_for(family: str) -> tuple[str, ...]:
    """Which entity keys move to the series chunk for `family`."""
    if family == "sectors":
        return _HEAVY_ALL + _HEAVY_SECTORS
    return _HEAVY_ALL + _HEAVY_NON_SECTORS


def split_cycles_payload(data: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Split `data` into ``(core, series)`` without mutating `data`.

    ``core`` is a deep copy of `data` with the heavy per-entity arrays removed;
    ``series`` maps each entity id -> the removed arrays (only the keys actually
    present on that entity). ``series`` is keyed globally across families (ids are
    unique across the one shared chart space), matching the client's ``byId`` map.
    """
    core = copy.deepcopy(data)
    series: Dict[str, Any] = {}

    for family in FAMILY_KEYS:
        entities = core.get(family)
        if not isinstance(entities, list):
            continue
        heavy = _heavy_keys_for(family)
        for ent in entities:
            if not isinstance(ent, dict):
                continue
            eid = ent.get("id")
            if eid is None:
                continue                      # no id -> can't rehydrate; leave whole in core
            moved: Dict[str, Any] = {}
            for k in heavy:
                if k in ent:
                    moved[k] = ent.pop(k)
            if moved:
                series[eid] = moved
    return core, series
